#!/usr/bin/env python3
"""Local TTS service for Mia — Gepard (Slovenian) with CPU/RAM fallback.

Why a service: Gepard is a 555 M autoregressive model plus a NeMo codec. Loading
it per sentence (tts.provider: command) costs seconds; loading it once and
answering HTTP costs milliseconds. Mia's server talks to it via
`tts.provider: http`.

    # recommended
    scripts/gepard_tts.py --serve --port 8770 --device auto --min-free-vram-gb 3
    # one-shot (debugging; tts.provider: command)
    echo "Dober dan." | scripts/gepard_tts.py --stdio --engine gepard

Engine:
  gepard   texdata/Gepard-Slovenian-TTS + NVIDIA NanoCodec (needs the extras below)
  piper    local Piper voice — fallback and smoke tests, ~5x realtime on CPU
  tone     deterministic test tone, no models (used by the integration tests)

Install the Gepard extras (heavy, ~3 GB):
    pip install accelerate
    pip install "nemo_toolkit[tts]"
    pip install git+https://github.com/nineninesix-ai/gepard-inference

Device policy (--device auto): use CUDA only when torch sees a GPU **and** at
least --min-free-vram-gb is free right now; otherwise run on CPU (system RAM).
That is what keeps Mia working when the GPU is already full of the LLM: with
Qwen3-30B-A3B at Q4 (~18.6 GB) there is room for TTS; at Q6/8K context there
may not be, and the service quietly falls back instead of OOM-ing the LLM.
"""

import argparse
import io
import json
import os
import re
import sys
import threading
import time
import wave
from dataclasses import dataclass

import numpy as np

MODEL = os.environ.get("GEPARD_MODEL", "texdata/Gepard-Slovenian-TTS")
CODEC = os.environ.get("GEPARD_CODEC", "nvidia/nemo-nano-codec-22khz-1.89kbps-21.5fps")
LANG_PREFIX = os.environ.get("GEPARD_LANG_PREFIX", "sl: ")
MAX_CHARS = int(os.environ.get("GEPARD_MAX_CHARS", "400"))


def clean_text(text: str, max_chars: int = MAX_CHARS) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"[*_#`>]+", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_chars:
        cut = text[:max_chars]
        text = cut[: cut.rfind(" ")] if " " in cut else cut
    return text


# --------------------------------------------------------------------- device

def gpu_free_gb() -> float | None:
    """Free VRAM right now, or None when no usable CUDA device is visible."""
    try:
        import torch  # noqa: PLC0415 - optional dependency
    except Exception:
        return None
    try:
        if not torch.cuda.is_available():
            return None
        free, _total = torch.cuda.mem_get_info()
        return round(free / 1024**3, 2)
    except Exception:
        return None


def pick_device(policy: str, min_free_gb: float) -> tuple[str, str]:
    """Return (device, human-readable reason)."""
    policy = (policy or "auto").lower()
    free = gpu_free_gb()
    gpu_present = free is not None
    if policy == "cpu":
        return "cpu", "forced by --device cpu"
    if policy == "cuda":
        if not gpu_present:
            return "cpu", "cuda requested but no CUDA device visible -> RAM fallback"
        return "cuda", f"forced by --device cuda (free VRAM {free} GB)"
    if not gpu_present:
        return "cpu", "no CUDA device visible -> RAM fallback"
    if free is not None and free < min_free_gb:
        return "cpu", f"only {free} GB VRAM free (< {min_free_gb} GB) -> RAM fallback"
    return "cuda", f"{free} GB VRAM free (>= {min_free_gb} GB)"


# --------------------------------------------------------------------- engines

@dataclass
class SynthResult:
    pcm: np.ndarray            # int16 mono
    sample_rate: int
    seconds: float = 0.0
    engine: str = ""
    device: str = ""
    reason: str = ""
    load_seconds: float = 0.0
    synth_seconds: float = 0.0


class Engine:
    name = "base"
    device = "cpu"
    reason = ""

    def synth(self, text: str) -> SynthResult:  # pragma: no cover - interface
        raise NotImplementedError

    def describe(self) -> dict:
        return {"engine": self.name, "device": self.device, "reason": self.reason}


class ToneEngine(Engine):
    """No-model engine: fixed-frequency tone with a syllable-like envelope."""

    name = "tone"

    def __init__(self, device: str = "cpu", reason: str = ""):
        self.device, self.reason = device, reason

    def synth(self, text: str) -> SynthResult:
        rate = 22050
        words = max(1, len(text.split()))
        seconds = min(2.0, 0.18 * words)
        t0 = time.perf_counter()
        n = int(rate * seconds)
        t = np.arange(n) / rate
        env = (0.5 + 0.5 * np.sign(np.sin(2 * np.pi * 3.2 * t))) * 0.25
        sig = (np.sin(2 * np.pi * 220 * t) * env * 32767 * 0.6).astype(np.int16)
        return SynthResult(sig, rate, seconds, self.name, self.device, self.reason,
                           synth_seconds=time.perf_counter() - t0)


class PiperEngine(Engine):
    """Piper via its CLI — the fallback voice, and what the tests use."""

    name = "piper"

    def __init__(self, model: str, binary: str = "piper", device: str = "cpu", reason: str = ""):
        self.model, self.binary = model, binary
        self.device, self.reason = device, reason
        if not os.path.exists(model):
            raise SystemExit(f"piper voice not found: {model} (scripts/get-voice.sh sl)")

    def _rate(self) -> int:
        try:
            with open(self.model + ".json", encoding="utf-8") as f:
                return int(json.load(f)["audio"]["sample_rate"])
        except Exception:
            return 22050

    def synth(self, text: str) -> SynthResult:
        import subprocess  # noqa: PLC0415

        rate = self._rate()
        t0 = time.perf_counter()
        proc = subprocess.run([*self.binary.split(), "-m", self.model, "--output-raw"],
                              input=(text + "\n").encode(), capture_output=True, timeout=180)
        if proc.returncode != 0:
            raise RuntimeError(f"piper failed: {proc.stderr.decode('utf-8', 'replace')[:200]}")
        pcm = np.frombuffer(proc.stdout, dtype=np.int16)
        return SynthResult(pcm, rate, pcm.size / rate, self.name, self.device, self.reason,
                           synth_seconds=time.perf_counter() - t0)


class GepardEngine(Engine):
    """texdata/Gepard-Slovenian-TTS (LoRA on gepard-1.0) + NVIDIA NanoCodec."""

    name = "gepard"

    def __init__(self, device: str, reason: str, offload: str = "auto",
                 min_free_gb: float = 3.0, temperature: float = 0.4,
                 cfg_scale: float = 4.5, cfg_frames: int = 25,
                 repetition_penalty: float = 1.45, repetition_window: int = 32,
                 max_frames: int = 800):
        self.device, self.reason = device, reason
        self.offload = offload
        self.min_free_gb = min_free_gb
        self.temperature = temperature
        self.cfg_scale = cfg_scale
        self.cfg_frames = cfg_frames
        self.repetition_penalty = repetition_penalty
        self.repetition_window = repetition_window
        self.max_frames = max_frames
        self.lock = threading.Lock()
        self.load_seconds = 0.0
        self.offloaded_to_cpu = False
        t0 = time.perf_counter()
        self._load()
        self.load_seconds = time.perf_counter() - t0

    def _imports(self):
        try:
            import torch  # noqa: PLC0415
            from gepard_inference import GepardRunner, UnfoldedCodecModel  # noqa: PLC0415
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(
                "Gepard engine unavailable: "
                f"{type(exc).__name__}: {exc}\n"
                "Install it with:\n"
                "  pip install accelerate 'nemo_toolkit[tts]'\n"
                "  pip install git+https://github.com/nineninesix-ai/gepard-inference\n"
                "Or start with --engine piper to keep Mia speaking.\n"
            ) from exc
        return torch, GepardRunner, UnfoldedCodecModel

    def _load(self) -> None:
        torch, GepardRunner, UnfoldedCodecModel = self._imports()
        self.torch = torch
        self.runner = self._load_runner(GepardRunner)
        codec_device = "cuda" if self._runner_on_cuda else "cpu"
        self.codec = UnfoldedCodecModel.from_pretrained(CODEC).eval().to(codec_device)
        self.codec_device = codec_device

    @property
    def _runner_on_cuda(self) -> bool:
        try:
            dev = next(self.runner.model.parameters()).device
            return dev.type == "cuda"
        except Exception:
            return self.device == "cuda" and not self.offloaded_to_cpu

    def _load_runner(self, GepardRunner):
        """Try the requested device, then an accelerate split, then pure CPU."""
        if self.device != "cuda":
            return GepardRunner.from_checkpoint(MODEL, device="cpu")
        if self.offload == "auto":
            free = gpu_free_gb() or 0.0
            budget = max(1.0, min(free - 0.5, free))
            try:
                runner = GepardRunner.from_checkpoint(
                    MODEL, device_map="auto",
                    max_memory={0: f"{budget:.1f}GiB", "cpu": "24GiB"},
                )
                print(f"[gepard] accelerate device_map=auto (gpu budget {budget:.1f} GiB)",
                      file=sys.stderr, flush=True)
                return runner
            except (TypeError, ValueError, ImportError) as exc:
                print(f"[gepard] device_map unsupported ({type(exc).__name__}) — trying GPU",
                      file=sys.stderr, flush=True)
        try:
            return GepardRunner.from_checkpoint(MODEL, device="cuda")
        except Exception as exc:  # noqa: BLE001
            print(f"[gepard] CUDA load failed ({type(exc).__name__}: {exc}) — RAM fallback",
                  file=sys.stderr, flush=True)
            self.offloaded_to_cpu = True
            self.device = "cpu"
            self.reason += " | CUDA load failed -> RAM fallback"
            return GepardRunner.from_checkpoint(MODEL, device="cpu")

    def synth(self, text: str) -> SynthResult:
        prompt = text if text.startswith(LANG_PREFIX.strip()) else LANG_PREFIX + text
        with self.lock:  # one generation at a time: the model is stateful
            t0 = time.perf_counter()
            tokens = self.runner.generate(
                prompt,
                temperature=self.temperature, cfg_scale=self.cfg_scale,
                cfg_frames=self.cfg_frames, repetition_penalty=self.repetition_penalty,
                repetition_window=self.repetition_window, max_frames=self.max_frames,
            )
            codes = tokens.unsqueeze(0).to(self.codec_device)
            lengths = self.torch.tensor([codes.shape[-1]], device=self.codec_device)
            audio, audio_len = self.codec.decode_from_codes(codes, lengths)
            pcm = audio[0, : int(audio_len[0])].detach().float().cpu().numpy()
            pcm = np.clip(pcm, -1.0, 1.0)
            pcm16 = (pcm * 32767).astype(np.int16)
            rate = 22050
            return SynthResult(pcm16, rate, pcm16.size / rate, self.name, self.device,
                               self.reason, load_seconds=self.load_seconds,
                               synth_seconds=time.perf_counter() - t0)


def build_engine(args) -> Engine:
    device, reason = pick_device(args.device, args.min_free_vram_gb)
    print(f"[tts] device={device} ({reason})", file=sys.stderr, flush=True)
    engine = (args.engine or "gepard").lower()
    if engine == "tone":
        return ToneEngine(device, reason)
    if engine == "piper":
        return PiperEngine(args.piper_model, args.piper_bin, device, reason)
    try:
        return GepardEngine(device, reason, offload=args.offload,
                            min_free_gb=args.min_free_vram_gb,
                            temperature=args.temperature, cfg_scale=args.cfg_scale,
                            cfg_frames=args.cfg_frames,
                            repetition_penalty=args.repetition_penalty,
                            repetition_window=args.repetition_window,
                            max_frames=args.max_frames)
    except SystemExit as exc:
        if args.fallback_piper and os.path.exists(args.piper_model):
            print(f"[tts] Gepard unavailable — falling back to Piper.\n{exc}",
                  file=sys.stderr, flush=True)
            return PiperEngine(args.piper_model, args.piper_bin, device,
                               reason + " | gepard unavailable -> piper")
        raise


def wav_bytes(result: SynthResult) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(result.sample_rate)
        w.writeframes(result.pcm.tobytes())
    return buf.getvalue()


# ------------------------------------------------------------------------ main

def run_stdio(engine: Engine) -> int:
    text = clean_text(sys.stdin.read())
    if not text:
        print("no text on stdin", file=sys.stderr)
        return 2
    result = engine.synth(text)
    sys.stdout.buffer.write(wav_bytes(result))
    sys.stdout.buffer.flush()
    return 0


def run_server(engine: Engine, host: str, port: int, token: str) -> int:
    from fastapi import FastAPI, Header, HTTPException, Request, Response  # noqa: PLC0415
    import uvicorn  # noqa: PLC0415

    app = FastAPI(title="Mia local TTS")

    def check(auth: str | None, x_mia: str | None, x_jarvis: str | None) -> None:
        if not token:
            return
        supplied = x_mia or x_jarvis or (auth or "").removeprefix("Bearer ").strip()
        if supplied != token:
            raise HTTPException(status_code=401, detail="auth required")

    @app.get("/health")
    def health() -> dict:
        info = engine.describe()
        info.update(free_vram_gb=gpu_free_gb(), pid=os.getpid(),
                    model=MODEL if engine.name == "gepard" else engine.name)
        return info

    @app.post("/tts")
    async def tts(request: Request, authorization: str | None = Header(default=None),
                  x_mia_token: str | None = Header(default=None),
                  x_jarvis_token: str | None = Header(default=None)) -> Response:
        check(authorization, x_mia_token, x_jarvis_token)
        try:
            payload = await request.json()
        except Exception:  # noqa: BLE001
            raise HTTPException(status_code=400, detail="JSON body required")
        text = clean_text(str((payload or {}).get("text") or ""))
        if not text:
            raise HTTPException(status_code=400, detail="empty text")
        result = engine.synth(text)
        return Response(content=wav_bytes(result), media_type="audio/wav",
                        headers={"X-TTS-Engine": result.engine, "X-TTS-Device": result.device,
                                 "X-TTS-Seconds": f"{result.seconds:.2f}",
                                 "X-TTS-Synth-Seconds": f"{result.synth_seconds:.3f}"})

    print(f"[tts] serving {engine.describe()} on http://{host}:{port}", file=sys.stderr, flush=True)
    uvicorn.run(app, host=host, port=port, log_level="warning")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Local TTS service for Mia (Gepard + fallback)")
    ap.add_argument("--serve", action="store_true", help="run HTTP JSON service (recommended)")
    ap.add_argument("--stdio", action="store_true", help="one-shot: stdin text -> WAV on stdout")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--engine", default="gepard", choices=("gepard", "piper", "tone"))
    ap.add_argument("--device", default="auto", choices=("auto", "cuda", "cpu"))
    ap.add_argument("--min-free-vram-gb", type=float, default=3.0,
                    help="below this free VRAM the service runs on CPU/RAM instead")
    ap.add_argument("--offload", default="auto", choices=("auto", "none"),
                    help="auto = try accelerate device_map split before CPU fallback")
    ap.add_argument("--fallback-piper", action="store_true",
                    help="serve Piper if the Gepard stack cannot be loaded")
    ap.add_argument("--piper-model",
                    default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                         "voices", "sl_PLACEHOLDER.onnx"),
                    help="Piper voice path used by --engine piper / --fallback-piper")
    ap.add_argument("--piper-bin", default="piper")
    ap.add_argument("--token-env", default="MIA_HUD_TOKEN")
    ap.add_argument("--temperature", type=float, default=0.4)
    ap.add_argument("--cfg-scale", type=float, default=4.5)
    ap.add_argument("--cfg-frames", type=int, default=25)
    ap.add_argument("--repetition-penalty", type=float, default=1.45)
    ap.add_argument("--repetition-window", type=int, default=32)
    ap.add_argument("--max-frames", type=int, default=800)
    args = ap.parse_args(argv)

    if args.piper_model.endswith("sl_PLACEHOLDER.onnx"):  # keep the default path usable
        args.piper_model = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "voices", "sl_SI-artur-medium.onnx")

    engine = build_engine(args)
    token = os.environ.get(args.token_env) or os.environ.get("JARVIS_HUD_TOKEN") or ""
    if args.serve:
        return run_server(engine, args.host, args.port, token)
    return run_stdio(engine)


if __name__ == "__main__":
    raise SystemExit(main())

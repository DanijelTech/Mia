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
  gepard   texdata/Gepard-Slovenian-TTS + NVIDIA NanoCodec (~2 GB VRAM)
  maya1    texdata/Maya1-Slovenian-TTS (3B + SNAC-24k, best SL pronunciation,
           ~6-7 GB VRAM, needs espeak-ng + phonemizer; slow on CPU)
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
import pathlib
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
        self.label = "tone"

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
        self.label = f"piper:{pathlib.Path(model).stem}"
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
        self.temperature = 0.4 if temperature is None else temperature
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


class MayaEngine(Engine):
    """texdata/Maya1-Slovenian-TTS — 3B Orpheus-style LM + SNAC-24kHz codec.

    Phoneme front-end: input MUST be espeak-ng `sl` IPA (the adapter was trained
    on phonemes, not graphemes), so `phonemizer` + the espeak-ng shared library
    are required. Heavier than Gepard (~6-7 GB in bf16) and autoregressive, so
    the same GPU/RAM policy applies; on CPU it works but is far slower than
    realtime — Piper or Gepard is the better choice there.
    """

    name = "maya1"
    CODE_END = 128258
    OFFSET = 128266
    SNAC_MIN = 128266
    SNAC_MAX = 156937
    DEFAULT_ADAPTER = "texdata/Maya1-Slovenian-TTS"
    DEFAULT_BASE = "maya-research/maya1"
    DEFAULT_SNAC = "hubertsiuzdak/snac_24khz"
    DEFAULT_SPEAKER = "Artur-B-G0911"
    # English voice descriptions the base model understands. The Slovenian
    # adapter was trained on ARTUR speaker IDs, so gender/age control is a nudge,
    # not a guarantee — try a few and keep what sounds best.
    VOICES = {
        "nevtralno": "A neutral Slovenian voice.",
        "zenski": "A clear Slovenian female voice.",
        "zenski-nezni": "A soft, gentle, warm Slovenian female voice, calm and quiet delivery.",
        "zenski-veseli": "A cheerful, bright Slovenian female voice.",
        "moski": "A calm Slovenian male voice.",
        "starejsi": "An older, warm Slovenian voice.",
    }
    EMOTIONS = {
        "nevtralno": "A neutral Slovenian voice.",
        "veselo": "An amused, cheerful, laughing Slovenian voice.",
        "jezno": "An angry, upset Slovenian voice.",
        "gnus": "A disgusted Slovenian voice.",
        "zaspano": "A sleepy, tired Slovenian voice.",
    }

    def __init__(self, device: str, reason: str, adapter: str = "", base: str = "",
                 speaker: str = "", emotion: str = "", voice: str = "",
                 description: str = "", temperature: float | None = None,
                 max_new_tokens: int = 1800, repetition_penalty: float = 1.1,
                 offload: str = "auto", min_free_gb: float = 3.0):
        self.device, self.reason = device, reason
        self.adapter = adapter or self.DEFAULT_ADAPTER
        self.base = base or self.DEFAULT_BASE
        self.speaker = speaker or self.DEFAULT_SPEAKER
        self.emotion = (emotion or "").strip().lower()
        self.voice = (voice or "").strip().lower()
        self.custom_description = (description or "").strip()
        self.temperature = 0.75 if temperature is None else float(temperature)
        self.max_new_tokens = int(max_new_tokens)
        self.repetition_penalty = float(repetition_penalty)
        self.offload = offload
        self.min_free_gb = min_free_gb
        self.lock = threading.Lock()
        self.load_seconds = 0.0
        self.offloaded_to_cpu = False
        t0 = time.perf_counter()
        self._load()
        self.load_seconds = time.perf_counter() - t0

    # -- description the model understands (English), tuned per emotion preset
    @property
    def description(self) -> str:
        # explicit description wins, then a voice preset, then an emotion preset
        if self.custom_description:
            return self.custom_description
        if self.voice and self.voice in self.VOICES:
            return self.VOICES[self.voice]
        if self.emotion and self.emotion in self.EMOTIONS:
            return self.EMOTIONS[self.emotion]
        return f"A Slovenian voice, speaker {self.speaker}."

    def describe(self) -> dict:
        info = super().describe()
        info.update(adapter=self.adapter, speaker=self.speaker,
                    voice=self.voice or "nevtralno",
                    emotion=self.emotion or "nevtralno",
                    description=self.description)
        return info

    def _imports(self):
        try:
            import torch  # noqa: PLC0415
            from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: PLC0415
            from peft import PeftModel  # noqa: PLC0415
            from snac import SNAC  # noqa: PLC0415
            from phonemizer.backend import EspeakBackend  # noqa: PLC0415
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(
                "Maya1 engine unavailable: "
                f"{type(exc).__name__}: {exc}\n"
                "Install it with:\n"
                "  pip install transformers peft torch snac soundfile phonemizer accelerate\n"
                "  sudo apt-get install espeak-ng        (or: brew install espeak)\n"
                "Or start with --engine piper / --engine gepard to keep Mia speaking.\n"
            ) from exc
        return torch, AutoModelForCausalLM, AutoTokenizer, PeftModel, SNAC, EspeakBackend

    def _ensure_espeak_lib(self) -> None:
        if os.environ.get("PHONEMIZER_ESPEAK_LIBRARY"):
            return
        for candidate in ("/usr/lib/x86_64-linux-gnu/libespeak-ng.so.1",
                          "/usr/lib64/libespeak-ng.so.1",
                          "/usr/lib/libespeak-ng.so.1",
                          "/usr/local/lib/libespeak-ng.dylib",
                          "/opt/homebrew/lib/libespeak-ng.dylib"):
            if os.path.exists(candidate):
                os.environ["PHONEMIZER_ESPEAK_LIBRARY"] = candidate
                return

    @staticmethod
    def _explain(exc: BaseException) -> str:
        text = f"{type(exc).__name__}: {exc}"
        low = text.lower()
        if "torchao" in low:
            return (text + "\nTorchao in peft se ne ujemata (peft 0.18 + starejši torchao).\n"
                    "Odstrani torchao ali pripni starejši peft:\n"
                    "  python3 -m pip uninstall -y torchao\n"
                    "  # ali: python3 -m pip install \"peft<0.18\"\n")
        if "libnvjitlink" in low or "cannot open shared object" in low:
            return (text + "\nManjka CUDA 13 knjižnica za torch. Namesti in nastavi pot:\n"
                    "  python3 -m pip install -U nvidia-nvjitlink-cu13 nvidia-cuda-runtime-cu13\n"
                    "  export LD_LIBRARY_PATH=$HOME/.local/lib/python3.12/site-packages/nvidia/nvjitlink/lib:$LD_LIBRARY_PATH\n")
        return text

    def _load(self) -> None:
        torch, AutoModelForCausalLM, AutoTokenizer, PeftModel, SNAC, EspeakBackend = self._imports()
        self.torch = torch
        self._ensure_espeak_lib()
        self.tokenizer = AutoTokenizer.from_pretrained(self.base)
        self.backend = EspeakBackend("sl", with_stress=True, preserve_punctuation=True)
        try:
            self.model = self._load_model(AutoModelForCausalLM, PeftModel)
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001 - convert to a clean, actionable failure
            raise SystemExit("Maya1 se ni naložil: " + self._explain(exc)) from exc
        codec_device = "cuda" if self.device == "cuda" and not self.offloaded_to_cpu else "cpu"
        try:
            codec_device = str(next(self.model.parameters()).device)
        except Exception:  # noqa: BLE001
            pass
        self.codec_device = codec_device
        self.snac = SNAC.from_pretrained(self.DEFAULT_SNAC).eval().to(codec_device)

    def _load_model(self, AutoModelForCausalLM, PeftModel):
        dtype = self.torch.bfloat16 if self.device == "cuda" else self.torch.float32
        if self.device != "cuda":
            # peft loads adapter weights on infer_device() -> "cuda" as soon as a GPU
            # is visible, which OOMs when the LLM already owns the card. CPU mode
            # means no CUDA at all, so make that explicit for every library.
            os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
            try:
                self.torch.cuda.is_available = lambda: False  # type: ignore[assignment]
            except Exception:
                pass
            print("[maya1] CPU mode: CUDA disabled for this process", file=sys.stderr, flush=True)
        model = None
        if self.device == "cuda" and self.offload == "auto":
            free = gpu_free_gb() or 0.0
            budget = max(1.0, free - 0.5)
            try:
                model = AutoModelForCausalLM.from_pretrained(
                    self.base, dtype=dtype, device_map="auto",
                    max_memory={0: f"{budget:.1f}GiB", "cpu": "24GiB"},
                )
                print(f"[maya1] accelerate device_map=auto (gpu budget {budget:.1f} GiB)",
                      file=sys.stderr, flush=True)
            except Exception as exc:  # noqa: BLE001
                print(f"[maya1] device_map failed ({type(exc).__name__}) — plain device",
                      file=sys.stderr, flush=True)
                model = None
        if model is None:
            try:
                model = AutoModelForCausalLM.from_pretrained(self.base, dtype=dtype).to(self.device)
            except Exception as exc:  # noqa: BLE001
                if self.device != "cuda":
                    raise
                print(f"[maya1] CUDA load failed ({type(exc).__name__}: {exc}) — RAM fallback",
                      file=sys.stderr, flush=True)
                self.offloaded_to_cpu = True
                self.device = "cpu"
                self.reason += " | CUDA load failed -> RAM fallback"
                model = AutoModelForCausalLM.from_pretrained(
                    self.base, dtype=self.torch.float32).to("cpu")
        return PeftModel.from_pretrained(model, self.adapter).eval()

    # -- SNAC token unpacking (7 tokens per frame, 3 hierarchical levels)
    def unpack_snac(self, ids: list[int]) -> list[list[int]]:
        frames = len(ids) // 7
        ids = ids[: frames * 7]
        l1, l2, l3 = [], [], []
        for i in range(frames):
            s = ids[i * 7:(i + 1) * 7]
            l1.append((s[0] - self.OFFSET) % 4096)
            l2 += [(s[1] - self.OFFSET) % 4096, (s[4] - self.OFFSET) % 4096]
            l3 += [(s[2] - self.OFFSET) % 4096, (s[3] - self.OFFSET) % 4096,
                   (s[5] - self.OFFSET) % 4096, (s[6] - self.OFFSET) % 4096]
        return [l1, l2, l3]

    def phonemize(self, text: str) -> str:
        from phonemizer.separator import Separator  # noqa: PLC0415
        return self.backend.phonemize([text], separator=Separator(phone="", word=" "),
                                      strip=True)[0]

    def synth(self, text: str) -> SynthResult:
        phonemes = self.phonemize(clean_text(text))
        content = f'<description="{self.description}"> {phonemes}'
        prompt = self.tokenizer.apply_chat_template(
            [{"role": "user", "content": content}], tokenize=False, add_generation_prompt=True)
        with self.lock:  # one generation at a time: the model is stateful
            t0 = time.perf_counter()
            ids = self.tokenizer(prompt, add_special_tokens=False,
                                 return_tensors="pt").input_ids.to(self.codec_device)
            out = self.model.generate(
                ids, max_new_tokens=self.max_new_tokens, do_sample=True,
                temperature=self.temperature, top_p=0.9,
                repetition_penalty=self.repetition_penalty,
                eos_token_id=self.CODE_END, pad_token_id=self.CODE_END,
            )
            generated = out[0, ids.shape[1]:].tolist()
            snac_ids = [t for t in generated if self.SNAC_MIN <= t <= self.SNAC_MAX]
            if not snac_ids:
                raise RuntimeError("Maya1 produced no SNAC tokens (runaway or empty generation)")
            codes = [self.torch.tensor(c, device=self.codec_device).unsqueeze(0)
                     for c in self.unpack_snac(snac_ids)]
            audio = self.snac.decoder(self.snac.quantizer.from_codes(codes))[0, 0]
            pcm = audio.detach().float().cpu().numpy()
            pcm16 = (np.clip(pcm, -1.0, 1.0) * 32767).astype(np.int16)
            rate = 24000
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

    def piper_fallback(exc) -> Engine:
        if not (args.fallback_piper and os.path.exists(args.piper_model)):
            raise exc
        print(f"[tts] {engine} unavailable — falling back to Piper.\n{exc}",
              file=sys.stderr, flush=True)
        return PiperEngine(args.piper_model, args.piper_bin, device,
                           reason + f" | {engine} unavailable -> piper")

    if engine == "maya1":
        try:
            return MayaEngine(device, reason, adapter=args.maya_adapter, base=args.maya_base,
                              speaker=args.maya_speaker, emotion=args.maya_emotion,
                              voice=args.maya_voice, description=args.maya_description,
                              temperature=args.temperature,
                              max_new_tokens=args.maya_max_new_tokens,
                              offload=args.offload, min_free_gb=args.min_free_vram_gb)
        except (SystemExit, Exception) as exc:  # noqa: BLE001
            return piper_fallback(exc)
    try:
        return GepardEngine(device, reason, offload=args.offload,
                            min_free_gb=args.min_free_vram_gb,
                            temperature=0.4 if args.temperature is None else args.temperature,
                            cfg_scale=args.cfg_scale, cfg_frames=args.cfg_frames,
                            repetition_penalty=args.repetition_penalty,
                            repetition_window=args.repetition_window,
                            max_frames=args.max_frames)
    except SystemExit as exc:
        return piper_fallback(exc)


def wav_bytes(result: SynthResult) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(result.sample_rate)
        w.writeframes(result.pcm.tobytes())
    return buf.getvalue()


def pitch_shift_pcm(pcm: np.ndarray, rate: int, semitones: float) -> np.ndarray:
    """Raise pitch AND formants by `semitones` via ffmpeg (asetrate + atempo).

    The formant shift is the point: the Slovenian Maya1 adapter was trained on
    a male speaker, and prompt steering alone leaves the voice masculine. A
    resample-based shift shortens the virtual vocal tract, which is what makes
    the result read as a woman's voice rather than a sped-up man.
    """
    import shutil
    import subprocess
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not semitones:
        return pcm
    ratio = 2.0 ** (semitones / 12.0)
    af = f"asetrate={int(round(rate * ratio))},aresample={rate},atempo={1.0 / ratio:.6f}"
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error",
         "-f", "s16le", "-ar", str(rate), "-ac", "1", "-i", "pipe:0",
         "-af", af,
         "-f", "s16le", "-ac", "1", "-ar", str(rate), "pipe:1"],
        input=pcm.tobytes(), capture_output=True, timeout=120,
    )
    if proc.returncode != 0 or not proc.stdout:
        print(f"[tts] pitch shift failed ({proc.stderr.decode('utf-8', 'replace')[:200]})"
              " — returning the original voice", file=sys.stderr, flush=True)
        return pcm
    out = np.frombuffer(proc.stdout, dtype=np.int16)
    return out if out.size else pcm


def apply_pitch(result: SynthResult, semitones: float) -> SynthResult:
    if semitones:
        result.pcm = pitch_shift_pcm(result.pcm, result.sample_rate, semitones)
    return result


# ------------------------------------------------------------------------ main

def run_stdio(engine: Engine, pitch: float = 0.0) -> int:
    text = clean_text(sys.stdin.read())
    if not text:
        print("no text on stdin", file=sys.stderr)
        return 2
    result = apply_pitch(engine.synth(text), pitch)
    sys.stdout.buffer.write(wav_bytes(result))
    sys.stdout.buffer.flush()
    return 0


def run_server(engine: Engine, host: str, port: int, token: str, pitch: float = 0.0) -> int:
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
        # per-request pitch (HUD slider) overrides the startup default
        req_pitch = (payload or {}).get("pitch_semitones")
        eff_pitch = pitch if req_pitch is None else max(-12.0, min(12.0, float(req_pitch)))
        result = apply_pitch(engine.synth(text), eff_pitch)
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
    ap.add_argument("--engine", default="gepard", choices=("gepard", "maya1", "piper", "tone"))
    ap.add_argument("--device", default="auto", choices=("auto", "cuda", "cpu"))
    ap.add_argument("--min-free-vram-gb", type=float, default=3.0,
                    help="below this free VRAM the service runs on CPU/RAM instead")
    ap.add_argument("--offload", default="auto", choices=("auto", "none"),
                    help="auto = try accelerate device_map split before CPU fallback")
    ap.add_argument("--fallback-piper", action="store_true",
                    help="serve Piper if the Gepard stack cannot be loaded")
    ap.add_argument("--piper-model",
                    default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                         "voices", "sl_SI-artur-medium.onnx"),
                    help="Piper voice path used by --engine piper / --fallback-piper")
    ap.add_argument("--piper-bin", default="piper")
    ap.add_argument("--token-env", default="MIA_HUD_TOKEN")
    ap.add_argument("--temperature", type=float, default=None,
                    help="sampling temperature (gepard: 0.4, maya1: 0.75)")
    ap.add_argument("--maya-adapter", default="", help="LoRA id/path (default: texdata/Maya1-Slovenian-TTS)")
    ap.add_argument("--maya-base", default="", help="base model (default: maya-research/maya1)")
    ap.add_argument("--maya-speaker", default="", help="speaker description (default: Artur-B-G0911)")
    ap.add_argument("--maya-emotion", default="",
                    choices=("", "nevtralno", "veselo", "jezno", "gnus", "zaspano"),
                    help="emotion preset (neutral read-speech adapter)")
    ap.add_argument("--maya-voice", default="",
                    choices=("", "nevtralno", "zenski", "zenski-nezni", "zenski-veseli",
                             "moski", "starejsi"),
                    help="voice-character preset, e.g. zenski-nezni (female, gentle)")
    ap.add_argument("--maya-description", default="",
                    help="free-form English voice description (overrides presets), "
                         "e.g. 'A soft, gentle Slovenian female voice.'")
    ap.add_argument("--maya-max-new-tokens", type=int, default=1800)
    ap.add_argument("--pitch-semitones", type=float, default=0.0,
                    help="post-shift pitch+formants by N semitones (e.g. 4 feminizes a "
                         "male-trained voice; needs ffmpeg; 0 = off)")
    ap.add_argument("--cfg-scale", type=float, default=4.5)
    ap.add_argument("--cfg-frames", type=int, default=25)
    ap.add_argument("--repetition-penalty", type=float, default=1.45)
    ap.add_argument("--repetition-window", type=int, default=32)
    ap.add_argument("--max-frames", type=int, default=800)
    args = ap.parse_args(argv)

    if (args.device or "").lower() == "cpu":
        # before torch is imported anywhere: keep the GPU untouched
        os.environ["CUDA_VISIBLE_DEVICES"] = ""

    engine = build_engine(args)
    token = os.environ.get(args.token_env) or os.environ.get("JARVIS_HUD_TOKEN") or ""
    if args.serve:
        return run_server(engine, args.host, args.port, token, pitch=args.pitch_semitones)
    return run_stdio(engine, pitch=args.pitch_semitones)


if __name__ == "__main__":
    raise SystemExit(main())

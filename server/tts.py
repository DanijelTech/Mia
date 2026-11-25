"""Text-to-speech backends that stream 16 kHz mono int16 PCM.

Local providers are the default: `piper` (fast, CPU, MIT voices) and `command`
(any local TTS binary that reads text on stdin and writes WAV or raw PCM on
stdout, e.g. Gepard or Maya1 wrappers). `elevenlabs` stays available for cloud
setups but is never used unless explicitly configured.
"""

from __future__ import annotations

import io
import json
import os
import shlex
import subprocess
import wave
from pathlib import Path
from typing import Iterator

import numpy as np

TARGET_RATE = 16000


class PCMResampler:
    """Streaming linear resampler for int16 mono, phase-continuous across chunks."""

    def __init__(self, src_rate: int, dst_rate: int = TARGET_RATE):
        if src_rate <= 0 or dst_rate <= 0:
            raise ValueError("sample rates must be positive")
        self.step = src_rate / dst_rate
        self.src_rate = src_rate
        self.dst_rate = dst_rate
        self._buf = np.zeros(0, dtype=np.float32)
        self._pos = 0.0

    @property
    def passthrough(self) -> bool:
        return self.src_rate == self.dst_rate

    def process(self, data: bytes) -> bytes:
        if not data:
            return b""
        if self.passthrough:
            return data
        self._buf = np.concatenate([self._buf, np.frombuffer(data, dtype=np.int16).astype(np.float32)])
        count = int(np.floor((len(self._buf) - 1 - self._pos) / self.step)) + 1
        if count <= 0:
            return b""
        idx = self._pos + self.step * np.arange(count)
        out = np.interp(idx, np.arange(len(self._buf)), self._buf)
        self._pos = idx[-1] + self.step
        drop = int(np.floor(self._pos))
        if drop > 0:
            self._buf = self._buf[drop:]
            self._pos -= drop
        return np.clip(np.rint(out), -32768, 32767).astype(np.int16).tobytes()

    def flush(self) -> bytes:
        if self.passthrough or len(self._buf) == 0:
            return b""
        idx = np.arange(self._pos, len(self._buf), self.step)
        if idx.size == 0:
            return b""
        out = np.interp(idx, np.arange(len(self._buf)), self._buf)
        self._buf = np.zeros(0, dtype=np.float32)
        self._pos = 0.0
        return np.clip(np.rint(out), -32768, 32767).astype(np.int16).tobytes()


def _wav_to_pcm16(data: bytes) -> tuple[bytes, int]:
    with wave.open(io.BytesIO(data), "rb") as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise RuntimeError("TTS WAV must be mono 16-bit")
        return w.readframes(w.getnframes()), w.getframerate()


class TTSBackend:
    name = "base"
    label = ""

    def __init__(self, cfg: dict | None = None, root: Path | None = None):
        self.cfg = cfg or {}
        self.root = root or Path(__file__).resolve().parent

    def _path(self, value: str) -> Path:
        p = Path(os.path.expanduser(value))
        return p if p.is_absolute() else (self.root / p)

    def synth(self, text: str) -> Iterator[bytes]:
        raise NotImplementedError


class PiperBackend(TTSBackend):
    """Piper voices (MIT voices; the piper CLI itself is GPL-3.0)."""

    name = "piper"

    def __init__(self, cfg: dict | None = None, root: Path | None = None):
        super().__init__(cfg, root)
        self.binary = self.cfg.get("binary") or "piper"
        self.mode = (self.cfg.get("mode") or "cli").lower()
        self.model = self._resolve_model()
        self.speaker = self.cfg.get("speaker")
        self.length_scale = self.cfg.get("length_scale")
        self.sample_rate = int(self.cfg.get("sample_rate") or self._model_rate())
        self.label = f"piper:{self.model.stem}"

    def _resolve_model(self) -> Path:
        voices = self.cfg.get("voices") or {}
        language = (self.cfg.get("language") or "").lower()
        chosen = voices.get(language) or self.cfg.get("model")
        if not chosen:
            raise RuntimeError("tts.piper.model (or tts.piper.voices) is required")
        path = self._path(chosen)
        if not path.exists():
            raise RuntimeError(f"Piper voice model not found: {path} (run scripts/get-voice.sh)")
        return path

    def _model_rate(self) -> int:
        cfg_json = self.model.with_suffix(self.model.suffix + ".json")
        try:
            return int(json.loads(cfg_json.read_text())["audio"]["sample_rate"])
        except Exception:
            return 22050

    def _cmd(self) -> list[str]:
        cmd = [*shlex.split(self.binary), "-m", str(self.model), "--output-raw"]
        if self.speaker is not None:
            cmd += ["--speaker", str(self.speaker)]
        if self.length_scale is not None:
            cmd += ["--length-scale", str(self.length_scale)]
        return cmd

    def synth(self, text: str) -> Iterator[bytes]:
        if self.mode == "python":
            yield from self._synth_python(text)
        else:
            yield from self._synth_cli(text)

    def _synth_cli(self, text: str) -> Iterator[bytes]:
        proc = subprocess.Popen(
            self._cmd(), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, bufsize=0,
        )
        resampler = PCMResampler(self.sample_rate)
        try:
            assert proc.stdin and proc.stdout
            proc.stdin.write((text.strip() + "\n").encode("utf-8"))
            proc.stdin.close()
            while True:
                chunk = proc.stdout.read(4096)
                if not chunk:
                    break
                out = resampler.process(chunk)
                if out:
                    yield out
            tail = resampler.flush()
            if tail:
                yield tail
        finally:
            if proc.poll() is None:
                proc.kill()
            err = b""
            if proc.stderr:
                try:
                    err = proc.stderr.read() or b""
                except Exception:
                    pass
                proc.stderr.close()
            proc.wait(timeout=10)
            if proc.returncode not in (0, None) and not err:
                raise RuntimeError(f"piper exited with {proc.returncode}")

    def _synth_python(self, text: str) -> Iterator[bytes]:
        try:
            from piper import PiperVoice  # GPL-3.0: only import when explicitly enabled
        except ImportError as exc:
            raise RuntimeError("piper python mode needs `pip install piper-tts`") from exc
        if not getattr(self, "_voice", None):
            self._voice = PiperVoice.load(str(self.model))
        resampler = PCMResampler(self.sample_rate)
        for chunk in self._voice.synthesize(text.strip()):
            out = resampler.process(chunk.audio_int16_bytes)
            if out:
                yield out
        tail = resampler.flush()
        if tail:
            yield tail


class CommandBackend(TTSBackend):
    """Any local TTS CLI: text on stdin, WAV (default) or raw PCM16 on stdout.

    Wraps Gepard/Maya1/Piper-alternatives without this repo depending on them.
    """

    name = "command"

    def __init__(self, cfg: dict | None = None, root: Path | None = None):
        super().__init__(cfg, root)
        self.argv = self.cfg.get("argv") or []
        if not self.argv:
            raise RuntimeError("tts.command.argv is required")
        self.argv = [str(a) for a in self.argv]
        self.format = (self.cfg.get("format") or "wav").lower()
        self.sample_rate = int(self.cfg.get("sample_rate") or TARGET_RATE)
        self.label = f"command:{Path(self.argv[0]).name}"

    def synth(self, text: str) -> Iterator[bytes]:
        proc = subprocess.run(
            self.argv, input=(text.strip() + "\n").encode("utf-8"),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"tts command failed ({proc.returncode}): {proc.stderr.decode('utf-8', 'replace')[:300]}")
        data, rate = proc.stdout, self.sample_rate
        if self.format == "wav":
            data, rate = _wav_to_pcm16(proc.stdout)
        resampler = PCMResampler(rate)
        out = resampler.process(data) + resampler.flush()
        if out:
            yield out


class HTTPBackend(TTSBackend):
    """Local TTS HTTP service: POST {"text": ...} -> WAV (or raw PCM16).

    Model lives in that service, so it is loaded once instead of per sentence —
    the right shape for heavy local engines (Gepard, Maya1) and for running the
    voice on a second machine.
    """

    name = "http"

    def __init__(self, cfg: dict | None = None, root: Path | None = None):
        super().__init__(cfg, root)
        self.url = self.cfg.get("url")
        if not self.url:
            raise RuntimeError("tts.http.url is required (e.g. http://127.0.0.1:8770/tts)")
        self.timeout = float(self.cfg.get("timeout") or 120)
        self.format = (self.cfg.get("format") or "wav").lower()
        self.sample_rate = int(self.cfg.get("sample_rate") or TARGET_RATE)
        self.token = (os.environ.get(self.cfg.get("token_env") or "MIA_HUD_TOKEN", "")
                      or os.environ.get("JARVIS_HUD_TOKEN", ""))
        self.label = self.cfg.get("name") or f"http:{self.url.split('//')[-1]}"

    def synth(self, text: str) -> Iterator[bytes]:
        import requests

        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["X-Mia-Token"] = self.token
        response = requests.post(self.url, json={"text": text}, headers=headers,
                                 timeout=self.timeout)
        if response.status_code >= 400:
            raise RuntimeError(f"TTS service HTTP {response.status_code}: {response.text[:300]}")
        data, rate = response.content, self.sample_rate
        if self.format == "wav":
            data, rate = _wav_to_pcm16(response.content)
        resampler = PCMResampler(rate)
        out = resampler.process(data) + resampler.flush()
        if out:
            yield out


class ElevenLabsBackend(TTSBackend):
    """Cloud fallback — only used when tts.provider is explicitly elevenlabs."""

    name = "elevenlabs"

    def __init__(self, cfg: dict | None = None, root: Path | None = None):
        super().__init__(cfg, root)
        self.model = self.cfg.get("model") or "eleven_flash_v2_5"
        self.voice_id = self.cfg.get("voice_id") or ""
        self.output_format = self.cfg.get("output_format") or "pcm_16000"
        self.label = f"elevenlabs:{self.model}"

    def synth(self, text: str) -> Iterator[bytes]:
        import requests

        key = (os.environ.get("ELEVENLABS_API_KEY") or os.environ.get("ELEVEN_API_KEY")
               or os.environ.get("XI_API_KEY"))
        if not key:
            raise RuntimeError("ELEVENLABS_API_KEY not set (tts.provider is elevenlabs)")
        response = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream",
            params={"output_format": self.output_format},
            headers={"xi-api-key": key, "Accept": "application/octet-stream",
                     "Content-Type": "application/json"},
            json={"text": text, "model_id": self.model,
                  "voice_settings": {"stability": 0.55, "similarity_boost": 0.70,
                                     "style": 0.10, "use_speaker_boost": True}},
            stream=True, timeout=120,
        )
        if response.status_code >= 400:
            response.close()
            raise RuntimeError(f"ElevenLabs HTTP {response.status_code}: {response.text[:300]}")
        try:
            for chunk in response.iter_content(chunk_size=4096):
                if chunk:
                    yield chunk
        finally:
            response.close()


def build_backend(cfg: dict, root: Path) -> TTSBackend:
    tts_cfg = dict(cfg.get("tts") or {})
    provider = (tts_cfg.get("provider") or "").lower()
    if not provider:
        provider = "elevenlabs" if cfg.get("voice") else "piper"
    if provider == "piper":
        return PiperBackend(tts_cfg.get("piper") or {}, root)
    if provider == "command":
        return CommandBackend(tts_cfg.get("command") or {}, root)
    if provider == "http":
        return HTTPBackend(tts_cfg.get("http") or {}, root)
    if provider == "elevenlabs":
        legacy = dict(cfg.get("voice") or {})
        legacy.update({k: v for k, v in (tts_cfg.get("elevenlabs") or {}).items() if v})
        return ElevenLabsBackend(legacy, root)
    raise RuntimeError(f"unknown tts.provider: {provider}")

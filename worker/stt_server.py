#!/usr/bin/env python3
"""Mia GPU STT server — run on any machine with an NVIDIA GPU.

Gives the voice pipeline big-model transcription (~0.2s for a sentence on a
modern GPU) while the host machine keeps a small local model as fallback.

Setup (Windows or Linux, NVIDIA driver installed):
    python -m venv .venv
    .venv/Scripts/pip install faster-whisper fastapi uvicorn nvidia-cublas-cu12 nvidia-cudnn-cu12
    set MIA_STT_TOKEN=<same value as MIA_HUD_TOKEN on the server>
    set MIA_STT_LANGUAGE=sl        (optional; "" = auto-detect)
    .venv/Scripts/python stt_server.py

Then point the voice server's `stt.remote.url` at http://this-machine:8768/stt

API:
    POST /stt    body: raw int16 16 kHz mono PCM, header X-Mia-Token
                 -> {"text": "..."}
    GET  /health -> {"status":"ok", ...}
"""
import os
import pathlib
import sys
import time

# Make the pip-installed NVIDIA cuBLAS/cuDNN DLLs loadable for ctranslate2.
# NOTE: use sys.prefix — site.getsitepackages() misses the venv on Windows.
_nv = pathlib.Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
for sub in ("cublas/bin", "cudnn/bin", "cuda_nvrtc/bin"):
    p = _nv / sub
    if p.exists():
        os.add_dll_directory(str(p))
        os.environ["PATH"] = str(p) + os.pathsep + os.environ.get("PATH", "")

import numpy as np
import torch
import uvicorn
from fastapi import FastAPI, Request, Response
from faster_whisper import WhisperModel

def _env(name: str, default: str = "") -> str:
    """Read MIA_* first, then the pre-rebrand JARVIS_* equivalent."""
    return os.environ.get(name) or os.environ.get(name.replace("MIA_", "JARVIS_", 1)) or default


MODEL_NAME = _env("MIA_STT_MODEL", "large-v3-turbo")
DEVICE_REQ = _env("MIA_STT_DEVICE", "auto")        # auto | cuda | cpu
MIN_FREE_VRAM_GB = float(_env("MIA_STT_MIN_FREE_VRAM_GB", "2.5") or 0)
COMPUTE_REQ = _env("MIA_STT_COMPUTE_TYPE")
TOKEN = _env("MIA_STT_TOKEN")
PORT = int(_env("MIA_STT_PORT", "8768"))
LANGUAGE = _env("MIA_STT_LANGUAGE")      # "" = auto-detect; "sl", "sr", "en" ...
INITIAL_PROMPT = _env("MIA_STT_INITIAL_PROMPT")

def resolve_device(requested: str) -> str:
    """auto = CUDA when a GPU has room, else CPU/RAM (shared box with the LLM)."""
    requested = (requested or "auto").lower()
    if requested in ("cpu", "cuda"):
        return requested
    if not torch.cuda.is_available():
        return "cpu"
    free, _total = torch.cuda.mem_get_info()
    free_gb = free / 1024**3
    if free_gb < MIN_FREE_VRAM_GB:
        print(f"only {free_gb:.1f} GB VRAM free (< {MIN_FREE_VRAM_GB}) -> CPU", flush=True)
        return "cpu"
    return "cuda"


DEVICE = resolve_device(DEVICE_REQ)
COMPUTE_TYPE = COMPUTE_REQ or ("float16" if DEVICE == "cuda" else "int8")
print(f"Loading {MODEL_NAME} on {DEVICE.upper()} ({COMPUTE_TYPE})...", flush=True)
t0 = time.time()
try:
    model = WhisperModel(MODEL_NAME, device=DEVICE, compute_type=COMPUTE_TYPE)
except Exception as exc:
    if DEVICE == "cuda":
        print(f"CUDA load failed ({type(exc).__name__}: {exc}) -> CPU fallback", flush=True)
        DEVICE, COMPUTE_TYPE = "cpu", "int8"
        model = WhisperModel(MODEL_NAME, device=DEVICE, compute_type=COMPUTE_TYPE)
    else:
        raise
print(f"Model ready in {time.time()-t0:.1f}s on {DEVICE}", flush=True)

app = FastAPI(title="Mia GPU STT")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "model": MODEL_NAME, "device": DEVICE,
            "compute_type": COMPUTE_TYPE, "language": LANGUAGE or "auto"}


@app.post("/stt")
async def stt(request: Request):
    if TOKEN and request.headers.get("x-mia-token") != TOKEN:
        return Response(status_code=401, content="auth required")
    body = await request.body()
    if len(body) < 3200:  # <0.1s of audio
        return {"text": ""}
    audio = np.frombuffer(body[: len(body) // 2 * 2], dtype=np.int16).astype(np.float32) / 32768.0
    t0 = time.time()
    language = request.query_params.get("language") or LANGUAGE or None
    prompt = request.query_params.get("initial_prompt") or INITIAL_PROMPT or None
    try:
        segments, _info = model.transcribe(
            audio, language=language, beam_size=1, vad_filter=False,
            initial_prompt=prompt,
        )
        text = " ".join(s.text.strip() for s in segments).strip()
    except Exception as exc:  # silence/garbage audio -> empty transcript, not a 500
        print(f"transcribe error -> empty: {exc}", flush=True)
        text = ""
    print(f"{len(audio)/16000:.1f}s audio -> {time.time()-t0:.2f}s : {text[:80]}", flush=True)
    return {"text": text}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")

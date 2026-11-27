#!/usr/bin/env python3
"""Windows LAN voice client for the Hermes voice pipeline.

Captures 16 kHz mono PCM, runs openWakeWord locally unless push-to-talk is used,
streams audio to the Mac server, and plays returned audio through the default
Windows output device.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import queue
import signal
import sys
import threading
import time
from dataclasses import dataclass

import numpy as np
import sounddevice as sd
import websockets

try:
    from openwakeword.model import Model as WakeWordModel
except Exception:  # Import failure is handled at runtime for clearer messages.
    WakeWordModel = None

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"
CHUNK_MS = 80
CHUNK_FRAMES = int(SAMPLE_RATE * CHUNK_MS / 1000)
DEFAULT_SERVER = (os.environ.get("MIA_SERVER_URL")
                  or os.environ.get("JARVIS_SERVER_URL")
                  or "ws://127.0.0.1:8765/ws")
# openWakeWord ships no "hey mia" model — "hey_jarvis" is the closest stock one.
# Set MIA_WAKE_WORD (or --wake-word) to any model your install has, or train a
# custom .onnx. Push-to-talk (--push-to-talk) needs no wake word at all.
DEFAULT_WAKE_WORD = os.environ.get("MIA_WAKE_WORD") or "hey_jarvis"


@dataclass
class DeviceChoice:
    input_device: int | None
    output_device: int | None


def list_devices() -> None:
    print(sd.query_devices())


def make_beep(sample_rate: int = SAMPLE_RATE, duration: float = 0.18, freq: float = 880.0) -> np.ndarray:
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    wave = 0.20 * np.sin(2 * math.pi * freq * t)
    envelope = np.linspace(0.0, 1.0, min(400, len(wave)))
    wave[: len(envelope)] *= envelope
    wave[-len(envelope) :] *= envelope[::-1]
    return wave.astype(np.float32)


def play_beep(output_device: int | None) -> None:
    try:
        sd.play(make_beep(), samplerate=SAMPLE_RATE, device=output_device, blocking=True)
    except Exception as exc:
        print(f"Warning: could not play wake beep: {exc}")


def audio_callback_factory(audio_q: queue.Queue[bytes]):
    def callback(indata, frames, time_info, status):
        if status:
            print(f"Audio input warning: {status}", file=sys.stderr)
        audio_q.put(bytes(indata))

    return callback


class StreamingPlayer:
    """Play 16 kHz int16 PCM as it arrives through a small device buffer.

    The old client accumulated a whole reply and played it only on `done`,
    which added the full generation + synthesis time to the first word. A
    RawOutputStream drained by a writer thread keeps the server stream and the
    speaker in step, with backpressure in the device itself.
    """

    def __init__(self, output_device: int | None):
        self.q: queue.Queue = queue.Queue()
        self.closed = False
        self._lock = threading.Lock()
        self._fed = 0
        self._played = 0
        self.stream = sd.RawOutputStream(
            samplerate=SAMPLE_RATE, channels=CHANNELS, dtype=DTYPE,
            device=output_device)
        self.stream.start()
        self.thread = threading.Thread(target=self._run, name="audio-writer",
                                       daemon=True)
        self.thread.start()

    def _run(self) -> None:
        while True:
            data = self.q.get()
            if data is None:
                break
            try:
                self.stream.write(data)
            except Exception as exc:
                print(f"[audio] output error: {exc}", file=sys.stderr)
                break
            with self._lock:
                self._played += len(data)
        for closer in (self.stream.stop, self.stream.close):
            try:
                closer()
            except Exception:
                pass

    def feed(self, data: bytes) -> None:
        if not self.closed and data:
            with self._lock:
                self._fed += len(data)
            self.q.put(data)

    def wait_drained(self, timeout: float = 30.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if self._played >= self._fed:
                    return True
            time.sleep(0.05)
        return False

    def close(self, flush: bool = True) -> None:
        """Stop the writer. `flush=True` plays what is already queued."""
        if self.closed:
            return
        self.closed = True
        if not flush:
            while not self.q.empty():
                try:
                    self.q.get_nowait()
                except queue.Empty:
                    break
        self.q.put(None)
        self.thread.join(timeout=30 if flush else 3)

    def stop(self) -> None:
        self.close(flush=False)


_CURRENT_PLAYER: "StreamingPlayer | None" = None


def stop_playback() -> None:
    """Stop whatever the streaming player is playing (push-to-talk interrupt)."""
    global _CURRENT_PLAYER
    player, _CURRENT_PLAYER = _CURRENT_PLAYER, None
    if player is not None:
        player.stop()


async def playback_worker(ws, output_device: int | None, stop_event: asyncio.Event, turn_complete: asyncio.Event | None = None) -> None:
    """Receive audio messages from the server and play them as they arrive."""
    global _CURRENT_PLAYER
    player: StreamingPlayer | None = None
    buffered = bytearray()   # fallback when RawOutputStream is unavailable
    streaming_failed = False

    def _close_player(stop: bool = False) -> None:
        global _CURRENT_PLAYER
        nonlocal player
        if player is not None:
            if stop:
                player.stop()
            else:
                player.close()
            if _CURRENT_PLAYER is player:
                _CURRENT_PLAYER = None
            player = None

    def _play_buffered() -> None:
        usable = len(buffered) - (len(buffered) % 2)
        if not usable:
            return
        audio = np.frombuffer(bytes(buffered[:usable]), dtype=np.int16)
        if audio.size:
            sd.play(audio, samplerate=SAMPLE_RATE, device=output_device,
                    blocking=True)
        buffered.clear()

    try:
        async for message in ws:
            if isinstance(message, str):
                try:
                    event = json.loads(message)
                except json.JSONDecodeError:
                    print(f"Server: {message}")
                    continue
                event_type = event.get("type")
                if event_type == "error":
                    print(f"Server error: {event.get('message', 'unknown error')}")
                elif event_type == "status":
                    print(f"Server: {event.get('message', '')}")
                elif event_type == "transcript":
                    print(f"Transcript: {event.get('text', '')}")
                elif event_type == "agent_status" and event.get("state") == "stopped":
                    await asyncio.to_thread(_close_player, True)
                    buffered.clear()
                elif event_type == "done":
                    if player is not None:
                        async def _finish(p=player, ev=turn_complete):
                            try:
                                await asyncio.to_thread(p.wait_drained, 30)
                            finally:
                                if ev is not None:
                                    ev.set()
                        asyncio.create_task(_finish())
                    elif buffered:
                        await asyncio.to_thread(_play_buffered)
                        if turn_complete is not None:
                            turn_complete.set()
                    else:
                        print("[audio] no response audio received for this turn")
                        if turn_complete is not None:
                            turn_complete.set()
                    print("Turn complete.")
                continue

            if player is None and not buffered and not streaming_failed:
                try:
                    player = StreamingPlayer(output_device)
                    _CURRENT_PLAYER = player
                except Exception as exc:
                    streaming_failed = True
                    print(f"[audio] streaming unavailable ({exc}); buffering the turn",
                          file=sys.stderr)
            if player is not None:
                player.feed(bytes(message))
            else:
                buffered.extend(message)
    except websockets.ConnectionClosed:
        if not stop_event.is_set():
            print("Server connection closed.")
    finally:
        if player is not None:
            await asyncio.to_thread(_close_player)
        elif buffered:
            await asyncio.to_thread(_play_buffered)
        stop_event.set()


def start_stdin_reader(loop: asyncio.AbstractEventLoop, enter_q: "asyncio.Queue") -> threading.Thread:
    """Read lines from stdin on a daemon thread and push them to an asyncio queue.

    A single reader avoids multiple competing blocking input() calls and lets the
    push-to-talk loop treat every Enter press uniformly (start, stop, or barge-in).
    The thread is a daemon so it never blocks interpreter exit.
    """
    def _run() -> None:
        while True:
            line = sys.stdin.readline()
            if line == "":
                loop.call_soon_threadsafe(enter_q.put_nowait, None)
                return
            loop.call_soon_threadsafe(enter_q.put_nowait, line.rstrip("\r\n"))

    thread = threading.Thread(target=_run, name="stdin-reader", daemon=True)
    thread.start()
    return thread


async def push_to_talk_loop(
    ws,
    audio_q: queue.Queue[bytes],
    stop_event: asyncio.Event,
    turn_complete: asyncio.Event,
    enter_q: "asyncio.Queue",
    output_device: int | None,
) -> None:
    print("Push-to-talk mode. Press Enter to start a turn, press Enter again to stop.")
    print("While Hermes is speaking, press Enter to interrupt and take your next turn.")
    print("Type 'q' then Enter (or press Ctrl+C) to quit.")

    auto_start = False
    while not stop_event.is_set():
        if not auto_start:
            print("\nReady. Press Enter to start talking (or 'q' to quit)...")
            command = await enter_q.get()
            if command is None or command.strip().lower() in ("q", "quit", "exit"):
                break
            if stop_event.is_set():
                break
        auto_start = False

        turn_complete.clear()
        while True:
            try:
                audio_q.get_nowait()
            except queue.Empty:
                break

        print("Streaming. Press Enter to stop.")
        await asyncio.to_thread(stop_playback)
        play_beep(output_device)
        await ws.send(json.dumps({"type": "start", "sample_rate": SAMPLE_RATE, "format": "pcm_s16le", "channels": CHANNELS}))

        stop_command = None
        while not stop_event.is_set():
            try:
                stop_command = enter_q.get_nowait()
                break
            except asyncio.QueueEmpty:
                pass
            try:
                chunk = await asyncio.to_thread(audio_q.get, True, 0.2)
            except queue.Empty:
                continue
            await ws.send(chunk)

        await ws.send(json.dumps({"type": "stop"}))
        print("Stopped streaming. Waiting for response (press Enter to interrupt)...")

        if stop_command is not None and stop_command.strip().lower() in ("q", "quit", "exit"):
            break

        complete_task = asyncio.create_task(turn_complete.wait())
        interrupt_task = asyncio.create_task(enter_q.get())
        done, _ = await asyncio.wait(
            {complete_task, interrupt_task}, return_when=asyncio.FIRST_COMPLETED
        )

        if interrupt_task in done:
            await asyncio.to_thread(stop_playback)
            complete_task.cancel()
            command = interrupt_task.result()
            if command is None or command.strip().lower() in ("q", "quit", "exit"):
                break
            try:
                await asyncio.wait_for(turn_complete.wait(), timeout=2)
            except asyncio.TimeoutError:
                pass
            print("(interrupted) go ahead.")
            auto_start = True
        else:
            interrupt_task.cancel()

    print("Exiting push-to-talk.")


async def wake_word_loop(
    ws,
    audio_q: queue.Queue[bytes],
    stop_event: asyncio.Event,
    output_device: int | None,
    wake_word: str,
    threshold: float,
    max_record_seconds: float,
) -> None:
    if WakeWordModel is None:
        print("openWakeWord could not be imported. Run with --push-to-talk or reinstall requirements-client.txt.")
        stop_event.set()
        return

    print(f"Loading openWakeWord model for stock wake word: {wake_word}")
    print("To swap later, pass --wake-word NAME if your installed openWakeWord package includes that model, or update this script to load a custom .onnx model.")
    model = WakeWordModel(wakeword_models=[wake_word])
    print("Listening for wake word. Press Ctrl+C to exit.")

    while not stop_event.is_set():
        try:
            chunk = await asyncio.to_thread(audio_q.get, True, 0.2)
        except queue.Empty:
            continue

        frame = np.frombuffer(chunk, dtype=np.int16)
        prediction = model.predict(frame)
        score = float(prediction.get(wake_word, 0.0))
        if score < threshold:
            continue

        print(f"Wake word detected ({wake_word}, score {score:.2f}). Streaming for up to {max_record_seconds:.1f}s, press Ctrl+C to exit.")
        await asyncio.to_thread(stop_playback)
        play_beep(output_device)
        await ws.send(json.dumps({"type": "start", "sample_rate": SAMPLE_RATE, "format": "pcm_s16le", "channels": CHANNELS}))
        start = time.perf_counter()
        while time.perf_counter() - start < max_record_seconds and not stop_event.is_set():
            try:
                speech_chunk = await asyncio.to_thread(audio_q.get, True, 0.2)
            except queue.Empty:
                continue
            await ws.send(speech_chunk)
        await ws.send(json.dumps({"type": "stop"}))
        print("Utterance sent. Waiting for response audio...")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hermes LAN voice client for Windows")
    parser.add_argument("--server", default=DEFAULT_SERVER, help=f"WebSocket server URL, default {DEFAULT_SERVER}")
    parser.add_argument("--input-device", type=int, default=None, help="sounddevice input device index")
    parser.add_argument("--output-device", type=int, default=None, help="sounddevice output device index")
    parser.add_argument("--list-devices", action="store_true", help="list Windows audio devices and exit")
    parser.add_argument("--push-to-talk", action="store_true", help="bypass wake word; press Enter to start and stop streaming")
    parser.add_argument("--wake-word", default=DEFAULT_WAKE_WORD, help=f"openWakeWord stock model name, default {DEFAULT_WAKE_WORD}")
    parser.add_argument("--wake-threshold", type=float, default=0.55, help="wake detection threshold")
    parser.add_argument("--max-record-seconds", type=float, default=8.0, help="maximum utterance length after wake word")
    return parser.parse_args()


async def main_async() -> int:
    args = parse_args()
    if args.list_devices:
        list_devices()
        return 0

    audio_q: queue.Queue[bytes] = queue.Queue(maxsize=200)
    stop_event = asyncio.Event()
    turn_complete = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            try:
                loop.add_signal_handler(sig, stop_event.set)
            except NotImplementedError:
                pass

    try:
        input_stream = sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            blocksize=CHUNK_FRAMES,
            dtype=DTYPE,
            channels=CHANNELS,
            device=args.input_device,
            callback=audio_callback_factory(audio_q),
        )
    except Exception as exc:
        print(f"Could not open microphone at 16 kHz mono: {exc}")
        print("Run: python client.py --list-devices")
        print("Then retry with: python client.py --input-device DEVICE_INDEX")
        return 2

    try:
        async with websockets.connect(args.server, max_size=None) as ws:
            print(f"Connected to {args.server}")
            with input_stream:
                player = asyncio.create_task(playback_worker(ws, args.output_device, stop_event, turn_complete))
                if args.push_to_talk:
                    enter_q: asyncio.Queue = asyncio.Queue()
                    start_stdin_reader(loop, enter_q)
                    await push_to_talk_loop(ws, audio_q, stop_event, turn_complete, enter_q, args.output_device)
                    stop_event.set()
                    player.cancel()
                    try:
                        await player
                    except asyncio.CancelledError:
                        pass
                else:
                    await wake_word_loop(
                        ws,
                        audio_q,
                        stop_event,
                        args.output_device,
                        args.wake_word,
                        args.wake_threshold,
                        args.max_record_seconds,
                    )
                    await player
    except OSError as exc:
        print(f"Could not connect to server at {args.server}.")
        print("Make sure server.py is running on the Mac, both machines are on the same LAN, and macOS firewall allows the port.")
        print(f"Connection detail: {exc}")
        return 3
    except websockets.ConnectionClosed:
        print("Connection to the server was closed (it may have restarted). Re-run the client once the server is back up.")
        return 3
    except websockets.InvalidURI:
        print(f"Invalid WebSocket URL: {args.server}")
        return 3
    except websockets.InvalidHandshake as exc:
        print(f"Connected to {args.server}, but the server did not speak WebSocket correctly: {exc}")
        return 3
    except KeyboardInterrupt:
        print("Exiting.")
        return 0
    return 0


def main() -> int:
    try:
        return asyncio.run(main_async())
    except KeyboardInterrupt:
        print("Exiting.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

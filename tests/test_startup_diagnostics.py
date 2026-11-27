"""Tests for the startup readiness checks and Hermes failure messages."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from mia_core.integration import hermes_error_text  # noqa: E402

SCRIPT = (ROOT / "start-mia.sh").read_text(encoding="utf-8")


def _shell_helpers() -> str:
    """The logging + utility functions of start-mia.sh, without side effects."""
    head = SCRIPT[SCRIPT.index("say()  {"):SCRIPT.index('PY="${PYTHON:-python3}"')]
    tail = SCRIPT[SCRIPT.index("# ------------------------------------------------------------------ utilities"):
                  SCRIPT.index("start_background()")]
    return head + "\n" + tail


def _handler(status: int):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            body = b'{"status":"loading model"}' if status == 503 else b'{"status":"ok"}'
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    return Handler


class ShellHealthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.server = None

    def tearDown(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()

    def serve(self, status: int) -> str:
        self.server = HTTPServer(("127.0.0.1", 0), _handler(status))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{self.server.server_address[1]}/health"

    def bash(self, body: str) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", "-c", _shell_helpers() + "\n" + body],
                              capture_output=True, text=True, timeout=30)

    def test_loading_model_is_open_but_not_ready(self):
        url = self.serve(503)
        out = self.bash(
            f'http_ready "{url}" && echo ready || echo not-ready\n'
            f'port_open "{url}" && echo open || echo closed\n')
        self.assertEqual(out.stdout.split(), ["not-ready", "open"], out.stderr)

    def test_healthy_endpoint_is_ready(self):
        url = self.serve(200)
        out = self.bash(f'http_ready "{url}" && echo ready || echo not-ready\n')
        self.assertEqual(out.stdout.strip(), "ready", out.stderr)

    def test_wait_health_stops_when_the_process_died(self):
        url = self.serve(503)
        dead = subprocess.Popen(["true"])
        dead.wait()
        pidfile = Path(self.tmp.name) / "chat.pid"
        pidfile.write_text(str(dead.pid), encoding="utf-8")
        out = self.bash(f'wait_health "{url}" 60 "{pidfile}"; echo "rc=$?"\n')
        self.assertIn("rc=2", out.stdout, out.stderr)

    def test_failed_start_reports_log_and_common_cause(self):
        log = Path(self.tmp.name) / "chat-model.out"
        log.write_text("ggml_cuda_host_malloc: failed to allocate 5.40 GiB\n"
                       "CUDA error: out of memory\n", encoding="utf-8")
        out = self.bash(f'report_failed "chat model" "{log}" 2 120\n'
                        f'echo "degraded=${{DEGRADED[*]}}"\n')
        self.assertIn("exited during startup", out.stdout)
        self.assertIn("CUDA error: out of memory", out.stdout)
        self.assertIn("not enough VRAM", out.stdout)
        self.assertIn("degraded=chat model", out.stdout)

    def test_hints_ignore_an_older_crash(self):
        log = Path(self.tmp.name) / "chat-model.out"
        log.write_text("CUDA error: out of memory\n"
                       "\n==> chat model started 2026-01-01 10:00:00\n"
                       "llama_model_load: loaded\n"
                       "listening on 127.0.0.1:18084\n", encoding="utf-8")
        out = self.bash(f'hint_from_log "{log}"; echo done\n')
        self.assertNotIn("VRAM", out.stdout)
        self.assertIn("done", out.stdout)


class HermesErrorTextTests(unittest.TestCase):
    def test_empty_provider_and_model_is_explained(self):
        payload = {
            "completed": False,
            "messages": [],
            "runtime": {"provider": "", "model": "",
                        "requested": {"provider": "", "model": ""}},
        }
        text = hermes_error_text(payload, '{"session_id": "abc"}')
        self.assertIn("ni izbral modela", text)
        self.assertNotIn("session_id", text)

    def test_explicit_error_message_wins(self):
        payload = {"error": {"message": "context length exceeded"}}
        self.assertEqual(hermes_error_text(payload), "context length exceeded")

    def test_unknown_failure_falls_back_to_payload(self):
        payload = {"runtime": {"provider": "local", "model": "x"}}
        self.assertEqual(hermes_error_text(payload, "boom"), "boom")


if __name__ == "__main__":
    unittest.main()

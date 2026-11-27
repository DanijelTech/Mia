"""The single-model migration must edit server.yaml without breaking it."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server" / "scripts"))

import use_single_model as usm  # noqa: E402

CONFIG = """\
llm:
  provider: hermes
  model: local
  router:
    enabled: true
  chat:
    enabled: true
    base_url: http://127.0.0.1:18084/v1
    model: local-chat
    timeout: 30
    system_prompt: >
      Govoriš kot Mia.
      Brez markdowna.

hermes:
  base_url: http://127.0.0.1:8642

stack:
  llama:
    health: http://127.0.0.1:18083/health
    start_timeout: 420
    argv:
      - env
      - CUDA_VISIBLE_DEVICES=0
      - /home/user/llama.cpp/build/bin/llama-server
      - -m
      - /mnt/models/HauhauCS/Gemma4-12B/Gemma4-12B-Q4_K_M.gguf
      - --alias
      - HauhauCS/Gemma4-12B-QAT-Uncensored-HauhauCS-Balanced
      - --port
      - "18083"
  chat:
    health: http://127.0.0.1:18084/health
    start_timeout: 120
    argv:
      - env
      - CUDA_VISIBLE_DEVICES=1
      - /home/user/llama.cpp/build/bin/llama-server
      - -m
      - /mnt/models/Qwen2.5-7B-Instruct-Q5_K_M.gguf
      - --port
      - "18084"
  hermes:
    health: http://127.0.0.1:8642/health
"""


class SingleModelRewriteTests(unittest.TestCase):
    def setUp(self):
        self.new, self.notes = usm.rewrite_config(CONFIG, "18083")
        self.lines = self.new.splitlines()

    def _line(self, needle: str) -> str:
        for line in self.lines:
            if needle in line:
                return line
        self.fail(f"{needle!r} not found")

    def test_chat_brain_points_at_the_main_server(self):
        self.assertIn("base_url: http://127.0.0.1:18083/v1", self.new)
        self.assertNotIn("18084/v1", self.new)
        self.assertIn("    model: HauhauCS/Gemma4-12B-QAT-Uncensored-HauhauCS-Balanced\n",
                      self.new)

    def test_stack_chat_is_commented_out(self):
        self.assertIn(usm.MARKER, self.new)
        self.assertIn("    # health: http://127.0.0.1:18084/health", self.new)
        self.assertIn("      # - /mnt/models/"
                      "Qwen2.5-7B-Instruct-Q5_K_M.gguf", self.new)
        stack = self.lines.index("stack:")
        active = [line for line in self.lines[stack:]
                  if line.strip() == "chat:" and not line.lstrip().startswith("#")]
        self.assertEqual(active, [], "an active stack.chat block is still there")

    def test_result_is_valid_yaml(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed")
        cfg = yaml.safe_load(self.new)
        self.assertEqual(cfg["llm"]["chat"]["base_url"],
                         "http://127.0.0.1:18083/v1")
        self.assertTrue(cfg["llm"]["chat"]["enabled"])
        self.assertNotIn("chat", cfg["stack"])
        self.assertIn("llama", cfg["stack"])

    def test_main_model_is_untouched(self):
        self.assertIn(
            "      - /mnt/models/HauhauCS/Gemma4-12B/"
            "Gemma4-12B-Q4_K_M.gguf", self.new)
        self.assertIn("  llama:", self.new)
        self.assertIn("    health: http://127.0.0.1:18083/health", self.new)

    def test_rewrite_is_idempotent(self):
        again, notes = usm.rewrite_config(self.new, "18083")
        self.assertEqual(again, self.new)
        self.assertFalse([n for n in notes if "stack.chat" in n])

    def test_model_label_falls_back_to_local_without_an_alias(self):
        plain = CONFIG.replace(
            "      - --alias\n"
            "      - HauhauCS/Gemma4-12B-QAT-Uncensored-HauhauCS-Balanced\n", "")
        self.assertIsNone(usm.llama_alias(plain))
        new, _ = usm.rewrite_config(plain, "18083")
        self.assertIn("    model: local\n", new)

    def test_port_comes_from_the_llama_health_url(self):
        self.assertEqual(usm.llama_port(CONFIG), "18083")
        custom = CONFIG.replace("18083/health", "19090/health")
        new, _ = usm.rewrite_config(custom)
        self.assertIn("base_url: http://127.0.0.1:18083/v1", new)
        new, _ = usm.rewrite_config(custom, "19090")
        self.assertIn("base_url: http://127.0.0.1:19090/v1", new)


class SingleModelCliTests(unittest.TestCase):
    def test_dry_run_does_not_touch_the_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "server.yaml"
            path.write_text(CONFIG, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(ROOT / "server" / "scripts" / "use_single_model.py"),
                 "--config", str(path), "--dry-run"],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("base_url: http://127.0.0.1:18083/v1", result.stdout)
            self.assertEqual(path.read_text(encoding="utf-8"), CONFIG)

    def test_real_run_writes_a_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "server.yaml"
            path.write_text(CONFIG, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(ROOT / "server" / "scripts" / "use_single_model.py"),
                 "--config", str(path)],
                capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            backups = list(Path(tmp).glob("server.yaml.bak-*"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(encoding="utf-8"), CONFIG)
            self.assertIn("18083/v1", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

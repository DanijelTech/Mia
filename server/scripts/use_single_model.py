"""Switch Mia to a single model: the main llama-server (Gemma) answers chat too.

A separate small chat model (a second GGUF such as Qwen) is optional and easy to
configure wrongly. This script points the fast chat brain at the *same*
llama-server the agent uses and comments out the `stack.chat` block, so nothing
tries to load a second model.

    python3 server/scripts/use_single_model.py --dry-run
    python3 server/scripts/use_single_model.py

The config keeps its comments: the edit is line based and a timestamped backup
is written next to server.yaml before anything changes.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
import time
from pathlib import Path

DEFAULT_PORT = "18083"
MARKER = ("# removed by use_single_model.py — the main model serves chat and "
          "agent; restore from the backup to undo")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _top_index(lines: list[str], key: str) -> int | None:
    for i, line in enumerate(lines):
        if line.startswith(key + ":"):
            return i
    return None


def _child_index(lines: list[str], parent: int, key: str) -> int | None:
    base = _indent(lines[parent])
    i = parent + 1
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        if _indent(line) <= base:
            return None
        if line.strip().split(":", 1)[0].strip() == key:
            return i
        i += 1
    return None


def _block_end(lines: list[str], start: int) -> int:
    base = _indent(lines[start])
    i = start + 1
    while i < len(lines):
        line = lines[i]
        if line.strip() and not line.lstrip().startswith("#") and _indent(line) <= base:
            break
        i += 1
    return i


def _set_value(lines: list[str], index: int, value: str) -> None:
    key = lines[index].split(":", 1)[0].strip()
    lines[index] = " " * _indent(lines[index]) + f"{key}: {value}"


def llama_alias(text: str) -> str | None:
    """Read the model alias from stack.llama.argv (--alias VALUE)."""
    lines = text.splitlines()
    stack = _top_index(lines, "stack")
    if stack is None:
        return None
    llama = _child_index(lines, stack, "llama")
    if llama is None:
        return None
    argv = _child_index(lines, llama, "argv")
    if argv is None:
        return None
    items: list[str] = []
    for i in range(argv, _block_end(lines, argv)):
        item = lines[i].strip()
        if item.startswith("- "):
            items.append(item[2:].strip().strip('"').strip("'"))
    for i, item in enumerate(items):
        if item in ("--alias", "-a") and i + 1 < len(items):
            return items[i + 1]
        if item.startswith("--alias="):
            return item.split("=", 1)[1]
    return None


def llama_port(text: str) -> str | None:
    """Read the port from stack.llama.health (the agent's llama-server)."""
    lines = text.splitlines()
    stack = _top_index(lines, "stack")
    if stack is None:
        return None
    llama = _child_index(lines, stack, "llama")
    if llama is None:
        return None
    health = _child_index(lines, llama, "health")
    if health is None:
        return None
    match = re.search(r":(\d+)", lines[health])
    return match.group(1) if match else None


def rewrite_config(text: str, port: str = DEFAULT_PORT,
                   model: str | None = None) -> tuple[str, list[str]]:
    """Return (new_text, notes). Pure: no file access."""
    lines = text.splitlines()
    notes: list[str] = []
    model = model or llama_alias(text) or "local"

    llm = _top_index(lines, "llm")
    chat = _child_index(lines, llm, "chat") if llm is not None else None
    if chat is None:
        notes.append("llm.chat not found — add it by hand if you want the fast "
                     "chat path: router.enabled: true, chat.enabled: true, "
                     f"chat.base_url: http://127.0.0.1:{port}/v1, "
                     f"chat.model: {model}")
    else:
        for key, value in (("enabled", "true"),
                           ("base_url", f"http://127.0.0.1:{port}/v1"),
                           ("model", model)):
            index = _child_index(lines, chat, key)
            if index is None:
                insert_at = _block_end(lines, chat)
                lines.insert(insert_at, " " * (_indent(lines[chat]) + 2)
                             + f"{key}: {value}")
                chat = _child_index(lines, llm, "chat")  # indices shifted
                notes.append(f"llm.chat.{key}: {value} (added)")
            else:
                _set_value(lines, index, value)
                notes.append(f"llm.chat.{key}: {value}")

    stack = _top_index(lines, "stack")
    stack_chat = _child_index(lines, stack, "chat") if stack is not None else None
    if stack_chat is not None:
        end = _block_end(lines, stack_chat)
        for j in range(stack_chat, end):
            if lines[j].strip():
                lines[j] = " " * _indent(lines[j]) + "# " + lines[j].lstrip()
        lines.insert(stack_chat, " " * _indent(lines[stack_chat]) + MARKER)
        notes.append("stack.chat: commented out (no second model is started)")

    return "\n".join(lines) + ("\n" if text.endswith("\n") else ""), notes


def default_config() -> Path:
    home = os.environ.get("MIA_HOME")
    if home:
        candidate = Path(home).expanduser() / "server" / "config" / "server.yaml"
        if candidate.is_file():
            return candidate
    return Path(__file__).resolve().parents[1] / "config" / "server.yaml"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Use one model: point llm.chat at the main llama-server "
                    "and disable stack.chat.")
    parser.add_argument("--config", help="path to server.yaml")
    parser.add_argument("--port", help=f"llama-server port (default {DEFAULT_PORT})")
    parser.add_argument("--model", help="label for llm.chat.model "
                                       "(default: stack.llama --alias)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the result, change nothing")
    args = parser.parse_args(argv)

    path = Path(args.config).expanduser() if args.config else default_config()
    if not path.is_file():
        print(f"config not found: {path}", file=sys.stderr)
        return 1
    text = path.read_text(encoding="utf-8")
    port = args.port or llama_port(text) or DEFAULT_PORT
    new, notes = rewrite_config(text, port, args.model)

    for note in notes:
        print(f" - {note}")
    if new == text:
        print("nothing to change")
        return 0
    if args.dry_run:
        print("\n--- would write ---\n")
        print(new)
        return 0

    backup = path.with_name(path.name + time.strftime(".bak-%Y%m%d-%H%M%S"))
    shutil.copy2(path, backup)
    path.write_text(new, encoding="utf-8")
    print(f"backup: {backup}")
    print("restart: ./stop-mia.sh && ./start-mia.sh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

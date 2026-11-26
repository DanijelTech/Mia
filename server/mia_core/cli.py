"""`mia-learn` command line: the agent's and the user's window into memory."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from .config import load_config, repo_root, skills_root
from .knowledge import install_skills, search_skills, tree_payload, validate_tree
from .learning import LearningCore


def _ts(value: Any) -> str:
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(float(value)))
    except (TypeError, ValueError, OSError):
        return "—"


def _print(obj: Any, as_json: bool) -> None:
    if as_json:
        print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))
        return
    if isinstance(obj, str):
        print(obj)
    else:
        print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _episode_line(e: dict) -> str:
    outcome = e.get("outcome") or "?"
    mark = {"success": "✓", "failure": "✗", "partial": "~"}.get(outcome, "·")
    return (f"{mark} #{e.get('id')} {_ts(e.get('ts'))} [{e.get('source')}] "
            f"{(e.get('request') or '')[:90]}")


def _recipe_line(r: dict) -> str:
    return (f"#{r.get('id')} {r.get('title') or r.get('key')}  "
            f"(conf {float(r.get('confidence') or 0):.2f}, "
            f"✓{r.get('success_count', 0)} ✗{r.get('fail_count', 0)})")


def _habit_line(h: dict) -> str:
    detail = h.get("detail") or {}
    bits = [f"×{detail.get('count', h.get('evidence'))}",
            f"conf {float(h.get('confidence') or 0):.2f}"]
    if detail.get("routine"):
        bits.append(detail["routine"])
    if h.get("pinned"):
        bits.append("📌")
    return f"[{h.get('kind')}] {h.get('subject')} — " + ", ".join(bits)


def _mistake_line(m: dict) -> str:
    return (f"#{m.get('id')} ×{m.get('hits')} {m.get('symptom')} — "
            f"vzrok: {m.get('cause') or '?'}"
            + (f"; fix: {m.get('fix')}" if m.get("fix") else ""))


def _payload_from_args(args: argparse.Namespace) -> dict:
    meta: dict = {}
    if args.meta:
        try:
            meta.update(json.loads(args.meta))
        except ValueError:
            meta["note"] = args.meta
    steps = []
    for raw in args.step or []:
        try:
            steps.append(json.loads(raw))
        except ValueError:
            steps.append({"action": raw})
    for tool in args.tool or []:
        steps.append({"tool": tool})
    return {
        "session": args.session,
        "source": args.source,
        "intent": args.intent or "",
        "request": args.request,
        "response": args.response or "",
        "tools": args.tool or [],
        "steps": steps,
        "outcome": args.outcome,
        "error": args.error or "",
        "duration_s": args.duration,
        "tags": args.tag or [args.source],
        "meta": meta,
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mia-learn",
        description="Mia's durable learning: episodes, habits, recipes, mistakes, skills.")
    p.add_argument("--db", help="override learning database path")
    p.add_argument("--json", action="store_true", help="JSON output")
    sub = p.add_subparsers(dest="cmd")

    r = sub.add_parser("record", help="record one episode")
    r.add_argument("--request", required=True)
    r.add_argument("--response", default="")
    r.add_argument("--source", default="cli")
    r.add_argument("--intent", default="")
    r.add_argument("--outcome", default="success",
                   choices=["success", "failure", "partial", "unknown"])
    r.add_argument("--error", default="")
    r.add_argument("--tool", action="append")
    r.add_argument("--step", action="append")
    r.add_argument("--tag", action="append")
    r.add_argument("--meta", default="")
    r.add_argument("--session", default="cli")
    r.add_argument("--duration", type=float)
    r.add_argument("--no-learn", action="store_true")

    f = sub.add_parser("feedback", help="positive/negative feedback on an episode")
    f.add_argument("--episode", type=int)
    f.add_argument("--verdict", default="positive",
                   choices=["positive", "negative", "ok", "prav", "fail"])
    f.add_argument("--note", default="")
    f.add_argument("--conversation", default="mia-main")

    v = sub.add_parser("verify", help="confirm/reject one episode (verified learning)")
    v.add_argument("--episode", type=int, required=True)
    v.add_argument("--verdict", default="positive",
                   choices=["positive", "negative", "ok", "prav", "fail"])
    v.add_argument("--note", default="")

    rm = sub.add_parser("remember", help="force-save the last/selected episode as a recipe")
    rm.add_argument("--episode", type=int)
    rm.add_argument("--note", default="")
    rm.add_argument("--conversation", default="mia-main")

    b = sub.add_parser("brief", help="show the memory brief injected into a turn")
    b.add_argument("request", nargs="?", default="")

    sub.add_parser("mine", help="mine habits, ingest control audit, refresh skills")
    ia = sub.add_parser("ingest-audit", help="import mia-ctl audit JSONL")
    ia.add_argument("path", nargs="?")

    t = sub.add_parser("tree", help="show the skill tree")
    t.add_argument("--validate", action="store_true")
    t.add_argument("--search", default="")
    t.add_argument("--install", metavar="HERMES_HOME")
    t.add_argument("--root")

    s = sub.add_parser("search", help="search all memory")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=30)

    for name in ("stats", "status", "doctor"):
        sub.add_parser(name)
    sub.add_parser("sysinfo")

    h = sub.add_parser("habits", help="list/curate habits")
    h.add_argument("--limit", type=int, default=30)
    h.add_argument("--min-confidence", type=float, default=0.0)
    h.add_argument("--pin")
    h.add_argument("--unpin")
    h.add_argument("--delete")

    rec = sub.add_parser("recipes", help="list/show/add/delete recipes")
    rec.add_argument("--limit", type=int, default=30)
    rec.add_argument("--show")
    rec.add_argument("--delete")
    rec.add_argument("--add", metavar="TITLE")
    rec.add_argument("--step", action="append")
    rec.add_argument("--note", default="")

    m = sub.add_parser("mistakes", help="list/add/delete anti-patterns")
    m.add_argument("--limit", type=int, default=30)
    m.add_argument("--add", metavar="SYMPTOM")
    m.add_argument("--cause", default="")
    m.add_argument("--fix", default="")
    m.add_argument("--severity", default="medium")
    m.add_argument("--delete")

    cap = sub.add_parser("capabilities", help="inspect/confirm the capability checklist")
    cap.add_argument("--refresh", action="store_true")
    cap.add_argument("--category")
    cap.add_argument("--status")
    cap.add_argument("--query", default="")
    cap.add_argument("--confirm", metavar="ID")
    cap.add_argument("--fail", metavar="ID")
    cap.add_argument("--notes", default="")

    fa = sub.add_parser("facts", help="list/set/get/delete facts")
    fa.add_argument("--list", action="store_true")
    fa.add_argument("--kind")
    fa.add_argument("--set", nargs=2, metavar=("KEY", "VALUE"))
    fa.add_argument("--get")
    fa.add_argument("--delete")

    ep = sub.add_parser("episodes", help="recent episodes")
    ep.add_argument("--limit", type=int, default=25)
    ep.add_argument("--source")
    ep.add_argument("--outcome")

    ev = sub.add_parser("events", help="recent learning events")
    ev.add_argument("--limit", type=int, default=50)

    ex = sub.add_parser("export", help="export all memory to JSON")
    ex.add_argument("file")
    im = sub.add_parser("import", help="import memory JSON")
    im.add_argument("file")
    im.add_argument("--replace", action="store_true")
    bk = sub.add_parser("backup", help="SQLite backup")
    bk.add_argument("file")
    sub.add_parser("prune", help="apply retention policy")
    return p


def _extract_globals(argv: list[str]) -> tuple[list[str], str | None, bool]:
    """Accept --json and --db before or after the subcommand."""
    out: list[str] = []
    db = None
    as_json = False
    i = 0
    while i < len(argv):
        item = argv[i]
        if item == "--json":
            as_json = True
            i += 1
        elif item == "--db" and i + 1 < len(argv):
            db = argv[i + 1]
            i += 2
        elif item.startswith("--db="):
            db = item.split("=", 1)[1]
            i += 1
        else:
            out.append(item)
            i += 1
    return out, db, as_json


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    clean, db_override, as_json = _extract_globals(raw)
    args = build_parser().parse_args(clean)
    args.json = as_json
    if db_override:
        args.db = db_override
    cfg = load_config()
    if args.db:
        cfg = dict(cfg)
        cfg["db_path"] = args.db
    core = LearningCore(cfg)
    cmd = args.cmd or "status"
    as_json = args.json

    try:
        if cmd == "record":
            payload = _payload_from_args(args)
            ep_id = core.record_episode(payload, learn=not args.no_learn)
            _print({"ok": ep_id is not None, "episode_id": ep_id}, as_json)
            return 0 if ep_id else 1
        if cmd == "feedback":
            if args.episode:
                result = core.feedback(args.episode, args.verdict, args.note)
            else:
                result = core.feedback_last(args.conversation, args.verdict, args.note)
            _print(result, as_json)
            return 0 if result.get("ok") else 1
        if cmd == "verify":
            result = core.feedback(args.episode, args.verdict, args.note)
            _print(result, as_json)
            return 0 if result.get("ok") else 1
        if cmd == "remember":
            if args.episode:
                result = core.remember(args.episode, args.note)
            else:
                result = core.remember_last(args.conversation, args.note)
            _print(result, as_json)
            return 0 if result.get("ok") else 1
        if cmd == "brief":
            preview = core.brief_preview(args.request)
            if as_json:
                _print(preview, True)
            else:
                print(preview.get("text") or "(prazen spomin)")
                print(f"\n— {preview.get('chars', 0)}/{preview.get('max_chars')} znakov —")
            return 0
        if cmd == "mine":
            _print(core.mine(), as_json)
            return 0
        if cmd == "ingest-audit":
            path = args.path or cfg.get("audit_path")
            from .config import expand_path
            count = core.store.ingest_audit(expand_path(path))
            _print({"ok": True, "records": count, "path": str(path)}, as_json)
            return 0
        if cmd == "tree":
            root = Path(args.root).expanduser() if args.root else skills_root(cfg)
            if args.install:
                _print(install_skills(root, args.install), as_json)
                return 0
            if args.validate:
                report = validate_tree(root)
                if as_json:
                    _print(report, True)
                else:
                    for issue in report["errors"]:
                        print(f"[ERROR] {issue['skill']}: {issue['message']}")
                    for issue in report["warnings"]:
                        print(f"[WARN]  {issue['skill']}: {issue['message']}")
                    print("OK" if report["ok"] else "FAILED")
                return 0 if report["ok"] else 1
            if args.search:
                _print(search_skills(root, args.search), as_json)
                return 0
            payload = tree_payload(root)
            if as_json:
                _print(payload, True)
            else:
                def walk(node: dict, depth: int = 0) -> None:
                    print("  " * depth + f"▸ {node['name']} — {node['description'][:85]}")
                    for child in node["children"]:
                        walk(child, depth + 1)
                for node in payload["tree"]:
                    walk(node)
                s = payload["summary"]
                print(f"\n{s['skills']} skills · {s['references']} references · "
                      f"{s['errors']} errors · {s['warnings']} warnings")
            return 0
        if cmd == "search":
            results = core.search(args.query, args.limit)
            if as_json:
                _print(results, True)
            else:
                for item in results:
                    print(f"{item['kind']:<8} #{item['ref']:<6} {item['text'][:110]}")
            return 0
        if cmd == "stats":
            _print(core.status()["db"], as_json)
            return 0
        if cmd == "status":
            _print(core.status(), as_json)
            return 0
        if cmd == "sysinfo":
            _print(core.system_facts(), as_json)
            return 0
        if cmd == "doctor":
            report = {
                "status": core.status(),
                "tree": validate_tree(skills_root(cfg)),
                "config": {k: cfg.get(k) for k in ("enabled", "db_path", "audit_path",
                                                    "skills_root", "auto_record")},
                "capabilities": core.capability_summary(),
                "tools": {name: bool(shutil.which(name)) for name in (
                    "xdotool", "wmctrl", "grim", "gnome-screenshot", "scrot",
                    "wl-copy", "xclip", "notify-send", "playerctl", "pactl",
                    "wpctl", "brightnessctl", "systemctl", "loginctl",
                    "osascript", "screencapture", "yt-dlp")},
                "paths": {
                    "repo": str(repo_root()),
                    "skills": str(skills_root(cfg)),
                    "db": str(core.store.path),
                    "audit": str(cfg.get("audit_path")),
                    "audit_exists": Path(str(cfg.get("audit_path"))).expanduser().exists(),
                },
            }
            _print(report, as_json)
            return 0 if report["tree"]["ok"] else 1
        if cmd == "habits":
            if args.pin:
                _print({"ok": core.pin_habit(args.pin, True)}, as_json)
                return 0
            if args.unpin:
                _print({"ok": core.pin_habit(args.unpin, False)}, as_json)
                return 0
            if args.delete:
                _print({"ok": core.delete("habit", args.delete)}, as_json)
                return 0
            habits = core.habits(args.limit, args.min_confidence)
            if as_json:
                _print(habits, True)
            else:
                for habit in habits:
                    print(_habit_line(habit))
                if not habits:
                    print("(še ni dovolj dokazov — zaženi `mia-learn mine`)")
            return 0
        if cmd == "recipes":
            if args.delete:
                _print({"ok": core.delete("recipe", args.delete)}, as_json)
                return 0
            if args.add:
                rec_id = core.add_recipe(args.add, args.step or [], notes=args.note)
                _print({"ok": bool(rec_id), "id": rec_id}, as_json)
                return 0
            if args.show:
                recipe = (core.store.get_recipe(int(args.show))
                          if str(args.show).isdigit()
                          else core.store.get_recipe_by_key(args.show))
                _print(recipe or {"error": "not found"}, as_json)
                return 0
            recipes = core.recipes(args.limit)
            if as_json:
                _print(recipes, True)
            else:
                for recipe in recipes:
                    print(_recipe_line(recipe))
                if not recipes:
                    print("(še ni receptov — uspešna opravila se dodajo sama)")
            return 0
        if cmd == "mistakes":
            if args.delete:
                _print({"ok": core.delete("mistake", args.delete)}, as_json)
                return 0
            if args.add:
                ap_id = core.add_mistake(args.add, args.cause, args.fix,
                                         severity=args.severity)
                _print({"ok": bool(ap_id), "id": ap_id}, as_json)
                return 0
            mistakes = core.mistakes(args.limit)
            if as_json:
                _print(mistakes, True)
            else:
                for mistake in mistakes:
                    print(_mistake_line(mistake))
                if not mistakes:
                    print("(ni zabeleženih napak)")
            return 0
        if cmd == "capabilities":
            if args.confirm or args.fail:
                cap_id = args.confirm or args.fail
                status = "confirmed" if args.confirm else "failed"
                ok = core.confirm_capability(cap_id, status, args.notes)
                _print({"ok": bool(ok), "id": cap_id, "status": status}, as_json)
                return 0 if ok else 1
            rows = core.capabilities(refresh=args.refresh, query=args.query,
                                     category=args.category, status=args.status)
            if as_json:
                _print({"capabilities": rows, "summary": core.capability_summary()}, True)
            else:
                current = ""
                for row in rows:
                    if row["category"] != current:
                        current = row["category"]
                        print(f"\n[{current.upper()}]")
                    mark = {"confirmed": "✓", "learned": "●", "detected": "○",
                            "failed": "✗", "unsupported": "—", "empty": "·"}.get(
                        row["status"], "·")
                    print(f" {mark} {row['id']:<30} {row['label']:<38} {row['how']}")
                summary = core.capability_summary()
                print(f"\n{summary.get('confirmed', 0)}/{summary.get('total', 0)} "
                      f"potrjenih ({summary.get('percent', 0)}%)")
            return 0
        if cmd == "facts":
            if args.set:
                key, value = args.set
                core.set_fact(key, value)
                _print({"ok": True, "key": key}, as_json)
                return 0
            if args.get:
                _print(core.store.get_fact(args.get) or {"error": "not found"}, as_json)
                return 0
            if args.delete:
                _print({"ok": core.delete("fact", args.delete)}, as_json)
                return 0
            facts = core.facts(kind=args.kind)
            if as_json:
                _print(facts, True)
            else:
                for fact in facts:
                    print(f"[{fact.get('kind')}] {fact['key']} = {fact.get('value')}")
            return 0
        if cmd == "episodes":
            episodes = core.episodes(args.limit, source=args.source, outcome=args.outcome)
            if as_json:
                _print(episodes, True)
            else:
                for episode in episodes:
                    print(_episode_line(episode))
            return 0
        if cmd == "events":
            events = core.events(args.limit)
            if as_json:
                _print(events, True)
            else:
                for event in events:
                    print(f"{_ts(event['ts'])} [{event['kind']}] {event.get('subject') or ''}")
            return 0
        if cmd == "export":
            _print({"ok": True, "file": str(core.export(args.file))}, as_json)
            return 0
        if cmd == "import":
            _print(core.import_(args.file, merge=not args.replace), as_json)
            return 0
        if cmd == "backup":
            _print({"ok": True, "file": str(core.backup(args.file))}, as_json)
            return 0
        if cmd == "prune":
            _print(core.prune(), as_json)
            return 0
    except BrokenPipeError:
        return 0
    except Exception as exc:
        print(f"mia-learn: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        core.close()
    return 2


if __name__ == "__main__":
    sys.exit(main())

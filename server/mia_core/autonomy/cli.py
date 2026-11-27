"""`mia-auto` — the operator's window into the autonomy core.

Commands are intentionally small and scriptable (`--json` everywhere). The same
AutonomyService powers the voice server, so anything done here is visible to
Mia and vice versa.
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from typing import Any

from ..config import load_config
from .intents import route
from .planner import build_template, find_ctl
from .profile import get_profile
from .scheduler import normalize_trigger, plan_for_reminder, trigger_summary
from .service import AutonomyService


def _json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def _service(args) -> AutonomyService:
    cfg = load_config()
    if getattr(args, "dry_run", False):
        cfg.setdefault("autonomy", {})["dry_run"] = True
    return AutonomyService(cfg=cfg, dry_run=bool(getattr(args, "dry_run", False)),
                           logger=lambda msg: print(msg, file=sys.stderr, flush=True))


def _print_profile(profile) -> None:
    data = profile.data
    print(profile.summary())
    print()
    print("SISTEM")
    osinfo = data.get("os") or {}
    print(f"  {osinfo.get('distro_name')} · jedro {osinfo.get('kernel')} · "
          f"{osinfo.get('machine')}")
    print(f"  init {data.get('init')} · paketi {(data.get('package_manager') or {}).get('name') or '—'}"
          f" · virtualizacija {data.get('virtualization') or 'brez'}")
    print(f"  namizje {(data.get('desktop') or {}).get('kind')} · seja "
          f"{(data.get('desktop') or {}).get('session')}")
    print()
    print("PRIPRAVLJENOST")
    for row in profile.readiness():
        mark = {"ready": "✓", "degraded": "~", "missing": "✗"}.get(row["status"], "?")
        backend = row.get("backend") or "—"
        print(f"  {mark} {row['label']:<26} {backend}")
        if row["status"] != "ready" and row.get("packages"):
            print(f"      namesti: {' '.join(row['packages'])}")
    print()
    score = data.get("score") or {}
    print(f"Ocena pripravljenosti: {score.get('percent', 0)}% "
          f"({score.get('ready', 0)}/{score.get('total', 0)} pripravljenih)")
    missing = profile.adaptation()
    if missing:
        print("\nPRILAGODITEV")
        for item in missing:
            state = "mogoče" if item.get("installable") else "ročno"
            print(f"  · {item['label']}: {item['hint']} ({state}: "
                  f"{' '.join(item.get('packages') or [])})")


def _print_health(report: dict) -> None:
    mark = {"ok": "✓", "warn": "!", "critical": "✗"}.get(report.get("level"), "?")
    print(f"{mark} {report.get('summary')}")
    for item in report.get("checks") or []:
        icon = {"ok": "✓", "info": "·", "warn": "!", "critical": "✗"}.get(
            item.get("level"), "·")
        print(f"  {icon} {item.get('title'):<22} {item.get('message')}")


def _print_jobs(rows: list[dict]) -> None:
    if not rows:
        print("(ni opravil)")
        return
    for job in rows:
        state = "vklopljeno" if job.get("enabled") else "izklopljeno"
        print(f"#{job['id']:<3} [{job.get('kind')}] {job.get('name')} · {state} · "
              f"{trigger_summary(job.get('trigger') or {})} · "
              f"zadnje: {job.get('last_status') or '—'}")


def _print_tasks(rows: list[dict]) -> None:
    if not rows:
        print("(ni nalog)")
        return
    for task in rows:
        print(f"#{task['id']:<3} {task.get('status'):<12} {task.get('name')} · "
              f"{time.strftime('%d.%m. %H:%M', time.localtime(task.get('created') or 0))}")


def _build_trigger(args) -> dict:
    if getattr(args, "trigger", None):
        return normalize_trigger(json.loads(args.trigger))
    if getattr(args, "every", None):
        return normalize_trigger({"kind": "every", "seconds": int(args.every)})
    if getattr(args, "daily", None):
        return normalize_trigger({"kind": "daily", "time": args.daily})
    if getattr(args, "at", None):
        return normalize_trigger({"kind": "at", "ts": float(args.at)})
    if getattr(args, "remind", None):
        return normalize_trigger({"kind": "at", "ts": time.time() + int(args.remind)})
    return normalize_trigger({"kind": "every", "seconds": 3600})


def _build_plan(args) -> dict:
    if getattr(args, "plan", None):
        return json.loads(args.plan)
    if getattr(args, "template", None):
        return build_template(args.template)
    text = getattr(args, "notify", None) or getattr(args, "text", None) or "Opomnik"
    return plan_for_reminder(text)


def cmd_profile(args) -> int:
    profile = get_profile(refresh=bool(args.refresh))
    if args.json:
        _json(profile.data)
    else:
        _print_profile(profile)
    return 0


def cmd_adapt(args) -> int:
    service = _service(args)
    result = service.adaptation(apply=bool(args.apply))
    if args.json:
        _json(result)
    else:
        _print_profile(service.profile())
        if args.apply:
            print()
            print("Prilagoditev: " + ("uspešna" if result.get("ok") else
                                        f"ni uspela ({result.get('error')})"))
    return 0 if result.get("ok", True) else 5


def cmd_health(args) -> int:
    service = _service(args)
    report = service.health(force=True)
    if args.remediate:
        result = service.remediate(force=True)
        if args.json:
            _json({**report, "remediation": result})
        else:
            _print_health(report)
            print("\nUKREPI")
            for action in result.get("actions") or []:
                print(f"  · {action.get('check')}: {action.get('action')} "
                      f"{'ok' if action.get('ok') else ''}")
    else:
        if args.json:
            _json(report)
        else:
            _print_health(report)
    return 0 if report.get("level") != "critical" else 2


def cmd_status(args) -> int:
    service = _service(args)
    status = service.status()
    if args.json:
        _json(status)
        return 0
    print(status["profile"]["summary"])
    health = status.get("health") or {}
    print(f"Zdravje: {health.get('level') or '—'} · ocena {health.get('score') or '—'}")
    scheduler = status.get("scheduler") or {}
    print(f"Opravila: {scheduler.get('enabled', 0)} aktivnih od {scheduler.get('total', 0)} "
          f"({scheduler.get('rules', 0)} pravil)")
    _print_jobs((scheduler.get("jobs") or [])[:10])
    print("\nNaloge:")
    _print_tasks(status.get("tasks") or [])
    alerts = status.get("alerts") or []
    if alerts:
        print("\nOpozorila:")
        for alert in alerts[:5]:
            print(f"  ! {alert.get('message')}")
    return 0


def cmd_plan(args) -> int:
    if args.list:
        from .planner import TEMPLATES
        for name in sorted(TEMPLATES):
            print(name)
        return 0
    plan = build_template(args.template)
    if args.run:
        service = _service(args)
        if plan.get("destructive") and not args.yes:
            print("Načrt je nevaren; dodaj --yes za izvedbo.", file=sys.stderr)
            return 4
        plan["confirmed"] = True
        result = service.planner.execute(plan, name=plan.get("name"),
                                         source="cli")
        if args.json:
            _json(result)
        else:
            print(f"Naloga #{result.get('task_id')}: {result.get('status')}")
            for step in result.get("steps") or []:
                print(f"  {step['idx']}. {step.get('label')} — {step['status']}")
        return 0 if result.get("ok") else 5
    if args.json:
        _json(plan)
    else:
        print(f"{plan['name']}: {plan.get('description') or ''}")
        for index, step in enumerate(plan["steps"], 1):
            print(f"  {index}. [{step['kind']}] {step.get('label')}")
    return 0


def cmd_do(args) -> int:
    service = _service(args)
    result = service.handle(args.text, conversation=args.conversation or "cli",
                            source="cli")
    if result is None:
        if args.json:
            _json({"ok": False, "text": "", "intent": None,
                   "note": "no matching system intent"})
        else:
            print("(ni sistemski ukaz — to bi šlo do agenta)")
        return 0
    if args.json:
        _json(result)
    else:
        print(result.get("text") or "")
        for tool in result.get("tools") or []:
            print(f"  · {tool.get('name')}: {tool.get('preview')}")
    return 0 if result.get("ok") else 5


def cmd_jobs(args) -> int:
    service = _service(args)
    if args.action == "list":
        rows = service.store.list_jobs(kind=args.kind)
        if args.json:
            _json(rows)
        else:
            _print_jobs(rows)
        return 0
    if args.action == "show":
        job = service.store.get_job(args.job_id)
        if not job:
            print("opravila ni", file=sys.stderr)
            return 3
        runs = service.store.list_job_runs(args.job_id)
        if args.json:
            _json({"job": job, "runs": runs})
        else:
            print(f"#{job['id']} {job['name']} · {trigger_summary(job['trigger'])}")
            print(f"  stanje: {job.get('last_status')} · {job.get('run_count')} zagonov")
            print(f"  načrt: {len((job.get('plan') or {}).get('steps') or [])} korakov")
            for run in runs[:10]:
                print(f"  · {time.strftime('%d.%m. %H:%M', time.localtime(run['started']))}"
                      f" {run.get('status')}")
        return 0
    if args.action == "remove":
        ok = service.scheduler.remove_job(args.job_id)
        print("odstranjeno" if ok else "ni najdeno")
        return 0 if ok else 3
    if args.action == "enable" or args.action == "disable":
        ok = service.store.update_job(args.job_id,
                                      enabled=args.action == "enable")
        print("spremenjeno" if ok else "ni najdeno")
        return 0 if ok else 3
    if args.action == "add":
        trigger = _build_trigger(args)
        plan = _build_plan(args)
        conditions = [json.loads(c) for c in (args.condition or [])]
        job_id = service.scheduler.add_job(
            args.name, trigger, plan, conditions=conditions,
            kind=args.kind or "job", max_runs=args.max_runs or 0,
            source="cli")
        job = service.store.get_job(job_id)
        if args.json:
            _json(job)
        else:
            print(f"opravilo #{job_id}: {trigger_summary(trigger)}")
        return 0
    print("neznana akcija", file=sys.stderr)
    return 2


def cmd_tasks(args) -> int:
    service = _service(args)
    if args.action == "list":
        rows = service.store.list_tasks(limit=args.limit)
        if args.json:
            _json(rows)
        else:
            _print_tasks(rows)
        return 0
    if args.action == "show":
        task = service.store.get_task(args.task_id)
        if not task:
            print("naloge ni", file=sys.stderr)
            return 3
        steps = service.store.list_task_steps(args.task_id)
        if args.json:
            _json({"task": task, "steps": steps})
        else:
            print(f"#{task['id']} {task['name']} · {task['status']} · {task.get('error') or ''}")
            for step in steps:
                print(f"  {step['idx']}. [{step['kind']}] {step['label']} — "
                      f"{step['status']} {step.get('error') or ''}")
        return 0
    if args.action == "resume":
        result = service.planner.resume(args.task_id)
        if args.json:
            _json(result)
        else:
            print(f"naloga #{args.task_id}: {result.get('status')}")
        return 0 if result.get("ok") else 5
    if args.action == "cancel":
        if args.task_id:
            service.store.update_task(args.task_id, status="cancelled",
                                      finished=time.time())
            print("preklicano")
        else:
            service.planner.cancel()
            print("signal za preklic poslan")
        return 0
    print("neznana akcija", file=sys.stderr)
    return 2


def cmd_tick(args) -> int:
    service = _service(args)
    result = service.tick(execute=not args.dry_run, health=not args.no_health)
    if args.json:
        _json(result)
    else:
        scheduler = result.get("scheduler") or {}
        print(f"pregledanih {scheduler.get('checked', 0)} · "
              f"sproženih {scheduler.get('count', 0)}")
        health = result.get("health") or {}
        if health:
            print(f"zdravje: {health.get('level')} · ocena {health.get('score')}")
    return 0


def cmd_daemon(args) -> int:
    service = _service(args)
    stop = {"flag": False}

    def _stop(signum, frame):
        stop["flag"] = True
        service.planner.cancel()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    print(f"mia-auto daemon: interval {args.interval}s", flush=True)
    service.refresh_profile(save=True)
    while not stop["flag"]:
        try:
            result = service.tick(execute=True, health=True)
            scheduler = result.get("scheduler") or {}
            if scheduler.get("count"):
                print(f"tick: fired {scheduler['count']}", flush=True)
        except Exception as exc:
            print(f"tick error: {type(exc).__name__}: {exc}", flush=True)
        for _ in range(max(1, int(args.interval))):
            if stop["flag"]:
                break
            time.sleep(1)
    print("mia-auto daemon stopped", flush=True)
    return 0


def cmd_route(args) -> int:
    intent = route(args.text)
    if args.json:
        _json(intent.to_dict() if intent else None)
    elif intent:
        print(f"{intent.kind}: {intent.name} {intent.args}")
    else:
        print("(no system intent)")
    return 0


def cmd_doctor(args) -> int:
    service = _service(args)
    profile = service.refresh_profile()
    report = service.health(force=True)
    ctl = find_ctl()
    data = {"ctl": ctl, "profile": profile.summary(),
            "score": profile.data.get("score"),
            "health": {"level": report.get("level"),
                       "score": report.get("score"),
                       "summary": report.get("summary")},
            "policy": service.planner.autonomy_policy(),
            "scheduler": service.scheduler.status()}
    if args.json:
        _json(data)
    else:
        print(f"mia-auto · {profile.summary()}")
        print(f"ctl: {ctl}")
        print(report.get("summary"))
        print(f"opravila: {data['scheduler']['total']} · "
              f"pravila: {data['scheduler']['rules']}")
        missing = [row for row in profile.readiness() if row["status"] != "ready"]
        if missing:
            print("manjka:")
            for row in missing[:8]:
                print(f"  · {row['label']}: {row['hint']}")
    return 0


# ---------------------------------------------------------------- argparse
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mia-auto",
        description="Mia autonomy: adaptive profile, plans, jobs, rules and health.")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--dry-run", action="store_true", help="simulate actions")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("profile", help="detect this machine and its backends")
    p.add_argument("--refresh", action="store_true")
    p.set_defaults(func=cmd_profile)

    p = sub.add_parser("adapt", help="show or apply the adaptation plan")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(func=cmd_adapt)

    p = sub.add_parser("health", help="health checks and safe remediation")
    p.add_argument("--remediate", action="store_true")
    p.set_defaults(func=cmd_health)

    p = sub.add_parser("status", help="one-page autonomy status")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("doctor", help="profile + health + ctl + policy")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("route", help="show the parsed intent for a phrase")
    p.add_argument("text")
    p.set_defaults(func=cmd_route)

    p = sub.add_parser("plan", help="list or run built-in plans")
    p.add_argument("template", nargs="?", default="")
    p.add_argument("--list", action="store_true")
    p.add_argument("--run", action="store_true")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("do", help="execute one natural-language command")
    p.add_argument("text")
    p.add_argument("--conversation", default="cli")
    p.set_defaults(func=cmd_do)

    p = sub.add_parser("jobs", help="scheduled jobs")
    jsub = p.add_subparsers(dest="action", required=True)
    jl = jsub.add_parser("list")
    jl.add_argument("--kind", choices=["job", "rule"])
    js = jsub.add_parser("show")
    js.add_argument("job_id", type=int)
    jr = jsub.add_parser("remove")
    jr.add_argument("job_id", type=int)
    for name in ("enable", "disable"):
        je = jsub.add_parser(name)
        je.add_argument("job_id", type=int)
    ja = jsub.add_parser("add")
    ja.add_argument("name")
    ja.add_argument("--kind", choices=["job", "rule"], default="job")
    ja.add_argument("--trigger", help="JSON trigger")
    ja.add_argument("--every", type=int, help="seconds")
    ja.add_argument("--daily", help="HH:MM")
    ja.add_argument("--at", type=float, help="epoch")
    ja.add_argument("--remind", type=int, help="seconds from now")
    ja.add_argument("--plan", help="JSON plan")
    ja.add_argument("--template", help="built-in plan name")
    ja.add_argument("--notify", help="notification text")
    ja.add_argument("--text", help="alias for --notify")
    ja.add_argument("--condition", action="append", help="JSON condition")
    ja.add_argument("--max-runs", type=int, default=0)
    p.set_defaults(func=cmd_jobs)

    p = sub.add_parser("tasks", help="task journal")
    tsub = p.add_subparsers(dest="action", required=True)
    tl = tsub.add_parser("list")
    tl.add_argument("--limit", type=int, default=20)
    ts = tsub.add_parser("show")
    ts.add_argument("task_id", type=int)
    tr = tsub.add_parser("resume")
    tr.add_argument("task_id", type=int)
    tc = tsub.add_parser("cancel")
    tc.add_argument("task_id", type=int, nargs="?", default=0)
    p.set_defaults(func=cmd_tasks)

    p = sub.add_parser("tick", help="run one scheduler/health cycle")
    p.add_argument("--no-health", action="store_true")
    p.set_defaults(func=cmd_tick)

    p = sub.add_parser("daemon", help="run scheduled jobs and health checks forever")
    p.add_argument("--interval", type=int, default=30)
    p.set_defaults(func=cmd_daemon)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    raw = list(sys.argv[1:] if argv is None else argv)
    # `--json`/`--dry-run` are global but users (and the docs) put them after
    # the subcommand: `mia-auto profile --json`. Accept both positions.
    want_json = "--json" in raw
    want_dry = "--dry-run" in raw
    clean = [a for a in raw if a not in ("--json", "--dry-run")]
    args = parser.parse_args(clean)
    args.json = bool(want_json or getattr(args, "json", False))
    args.dry_run = bool(want_dry or getattr(args, "dry_run", False))
    if not getattr(args, "cmd", None):
        parser.print_help()
        return 2
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        if getattr(args, "json", False):
            _json({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
        else:
            print(f"mia-auto: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 5

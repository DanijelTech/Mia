"""Plan execution with policy, verification, retries, rollback and journaling.

A plan is a list of small, declarative steps. `mia-ctl` does the actual work;
this engine owns the things that make autonomy trustworthy:

* **preflight** — destructive plans need explicit confirmation,
* **verification** — a step is only "done" when its post-condition holds,
* **retries** — transient failures are retried, denials are not,
* **rollback** — steps may carry an undo action,
* **journal** — every step is persisted, so a restart can resume or audit it.

Nothing here uses a shell. Ctl steps are argv lists.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .conditions import evaluate

STEP_KINDS = ("ctl", "python", "notify", "speak", "sleep", "probe",
              "wait_for", "plan")
CTL_COMMANDS = {
    "windows", "apps", "open", "type", "key", "click", "move", "scroll",
    "screenshot", "clipboard", "notify", "media", "volume", "brightness",
    "power", "process", "service", "files", "net", "displays", "resources",
    "audio", "sysinfo", "pkg", "sys", "audit", "policy", "doctor",
}
DESTRUCTIVE_TOKENS = {
    ("power", "reboot"), ("power", "shutdown"), ("power", "suspend"),
    ("process", "kill"), ("service", "stop"), ("service", "restart"),
    ("files", "delete"), ("files", "trash"), ("files", "move"),
    ("pkg", "install"), ("pkg", "remove"), ("pkg", "upgrade"),
    ("pkg", "autoremove"),
}
MAX_STEPS = 60


class PlannerError(Exception):
    pass


class PreflightError(PlannerError):
    pass


class NeedsConfirmation(PreflightError):
    pass


class Cancelled(PlannerError):
    pass


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def find_ctl() -> str:
    env = os.environ.get("MIA_CTL")
    if env and Path(env).exists():
        return env
    found = shutil.which("mia-ctl")
    if found:
        return found
    candidate = repo_root() / "skills" / "mia-companion" / "bin" / "mia-ctl"
    if candidate.exists():
        return str(candidate)
    return "mia-ctl"


def ctl_argv(ctl: str) -> list[str]:
    path = Path(ctl)
    if path.exists():
        if os.access(str(path), os.X_OK):
            return [str(path)]
        return [sys.executable, str(path)]
    return [ctl]


# --------------------------------------------------------------------- steps
def step_ctl(action: list[str], label: str = "", *, yes: bool = False,
             expect: dict | None = None, retries: int = 0,
             timeout: float = 60, on_fail: str = "abort",
             undo: list[str] | None = None,
             require_verified: bool = False) -> dict:
    return {"kind": "ctl", "label": label or " ".join(action[:3]),
            "action": [str(x) for x in action], "yes": bool(yes),
            "expect": expect or {}, "retries": int(retries),
            "timeout": float(timeout), "on_fail": on_fail,
            "undo": [str(x) for x in (undo or [])],
            "require_verified": bool(require_verified)}


def step_python(action: str, label: str = "", *, args: dict | None = None,
                expect: dict | None = None, on_fail: str = "abort") -> dict:
    return {"kind": "python", "label": label or action, "action": action,
            "args": args or {}, "expect": expect or {}, "retries": 0,
            "timeout": 120, "on_fail": on_fail, "undo": [],
            "require_verified": False}


def step_notify(title: str, body: str = "", *, label: str = "",
                on_fail: str = "continue") -> dict:
    return {"kind": "notify", "label": label or f"obvestilo: {title}",
            "title": title, "body": body, "retries": 0, "timeout": 15,
            "on_fail": on_fail, "undo": [], "expect": {},
            "require_verified": False}


def step_speak(text: str, label: str = "",
               on_fail: str = "continue") -> dict:
    return {"kind": "speak", "label": label or f"izreci: {text[:40]}",
            "text": text, "retries": 0, "timeout": 10,
            "on_fail": on_fail, "undo": [], "expect": {},
            "require_verified": False}


def step_sleep(seconds: float, label: str = "") -> dict:
    return {"kind": "sleep", "label": label or f"počakaj {seconds:g}s",
            "seconds": float(seconds), "retries": 0, "timeout": seconds + 5,
            "on_fail": "abort", "undo": [], "expect": {},
            "require_verified": False}


def step_probe(condition: dict, label: str = "",
               on_fail: str = "abort") -> dict:
    return {"kind": "probe", "label": label or "preveri pogoj",
            "condition": condition, "retries": 0, "timeout": 10,
            "on_fail": on_fail, "undo": [], "expect": {},
            "require_verified": False}


def step_wait(condition: dict, *, timeout: float = 60, poll: float = 2,
              label: str = "", on_fail: str = "abort") -> dict:
    return {"kind": "wait_for", "label": label or "počakaj na pogoj",
            "condition": condition, "wait_timeout": float(timeout),
            "poll": max(0.2, float(poll)), "retries": 0,
            "timeout": float(timeout) + 5, "on_fail": on_fail,
            "undo": [], "expect": {}, "require_verified": False}


def make_plan(steps: list[dict], name: str = "načrt", *,
              description: str = "", destructive: bool = False,
              confirmed: bool = False, rollback: bool = True,
              origin: str = "") -> dict:
    return {"name": name, "description": description,
            "destructive": bool(destructive), "confirmed": bool(confirmed),
            "rollback": bool(rollback), "origin": origin,
            "created": time.time(), "steps": steps}


def is_destructive(step: dict) -> bool:
    if step.get("kind") != "ctl":
        return False
    action = step.get("action") or []
    if len(action) >= 2 and (action[0], action[1]) in DESTRUCTIVE_TOKENS:
        return True
    return step.get("yes", False)


def sanitize_plan(plan: dict) -> dict:
    """Accept agent-produced JSON but keep it inside the supported vocabulary."""
    if not isinstance(plan, dict):
        raise PreflightError("plan must be an object")
    raw_steps = plan.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise PreflightError("plan needs a non-empty steps list")
    if len(raw_steps) > MAX_STEPS:
        raise PreflightError(f"plan has more than {MAX_STEPS} steps")
    steps: list[dict] = []
    for idx, raw in enumerate(raw_steps):
        if not isinstance(raw, dict):
            raise PreflightError(f"step {idx} is not an object")
        kind = str(raw.get("kind") or "")
        if kind not in STEP_KINDS:
            raise PreflightError(f"step {idx}: unsupported kind {kind!r}")
        if kind == "ctl":
            action = raw.get("action")
            if isinstance(action, str):
                action = shlex.split(action)
            if not isinstance(action, list) or not action:
                raise PreflightError(f"step {idx}: ctl action must be a list")
            if str(action[0]) not in CTL_COMMANDS:
                raise PreflightError(f"step {idx}: ctl command {action[0]!r} is not allowed")
            steps.append(step_ctl(action, str(raw.get("label") or ""),
                                  yes=bool(raw.get("yes")),
                                  expect=raw.get("expect") or {},
                                  retries=int(raw.get("retries") or 0),
                                  timeout=float(raw.get("timeout") or 60),
                                  on_fail=str(raw.get("on_fail") or "abort"),
                                  undo=raw.get("undo") or [],
                                  require_verified=bool(raw.get("require_verified"))))
        elif kind == "python":
            built = step_python(str(raw.get("action") or ""),
                                str(raw.get("label") or ""),
                                args=raw.get("args") or {},
                                expect=raw.get("expect") or {},
                                on_fail=str(raw.get("on_fail") or "abort"))
            built["retries"] = int(raw.get("retries") or 0)
            steps.append(built)
        elif kind == "notify":
            steps.append(step_notify(str(raw.get("title") or "Mia"),
                                     str(raw.get("body") or ""),
                                     label=str(raw.get("label") or ""),
                                     on_fail=str(raw.get("on_fail") or "continue")))
        elif kind == "speak":
            steps.append(step_speak(str(raw.get("text") or ""),
                                    str(raw.get("label") or ""),
                                    str(raw.get("on_fail") or "continue")))
        elif kind == "sleep":
            steps.append(step_sleep(float(raw.get("seconds") or 0),
                                    str(raw.get("label") or "")))
        elif kind == "probe":
            steps.append(step_probe(raw.get("condition") or {},
                                    str(raw.get("label") or ""),
                                    str(raw.get("on_fail") or "abort")))
        elif kind == "wait_for":
            steps.append(step_wait(raw.get("condition") or {},
                                   timeout=float(raw.get("wait_timeout") or 60),
                                   poll=float(raw.get("poll") or 2),
                                   label=str(raw.get("label") or ""),
                                   on_fail=str(raw.get("on_fail") or "abort")))
        elif kind == "plan":
            nested = sanitize_plan({"steps": raw.get("steps") or []})
            steps.append({"kind": "plan", "label": str(raw.get("label") or "podnačrt"),
                          "steps": nested["steps"], "on_fail": "abort",
                          "retries": 0, "timeout": 300, "undo": [],
                          "expect": {}, "require_verified": False})
    return {"name": str(plan.get("name") or "načrt"),
            "description": str(plan.get("description") or ""),
            "destructive": bool(plan.get("destructive")) or
                           any(is_destructive(s) for s in steps),
            "confirmed": bool(plan.get("confirmed")),
            "rollback": bool(plan.get("rollback", True)),
            "origin": str(plan.get("origin") or ""),
            "created": float(plan.get("created") or time.time()),
            "steps": steps}


# ------------------------------------------------------------------- planner
class Planner:
    def __init__(self, store, *, cfg: dict | None = None, ctl: str | None = None,
                 dry_run: bool = False, logger: Callable[[str], None] | None = None,
                 policy: dict | None = None):
        self.store = store
        self.cfg = cfg or {}
        self.ctl = ctl or find_ctl()
        self.dry_run = bool(dry_run)
        self.log = logger or (lambda msg: None)
        self.policy = policy or {}
        self.internals: dict[str, Callable[..., Any]] = {}
        self.on_speak: Callable[[str], Any] | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._current_task: int | None = None
        self.register_default_internals()

    # ------------------------------------------------------------ internals
    def register(self, name: str, fn: Callable[..., Any]) -> None:
        self.internals[name] = fn

    def register_default_internals(self) -> None:
        self.register("noop", lambda **kw: {"ok": True})
        self.register("report", lambda text="", **kw: {"ok": True, "text": text})

        def profile_summary(**kw):
            from .profile import get_profile
            return {"ok": True, "summary": get_profile(refresh=True).summary()}
        self.register("profile_summary", profile_summary)

        def health_check(**kw):
            from .health import check
            from .profile import get_profile
            return {"ok": True, "report": check(get_profile(), self.cfg)}
        self.register("health_check", health_check)

        def learning_prune(**kw):
            from ..learning import get_core
            return {"ok": True, "result": get_core(self.cfg).prune()}
        self.register("learning_prune", learning_prune)

        def learning_mine(**kw):
            from ..learning import get_core
            return {"ok": True, "result": get_core(self.cfg).mine(True)}
        self.register("learning_mine", learning_mine)

        def clean_temp(**kw):
            return self._clean_temp()
        self.register("clean_temp", clean_temp)

        def scan_large(**kw):
            return self._scan_large(**kw)
        self.register("scan_large", scan_large)

    # --------------------------------------------------------------- policy
    def autonomy_policy(self) -> dict:
        if self.policy:
            return self.policy
        block = dict(self.cfg.get("autonomy") or {})
        path = Path(os.environ.get(
            "MIA_CONTROL_POLICY",
            Path.home() / ".config" / "mia" / "control.json"))
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                block = {**(data.get("autonomy") or {}), **block}
        except (OSError, ValueError):
            pass
        return block

    def destructive_allowed(self) -> bool:
        return bool(self.autonomy_policy().get("allow_destructive", False))

    def preflight(self, plan: dict) -> dict:
        clean = sanitize_plan(plan)
        if clean.get("destructive"):
            confirmed = bool(clean.get("confirmed")) or self.destructive_allowed()
            if not confirmed:
                raise NeedsConfirmation(
                    "načrt vsebuje nevarno dejanje; potrebna je potrditev")
        if not Path(self.ctl).exists() and not shutil.which(self.ctl):
            if any(s["kind"] in ("ctl", "notify") for s in clean["steps"]):
                raise PreflightError(f"mia-ctl not found: {self.ctl}")
        return clean

    # ---------------------------------------------------------------- task
    def cancel(self) -> None:
        self._stop.set()

    def reset_cancel(self) -> None:
        self._stop.clear()

    def execute(self, plan: dict, *, name: str = "", source: str = "manual",
                job_id: int | None = None, origin: str = "",
                resume_task_id: int | None = None) -> dict:
        clean = self.preflight(plan)
        with self._lock:
            if resume_task_id:
                task_id = int(resume_task_id)
                self.store.update_task(task_id, status="running", error="",
                                       finished=None)
            else:
                task_id = self.store.create_task(
                    clean, name=name or clean.get("name") or "naloga",
                    source=source, job_id=job_id, dry_run=self.dry_run,
                    origin=origin)
            self._current_task = task_id
            for idx, step in enumerate(clean["steps"]):
                self.store.add_task_step(task_id, idx, step["kind"],
                                         step.get("label") or "",
                                         step.get("action") if step["kind"] == "ctl"
                                         else step.get("action"))
            self.store.update_task(task_id, steps_total=len(clean["steps"]),
                                   started=time.time())
            self.store.add_event("task", f"#{task_id}", {
                "name": name or clean.get("name"), "source": source,
                "steps": len(clean["steps"]), "dry_run": self.dry_run})
            self.log(f"task #{task_id} start: {name or clean.get('name')}")
        self._stop.clear()
        results: list[dict] = []
        soft_failures: list[dict] = []
        failed: dict | None = None
        try:
            for idx, step in enumerate(clean["steps"]):
                if self._stop.is_set():
                    raise Cancelled("task cancelled")
                previous = self.store.list_task_steps(task_id)
                if resume_task_id and idx < len(previous) and \
                        previous[idx].get("status") == "done":
                    results.append({"idx": idx, "status": "done",
                                    "skipped": True, "label": step.get("label")})
                    continue
                self.store.update_task(task_id, current_step=idx)
                outcome = self._run_step(task_id, idx, step, clean)
                results.append(outcome)
                if outcome["status"] != "done":
                    if step.get("on_fail") == "continue":
                        soft_failures.append(outcome)
                        continue
                    failed = outcome
                    break
            if failed is None:
                status, error = "done", ""
            elif self._stop.is_set():
                status, error = "cancelled", "cancelled"
            else:
                status, error = "failed", failed.get("error", "")
            if failed and clean.get("rollback") and status != "done":
                self._rollback(task_id, clean, results)
            result = {"ok": status == "done", "task_id": task_id,
                      "status": status, "error": error,
                      "steps": results, "failed_step": (failed or {}).get("idx"),
                      "soft_failures": soft_failures,
                      "dry_run": self.dry_run}
            self.store.update_task(task_id, status=status, result=result,
                                   error=error, finished=time.time(),
                                   current_step=len(results))
            self.store.add_event("task", f"#{task_id}",
                                 {"status": status, "error": error[:300],
                                  "failed_step": (failed or {}).get("idx")})
            self.log(f"task #{task_id} {status}")
            return result
        except Cancelled as exc:
            result = {"ok": False, "task_id": task_id, "status": "cancelled",
                      "error": str(exc), "steps": results,
                      "failed_step": len(results), "dry_run": self.dry_run}
            self.store.update_task(task_id, status="cancelled", result=result,
                                   error=str(exc), finished=time.time())
            return result
        except Exception as exc:
            result = {"ok": False, "task_id": task_id, "status": "failed",
                      "error": f"{type(exc).__name__}: {exc}", "steps": results,
                      "failed_step": len(results), "dry_run": self.dry_run}
            self.store.update_task(task_id, status="failed", result=result,
                                   error=result["error"], finished=time.time())
            self.store.add_event("task", f"#{task_id}",
                                 {"status": "failed", "error": result["error"][:300]})
            self.log(f"task #{task_id} failed: {result['error']}")
            return result

    # ----------------------------------------------------------- step runner
    def _run_step(self, task_id: int, idx: int, step: dict, plan: dict) -> dict:
        attempts = 0
        retries = int(step.get("retries") or 0)
        while True:
            attempts += 1
            self.store.update_task_step(task_id, idx, status="running",
                                        started=time.time(), attempts=attempts)
            try:
                outcome = self._execute_step(step, plan)
                status = "done" if outcome.get("ok") else "failed"
                self.store.update_task_step(
                    task_id, idx, status=status, finished=time.time(),
                    rc=outcome.get("rc"), output=str(outcome.get("output") or "")[:2000],
                    error=str(outcome.get("error") or "")[:1000],
                    verification=outcome.get("verification") or {})
                if status == "done":
                    return {"idx": idx, "kind": step["kind"],
                            "label": step.get("label"), "status": "done",
                            "attempts": attempts,
                            "verification": outcome.get("verification") or {},
                            "output": str(outcome.get("output") or "")[:600]}
                rc = outcome.get("rc")
                permanent = rc in (3, 4) or outcome.get("permanent")
                if attempts <= retries and not permanent:
                    time.sleep(min(30, 0.5 * (2 ** attempts)))
                    continue
                return {"idx": idx, "kind": step["kind"],
                        "label": step.get("label"), "status": "failed",
                        "attempts": attempts, "rc": rc,
                        "error": outcome.get("error") or "step failed",
                        "verification": outcome.get("verification") or {}}
            except Cancelled:
                self.store.update_task_step(task_id, idx, status="failed",
                                            finished=time.time(),
                                            error="cancelled")
                raise
            except Exception as exc:
                self.store.update_task_step(task_id, idx, status="failed",
                                            finished=time.time(),
                                            error=f"{type(exc).__name__}: {exc}")
                return {"idx": idx, "kind": step["kind"],
                        "label": step.get("label"), "status": "failed",
                        "attempts": attempts,
                        "error": f"{type(exc).__name__}: {exc}"}

    def _execute_step(self, step: dict, plan: dict) -> dict:
        kind = step["kind"]
        if kind == "sleep":
            deadline = time.time() + float(step.get("seconds") or 0)
            while time.time() < deadline:
                if self._stop.is_set():
                    raise Cancelled("cancelled during sleep")
                time.sleep(min(0.2, max(0.0, deadline - time.time())))
            return {"ok": True, "output": f"slept {step.get('seconds')}s"}
        if kind == "probe":
            ok, detail = evaluate(step.get("condition") or {},
                                  self._metrics(), None)
            return {"ok": ok, "output": detail,
                    "error": "" if ok else f"condition false: {detail}",
                    "permanent": True, "verification": detail}
        if kind == "wait_for":
            deadline = time.time() + float(step.get("wait_timeout") or 60)
            last: dict = {}
            while time.time() < deadline:
                if self._stop.is_set():
                    raise Cancelled("cancelled while waiting")
                ok, last = evaluate(step.get("condition") or {}, self._metrics(), None)
                if ok:
                    return {"ok": True, "output": last, "verification": last}
                time.sleep(float(step.get("poll") or 2))
            return {"ok": False, "output": last,
                    "error": f"condition not met within {step.get('wait_timeout')}s",
                    "permanent": True, "verification": last}
        if kind == "python":
            fn = self.internals.get(str(step.get("action") or ""))
            if fn is None:
                return {"ok": False, "rc": 2, "permanent": True,
                        "error": f"unknown internal action: {step.get('action')}"}
            data = fn(**(step.get("args") or {}))
            ok = bool((data or {}).get("ok", True))
            return {"ok": ok, "output": data,
                    "error": "" if ok else str((data or {}).get("error") or "action failed"),
                    "verification": {"status": "verified" if ok else "failed",
                                     "method": "internal"}}
        if kind == "notify":
            action = ["notify", str(step.get("title") or "Mia"),
                      str(step.get("body") or "")]
            return self._run_ctl(action, step, plan, force_yes=False)
        if kind == "speak":
            text = str(step.get("text") or "")
            if self.on_speak is not None and text:
                try:
                    self.on_speak(text)
                except Exception as exc:
                    return {"ok": False, "error": f"speak failed: {exc}",
                            "permanent": True}
            return {"ok": True, "output": text,
                    "verification": {"status": "verified",
                                     "method": "spoken"}}
        if kind == "plan":
            nested = make_plan(step.get("steps") or [],
                               name=str(step.get("label") or "podnačrt"),
                               confirmed=True)
            outcome = self.execute(nested, name=step.get("label") or "podnačrt",
                                   source="subplan")
            return {"ok": outcome["ok"], "output": outcome,
                    "error": outcome.get("error") or ""}
        if kind == "ctl":
            return self._run_ctl(step.get("action") or [], step, plan,
                                 force_yes=bool(step.get("yes")))
        return {"ok": False, "rc": 2, "permanent": True,
                "error": f"unsupported step kind: {kind}"}

    def _run_ctl(self, action: list[str], step: dict, plan: dict,
                 force_yes: bool) -> dict:
        if not action:
            return {"ok": False, "rc": 2, "permanent": True, "error": "empty action"}
        argv = ctl_argv(self.ctl) + list(action) + ["--json"]
        if force_yes or (plan.get("confirmed") and is_destructive(step)):
            argv.append("--yes")
        if self.dry_run:
            argv.append("--dry-run")
        try:
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=float(step.get("timeout") or 60),
                                  env=self._env())
        except subprocess.TimeoutExpired:
            return {"ok": False, "rc": 5, "error": "timeout",
                    "permanent": False}
        except OSError as exc:
            return {"ok": False, "rc": 5, "error": str(exc), "permanent": True}
        payload: dict = {}
        try:
            payload = json.loads(proc.stdout or "{}")
        except ValueError:
            payload = {"ok": proc.returncode == 0, "data": (proc.stdout or "")[:1000]}
        ok = bool(payload.get("ok", proc.returncode == 0))
        data = payload.get("data")
        verification = data.get("verification", {}) if isinstance(data, dict) else {}
        result = {"ok": ok, "rc": proc.returncode, "output": data,
                  "error": str(payload.get("error") or (proc.stderr or "").strip())[:1000],
                  "verification": verification,
                  "permanent": proc.returncode in (3, 4)}
        if ok and (step.get("expect") or {}):
            checked = self._check_expect(step.get("expect") or {}, proc, data)
            result["verification"] = checked
            if not checked["ok"]:
                result.update({"ok": False, "error": checked["error"]})
        elif step.get("require_verified") and verification.get("status") == "failed":
            result["permanent"] = True
        return result

    @staticmethod
    def _check_expect(expect: dict, proc: subprocess.CompletedProcess,
                      data: Any) -> dict:
        if not expect:
            return {"ok": True}
        if "exit" in expect and proc.returncode != int(expect["exit"]):
            return {"ok": False, "error": f"exit {proc.returncode} != {expect['exit']}",
                    "status": "failed", "method": "exit"}
        if "stdout_contains" in expect and \
                str(expect["stdout_contains"]) not in (proc.stdout or ""):
            return {"ok": False, "error": "stdout does not contain expected text",
                    "status": "failed", "method": "stdout"}
        if "json" in expect:
            node: Any = data
            for part in str(expect["json"]).split("."):
                if isinstance(node, dict) and part in node:
                    node = node[part]
                else:
                    node = None
                    break
            if "equals" in expect and node != expect["equals"]:
                return {"ok": False, "error": f"{expect['json']}={node!r}",
                        "status": "failed", "method": "json"}
            if "contains" in expect and str(expect["contains"]) not in str(node):
                return {"ok": False, "error": f"{expect['json']} lacks text",
                        "status": "failed", "method": "json"}
        return {"ok": True, "status": "verified", "method": "expect"}

    def _rollback(self, task_id: int, plan: dict, results: list[dict]) -> None:
        for item in reversed(results):
            if item.get("status") != "done":
                continue
            idx = int(item.get("idx") or 0)
            if idx >= len(plan["steps"]):
                continue
            undo = plan["steps"][idx].get("undo") or []
            if not undo:
                continue
            self.store.add_event("task", f"#{task_id}", {"rollback": undo})
            self._run_ctl(undo, {"timeout": 30}, {"confirmed": True},
                          force_yes=True)

    # ---------------------------------------------------------- maintenance
    def resume(self, task_id: int) -> dict:
        task = self.store.get_task(task_id)
        if not task:
            raise PlannerError(f"task {task_id} does not exist")
        if task["status"] == "done":
            return {"ok": True, "task_id": task_id, "status": "done",
                    "message": "already done"}
        return self.execute(task["plan"], name=task.get("name") or "",
                            source="resume", job_id=task.get("job_id"),
                            origin=task.get("origin") or "",
                            resume_task_id=task_id)

    def _env(self) -> dict:
        env = dict(os.environ)
        env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
        return env

    def _metrics(self) -> dict:
        from .profile import get_profile
        try:
            return get_profile().metrics(sample_seconds=0.02)
        except Exception:
            return {}

    def _clean_temp(self) -> dict:
        removed = 0
        freed = 0
        root = Path(os.environ.get("TMPDIR") or "/tmp")
        cutoff = time.time() - float(
            (self.cfg.get("autonomy") or {}).get("temp_max_age_hours", 48)) * 3600
        for entry in root.glob("*"):
            if entry.name.startswith(("mia-", "systemd-", "snap-", ".X")):
                continue
            try:
                stat = entry.stat()
            except OSError:
                continue
            if stat.st_mtime > cutoff:
                continue
            try:
                if entry.is_dir() and not entry.is_symlink():
                    size = sum(p.stat().st_size for p in entry.rglob("*")
                               if p.is_file())
                    shutil.rmtree(entry, ignore_errors=True)
                else:
                    size = stat.st_size
                    entry.unlink()
                removed += 1
                freed += size
            except OSError:
                continue
        return {"ok": True, "removed": removed, "freed_bytes": freed,
                "root": str(root)}

    def _scan_large(self, root: str | None = None, min_mb: int = 200,
                    limit: int = 20, **kw) -> dict:
        root_path = Path(root or Path.home()).expanduser()
        cutoff = float(min_mb) * 1024 * 1024
        found: list[dict] = []
        scanned = 0
        for base, dirs, files in os.walk(root_path):
            dirs[:] = [d for d in dirs if not d.startswith(".") and
                       d not in ("node_modules", "__pycache__", ".git")]
            for name in files:
                path = Path(base) / name
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                scanned += 1
                if size >= cutoff:
                    found.append({"path": str(path), "size": size})
            if scanned > 200000:
                break
        found.sort(key=lambda item: item["size"], reverse=True)
        return {"ok": True, "root": str(root_path), "min_mb": min_mb,
                "files": found[:int(limit)], "scanned": scanned}


# ------------------------------------------------------------------ templates
def template_workday(profile=None) -> dict:
    steps = [step_notify("Delovni način", "Pripravljam okolje.")]
    return make_plan(steps, name="delovni način",
                     description="Miren začetek dela: glasnost, obvestilo, pogled virov.")


def template_cleanup() -> dict:
    steps = [
        step_python("scan_large", "Poišči velike datoteke",
                    args={"min_mb": 500, "limit": 25}),
        step_python("clean_temp", "Počisti stare temp datoteke"),
    ]
    return make_plan(steps, name="čiščenje diska",
                     description="Poišče velike datoteke in počisti star temp.",
                     destructive=True)


def template_system_update() -> dict:
    steps = [
        step_python("health_check", "Preveri stanje pred posodobitvijo"),
        step_ctl(["pkg", "update"], "Osveži sezname paketov", yes=True,
                 timeout=300),
        step_ctl(["pkg", "upgrade"], "Namesti posodobitve", yes=True,
                 timeout=1800),
        step_python("health_check", "Preveri stanje po posodobitvi"),
    ]
    return make_plan(steps, name="posodobitev sistema",
                     destructive=True,
                     description="Osveži in posodobi sistemske pakete.")


def template_night() -> dict:
    steps = [
        step_ctl(["media", "pause"], "Ustavi predvajanje"),
        step_ctl(["volume", "set", "20"], "Znižaj glasnost"),
        step_ctl(["power", "lock"], "Zakleni zaslon"),
    ]
    return make_plan(steps, name="nočni način",
                     description="Ustavi medije, zniža glasnost in zaklene zaslon.")


def template_health_report() -> dict:
    return make_plan([step_python("health_check", "Zberi zdravstveno poročilo")],
                     name="zdravstveno poročilo")


TEMPLATES: dict[str, Callable[..., dict]] = {
    "workday": template_workday,
    "cleanup": template_cleanup,
    "system_update": template_system_update,
    "night": template_night,
    "health_report": template_health_report,
}


def build_template(name: str, profile=None) -> dict:
    fn = TEMPLATES.get(name)
    if not fn:
        raise PlannerError(f"unknown template: {name}")
    try:
        return fn(profile)
    except TypeError:
        return fn()

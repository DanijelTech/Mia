"""Tests for the autonomy core: profile, planner, scheduler, health, intents."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))

from mia_core.autonomy import health, intents, planner  # noqa: E402
from mia_core.autonomy.profile import SystemProfile  # noqa: E402
from mia_core.autonomy.scheduler import Scheduler, next_run  # noqa: E402
from mia_core.autonomy.service import AutonomyService  # noqa: E402
from mia_core.db import Store  # noqa: E402

CTL = ROOT / "skills" / "mia-companion" / "bin" / "mia-ctl"


class FakeProfile:
    def __init__(self, metrics: dict | None = None):
        self._metrics = metrics or _default_metrics()
        self.data = {"score": {"percent": 50}, "readiness": [], "adaptation": []}

    def metrics(self, sample_seconds: float = 0) -> dict:
        return dict(self._metrics)

    def summary(self) -> str:
        return "fake machine"

    def readiness(self) -> list:
        return []

    def adaptation(self) -> list:
        return []


def _default_metrics(**overrides) -> dict:
    base = {
        "cpu_percent": 4.0, "cpu_cores": 4, "load": [0.2, 0.1, 0.1],
        "mem_total": 8 * 1024 ** 3, "mem_available": 6 * 1024 ** 3,
        "mem_used_percent": 25.0, "swap_total": 0, "swap_used_percent": 0.0,
        "disk_root": {"total": 100 * 1024 ** 3, "used": 40 * 1024 ** 3,
                      "free": 60 * 1024 ** 3, "percent": 40.0},
        "disk_home": {"total": 100 * 1024 ** 3, "used": 40 * 1024 ** 3,
                      "free": 60 * 1024 ** 3, "percent": 40.0},
        "disk_free_percent": 60.0, "battery": {"present": False},
        "battery_percent": None, "on_battery": False, "temperatures": [],
        "max_temp_c": None, "uptime": 3600.0, "wifi_connected": True,
        "network_up": True,
    }
    base.update(overrides)
    return base


class ProfileTests(unittest.TestCase):
    def test_detect_shape_and_fingerprint(self):
        profile = SystemProfile()
        self.assertTrue(profile.data["os"]["system"])
        self.assertTrue(profile.data["cpu"]["cores"] >= 1)
        self.assertIn("tools", profile.data)
        self.assertIn("readiness", profile.data)
        self.assertGreater(len(profile.readiness()), 10)
        self.assertEqual(len(profile.fingerprint), 16)
        self.assertIn("pripravljenost", profile.summary())

    def test_metrics_are_well_formed(self):
        metrics = SystemProfile().metrics(sample_seconds=0)
        for key in ("cpu_percent", "mem_used_percent", "disk_free_percent",
                    "load", "uptime"):
            self.assertIn(key, metrics)
        self.assertGreaterEqual(metrics["cpu_percent"], 0)
        self.assertLessEqual(metrics["mem_used_percent"], 100)

    def test_diff_detects_tool_changes(self):
        profile = SystemProfile()
        previous = dict(profile.data)
        previous["tools"] = {**profile.data["tools"], "xdotool": "/usr/bin/xdotool"}
        changes = profile.diff(previous)
        self.assertIn("tools_removed", changes)
        self.assertIn("xdotool", changes["tools_removed"])


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        (self.home / "Documents").mkdir()
        (self.home / "Documents" / "a.txt").write_text("hello")
        self.store = Store(self.home / "learning.db")
        self.env = mock.patch.dict(os.environ, {
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "XDG_STATE_HOME": str(self.home / ".local" / "state"),
            "XDG_DATA_HOME": str(self.home / ".local" / "share"),
        })
        self.env.start()
        self.planner = planner.Planner(self.store, ctl=str(CTL))

    def tearDown(self):
        self.env.stop()
        self.store.close()
        self.tmp.cleanup()

    def test_ctl_step_executes_and_verifies(self):
        target = self.home / "newdir"
        plan = planner.make_plan([
            planner.step_ctl(["files", "mkdir", str(target)],
                             expect={"json": "is_dir", "equals": True})],
            name="mkdir")
        result = self.planner.execute(plan, name="mkdir")
        self.assertTrue(result["ok"], result)
        self.assertTrue(target.is_dir())
        task = self.store.get_task(result["task_id"])
        self.assertEqual(task["status"], "done")
        steps = self.store.list_task_steps(result["task_id"])
        self.assertEqual(steps[0]["verification"].get("method"), "expect")

    def test_destructive_plan_needs_confirmation(self):
        target = self.home / "Documents" / "a.txt"
        plan = planner.make_plan([
            planner.step_ctl(["files", "delete", str(target)], yes=True)],
            name="delete", destructive=True)
        with self.assertRaises(planner.NeedsConfirmation):
            self.planner.execute(plan)
        self.assertTrue(target.exists())
        plan["confirmed"] = True
        result = self.planner.execute(plan, name="delete")
        self.assertTrue(result["ok"], result)
        self.assertFalse(target.exists())

    def test_retries_transient_internal_failure(self):
        calls = {"n": 0}

        def flaky(**kwargs):
            calls["n"] += 1
            return {"ok": calls["n"] >= 3, "error": "not yet"}

        self.planner.register("flaky", flaky)
        step = planner.step_python("flaky", "flaky")
        step["retries"] = 2
        result = self.planner.execute(planner.make_plan([step]))
        self.assertTrue(result["ok"], result)
        self.assertEqual(calls["n"], 3)

    def test_speak_step_uses_callback(self):
        spoken: list[str] = []
        self.planner.on_speak = spoken.append
        result = self.planner.execute(
            planner.make_plan([planner.step_speak("pij vodo")]))
        self.assertTrue(result["ok"], result)
        self.assertEqual(spoken, ["pij vodo"])

    def test_preflight_rejects_shell_and_unknown(self):
        with self.assertRaises(planner.PreflightError):
            self.planner.preflight({"steps": [{"kind": "ctl",
                                               "action": ["bash", "-c", "rm -rf /"]}]})
        with self.assertRaises(planner.PreflightError):
            self.planner.preflight({"steps": [{"kind": "eval", "action": "1"}]})

    def test_recover_tasks(self):
        plan = planner.make_plan([planner.step_python("noop")])
        task_id = self.store.create_task(plan, name="x")
        self.store.update_task(task_id, status="running")
        self.assertEqual(self.store.recover_tasks(), 1)
        self.assertEqual(self.store.get_task(task_id)["status"], "interrupted")


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "learning.db")
        self.metrics = _default_metrics()
        self.profile = FakeProfile(self.metrics)
        self.planner = planner.Planner(self.store, ctl=str(CTL))
        self.scheduler = Scheduler(self.store, self.planner,
                                   lambda: self.profile)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_next_run_shapes(self):
        now = time.time()
        self.assertAlmostEqual(next_run({"kind": "every", "seconds": 60}, now,
                                        now), now + 60)
        daily = next_run({"kind": "daily", "time": "23:59"}, now)
        self.assertGreater(daily, now)

    def test_every_job_fires_and_runs_plan(self):
        job_id = self.scheduler.add_job(
            "noop", {"kind": "every", "seconds": 60},
            planner.make_plan([planner.step_python("noop")]))
        self.store.update_job(job_id, next_run=time.time() - 1)
        result = self.scheduler.tick()
        self.assertEqual(result["count"], 1)
        job = self.store.get_job(job_id)
        self.assertEqual(job["run_count"], 1)
        self.assertEqual(job["last_status"], "done")
        runs = self.store.list_job_runs(job_id)
        self.assertEqual(runs[0]["status"], "done")

    def test_condition_trigger_is_edge_triggered(self):
        job_id = self.scheduler.add_job(
            "disk rule",
            {"kind": "condition", "for_seconds": 0, "poll": 60,
             "condition": {"metric": "disk_free_percent", "op": "<", "value": 10}},
            planner.make_plan([planner.step_python("noop")]), kind="rule")
        self.metrics["disk_free_percent"] = 5.0
        self.scheduler.tick()
        self.assertEqual(self.store.get_job(job_id)["run_count"], 1)
        self.scheduler.tick()  # still low, but not re-armed
        self.assertEqual(self.store.get_job(job_id)["run_count"], 1)
        self.metrics["disk_free_percent"] = 50.0
        self.scheduler.tick()  # clears and re-arms
        self.metrics["disk_free_percent"] = 5.0
        self.scheduler.tick()
        self.assertEqual(self.store.get_job(job_id)["run_count"], 2)

    def test_event_trigger_starts_with_baseline(self):
        watched = Path(self.tmp.name) / "watched.txt"
        watched.write_text("one")
        job_id = self.scheduler.add_job(
            "watch", {"kind": "event", "name": "file_changed",
                      "path": str(watched), "poll": 5},
            planner.make_plan([planner.step_python("noop")]))
        self.scheduler.tick()
        self.assertEqual(self.store.get_job(job_id)["run_count"], 0)
        time.sleep(0.01)
        watched.write_text("two")
        self.scheduler.tick()
        self.assertEqual(self.store.get_job(job_id)["run_count"], 1)


class HealthTests(unittest.TestCase):
    def test_levels_and_score(self):
        report = health.check(FakeProfile(_default_metrics(
            disk_free_percent=3.0,
            disk_root={"total": 100, "used": 97, "free": 3, "percent": 97},
            mem_used_percent=97.0)))
        self.assertEqual(report["level"], "critical")
        self.assertLess(report["score"], 100)
        keys = {c["key"] for c in report["checks"]}
        self.assertIn("disk.root", keys)
        self.assertIn("memory.used", keys)
        self.assertIn("Pozor", report["summary"])

    def test_watch_deduplicates_alerts(self):
        tmp = tempfile.TemporaryDirectory()
        store = Store(Path(tmp.name) / "learning.db")
        try:
            report = health.check(FakeProfile(_default_metrics(
                disk_free_percent=3.0,
                disk_root={"total": 100, "used": 97, "free": 3, "percent": 97})))
            first = health.watch(store, report)
            second = health.watch(store, report)
            self.assertTrue(first)
            self.assertFalse(second)
            self.assertGreaterEqual(len(store.list_alerts(limit=20)), 1)
        finally:
            store.close()
            tmp.cleanup()


class IntentTests(unittest.TestCase):
    CASES = [
        ("Mia, nastavi glasnost na 40", "action", "volume.set"),
        ("pojačaj za 10", "action", "volume.up"),
        ("naredi posnetek zaslona", "action", "screenshot"),
        ("Mia, zakleni zaslon", "action", "power.lock"),
        ("ugasni računalnik", "action", "power.shutdown"),
        ("zapri firefox", "action", "apps.quit"),
        ("preklopi na terminal", "action", "window.focus"),
        ("najdi datoteko invoice", "action", "files.search"),
        ("ustvari mapo Projekti", "action", "files.mkdir"),
        ("kopiraj datoteko a.txt v b.txt", "action", "files.copy"),
        ("izbriši datoteko a.txt", "action", "files.delete"),
        ("koliko je prostega prostora", "query", "resources"),
        ("kateri sistem imaš", "query", "sysinfo"),
        ("kako si", "query", "health"),
        ("kaj si avtomatizirala", "query", "jobs"),
        ("počisti disk", "plan", "plan.cleanup"),
        ("posodobi sistem", "plan", "plan.system_update"),
        ("preveri posodobitve", "action", "pkg.list-upgradable"),
        ("opomni me čez 10 minut, da pijem vodo", "schedule", "schedule.reminder"),
        ("vsak dan ob 8:00 mi povej dobro jutro", "schedule", "schedule.daily"),
        ("vsakih 30 minut preveri pošto", "schedule", "schedule.every"),
        ("ko bo baterija pod 20, me opozori", "schedule", "rule.condition"),
        ("preklici opomnik 3", "cancel_job", "cancel_job"),
        ("ali teče storitev mia-voice", "action", "service.status"),
        ("ustavi proces chrome", "action", "process.kill"),
        ("vklopi požarni zid", "action", "net.firewall"),
        ("pingaj 8.8.8.8", "action", "net.ping"),
        ("poišči paket htop", "action", "pkg.search"),
    ]

    def test_expected_intents(self):
        for text, kind, name in self.CASES:
            with self.subTest(text=text):
                intent = intents.route(text)
                self.assertIsNotNone(intent, text)
                self.assertEqual(intent.kind, kind)
                self.assertEqual(intent.name, name)

    def test_conversation_is_not_hijacked(self):
        for text in ("danes je lep dan, kaj predlagaš?",
                     "ali lahko odpreš kaj zanimivega?",
                     "povej mi vic o robotu",
                     "kako se počutiš danes"):
            with self.subTest(text=text):
                self.assertIsNone(intents.route(text))

    def test_confirmation_flags(self):
        self.assertTrue(intents.route("ugasni računalnik").confirmation)
        self.assertTrue(intents.route("izbriši datoteko x").confirmation)
        self.assertFalse(intents.route("nastavi glasnost na 20").confirmation)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        (self.home / "Documents").mkdir()
        self.target = self.home / "Documents" / "x.txt"
        self.target.write_text("hello")
        self.store = Store(self.home / "learning.db")
        self.service = AutonomyService(
            store=self.store,
            cfg={"db_path": str(self.home / "learning.db"),
                 "autonomy": {"allow_destructive": False}},
            ctl=str(CTL), dry_run=False)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_query_and_health(self):
        result = self.service.handle("koliko je prostega prostora")
        self.assertTrue(result["ok"])
        self.assertIn("CPU", result["text"])
        result = self.service.handle("kaj si avtomatizirala")
        self.assertTrue(result["ok"])

    def test_reminder_creates_job(self):
        result = self.service.handle("opomni me čez 5 minut, da pijem vodo",
                                     conversation="test")
        self.assertTrue(result["ok"])
        jobs = self.store.list_jobs()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["kind"], "job")
        self.assertGreater(jobs[0]["next_run"], time.time())

    def test_rule_creates_condition_job(self):
        result = self.service.handle("ko bo baterija pod 20, me opozori",
                                     conversation="test")
        self.assertTrue(result["ok"])
        job = self.store.list_jobs()[0]
        self.assertEqual(job["kind"], "rule")
        self.assertEqual(job["trigger"]["condition"]["metric"], "battery_percent")

    def test_confirmation_flow_cancel(self):
        text = f"izbriši datoteko {self.target}"
        first = self.service.handle(text, conversation="c1")
        self.assertTrue(first.get("pending"))
        self.assertTrue(self.target.exists())
        second = self.service.handle("ne", conversation="c1")
        self.assertTrue(second["ok"])
        self.assertIsNone(self.store.get_pending("pending:c1"))
        self.assertTrue(self.target.exists())

    def test_unknown_text_passes_through(self):
        self.assertIsNone(self.service.handle("povej mi vic o robotu",
                                              conversation="c2"))

    def test_file_actions_and_confirmation(self):
        folder = self.home / "Projekti"
        first = self.service.handle(f"ustvari mapo {folder}", conversation="f1")
        self.assertTrue(first["ok"], first)
        self.assertTrue(folder.is_dir())

        source = self.home / "Documents" / "x.txt"
        target = self.home / "Documents" / "y.txt"
        copied = self.service.handle(
            f"kopiraj datoteko {source} v {target}", conversation="f1")
        self.assertTrue(copied["ok"], copied)
        self.assertTrue(target.exists())

        asked = self.service.handle(f"izbriši datoteko {target}",
                                    conversation="f1")
        self.assertTrue(asked.get("pending"))
        confirmed = self.service.handle("ja", conversation="f1")
        self.assertTrue(confirmed["ok"], confirmed)
        self.assertFalse(target.exists())

    def test_rule_for_full_disk(self):
        result = self.service.handle("ko bo disk poln, me opozori",
                                     conversation="r1")
        self.assertTrue(result["ok"], result)
        job = self.store.list_jobs()[0]
        self.assertEqual(job["trigger"]["condition"]["metric"],
                         "disk_free_percent")

    def test_tick_recovers_and_runs(self):
        result = self.service.tick()
        self.assertIn("scheduler", result)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.env = os.environ.copy()
        self.env.update({
            "HOME": str(self.home),
            "MIA_HOME": str(ROOT),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "XDG_STATE_HOME": str(self.home / ".local" / "state"),
            "XDG_DATA_HOME": str(self.home / ".local" / "share"),
            "PATH": f"{ROOT / 'skills' / 'mia-companion' / 'bin'}:"
                    + self.env.get("PATH", ""),
        })

    def tearDown(self):
        self.tmp.cleanup()

    def run_auto(self, *args: str):
        return subprocess.run(
            [sys.executable, str(ROOT / "skills" / "mia-companion" / "bin" /
                                 "mia-auto"), *args],
            capture_output=True, text=True, env=self.env, timeout=90)

    def test_route_and_jobs(self):
        result = self.run_auto("--json", "route", "opomni me čez 5 minut, da pijem vodo")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["name"], "schedule.reminder")

        plan = json.dumps({"steps": [{"kind": "python", "action": "noop"}]})
        added = self.run_auto("--json", "jobs", "add", "cli test",
                              "--every", "3600", "--plan", plan)
        self.assertEqual(added.returncode, 0, added.stderr)
        listed = self.run_auto("--json", "jobs", "list")
        payload = json.loads(listed.stdout)
        self.assertTrue(any(j["name"] == "cli test" for j in payload))

    def test_status_and_plan_list(self):
        result = self.run_auto("--json", "status")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("profile", json.loads(result.stdout))
        listed = self.run_auto("plan", "--list")
        self.assertIn("system_update", listed.stdout)


if __name__ == "__main__":
    unittest.main()

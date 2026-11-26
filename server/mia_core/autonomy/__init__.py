"""Mia autonomy core: adaptive system profile, planner, scheduler and health.

The package is stdlib-only and deliberately separate from the voice server so
that the same logic runs in the HUD/API, in `mia-auto` and in tests.
"""

from .conditions import describe, evaluate
from .health import check as health_check, remediate, watch
from .intents import Intent, route, route_help
from .planner import (NeedsConfirmation, Planner, PlannerError, PreflightError,
                      build_template, make_plan, sanitize_plan)
from .profile import SystemProfile, get_profile
from .scheduler import Scheduler, next_run, trigger_summary
from .service import AutonomyService

__all__ = [
    "AutonomyService", "SystemProfile", "get_profile", "Planner",
    "PlannerError", "PreflightError", "NeedsConfirmation", "Scheduler",
    "next_run", "trigger_summary", "Intent", "route", "route_help",
    "evaluate", "describe", "make_plan", "build_template", "sanitize_plan",
    "health_check", "remediate", "watch",
]

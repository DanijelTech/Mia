"""Tool schemas for Mia's autonomy layer.

The descriptions are forceful on purpose: the model should use these tools for
the machine itself (profile, plans, jobs, rules, health) instead of chaining
raw shell commands or inventing a one-off script.
"""

BASE = (
    "Mia's audited autonomy layer on THIS machine. Every action goes through "
    "mia-ctl or the planner: policy-checked, verified and journaled. Prefer "
    "these tools over raw shell. Destructive actions need explicit user "
    "confirmation."
)

SYSTEM_STATUS = {
    "name": "system_status",
    "description": (
        "One-page machine state: profile summary, readiness score, health, "
        "scheduled jobs, recent tasks, pending confirmations and alerts. Call "
        "this first for 'how is the machine', 'what are you doing', or before "
        "changing anything. " + BASE
    ),
    "parameters": {"type": "object", "properties": {}},
}

SYSTEM_PROFILE = {
    "name": "system_profile",
    "description": (
        "Detect the machine (OS, distro, init, package manager, desktop, "
        "backends, GPU, battery, network, privileges, container), its "
        "readiness score, missing tools and the adaptation plan with package "
        "names for this distribution. Use refresh=true after installing "
        "something. " + BASE
    ),
    "parameters": {
        "type": "object",
        "properties": {"refresh": {"type": "boolean", "default": False}},
    },
}

SYSTEM_HEALTH = {
    "name": "system_health",
    "description": (
        "Scored health report: disk, RAM, swap, load, temperature, battery, "
        "network, failed systemd units, TLS certificate, learning DB and stale "
        "tasks. Each check carries a remediation hint. " + BASE
    ),
    "parameters": {
        "type": "object",
        "properties": {"force": {"type": "boolean", "default": True}},
    },
}

SYSTEM_ADAPT = {
    "name": "system_adapt",
    "description": (
        "Show the adaptation plan (missing tools and packages). apply=true "
        "installs them through mia-ctl pkg install, but only when the policy "
        "allows autonomy.auto_install and the process can elevate. Never "
        "claim a tool works before a profile refresh proves it. " + BASE
    ),
    "parameters": {
        "type": "object",
        "properties": {"apply": {"type": "boolean", "default": False}},
    },
}

SYSTEM_PLANS = {
    "name": "system_plans",
    "description": (
        "List built-in plans (workday, cleanup, system_update, night, "
        "health_report) with their steps and whether they are destructive. "
        "Use before running one. " + BASE
    ),
    "parameters": {"type": "object", "properties": {}},
}

SYSTEM_RUN_PLAN = {
    "name": "system_run_plan",
    "description": (
        "Run a built-in template or an explicit plan. A plan is a list of "
        "steps: ctl (argv list, never a shell string), python (internal), "
        "notify, speak, sleep, probe, wait_for, plan. Destructive plans MUST "
        "be confirmed by the user first; then pass confirm=true. The result "
        "contains task_id, per-step verification and soft_failures. " + BASE
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "template": {"type": "string",
                         "enum": ["workday", "cleanup", "system_update",
                                  "night", "health_report"]},
            "plan": {"type": "object",
                     "description": "Explicit plan object (alternative to template)"},
            "confirm": {"type": "boolean", "default": False,
                        "description": "true only after the user confirmed a destructive plan"},
        },
    },
}

SYSTEM_COMMAND = {
    "name": "system_command",
    "description": (
        "Execute one deterministic natural-language system command: volume, "
        "brightness, media, windows/apps, files, processes, services, network, "
        "packages, power, reminders ('remind me in 10 minutes to ...'), daily "
        "and conditional rules. Returns handled=false when the sentence is "
        "not a system command — then answer it normally instead. Destructive "
        "commands return a pending confirmation; ask the user for 'ja' and "
        "call this again with their answer. " + BASE
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "input": {"type": "string", "description": "The user's sentence"},
            "conversation": {"type": "string", "default": "mia-main",
                             "description": "Confirmation scope"},
        },
        "required": ["input"],
    },
}

SYSTEM_JOBS = {
    "name": "system_jobs",
    "description": (
        "List scheduled jobs and reactive rules with their trigger, next run "
        "and last status. " + BASE
    ),
    "parameters": {
        "type": "object",
        "properties": {"kind": {"type": "string", "enum": ["job", "rule"]}},
    },
}

SYSTEM_JOB_ADD = {
    "name": "system_job_add",
    "description": (
        "Create a persistent job or rule. Triggers: {kind:'at',ts}, "
        "{kind:'every',seconds}, {kind:'daily',time:'08:00',weekdays:[0..6]}, "
        "{kind:'condition',condition:{metric,op,value},for_seconds,poll}, "
        "{kind:'event',name:'file_changed'|'service_down'|'battery_low'|"
        "'network_down',...}, {kind:'idle',for_seconds}. Conditions are "
        "edge-triggered. Provide template, plan, or notify/text. " + BASE
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "kind": {"type": "string", "enum": ["job", "rule"], "default": "job"},
            "trigger": {"type": "object"},
            "conditions": {"type": "array", "items": {"type": "object"}},
            "template": {"type": "string"},
            "plan": {"type": "object"},
            "notify": {"type": "string", "description": "Notification title"},
            "text": {"type": "string", "description": "Notification body"},
            "enabled": {"type": "boolean", "default": True},
            "max_runs": {"type": "integer", "default": 0},
        },
        "required": ["name"],
    },
}

SYSTEM_JOB_REMOVE = {
    "name": "system_job_remove",
    "description": "Delete a job or rule by id. " + BASE,
    "parameters": {
        "type": "object",
        "properties": {"job_id": {"type": "integer"}},
        "required": ["job_id"],
    },
}

SYSTEM_TASKS = {
    "name": "system_tasks",
    "description": (
        "List the task journal: every plan run, its status and when it "
        "started. An interrupted task can be resumed. " + BASE
    ),
    "parameters": {
        "type": "object",
        "properties": {"limit": {"type": "integer", "default": 20}},
    },
}

SYSTEM_TASK_RESUME = {
    "name": "system_task_resume",
    "description": (
        "Resume an interrupted/failed task. Steps already done are skipped; "
        "destructive steps still obey policy. " + BASE
    ),
    "parameters": {
        "type": "object",
        "properties": {"task_id": {"type": "integer"}},
        "required": ["task_id"],
    },
}

SYSTEM_TASK_CANCEL = {
    "name": "system_task_cancel",
    "description": "Cancel a task (and signal the running planner). " + BASE,
    "parameters": {
        "type": "object",
        "properties": {"task_id": {"type": "integer"}},
        "required": ["task_id"],
    },
}

SYSTEM_ALERTS = {
    "name": "system_alerts",
    "description": (
        "Unacknowledged health/autonomy alerts. Use for 'what is wrong' and "
        "before claiming the machine is healthy. " + BASE
    ),
    "parameters": {
        "type": "object",
        "properties": {"limit": {"type": "integer", "default": 20}},
    },
}

SYSTEM_ALERT_ACK = {
    "name": "system_alert_ack",
    "description": "Acknowledge an alert after it has been handled. " + BASE,
    "parameters": {
        "type": "object",
        "properties": {"alert_id": {"type": "integer"}},
        "required": ["alert_id"],
    },
}

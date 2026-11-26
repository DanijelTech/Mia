"""Tool schemas for Mia's learning loop.

The descriptions are deliberately forceful: the model must reach for these
tools when the user corrects it, asks it to remember, or repeats a task.
"""

BASE = (
    "Mia's durable local memory (episodes, habits, recipes, anti-patterns, "
    "facts, skill tree). Use it BEFORE asking the user something they may "
    "already have told you, and AFTER a correction so the mistake is not "
    "repeated."
)

MEMORY_BRIEF = {
    "name": "memory_brief",
    "description": (
        "Fetch the exact memory brief Mia would inject for a request: relevant "
        "habits, proven recipes, known mistakes to avoid and preferences. Call "
        "this before a recurring task or when the user asks 'what do you know "
        "about ...'. " + BASE
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "request": {"type": "string", "description": "The user's request or task description"},
        },
        "required": ["request"],
    },
}

MEMORY_SEARCH = {
    "name": "memory_search",
    "description": (
        "Full-text search across Mia's episodes, recipes, mistakes and facts. "
        "Use for 'do you remember ...', older conversations, or when the brief "
        "is empty. " + BASE
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "description": "Default 20"},
        },
        "required": ["query"],
    },
}

MEMORY_FEEDBACK = {
    "name": "memory_feedback",
    "description": (
        "Record whether the previous action was RIGHT or WRONG. Call this "
        "whenever the user corrects you ('ne tako', 'ni prav') or confirms "
        "('tako je', 'to je bilo prav'). A negative verdict creates an "
        "anti-pattern; a positive one promotes the procedure to a recipe. " + BASE
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["positive", "negative"]},
            "note": {"type": "string", "description": "What exactly was right/wrong, or the corrected method"},
            "episode_id": {"type": "integer", "description": "Optional; default = the last episode"},
        },
        "required": ["verdict"],
    },
}

MEMORY_REMEMBER = {
    "name": "memory_remember",
    "description": (
        "Force-save the last (or a selected) episode as a reusable recipe. "
        "Use when the user says 'zapomni si postopek' / 'shrani recept' or "
        "when a non-obvious sequence succeeded. " + BASE
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "note": {"type": "string", "description": "Why this procedure works / pitfalls"},
            "episode_id": {"type": "integer"},
        },
    },
}

MEMORY_FACT = {
    "name": "memory_fact",
    "description": (
        "Store a durable preference, person, project or machine fact. Keys are "
        "short and stable ('pref.browser', 'person.ana', 'project.current'). "
        "Never store secrets. " + BASE
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "key": {"type": "string"},
            "value": {"type": "string"},
            "kind": {"type": "string", "enum": ["preference", "person", "project", "system", "habit"]},
        },
        "required": ["key", "value"],
    },
}

MEMORY_MISTAKE = {
    "name": "memory_mistake",
    "description": (
        "Record an anti-pattern: what failed, the cause, and the fix. Use when "
        "the user explains why something did not work. " + BASE
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "symptom": {"type": "string"},
            "cause": {"type": "string"},
            "fix": {"type": "string"},
            "severity": {"type": "string", "enum": ["low", "medium", "high"]},
        },
        "required": ["symptom"],
    },
}

MEMORY_STATUS = {
    "name": "memory_status",
    "description": (
        "Show how much Mia remembers: episodes, habits, recipes, mistakes, "
        "facts, skills, last mining. Use for 'koliko se spomniš' or diagnostics. " + BASE
    ),
    "parameters": {"type": "object", "properties": {}},
}

SKILL_TREE = {
    "name": "skill_tree",
    "description": (
        "List or search Mia's granular skill tree (mia-companion + mia-desktop, "
        "mia-learning, mia-music, mia-browser, mia-productivity, "
        "mia-diagnostics). Use to find which skill owns a capability. " + BASE
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Optional capability/keyword"},
        },
    },
}

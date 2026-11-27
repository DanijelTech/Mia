"""Mia autonomy plugin - registration.

`plugin.yaml` only declares the tools; Hermes needs `register(ctx)` to make
them callable. This file used to be empty, so the agent never saw the
system/plan/job tools even though the handlers and schemas existed.
"""

from . import schemas, tools

TOOLSET = "system"


def _schemas() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for attr in dir(schemas):
        if not attr.isupper():
            continue
        schema = getattr(schemas, attr)
        if isinstance(schema, dict) and schema.get("name"):
            out[str(schema["name"])] = schema
    return out


def register(ctx):
    for name, schema in _schemas().items():
        handler = getattr(tools, name, None)
        if handler is None:
            continue
        ctx.register_tool(name=name, toolset=TOOLSET, schema=schema,
                          handler=handler)

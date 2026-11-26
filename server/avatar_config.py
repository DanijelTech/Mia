"""Avatar appearance settings: defaults, validation and persistence helpers.

Pure stdlib module so tests can exercise it without importing the heavy
server. The keys mirror `server/hud/avatar/presets.js`; `tests/test_avatar.py`
fails if the two lists drift apart.
"""

from __future__ import annotations

import re

COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

DEFAULTS = {
    "enabled": True,
    "model": "/hud/avatar/models/mia-female.glb",
    "idle": "/hud/avatar/models/mia-female-idle.glb",

    "outfit": "casual",
    "top": True, "bottom": True, "footwear": True, "glasses": False,
    "topStyle": "casual",
    "topColor": "#1d3f52", "bottomColor": "#101820", "footwearColor": "#101820",
    "glassesColor": "#101820", "topRoughness": 0.8, "topMetalness": 0.0,

    "hair": True, "hairStyle": "default", "hairLook": "natural",
    "hairColor": "#3b2418", "hairScale": 1.0, "hairVolume": 1.0,
    "skinTone": "#ffffff", "eyeColor": "#5a7d8c",

    "bodyShape": "natural",
    "height": 1.0, "build": 1.0, "headSize": 1.0, "headWidth": 1.0,
    "neckLength": 1.0, "eyeSize": 1.0, "armLength": 1.0, "legLength": 1.0,
    "shoulderWidth": 1.0, "hipWidth": 1.0, "handSize": 1.0, "footSize": 1.0,

    "mood": "neutral", "smile": 0.0, "browRaise": 0.0, "eyeWide": 0.0,

    "autoBlink": True, "blinkSpeed": 1.0, "breathAmount": 1.0,
    "swayAmount": 1.0, "gazeFollow": 1.0, "idleSpeed": 1.0,
    "gestureAmount": 1.0,

    "camera": "bust", "cameraDistance": 1.0, "cameraHeight": 0.0,
    "cameraYaw": 0.0, "cameraFov": 32.0, "cameraParallax": 1.0,
    "autoOrbit": False,

    "light": "studio", "exposure": 1.05, "envIntensity": 1.0,
    "keyColor": "#ffe4c8", "keyIntensity": 3.2,
    "rimColor": "#00e5ff", "rimIntensity": 2.4,
    "fillColor": "#19f0d8", "fillIntensity": 2.2,
    "ambientColor": "#9fd8e8", "ambientIntensity": 1.5,

    "background": "transparent", "backgroundColor": "#050b14",
    "quality": "high", "shadows": True, "fpsCap": 0, "pixelRatio": 0.0,
}

COLOR_KEYS = frozenset({
    "topColor", "bottomColor", "footwearColor", "glassesColor", "hairColor",
    "skinTone", "eyeColor", "keyColor", "rimColor", "fillColor",
    "ambientColor", "backgroundColor",
})

BOOL_KEYS = frozenset({
    "enabled", "top", "bottom", "footwear", "glasses", "hair",
    "autoBlink", "autoOrbit", "shadows",
})

STRING_KEYS = frozenset({
    "model", "idle", "outfit", "topStyle", "hairStyle", "hairLook",
    "bodyShape", "mood", "camera", "light", "background", "quality",
})

RANGES = {
    "topRoughness": (0.0, 1.0),
    "topMetalness": (0.0, 1.0),
    "hairScale": (0.6, 1.4),
    "hairVolume": (0.6, 1.5),
    "height": (0.75, 1.35),
    "build": (0.75, 1.4),
    "headSize": (0.75, 1.35),
    "headWidth": (0.8, 1.25),
    "neckLength": (0.8, 1.3),
    "eyeSize": (0.7, 1.4),
    "armLength": (0.85, 1.15),
    "legLength": (0.85, 1.15),
    "shoulderWidth": (0.8, 1.25),
    "hipWidth": (0.8, 1.25),
    "handSize": (0.8, 1.3),
    "footSize": (0.8, 1.3),
    "smile": (0.0, 1.0),
    "browRaise": (0.0, 1.0),
    "eyeWide": (0.0, 1.0),
    "blinkSpeed": (0.3, 2.5),
    "breathAmount": (0.0, 2.0),
    "swayAmount": (0.0, 2.5),
    "gazeFollow": (0.0, 1.5),
    "idleSpeed": (0.3, 2.0),
    "gestureAmount": (0.0, 2.0),
    "cameraDistance": (0.6, 2.5),
    "cameraHeight": (-0.25, 0.35),
    "cameraYaw": (-60.0, 60.0),
    "cameraFov": (18.0, 60.0),
    "cameraParallax": (0.0, 2.5),
    "exposure": (0.4, 2.0),
    "envIntensity": (0.0, 2.0),
    "keyIntensity": (0.0, 6.0),
    "rimIntensity": (0.0, 6.0),
    "fillIntensity": (0.0, 6.0),
    "ambientIntensity": (0.0, 4.0),
    "fpsCap": (0.0, 120.0),
    "pixelRatio": (0.0, 3.0),
}

INT_KEYS = frozenset({"fpsCap"})


def merge(data) -> dict:
    """Defaults plus every known key from ``data`` (unknown keys dropped)."""
    cfg = dict(DEFAULTS)
    if isinstance(data, dict):
        for key, value in data.items():
            if key in DEFAULTS:
                cfg[key] = value
    return cfg


def sanitize(body, base=None) -> dict:
    """Validate a settings patch and return the merged config.

    Raises ``ValueError`` for a known key with an unusable value. Unknown keys
    are ignored so older clients keep working.
    """
    if not isinstance(body, dict):
        raise ValueError("config must be an object")
    cfg = merge(base if base is not None else DEFAULTS)
    for key, value in body.items():
        if key not in DEFAULTS:
            continue
        if key in COLOR_KEYS:
            if not isinstance(value, str) or not COLOR_RE.match(value):
                raise ValueError(f"invalid color for {key}")
            cfg[key] = value.lower()
        elif key in BOOL_KEYS:
            if not isinstance(value, bool):
                raise ValueError(f"invalid boolean for {key}")
            cfg[key] = value
        elif key in STRING_KEYS:
            if not isinstance(value, str) or len(value) > 300:
                raise ValueError(f"invalid {key}")
            cfg[key] = value
        elif key in RANGES:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"invalid number for {key}")
            lo, hi = RANGES[key]
            number = min(hi, max(lo, float(value)))
            cfg[key] = int(round(number)) if key in INT_KEYS else number
    return cfg

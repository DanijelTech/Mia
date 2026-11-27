"""Guards for the HUD entry page: it must boot past the overlay.

A top-level call that runs before a `const` it needs throws a ReferenceError
(temporal dead zone) and aborts the whole inline script, leaving the boot
overlay on screen with only "MIA / HERMES NEVRALNI VMESNIK" visible.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

HUD = Path(__file__).resolve().parent.parent / "server" / "hud"
INDEX = (HUD / "index.html").read_text(encoding="utf-8")


class HudBootOrderTests(unittest.TestCase):
    def test_brain_geometry_exists_before_the_first_draw(self):
        self.assertLess(INDEX.index("const BRAIN_OUTLINE"),
                        INDEX.index("\nsizeCanvas();"),
                        "sizeCanvas() runs before BRAIN_OUTLINE is declared")

    def test_boot_overlay_is_dismissed_by_the_script(self):
        self.assertIn('boot.style.display="none"', INDEX)
        self.assertIn("bootSequence(", INDEX)

    def test_inline_script_has_no_call_before_declaration_of_the_reactor(self):
        # every const/let the reactor needs must be declared above the first call
        call = INDEX.index("\nsizeCanvas();")
        for name in ("const cv=", "const RDPR=", "let brain=",
                     "const STATE_STYLE=", "function buildBrain(",
                     "const BRAIN_OUTLINE="):
            with self.subTest(name=name):
                self.assertLess(INDEX.index(name), call)

    def test_brain_builds_are_guarded_against_a_zero_size_canvas(self):
        self.assertIn("if(!(W>20&&H>20))", INDEX)


if __name__ == "__main__":
    unittest.main()

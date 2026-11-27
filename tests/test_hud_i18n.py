"""The HUD must stay fully translated: every static string has an entry."""

from __future__ import annotations

import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

HUD = Path(__file__).resolve().parent.parent / "server" / "hud"
PAGES = ("index.html", "settings.html", "capabilities.html",
         "autonomy.html", "learning.html", "background.html")
I18N = HUD / "i18n.js"

# Numbers, symbols and product/code names need no translation.
SKIP = {
    "CPU", "OS", "TTS", "STT", "KANBAN", "MIA", "OVERRIDE", "Hermes API",
    "hermes-agent", "mia-main", "mia:user:main", "cli", "view", "firefox",
    "use strict", "you live", "mia", "sys", "you", "approval requested",
    "standby", "listening", "thinking", "speaking", "tool", "pref.browser",
    "mia-ctl pkg install", "mia-ctl windows focus \"Chrome\"",
    "mia-open https://…", "disk_free_percent", "false.", "autonomy.auto_install",
    "HUD potrditev", "tab on", "pane on", "btn danger", "btn viewBtn",
    "dot off", "dot on", "holo pos-", "holoChroma c1", "holoChroma c2",
    "<", "✕ CLOSE", "240 Hz", "70 Hz", "3600 / 08:00 / 600",
    "Clear the visible chat (history stays in Hermes)", "Click to talk",
    'mia-ctl windows focus "Chrome" mia-open https://…',
}


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.texts: list[str] = []
        self.attrs: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        for key, value in attrs:
            if key in ("placeholder", "title", "aria-label", "alt") and value:
                self.attrs.append(" ".join(value.split()))

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._skip:
            return
        text = " ".join(data.split())
        if text:
            self.texts.append(text)


def _dict_keys() -> list[str]:
    source = I18N.read_text(encoding="utf-8")
    block = source[source.index("const DICT"):source.index("const PREFIX")]
    return [k.replace('\\"', '"') for k in
            re.findall(r'"((?:[^"\\]|\\.)+)"\s*:', block)]


def _needs_translation(text: str) -> bool:
    if not text or text in SKIP:
        return False
    if re.fullmatch(r"[0-9\s.:/|·—–+#%×x<>-]+", text):
        return False
    return bool(re.search(r"[A-Za-zČŠŽĆĐčšžćđ]{2}", text))


class HudI18nTests(unittest.TestCase):
    def test_every_page_loads_the_language_layer(self):
        for page in PAGES:
            with self.subTest(page=page):
                html = (HUD / page).read_text(encoding="utf-8")
                self.assertIn("/hud/i18n.js", html)

    def test_dictionary_has_no_duplicate_keys(self):
        keys = _dict_keys()
        dupes = {k for k in keys if keys.count(k) > 1}
        self.assertEqual(dupes, set())

    def test_all_static_strings_are_translated(self):
        keys = set(_dict_keys())
        missing: list[str] = []
        for page in PAGES:
            collector = _Collector()
            collector.feed((HUD / page).read_text(encoding="utf-8"))
            for text in collector.texts + collector.attrs:
                if _needs_translation(text) and text not in keys:
                    missing.append(f"{page}: {text}")
        self.assertEqual(missing, [], "untranslated HUD strings:\n" +
                         "\n".join(sorted(set(missing))))


if __name__ == "__main__":
    unittest.main()

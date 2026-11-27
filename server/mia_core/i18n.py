"""Bilingual deterministic replies (Slovenian / English).

The LLM answers in the language the user speaks, but a large part of Mia is
deterministic: time, weather, media control, volume, confirmations, autonomy
answers. Those strings used to be Slovenian-only, which made the HUD's ENG
switch feel broken. This module is the single place that turns a deterministic
Slovenian sentence into English when the UI language is English.

Design rules:
  * stdlib only, no imports from the server;
  * pure functions, safe to call from any thread;
  * an unknown sentence is returned unchanged (never mangled);
  * the language can come from the HUD (``set_lang``) or the environment
    (``MIA_LANG``), so subprocesses and CLIs behave the same as the server.
"""

from __future__ import annotations

import os
import re

SUPPORTED = ("sl", "en")
_ENV = "MIA_LANG"


def normalize_lang(value: object, default: str = "sl") -> str:
    text = str(value or "").strip().lower()
    if text.startswith("en"):
        return "en"
    if text.startswith("sl") or text.startswith("si"):
        return "sl"
    return default


def set_lang(lang: object) -> str:
    value = normalize_lang(lang)
    os.environ[_ENV] = value
    return value


def current_lang() -> str:
    return normalize_lang(os.environ.get(_ENV), "sl")


def is_english(lang: object | None = None) -> bool:
    return normalize_lang(lang if lang is not None else current_lang()) == "en"


# --------------------------------------------------------------- catalog
# Short server-owned confirmations. Autonomy/intent sentences go through
# ``localize`` instead, because they are built dynamically.
CATALOG: dict[str, tuple[str, str]] = {
    # key: (slovenian, english)
    "media.stopped": ("Ustavila sem glasbo, šefe.", "I stopped the music, boss."),
    "media.nothing": ("Nič ne igra, šefe.", "Nothing is playing, boss."),
    "media.no_active": ("Ni aktivnega predvajanja, šefe.",
                        "Nothing is playing right now, boss."),
    "media.opened_browser": ("Odprla sem ga v brskalniku, šefe.",
                             "I opened it in the browser, boss."),
    "media.browser_failed": ("Brskalnika nisem mogla odpreti, šefe.",
                             "I couldn't open the browser, boss."),
    "media.search_opened": ("Odprla sem YouTube iskanje, šefe.",
                            "I opened the YouTube search, boss."),
    "media.here": ("Evo šefe.", "Here you go, boss."),
    "media.found_not_open": ("Našla sem, a nisem mogla odpreti, šefe.",
                             "I found it but couldn't open it, boss."),
    "media.nothing_found": ("Nisem našla ničesar, šefe.",
                            "I didn't find anything, boss."),
    "enroll.saved": ("Zapomnjeno, šefe — ta glas zdaj poznam.",
                     "Got it, boss — I know this voice now."),
    "feedback.positive": ("Zapomnjeno, šefe — to je zdaj pravi postopek.",
                          "Noted, boss — that is the correct procedure now."),
    "feedback.negative": ("Prav, šefe — zapomnila sem si, da tako ne deluje.",
                          "Okay, boss — I noted that this way does not work."),
    "remember.saved": ("Shranjeno, šefe — postopek sem si zapomnila.",
                       "Saved, boss — I remembered the procedure."),
    "volume.unavailable": ("Glasnosti ne morem spremeniti, šefe.",
                           "I can't change the volume, boss."),
    "volume.unavailable_tool": (
        "Glasnosti ne morem spremeniti — mia-volume ni na voljo, šefe.",
        "I can't change the volume — mia-volume is not available, boss."),
    "volume.set": ("Glasnost {value}, šefe.", "Volume {value}, boss."),
    "volume.toggled": ("Zvok preklopljen, šefe.", "Sound toggled, boss."),
    "hermes.unreachable": (
        "Hermesov gateway ni dosegljiv. Zaženi hermes gateway in poskusi znova.",
        "The Hermes gateway is unreachable. Start hermes gateway and try again."),
    "calibration.saved": ("Kalibracija je shranjena. Zdaj te prepoznam tudi od daleč.",
                          "Calibration saved. I now recognise you from across the room."),
    "calibration.failed": ("Kalibracija ni uspela. Poskusi znova.",
                           "Calibration failed. Please try again."),
    "google.opened": ("Odprla sem v brskalniku, šefe.",
                      "I opened it in the browser, boss."),
    "google.failed": ("Brskalnika nisem mogla odpreti, šefe.",
                      "I couldn't open the browser, boss."),
}


def t(key: str, lang: object | None = None, **kwargs) -> str:
    """Return a catalog string in the requested language (English by default
    only when the language is English)."""
    sl, en = CATALOG.get(key, (key, key))
    text = en if is_english(lang) else sl
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            pass
    return text


# ------------------------------------------------------------ localization
# Exact sentences. Keep these in sync with intents.py / service.py / health.py.
_EXACT: dict[str, str] = {
    # generic
    "V redu.": "Okay.",
    "Narejeno.": "Done.",
    "Tega ne razumem, šefe.": "I don't understand that, boss.",
    "Tega dejanja še ne znam.": "I don't know that action yet.",
    "Tega ne znam več ponoviti, šefe.": "I can't repeat that any more, boss.",
    "Nič ne čaka na potrditev, šefe.": "Nothing is waiting for confirmation, boss.",
    "V redu, preklicano.": "Okay, cancelled.",
    "Politika mi tega ne dovoli, šefe.": "Policy does not allow that, boss.",
    "Za to dejanje mi manjka orodje. Poglej prilagoditev v HUD-u.":
        "I'm missing a tool for that. Check adaptation in the HUD.",
    "Načrt izveden.": "Plan executed.",
    "Načrt ni uspel.": "Plan failed.",
    "Načrta ne poznam.": "I don't know that plan.",
    "Opravilo shranjeno.": "Job saved.",
    "Katero opravilo naj prekličem?": "Which job should I cancel?",
    "Nič ne predvajam.": "Nothing is playing.",
    "Ničesar nisem našla za zapreti.": "I found nothing to close.",
    "Nobeno okno ni odprto.": "No window is open.",
    "Ni velikih datotek.": "No large files.",
    "Ničesar nisem našla.": "I found nothing.",
    "Ni nedavnih datotek.": "No recent files.",
    "Ni omrežij.": "No networks.",
    "Ni omrežja.": "No network.",
    "Ni zadetkov.": "No matches.",
    "Ni novih opozoril.": "No new alerts.",
    "Nobene naloge še ni bilo.": "No task has run yet.",
    "Nimam še nobenega opravila ali pravila.": "I have no jobs or rules yet.",
    "Sistem je posodobljen.": "The system is up to date.",
    "Posodobitve pripravljene.": "Updates are ready.",
    "Odložišče je prazno.": "The clipboard is empty.",
    "Odprto.": "Opened.",
    "Kopirano.": "Copied.",
    "Premaknjeno.": "Moved.",
    "Preimenovano.": "Renamed.",
    "Predvajanje.": "Playback.",
    "Zaprla sem predvajanje.": "Playback closed.",
    "Zaklenjeno.": "Locked.",
    "V spanje.": "Suspending.",
    "Ponovni zagon.": "Rebooting.",
    "Ugasnjeno.": "Shutting down.",
    "Glasnost nastavljena.": "Volume set.",
    "Svetlost nastavljena.": "Brightness set.",
    "Pojačano.": "Louder.",
    "Zmanjšano.": "Quieter.",
    "Utišano.": "Muted.",
    "Zvok vklopljen.": "Sound on.",
    "Pavza.": "Paused.",
    "Naslednja.": "Next.",
    "Prejšnja.": "Previous.",
    "Vse, kar potrebujem na tem računalniku, je na voljo.":
        "Everything I need on this machine is available.",
    "Tega procesa ne vidim.": "I can't see that process.",
    "Ni aktivne omrežne povezave": "No active network connection",
    "Opomnik": "Reminder",
    "Redni opravk": "Recurring task",
    "Dnevni opravk": "Daily task",
    "Delovni način": "Work mode",
    "Načrt je nevaren; dodaj --yes za izvedbo.":
        "The plan is destructive; add --yes to run it.",
    "Nič ne igra, šefe.": "Nothing is playing, boss.",
    "Evo šefe.": "Here you go, boss.",
    "Ni aktivnega predvajanja, šefe.": "Nothing is playing right now, boss.",
    "Nisem našla ničesar, šefe.": "I didn't find anything, boss.",
    "Našla sem, a nisem mogla odpreti, šefe.":
        "I found it but couldn't open it, boss.",
    "Odprla sem YouTube iskanje, šefe.": "I opened the YouTube search, boss.",
    "Odprla sem ga v brskalniku, šefe.": "I opened it in the browser, boss.",
    "Odprla sem v brskalniku, šefe.": "I opened it in the browser, boss.",
    "Brskalnika nisem mogla odpreti, šefe.": "I couldn't open the browser, boss.",
    "Zapomnjeno, šefe — ta glas zdaj poznam.":
        "Got it, boss — I know this voice now.",
    "Zapomnjeno, šefe — to je zdaj pravi postopek.":
        "Noted, boss — that is the correct procedure now.",
    "Prav, šefe — zapomnila sem si, da tako ne deluje.":
        "Okay, boss — I noted that this way does not work.",
    "Shranjeno, šefe — postopek sem si zapomnila.":
        "Saved, boss — I remembered the procedure.",
    "Glasnosti ne morem spremeniti, šefe.":
        "I can't change the volume, boss.",
    "Glasnosti ne morem spremeniti — mia-volume ni na voljo, šefe.":
        "I can't change the volume — mia-volume is not available, boss.",
    "Zvok preklopljen, šefe.": "Sound toggled, boss.",
    "Kalibracija je shranjena. Zdaj te prepoznam tudi od daleč.":
        "Calibration saved. I now recognise you from across the room.",
    "Kalibracija ni uspela. Poskusi znova.":
        "Calibration failed. Please try again.",
    "Hermesov gateway ni dosegljiv. Zaženi hermes gateway in poskusi znova.":
        "The Hermes gateway is unreachable. Start hermes gateway and try again.",
    "Sistem brez systemd: storitve niso na voljo.":
        "The system has no systemd; services are unavailable.",
    "Ni velikih datotek.": "No large files.",
    "Pozor, šefe.": "Attention, boss.",
    "Opazila sem spremembo.": "I noticed a change.",
    "Čas je za čiščenje diska.": "Time to clean the disk.",
    "Zakleni zaslon.": "Lock the screen.",
    "Opozarjam te.": "I'm warning you.",
    "V redu, opomnila te bom.": "Okay, I'll remind you.",
    "Takoj.": "Right away.",
    "Še delam.": "Still working.",
    "Skoraj.": "Almost.",
    "Prenizko je. Stopi bliže ali govori glasneje.":
        "That is too quiet. Step closer or speak louder.",
    "Stopi čisto blizu mikrofona in reci: Mia, to je moj glas.":
        "Step right up to the microphone and say: Mia, this is my voice.",
    "Stopi dva do tri metre stran in reci: Mia, ali me slišiš?":
        "Step two to three metres away and say: Mia, can you hear me?",
    "Pojdi čim dlje, pet do šest metrov, in reci: Mia, to je moj glas.":
        "Go as far as you can, five to six metres, and say: Mia, this is my voice.",
    "BLIZU mikrofona (0,5 m)": "NEAR the microphone (0.5 m)",
    "SREDNJE oddaljenosti (2–3 m)": "MID distance (2–3 m)",
    "DALEČ (5–6 m)": "FAR (5–6 m)",
}

# Dynamic sentences. Each entry: (compiled pattern, English template).
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^Glasnost je (.+?) odstotkov\.$"), r"Volume is \1 percent."),
    (re.compile(r"^Glasnost (\d+)\.$"), r"Volume \1."),
    (re.compile(r"^Glasnost (\d+), šefe\.$"), r"Volume \1, boss."),
    (re.compile(r"^Svetlost (\d+)\.$"), r"Brightness \1."),
    (re.compile(r"^Svetlost povečana\.$"), "Brightness increased."),
    (re.compile(r"^Svetlost zmanjšana\.$"), "Brightness decreased."),
    (re.compile(r"^Posnetek shranjen v (.+)\.$"), r"Screenshot saved to \1."),
    (re.compile(r"^Posnetek shranjen\.$"), "Screenshot saved."),
    (re.compile(r"^V odložišču je: (.+)$"), r"The clipboard contains: \1"),
    (re.compile(r"^Odprla sem (.+)\.$"), r"I opened \1."),
    (re.compile(r"^Zaprla sem (\d+) oken\.$"), r"I closed \1 windows."),
    (re.compile(r"^Zaprla sem (.+)\.$"), r"I closed \1."),
    (re.compile(r"^Odprta okna: (.+)\.$"), r"Open windows: \1."),
    (re.compile(r"^Predvaja se (.+)\.$"), r"Playing \1."),
    (re.compile(r"^Najbolj obremenjujejo: (.+)\.$"), r"Top consumers: \1."),
    (re.compile(r"^Našla sem: (.+)\.$"), r"I found: \1."),
    (re.compile(r"^Nedavne datoteke: (.+)\.$"), r"Recent files: \1."),
    (re.compile(r"^Mapa (.+) je pripravljena\.$"), r"Folder \1 is ready."),
    (re.compile(r"^(.+) je v smeteh\.$"), r"\1 is in the trash."),
    (re.compile(r"^(.+) je izbrisan\.$"), r"\1 was deleted."),
    (re.compile(r"^Arhiv (.+) je pripravljen\.$"), r"Archive \1 is ready."),
    (re.compile(r"^Razširjeno v (.+)\.$"), r"Extracted to \1."),
    (re.compile(r"^Razširjam v (.+)\.$"), r"Extracting to \1."),
    (re.compile(r"^Velikost je (.+)\.$"), r"Size is \1."),
    (re.compile(r"^Največja je (.+), (.+)\.$"), r"The largest is \1, \2."),
    (re.compile(r"^Vidim: (.+)\.$"), r"I see: \1."),
    (re.compile(r"^Požarni zid (.+)\.$"), r"Firewall \1."),
    (re.compile(r"^Povezujem se na (.+)\.$"), r"Connecting to \1."),
    (re.compile(r"^Ping (.+) končan\.$"), r"Ping \1 finished."),
    (re.compile(r"^IP (.+)\.$"), r"IP \1."),
    (re.compile(r"^Wi-Fi (.+)\.$"), r"Wi-Fi \1."),
    (re.compile(r"^Paket sem namestila\.$"), "Package installed."),
    (re.compile(r"^Paket sem odstranila\.$"), "Package removed."),
    (re.compile(r"^(\d+) posodobitev je na voljo\.$"), r"\1 updates available."),
    (re.compile(r"^Opravilo (\d+) preklicano\.$"), r"Job \1 cancelled."),
    (re.compile(r"^Opravila (\d+) ne najdem\.$"), r"Job \1 not found."),
    (re.compile(r"^Storitev (.+) deluje\.$"), r"Service \1 is running."),
    (re.compile(r"^Storitev (.+) ne deluje\.$"), r"Service \1 is not running."),
    (re.compile(r"^Storitev (.+) zagnana\.$"), r"Service \1 started."),
    (re.compile(r"^Storitev (.+) ustavljena\.$"), r"Service \1 stopped."),
    (re.compile(r"^Storitev (.+) ponovno zagnana\.$"), r"Service \1 restarted."),
    (re.compile(r"^Ustavila sem (.+)\.$"), r"I stopped \1."),
    (re.compile(r"^Načrt se je ustavil: (.+?)\.?$"), r"The plan stopped: \1."),
    (re.compile(r"^Načrta ne morem sestaviti: (.+?)\.?$"),
     r"I can't build the plan: \1."),
    (re.compile(r"^Ni uspelo\. (.+)$"), r"Failed. \1"),
    (re.compile(r"^Ni uspelo: (.+)$"), r"Failed: \1"),
    (re.compile(r"^Pripravljena sem na (\d+) odstotkov\. Manjka mi (.+?)\. (.+)$"),
     r"I am \1 percent ready. I'm missing \2. \3"),
    (re.compile(r"^Pozor, šefe: ocena (\d+) od 100\. (.+)$"),
     r"Attention, boss: score \1 of 100. \2"),
    (re.compile(r"^Ocena (\d+) od 100\. Opazila sem: (.+)$"),
     r"Score \1 of 100. I noticed: \2"),
    (re.compile(r"^Sistem je zdrav, ocena (\d+) od 100\.$"),
     r"The system is healthy, score \1 of 100."),
    (re.compile(r"^Zadnja naloga: (.+), stanje (.+)\.$"),
     r"Last task: \1, status \2."),
    (re.compile(r"^Opozorila: (.+)$"), r"Alerts: \1"),
    (re.compile(r"^Imam (.+)\.$"), r"I have \1."),
    (re.compile(r"^Opravila: (.+)$"), r"Jobs: \1"),
    (re.compile(r"^(.+), jedro (.+), (\d+) jeder (.+), (.+) RAM, namizje (.+)\.$"),
     r"\1, kernel \2, \3 cores \4, \5 RAM, desktop \6."),
    (re.compile(r"^CPU (.+?), RAM (.+?), disk (.+?)% zaseden(?:, (.+))?\.$"),
     r"CPU \1, RAM \2, disk \3% used\4."),
    (re.compile(r"^baterija (\d+)%$"), r"battery \1%"),
    (re.compile(r"^(\d+) stopinj$"), r"\1 degrees"),
    # confirmation prompts
    (re.compile(r"^Naj izvedem\? Potrdi s »ja«\.$"),
     "Should I do it? Confirm with yes."),
    (re.compile(r"^Naj trajno izbrišem (.+)\? Potrdi s »ja«\.$"),
     r"Should I permanently delete \1? Confirm with yes."),
    (re.compile(r"^Naj premaknem (.+) v smeti\? Potrdi s »ja«\.$"),
     r"Should I move \1 to the trash? Confirm with yes."),
    (re.compile(r"^Naj premaknem (.+) v (.+)\? Potrdi s »ja«\.$"),
     r"Should I move \1 to \2? Confirm with yes."),
    (re.compile(r"^Naj preimenujem (.+) v (.+)\? Potrdi s »ja«\.$"),
     r"Should I rename \1 to \2? Confirm with yes."),
    (re.compile(r"^Naj ustavim proces (.+)\? Potrdi s »ja«\.$"),
     r"Should I stop process \1? Confirm with yes."),
    (re.compile(r"^Naj ustavim storitev (.+)\? Potrdi s »ja«\.$"),
     r"Should I stop service \1? Confirm with yes."),
    (re.compile(r"^Naj ponovno zaženem storitev (.+)\? Potrdi s »ja«\.$"),
     r"Should I restart service \1? Confirm with yes."),
    (re.compile(r"^Naj vklopim požarni zid\? Potrdi s »ja«\.$"),
     "Should I enable the firewall? Confirm with yes."),
    (re.compile(r"^Naj izklopim požarni zid\? Potrdi s »ja«\.$"),
     "Should I disable the firewall? Confirm with yes."),
    (re.compile(r"^Naj namestim (.+)\? Potrdi s »ja«\.$"),
     r"Should I install \1? Confirm with yes."),
    (re.compile(r"^Naj odstranim (.+)\? Potrdi s »ja«\.$"),
     r"Should I remove \1? Confirm with yes."),
    (re.compile(r"^Naj osvežim in posodobim sistem\? Potrdi s »ja«\.$"),
     "Should I refresh and update the system? Confirm with yes."),
    (re.compile(r"^Naj počistim temp datoteke in poiščem velike datoteke\? "
                r"Potrdi s »ja«\.$"),
     "Should I clean temporary files and look for large files? Confirm with yes."),
    (re.compile(r"^Naj ugasnem računalnik\? Potrdi s »ja«\.$"),
     "Should I shut down the computer? Confirm with yes."),
    (re.compile(r"^Naj ponovno zaženem računalnik\? Potrdi s »ja«\.$"),
     "Should I reboot the computer? Confirm with yes."),
    (re.compile(r"^Naj se ustavim\? Potrdi s »ja«\.$"),
     "Should I stop? Confirm with yes."),
    (re.compile(r"^Preklopim v nočni način\? Potrdi s »ja«\.$"),
     "Switch to night mode? Confirm with yes."),
    (re.compile(r"^Pripravljam delovni način\.$"), "Preparing work mode."),
    (re.compile(r"^Arhiviram v (.+)\.$"), r"Archiving to \1."),
    (re.compile(r"^Ustvarjam mapo (.+)\.$"), r"Creating folder \1."),
    (re.compile(r"^V redu, opomnila te bom (.+)\.$"),
     r"Okay, I'll remind you \1."),
    (re.compile(r"^V redu, vsak dan ob (.+)\.$"), r"Okay, every day at \1."),
    (re.compile(r"^V redu, vsakih (\d+) (\w+)\.$"), r"Okay, every \1 \2."),
    (re.compile(r"^V redu, sporočila bom, ko bo (.+)\.$"),
     r"Okay, I'll tell you when \1."),
    (re.compile(r"^Pripravljam delovni način\.$"), "Preparing work mode."),
    (re.compile(r"^Nič ne igra, šefe\.$"), "Nothing is playing, boss."),
    (re.compile(r"^Glasnosti ne morem spremeniti, šefe\.$"),
     "I can't change the volume, boss."),
    (re.compile(r"^Hvala, šefe\.$"), "Thank you, boss."),
    # health checks (HUD autonomy page and spoken summary)
    (re.compile(r"^(.+)% prostega prostora \((.+)\)$"), r"\1% free space (\2)"),
    (re.compile(r"^(.+)% zasedenega RAM-a$"), r"\1% RAM used"),
    (re.compile(r"^(.+)% swapa$"), r"\1% swap"),
    (re.compile(r"^load (.+) na (\d+) jedrih$"), r"load \1 on \2 cores"),
    (re.compile(r"^(\d+)% \(na bateriji\)$"), r"\1% (on battery)"),
    (re.compile(r"^(\d+)% \(na napajanju\)$"), r"\1% (on power)"),
    (re.compile(r"^poteče čez (\d+) dni \((.+)\)$"),
     r"expires in \1 days (\2)"),
    (re.compile(r"^(\d+) nalog teče več kot eno uro$"),
     r"\1 tasks have been running for over an hour"),
]

# Health titles and short messages (exact).
_EXACT.update({
    "Korenski disk": "Root disk",
    "Domači disk": "Home disk",
    "Delovni pomnilnik": "Working memory",
    "Obremenitev CPU": "CPU load",
    "Temperatura": "Temperature",
    "Baterija": "Battery",
    "Omrežje": "Network",
    "Čas delovanja": "Uptime",
    "Učna baza": "Learning database",
    "na bateriji": "on battery",
    "na napajanju": "on power",
    # background page / close endpoint
    "zaprto": "closed",
    "plošča zaprta": "panel closed",
    "vse plošče zaprte": "all panels closed",
    "neveljaven id okna": "invalid window id",
    "okno ni Miino in ni medijsko okno brskalnika":
        "the window is not Mia's and not a media browser window",
    "xdotool ni nameščen": "xdotool is not installed",
    "zaprtje ni uspelo": "closing failed",
    "samodejnost ni na voljo": "autonomy is unavailable",
    "neveljaven id opravila": "invalid job id",
    "opravilo ustavljeno": "job stopped",
    "opravila ni": "job not found",
    "procesa ni bilo mogoče najti": "the process was not found",
    "medijska plošča": "media panel",
    "najdeno okno brskalnika": "browser window (found)",
    "TTS storitev": "TTS service",
})

_HELP_EN = (
    "I understand commands for volume, brightness, playback, opening and "
    "closing apps, windows, screenshots, clipboard, files, processes, "
    "services, network, packages, lock and sleep, and reminders. You can ask "
    "about resources, health, capabilities, tasks and the schedule."
)
_HELP_SL_MARKER = "Razumem ukaze za glasnost"


def localize(text: str, lang: object | None = None) -> str:
    """Translate a deterministic Slovenian reply when the language is English."""
    if not text or not is_english(lang):
        return text
    raw = str(text)
    stripped = raw.strip()
    if stripped.startswith(_HELP_SL_MARKER):
        return _HELP_EN
    if stripped in _EXACT:
        return _EXACT[stripped]
    for pattern, repl in _PATTERNS:
        if pattern.match(stripped):
            out = pattern.sub(repl, stripped)
            # A health summary embeds another deterministic sentence after the
            # score ("Pozor … 92 od 100. Ni aktivne omrežne povezave"). Translate
            # known exact phrases inside the remainder too.
            if out != stripped:
                for sl, en in _EXACT.items():
                    if sl in out:
                        out = out.replace(sl, en)
            return out
    return raw

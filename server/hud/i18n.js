/* Mia HUD language layer: SLO / ENG.
 *
 * The dictionary is keyed by the exact (trimmed) Slovenian text that appears in
 * the DOM, so dynamic labels written by the page scripts are translated too:
 * a MutationObserver watches text nodes and the placeholder/title/aria-label
 * attributes. Originals are kept in a WeakMap so switching back to SLO restores
 * the page without a reload.
 *
 * Add a new string: put it in DICT (Slovenian -> English). For messages built
 * with a variable prefix use PREFIX.
 */
(function () {
  "use strict";

  const DICT = {
    /* ---- shell / navigation ---------------------------------------- */
    "NASTAVITVE": "SETTINGS",
    "MIA // NASTAVITVE": "MIA // SETTINGS",
    "SAMODEJNOST": "AUTONOMY",
    "MIA // SAMODEJNOST": "MIA // AUTONOMY",
    "V OZADJU": "BACKGROUND",
    "MIA // V OZADJU": "MIA // BACKGROUND",
    "ZMOGLJIVOSTI": "CAPABILITIES",
    "MIA // ZMOGLJIVOSTI": "MIA // CAPABILITIES",
    "ZNANJE": "KNOWLEDGE",
    "MIA // ZNANJE": "MIA // KNOWLEDGE",
    "▸ KANBAN": "▸ KANBAN",
    "▸ HERMES NADZORNA PLOŠČA": "▸ HERMES DASHBOARD",
    "▸ KLEPET": "▸ CHAT",
    "▸ SAMODEJNOST": "▸ AUTONOMY",
    "▸ V OZADJU": "▸ BACKGROUND",
    "✕ ZAPRI": "✕ CLOSE",
    "ODPRI NASTAVITVE": "OPEN SETTINGS",
    "ODPRI SAMODEJNOST": "OPEN AUTONOMY",
    "ODPRI ZMOGLJIVOSTI": "OPEN CAPABILITIES",
    "ODPRI ZNANJE": "OPEN KNOWLEDGE",
    "ODPRI SEZNAM": "OPEN LIST",
    "ODPRI ZAVIHEK": "OPEN DRAWER",
    "POGLEDI": "VIEWS",
    "SEJA": "SESSION",
    "GLAS": "VOICE",
    "GLAS IN BUDNICA": "VOICE AND WAKE WORD",
    "GLAS · BUDNICA · UČENJE · PREVERJANJE · SISTEM": "VOICE · WAKE WORD · LEARNING · VERIFICATION · SYSTEM",
    "HERMES AGENTNI VMESNIK //": "HERMES AGENT INTERFACE //",
    "HERMES NEVRALNI VMESNIK": "HERMES NEURAL INTERFACE",
    "NOUS HERMES AGENT v0.16": "NOUS HERMES AGENT v0.16",
    "KANBAN": "KANBAN",
    "MIA": "MIA",
    "SISTEM": "SYSTEM",
    "DIAGNOSTIKA": "DIAGNOSTICS",
    "Pregled": "Overview",
    "PREGLED": "OVERVIEW",

    /* ---- main HUD panels ------------------------------------------- */
    "MERITVE IZMENJAVE": "TURN METRICS",
    "Izmenjave": "Turns",
    "Izmenjave danes": "Turns today",
    "Zadnji: govor→zvok": "Last: speech→audio",
    "Zadnji: skupaj": "Last: total",
    "Možgani": "Brain",
    "Pogovor": "Conversation",
    "Obseg spomina": "Memory scope",
    "Aktivne seje": "Active sessions",
    "Tekoči agenti": "Running agents",
    "AKTIVNOST AGENTA": "AGENT ACTIVITY",
    "ZADNJE AKTIVNOSTI": "RECENT ACTIVITY",
    "DNEVNIK": "LOG",
    "STANJE": "STATUS",
    "ČAS": "TIME",
    "SPOROČILO": "MESSAGE",
    "SKUPAJ": "TOTAL",
    "Žetoni danes": "Tokens today",
    "Ocena stroškov danes": "Cost estimate today",
    "STROJI": "MACHINES",
    "Pomnilnik": "Memory",
    "Zasloni": "Displays",
    "Zvočniki": "Speakers",
    "Mikrofon": "Microphone",
    "VIRI": "RESOURCES",
    "Vtičnica": "Socket",
    "Gostitelj": "Host",
    "CPU": "CPU",
    "OS": "OS",
    "TTS": "TTS",
    "STT": "STT",
    "MODELI": "MODELS",
    "STATUS": "STATUS",
    "STOPNJA": "LEVEL",
    "POKRITOST": "COVERAGE",
    "POSODOBITVE": "UPDATES",
    "AVTOMATIZACIJE": "AUTOMATIONS",
    "VRSTA": "TYPE",
    "VELIKOST": "SIZE",
    "DOKAZ": "EVIDENCE",
    "SPROŽILEC": "TRIGGER",
    "Sprožilec": "Trigger",
    "UKAZ": "COMMAND",
    "URNIK": "SCHEDULE",
    "Urnik": "Schedule",
    "NALOGE": "TASKS",
    "Naloge": "Tasks",
    "Naslednji zagon": "Next run",
    "Dejanje": "Action",
    "Stanje": "State",
    "Storitev": "Service",
    "Vrsta": "Type",
    "Vir": "Source",
    "Vrednost": "Value",
    "Vsebina": "Content",
    "Naslov": "Title",
    "Ime": "Name",
    "IME": "NAME",
    "Opravilo": "Job",
    "opravilo": "job",
    "OPRAVILA": "JOBS",
    "Opravila": "Jobs",
    "OPRAVILA IN PRAVILA": "JOBS AND RULES",
    "Opravila / pravila": "Jobs / rules",
    "OPRAVILA SAMODEJNOSTI": "AUTONOMY JOBS",
    "NOVO OPRAVILO ALI PRAVILO": "NEW JOB OR RULE",
    "obvestilo": "notification",
    "Besedilo obvestila": "Notification text",
    "Pogoj: metric op value (npr. disk_free_percent < 10)": "Condition: metric op value (e.g. disk_free_percent < 10)",
    "enkrat čez N sekund": "once in N seconds",
    "vsak dan ob HH:MM": "every day at HH:MM",
    "vsakih N sekund": "every N seconds",
    "ko velja pogoj": "when the condition holds",
    "vsi statusi": "all statuses",
    "vsi izidi": "all outcomes",
    "vsi viri": "all sources",
    "vse kategorije": "all categories",
    "vsa preverjanja": "all checks",
    "ni podatkov": "no data",
    "ni profila": "no profile",
    "profila še ni": "no profile yet",
    "ni aktivnih opravil": "no active jobs",
    "— ni nalog —": "— no tasks —",
    "— ni še aktivnosti —": "— no activity yet —",
    "—": "—",
    "Osveženo": "Refreshed",
    "neznana napaka": "unknown error",
    "ne deluje": "not working",
    "offline — gateway?": "offline — gateway?",
    "offline — ključ?": "offline — key?",
    "zaženi ZDRAVJE": "run HEALTH",
    "zdravstveno poročilo": "health report",
    "čiščenje diska": "disk cleanup",
    "počisti disk": "clean the disk",
    "preveri posodobitve": "check for updates",
    "kaj si avtomatizirala": "what have you automated",
    "kako si": "how are you",
    "koliko je prostega prostora": "how much free space",
    "npr. odpri mi google …": "e.g. open google …",
    "npr. opomni me čez 10 minut, da pijem vodo": "e.g. remind me in 10 minutes to drink water",
    "npr. jutranji pregled": "e.g. morning check",
    "Ukaz se izvede deterministično, brez modela: glasnost, okna, datoteke, procesi, storitve, omrežje, paketi, opomniki in pravila. Nevarna dejanja zahtevajo »ja«.":
      "The command runs deterministically, without a model: volume, windows, files, processes, services, network, packages, reminders and rules. Dangerous actions require »yes«.",
    "Vsak načrt se izvede kot naloga s koraki, preverjanjem in revizijo. Prekinjena naloga se lahko nadaljuje po ponovnem zagonu.":
      "Every plan runs as a task with steps, verification and an audit trail. An interrupted task can resume after a restart.",
    "Mia predlaga orodja, ki jih na tem stroju še nima. Namestitev gre skozi":
      "Mia suggests tools this machine does not have yet. Installation goes through",
    ", z revizijo in potrditvijo. Samodejna namestitev je izklopljena, dokler je v politiki":
      ", with an audit trail and confirmation. Automatic installation stays off while the policy says",
    "Pripravljenost stroja": "Machine readiness",
    "PRIPRAVLJENOST": "READINESS",
    "ZDRAVJE": "HEALTH",
    "Zdravje": "Health",
    "OPOZORILA": "ALERTS",
    "Opozorila": "Alerts",
    "PRILAGODITEV": "ADAPTATION",
    "PRILAGAJANJE · NAČRTI · OPRAVILA · PRAVILA · ZDRAVJE":
      "ADAPTATION · PLANS · JOBS · RULES · HEALTH",
    "ZAZNAJ": "DETECT",
    "ZAZNAJ SISTEM": "DETECT SYSTEM",
    "ZNOVA ZAZNAJ": "DETECT AGAIN",
    "OSVEŽI": "REFRESH",
    "OSVEŽI DETEKCIJO": "REFRESH DETECTION",
    "OSVEŽI SISTEM": "REFRESH SYSTEM",
    "OSVEŽI SPOMIN": "REFRESH MEMORY",
    "PREŽENI URNIK": "RUN SCHEDULE",
    "PREKINI": "CANCEL",
    "DODAJ": "ADD",
    "SHRANI": "SAVE",
    "SHRANJENO": "SAVED",
    "IZVOZ": "EXPORT",
    "IZVED I": "RUN",
    "USTVARJENO": "CREATED",
    "ZADNJE": "RECENT",
    "ČIŠČENJE": "CLEANUP",
    "IŠČI": "SEARCH",
    "ISKANJE": "SEARCH",
    "POKAŽI": "SHOW",
    "POČISTI": "CLEAR",
    "POŠLJI": "SEND",
    "STALNO": "ALWAYS",
    "■ STALNO": "■ ALWAYS",
    "■ USTAVI": "■ STOP",
    "■ USTAVI IN POŠLJI": "■ STOP AND SEND",
    "USTAVI": "STOP",
    "VKLOPI GLAS": "ENABLE VOICE",
    "KODA DOSTOPA": "ACCESS CODE",
    "PRIJAVA": "SIGN IN",
    "ŽETON JE POTEKEL ALI NI PRAV — VNESI NOVEGA":
      "THE TOKEN EXPIRED OR IS WRONG — ENTER A NEW ONE",

    /* ---- status labels written by scripts --------------------------- */
    "PRIPRAVLJEN": "READY",
    "KLIKNI MOŽGANE ALI PRESLEDNICO": "CLICK THE BRAIN OR PRESS SPACE",
    "POSLUŠAM": "LISTENING",
    "OBDELUJEM": "PROCESSING",
    "DELAM": "WORKING",
    "GOVORIM": "SPEAKING",
    "POVEZAVA VZPOSTAVLJENA": "CONNECTION ESTABLISHED",
    "POVEZAVA PREKINJENA": "CONNECTION LOST",
    "brez povezave": "offline",
    "povezan": "connected",
    "V ŽIVO": "LIVE",
    "RECI »MIA …« ALI KAR GOVORI": "SAY »MIA …« OR JUST TALK",
    "RECI »MIA …« · ODGOVOR PRIPRAVIM SAMA": "SAY »MIA …« · I PREPARE THE ANSWER MYSELF",
    "GLAS NI PREPOZNAN — MIA UBOGA LE TVOJEMU GLASU":
      "VOICE NOT RECOGNISED — MIA ONLY OBEYS YOUR VOICE",
    "GOVORI NARAVNO · ODGOVOR PRIPRAVIM SAMA":
      "SPEAK NATURALLY · I PREPARE THE ANSWER MYSELF",
    "SLIŠIM …": "I HEAR …",
    "MIA GOVORI — POČAKAJ": "MIA IS SPEAKING — WAIT",
    "GOVORI ZDAJ": "SPEAK NOW",
    "GOVORI ZDAJ —": "SPEAK NOW —",
    "Mia govori … poslušaj in počakaj na znak GOVORI ZDAJ.":
      "Mia is speaking … listen and wait for the SPEAK NOW cue.",
    "Mia bo govorila; ti ponavljaj za njo.": "Mia will speak; repeat after her.",
    "Mia odgovarja — počakaj, ali pritisni STOP za prekinitev":
      "Mia is answering — wait, or press STOP to interrupt",
    "KLIKNI ZNOVA ZA POŠILJANJE": "CLICK AGAIN TO SEND",
    "DOSTOP ZAVRNJEN": "ACCESS DENIED",
    "MIKROFON NI NA VOLJO": "MICROPHONE UNAVAILABLE",
    "NAPAKA POVEZAVE": "CONNECTION ERROR",
    "NAPAKA KALIBRACIJE": "CALIBRATION ERROR",
    "NI ODGOVORA STREŽNIKA": "NO SERVER RESPONSE",
    "NI ZVOKA": "NO SOUND",
    "STREŽNIK NI POVEZAN": "SERVER NOT CONNECTED",
    "VSI SISTEMI DELUJEJO": "ALL SYSTEMS OPERATIONAL",
    "SPOMINSKI SISTEMI USKLAJENI": "MEMORY SYSTEMS IN SYNC",
    "GLASOVNA POVEZAVA VZPOSTAVLJENA": "VOICE LINK ESTABLISHED",
    "GLASOVNI STREŽNIK POVEZAN": "VOICE SERVER CONNECTED",
    "INICIALIZACIJA NEVRALNEGA VMESNIKA": "INITIALISING NEURAL INTERFACE",
    "NALAGANJE MODULOV HUD": "LOADING HUD MODULES",
    "POVEZOVANJE Z JEDROM HERMES": "CONNECTING TO THE HERMES CORE",
    "PRIPRAVLJAM …": "PREPARING …",
    "Počakaj trenutek.": "One moment.",
    "Preverjam mikrofon in strežnik …": "Checking microphone and server …",
    "OROZJA IZKLOPLJENA. GRELNIK VKLOPLJEN.": "TOOLS OFF. HEATER ON.",
    "HUD se znova povezuje. Če se ne poveže v 5 s, preveri, da Mia teče na vratih 8766.":
      "The HUD is reconnecting. If it does not connect within 5 s, check that Mia runs on port 8766.",
    "Strežnik je vrnil napako.": "The server returned an error.",
    "Mia HUD je pripravljen. Klikni možgane ali pritisni preslednico.":
      "Mia HUD is ready. Click the ring or press space.",
    "neprestano poslušanje vklopljeno": "continuous listening on",
    "neprestano poslušanje izklopljeno": "continuous listening off",
    "mikrofon blokiran:": "microphone blocked:",
    "mikrofon spet pošilja zvok": "microphone is sending sound again",
    "mikrofon ne pošilja zvoka — preveri dovoljenje in izbiro mikrofona v brskalniku":
      "microphone sends no sound — check the permission and the selected input in the browser",
    "Brskalnik ni dovolil mikrofona:": "The browser did not allow the microphone:",
    "Ukaza nisem mogla poslati:": "Could not send the command:",
    "pogovor ponastavljen": "conversation reset",
    "poslano — Mia obdeluje": "sent — Mia is processing",
    "izvajanje ustavljeno": "run stopped",
    "glasovni strežnik ni dosegljiv": "voice server unreachable",
    "napaka klepeta:": "chat error:",
    "samodejnost ni dosegljiva:": "autonomy unavailable:",
    "zdravje:": "health:",
    "ni uspelo:": "failed:",
    "Ni uspelo:": "Failed:",
    "napaka:": "error:",
    "Nič ni igralo.": "Nothing was playing.",
    "Nič ne igra, šefe.": "Nothing is playing, boss.",
    "Ustavila sem glasbo, šefe.": "Playback stopped, boss.",
    "Ustavi to storitev? Mia morda ne bo več odgovarjala, dokler je ne zaženeš znova.":
      "Stop this service? Mia may stop answering until you start it again.",
    "Namestitev je uspela.": "Installation succeeded.",
    "ni odprtih medijskih oken": "no open media windows",
    "ni holografskih plošč": "no holographic panels",
    "ni nastavljenih storitev (stack: v server.yaml)":
      "no services configured (stack: in server.yaml)",
    "nalagam …": "loading …",
    "nalaganje …": "loading …",
    "preverjam …": "checking …",
    "najdeno": "found",

    /* ---- settings page --------------------------------------------- */
    "KALIBRACIJA GLASU PO ODDALJENOSTI": "DISTANCE VOICE CALIBRATION",
    "KALIBRIRAJ": "CALIBRATE",
    "KALIBRIRAJ GLAS": "CALIBRATE VOICE",
    "ZAČNI KALIBRACIJO": "START CALIBRATION",
    "Kalibracija": "Calibration",
    "HUD ob zagonu ponudi kalibracijo": "HUD offers calibration on start",
    "Mia se mora naučiti tvoj glas od blizu, s sredine sobe in od daleč.":
      "Mia has to learn your voice up close, from the middle of the room and from afar.",
    "Zahtevaj kalibracijo": "Require calibration",
    "brez kalibracije Mia ne obdeluje govora":
      "without calibration Mia does not process speech",
    "Stroga budnica": "Strict wake word",
    "Stroga budnica »Mia«": "Strict wake word »Mia«",
    "vsaka izjava se mora začeti z »Mia«": "every utterance must start with »Mia«",
    "Follow-up okno (s)": "Follow-up window (s)",
    "0 = strogo; v strict načinu se ne uporablja": "0 = strict; unused in strict mode",
    "Prag": "Threshold",
    "Prag govorca": "Speaker threshold",
    "višji = strožje, nižji = bolj dovzeten": "higher = stricter, lower = more permissive",
    "Raven vhoda": "Input level",
    "Učenje vklopljeno": "Learning enabled",
    "Dolžina spominskega briefa": "Memory brief length",
    "znaki, ki se vbrizgajo pred krog": "characters injected before a turn",
    "po opravilu vprašaj »je bilo prav?«": "after a task ask »was that right?«",
    "Zahtevaj profil": "Require profile",
    "Kalibracija ni uspela.": "Calibration failed.",
    "KALIBRACIJA SHRANJENA": "CALIBRATION SAVED",
    "Tvoj glas je shranjen za bližino, sredino in daljavo.":
      "Your voice is stored for near, middle and far distance.",
    "Klikni ZAČNI KALIBRACIJO. Mia te bo vodila skozi tri oddaljenosti in si tvoj glas trajno zapomnila.":
      "Click START CALIBRATION. Mia will guide you through three distances and remember your voice permanently.",
    "Kalibriraj glas po oddaljenosti": "Calibrate voice by distance",
    "neprestano poslušanje z budnico »Mia«": "continuous listening with the »Mia« wake word",
    "GLAS ŠE NI KALIBRIRAN": "VOICE NOT CALIBRATED YET",
    "najprej dokončaj ali prekini kalibracijo": "finish or cancel the calibration first",
    "obstaja stari profil brez oddaljenosti": "an old profile without distance exists",
    "samo profil": "profile only",

    /* ---- capabilities page ------------------------------------------ */
    "ZMOGLJIVOSTI NA TEM STROJU": "CAPABILITIES ON THIS MACHINE",
    "OKLJUKANE · POTRJENE · NAUČENE · PRAZNE · NEPODPRTE":
      "DETECTED · CONFIRMED · LEARNED · EMPTY · UNSUPPORTED",
    "Klikni ✓, ko si preveril, da zmogljivost res deluje. Mia se uči tudi sama iz uspešnih dejanj (●). Prazna polja so priložnost za kalibracijo ali namestitev orodja.":
      "Click ✓ once you have checked that the capability really works. Mia also learns by herself from successful actions (●). Empty rows are an opportunity to calibrate or install a tool.",
    "POTRJENE/NAUČENE": "CONFIRMED/LEARNED",
    "Potrjene/naučene": "Confirmed/learned",
    "Zaznane": "Detected",
    "zaznane": "detected",
    "Nepodprte": "Unsupported",
    "nepodprte": "unsupported",
    "Prazne": "Empty",
    "prazne": "empty",
    "naučene": "learned",
    "potrjene": "confirmed",
    "ZMOGLJIVOST": "CAPABILITY",
    "KAKO": "HOW",
    "NAMESTI MANJKAJOČA ORODJA": "INSTALL MISSING TOOLS",
    "znova zaznaj orodja": "detect tools again",
    "znova zaznaj stroj in osveži urnik": "detect the machine again and refresh the schedule",
    "ročno dodano v HUD": "added manually in the HUD",
    "ročno": "manual",
    "Seznam vsebuje okna, aplikacije, vnos, posnetke, odložišče, zvok, zaslone, vire, procese, storitve, datoteke, brskalnik in učenje.":
      "The list covers windows, applications, input, screenshots, clipboard, sound, displays, resources, processes, services, files, the browser and learning.",
    "Namizje": "Desktop",
    "Preverjanje": "Verification",
    "preverjeno": "verified",
    "zavrnjeno": "rejected",
    "spodletelo": "failed",
    "uspeh": "success",
    "prekinjeno": "interrupted",
    "NAUČENO": "LEARNED",

    /* ---- learning page --------------------------------------------- */
    "SPOMIN IN ZNANJE": "MEMORY AND KNOWLEDGE",
    "TRAJNI SPOMIN · NAVADE · RECEPTI · NAPAKE · DREVO VEŠČIN":
      "LONG-TERM MEMORY · HABITS · RECIPES · MISTAKES · SKILL TREE",
    "KAJ BI MIA ZDAJ VEDELA": "WHAT MIA WOULD KNOW NOW",
    "NAVADE": "HABITS",
    "Navade": "Habits",
    "Navade se same izkopljejo iz ponavljajočih se dejanj. Zanesljivost raste z dokazi in upada, ko navada preneha.":
      "Habits are mined from repeated actions. Confidence grows with evidence and fades when the habit stops.",
    "NAJMOČNEJŠE NAVADE": "STRONGEST HABITS",
    "RECEPTI": "RECIPES",
    "Recepti": "Recipes",
    "NAJBOLJ ZANESLJIVI RECEPTI": "MOST RELIABLE RECIPES",
    "Recept = preverjen postopek. Mia ga uporabi, ko se zahteva dovolj ujema. Neuspeh zniža zaupanje.":
      "A recipe is a verified procedure. Mia uses it when the request matches closely enough. Failure lowers confidence.",
    "DODAJ RECEPT": "ADD RECIPE",
    "SHRANI RECEPT": "SAVE RECIPE",
    "naslov recepta": "recipe title",
    "En korak na vrstico. Uporabi ga, ko je postopek nelinearen in ga je vredno ponoviti.":
      "One step per line. Use it when the procedure is non-linear and worth repeating.",
    "NAPAKE": "MISTAKES",
    "Napake": "Mistakes",
    "napake": "mistakes",
    "Napake, ki se ne smejo ponoviti. Vsak vnos ima vzrok in rešitev.":
      "Mistakes that must not repeat. Every entry has a cause and a fix.",
    "DODAJ NAPAKO": "ADD MISTAKE",
    "SHRANI NAPAKO": "SAVE MISTAKE",
    "simptom": "symptom",
    "vzrok": "cause",
    "rešitev": "fix",
    "Kaj se je zalomilo, zakaj, in kaj narediti namesto tega.":
      "What broke, why, and what to do instead.",
    "DEJSTVA": "FACTS",
    "DODAJ DEJSTVO": "ADD FACT",
    "SHRANI DEJSTVO": "SAVE FACT",
    "Trajna nastavitev ali oseba. Ključ naj bo kratek in stabilen.":
      "A lasting setting or a person. Keep the key short and stable.",
    "EPIZODE": "EPISODES",
    "Epizode": "Episodes",
    "epizode, navade, recepti, napake": "episodes, habits, recipes, mistakes",
    "DREVO VEŠČIN": "SKILL TREE",
    "VEŠČINE": "SKILLS",
    "Veščine": "Skills",
    "Naložene veščine": "Loaded skills",
    "išči po spominu, receptih, napakah, dejstvih …":
      "search memory, recipes, mistakes, facts …",
    "Izbrišem ta vnos iz spomina?": "Delete this entry from memory?",
    "takoj izkoplji navade in osveži indeks": "mine habits now and refresh the index",
    "UČENJE IN PREVERJANJE": "LEARNING AND VERIFICATION",

    /* ---- background page ------------------------------------------- */
    "MEDIJSKA OKNA · PLOŠČE · STORITVE · OPRAVILA":
      "MEDIA WINDOWS · PANELS · SERVICES · JOBS",
    "OKNA": "WINDOWS",
    "PLOŠČE": "PANELS",
    "STORITVE": "SERVICES",
    "HOLOGRAMSKE PLOŠČE": "HOLOGRAPHIC PANELS",
    "MEDIJSKA OKNA": "MEDIA WINDOWS",
    "STORITVE SKLADA": "STACK SERVICES",
    "ORODJA ZA ZAPIRANJE OKEN": "WINDOW-CLOSING TOOLS",
    "ROČNI NADZOR": "MANUAL OVERRIDE",
    "USTAVI VSE PREDVAJANJE": "STOP ALL PLAYBACK",
    "ZAPRI VSE PLOŠČE NA HUD-U": "CLOSE ALL HUD PANELS",
    "Okna, ki jih je Mia odprla. Zapri jih tu, če v ozadju igra več stvari.":
      "Windows Mia opened. Close them here when several things play in the background.",
    "Ustavi le, kar ne potrebuješ. Brez llama-serverja ali Hermesa Mia ne odgovarja.":
      "Stop only what you do not need. Without llama-server or Hermes Mia does not answer.",
    "Če se glasba še vedno predvaja, pritisni zgornji gumb: zapre tudi plošče, ki jih trenutni strežnik ne pozna (npr. po restartu).":
      "If the music still plays, press the button above: it also closes panels the current server does not know about (e.g. after a restart).",
    "Izklopljeno — Mia sama ustavi staro predvajanje.":
      "Off — Mia stops the previous playback by herself.",
    "Vklopljeno — Mia ne zapira oken sama; zapiraš jih ročno spodaj.":
      "On — Mia does not close windows herself; you close them manually below.",
    "Vklopljeno: Mia ne zapira več oken samodejno. Ukaz »Mia ustavi youtube« in gumb spodaj še vedno delujeta.":
      "On: Mia no longer closes windows automatically. The »Mia stop youtube« command and the button below still work.",
    "DELUJE": "UP",
    "NE ODGOVARJA": "DOWN",
    "ZAPRI": "CLOSE",
    "Manjka:": "Missing:",
    " — brez tega Mia oken ne more zapreti. Namesti: sudo apt install xdotool wmctrl (Chromium/Chrome ločeno).":
      " — without this Mia cannot close windows. Install: sudo apt install xdotool wmctrl (Chromium/Chrome separately).",
    "Orodja so pripravljena; vsa Miina okna so v registru in jih lahko zapreš spodaj.":
      "Tools are ready; all Mia windows are in the registry and can be closed below.",
    "Orodja so pripravljena; Mia še ni odprla okna (registracija se zgodi ob odpiranju).":
      "Tools are ready; Mia has not opened a window yet (registration happens when she opens one).",
    "registriranih oken:": "registered windows:",
    "88 Hz · izvirni": "88 Hz · original",
    "GLASOVNA POVEZAVA": "VOICE LINK",
    "Kartice za potrditev": "Approval cards",
    "NEPODPRTE": "UNSUPPORTED",
    "OPOMBA": "NOTE",
    "Okno": "Window",
    "Opomnik …": "Reminder …",
    "PRAZNE": "EMPTY",
    "Piši Hermesu … (/new ponastavi · glas: klikni možgane)":
      "Type to Hermes … (/new resets · voice: click the ring)",
    "Povezava": "Link",
    "Rezerva": "Spare",
    "ZAZNANE": "DETECTED",
    "Za potrditev": "For confirmation",
    "za potrditev": "for confirmation",
    "Zmogljivosti": "Capabilities",
    "brez dejanja": "no action",
    "brez orodij": "no tools",
    "glas": "voice",
    "išči zmogljivost, ukaz, ključno besedo …":
      "search a capability, command, keyword …",
    "kalibriraj glas po oddaljenosti": "calibrate voice by distance",
    "klepet": "chat",
    "miruje": "idle",
    "nadzor": "control",
    "napaka": "error",
    "potrdil uporabnik": "confirmed by the user",
    "počisti": "clear",
    "pravilo": "rule",
    "velja od naslednjega stavka naprej": "applies from the next sentence",
    "znakov danes": "characters today",
    "— brez tega Mia oken ne more zapreti.":
      "— without this Mia cannot close windows.",
    "Namesti: sudo apt install xdotool wmctrl (Chromium/Chrome ločeno).":
      "Install: sudo apt install xdotool wmctrl (Chromium/Chrome separately).",
    "— reci »Mia …«": "— say »Mia …«",
    "▶ KLIKNI ZA AKTIVACIJO MIKROFONA IN ZVOKA":
      "▶ CLICK TO ACTIVATE MICROPHONE AND SOUND",
    "✓ oddaljenost": "✓ distance",
    "brskalnik": "browser",
    "MANJKA": "MISSING",
  };

  const PREFIX = [
    ["napaka: ", "error: "],
    ["Ni uspelo: ", "Failed: "],
    ["ni uspelo: ", "failed: "],
    ["mikrofon blokiran: ", "microphone blocked: "],
    ["Ukaza nisem mogla poslati: ", "Could not send the command: "],
    ["samodejnost ni dosegljiva: ", "autonomy unavailable: "],
    ["napaka klepeta: ", "chat error: "],
    ["zdravje: ", "health: "]
  ];

  const STORE = "mia_hud_lang";
  const ATTRS = ["placeholder", "title", "aria-label", "alt"];
  const originals = new WeakMap();     // text node -> Slovenian source
  const written = new WeakMap();       // text node -> last value we wrote
  const attrOriginals = new WeakMap(); // element -> {attr: source}
  const attrWritten = new WeakMap();   // element -> {attr: last value we wrote}

  let stored = null;
  try { stored = localStorage.getItem(STORE); } catch (e) {}
  let lang = stored === "en" ? "en" : "sl";

  function translate(text) {
    if (lang !== "en" || typeof text !== "string") return text;
    const key = text.trim();
    if (!key) return text;
    if (Object.prototype.hasOwnProperty.call(DICT, key)) {
      return text.replace(key, DICT[key]);
    }
    for (let i = 0; i < PREFIX.length; i++) {
      const from = PREFIX[i][0];
      if (key.startsWith(from)) {
        return text.replace(key, PREFIX[i][1] + key.slice(from.length));
      }
    }
    return text;
  }

  function fixNode(node) {
    if (!node) return;
    if (node.nodeType === 3) {
      const current = node.nodeValue;
      const source = originals.get(node);
      const last = written.get(node);
      // the page replaced the text when it differs from both the source and
      // the value we wrote ourselves (switching language must not do that)
      if (source === undefined || (current !== source && current !== last)) {
        originals.set(node, current);
      }
      const wanted = translate(originals.get(node));
      if (current !== wanted) {
        node.nodeValue = wanted;
        written.set(node, wanted);
      } else {
        written.set(node, current);
      }
      return;
    }
    if (node.nodeType !== 1) return;
    let source = attrOriginals.get(node);
    if (!source) { source = {}; attrOriginals.set(node, source); }
    let last = attrWritten.get(node);
    if (!last) { last = {}; attrWritten.set(node, last); }
    for (let i = 0; i < ATTRS.length; i++) {
      const attr = ATTRS[i];
      if (!node.hasAttribute(attr)) continue;
      const current = node.getAttribute(attr);
      if (!(attr in source) || (current !== source[attr] && current !== last[attr])) {
        source[attr] = current;
      }
      const wanted = translate(source[attr]);
      if (current !== wanted) {
        node.setAttribute(attr, wanted);
        last[attr] = wanted;
      } else {
        last[attr] = current;
      }
    }
  }

  function walk(root) {
    if (!root) return;
    fixNode(root);
    if (root.nodeType !== 1) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    let node;
    while ((node = walker.nextNode())) fixNode(node);
  }

  function sync() {
    const bar = document.getElementById("miaLang");
    if (!bar) return;
    bar.querySelectorAll("button").forEach(function (btn) {
      btn.classList.toggle("on", btn.dataset.l === lang);
    });
  }

  function setLang(next) {
    lang = next === "en" ? "en" : "sl";
    try { localStorage.setItem(STORE, lang); } catch (e) {}
    document.documentElement.lang = lang;
    walk(document.body);
    sync();
    try {
      if (typeof fetch === "function") {
        fetch("/api/ui/language", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ lang: lang })
        }).catch(function () {});
      }
    } catch (e) {}
    try {
      window.dispatchEvent(new CustomEvent("mia-lang", { detail: { lang: lang } }));
    } catch (e) {}
  }

  function mount() {
    if (document.getElementById("miaLang")) return;
    const style = document.createElement("style");
    style.textContent =
      "#miaLang{display:flex;gap:4px;z-index:99999;font-family:'Orbitron',sans-serif;" +
      "opacity:.9;align-items:center}" +
      "#miaLang.fixed{position:fixed;right:10px;bottom:10px}" +
      "#miaLang button{background:#0a2435;color:#4d7d92;border:1px solid #0e2c40;" +
      "padding:4px 9px;font-family:'Orbitron',sans-serif;font-size:9px;letter-spacing:1.5px;" +
      "cursor:pointer}" +
      "#miaLang button.on{color:#00e5ff;border-color:#0a7f96;box-shadow:0 0 8px #00e5ff44}";
    document.head.appendChild(style);
    const bar = document.createElement("div");
    bar.id = "miaLang";
    bar.setAttribute("role", "group");
    bar.setAttribute("aria-label", "Language / Jezik");
    bar.innerHTML = '<button type="button" data-l="sl">SLO</button>' +
                    '<button type="button" data-l="en">ENG</button>';
    // the main HUD has an empty first footer slot: sit there, do not cover
    // the status text; other pages get a small fixed pill
    const slot = document.querySelector("footer > span:first-child");
    if (slot && !slot.textContent.trim()) {
      slot.appendChild(bar);
    } else {
      bar.className = "fixed";
      document.body.appendChild(bar);
    }
    bar.querySelectorAll("button").forEach(function (btn) {
      btn.addEventListener("click", function () { setLang(btn.dataset.l); });
    });
    sync();
  }

  window.MiaI18N = {
    t: translate,
    setLang: setLang,
    getLang: function () { return lang; },
    apply: function () { walk(document.body); }
  };
  window.t = translate;

  function start() {
    mount();
    document.documentElement.lang = lang;
    if (lang === "en") walk(document.body);
    if (stored === null) {
      // first visit: follow the language the server remembers
      try {
        if (typeof fetch === "function") {
          fetch("/api/hud-config").then(function (r) { return r.json(); })
            .then(function (j) {
              if (j && j.lang === "en" && lang !== "en") setLang("en");
            }).catch(function () {});
        }
      } catch (e) {}
    }
    new MutationObserver(function (mutations) {
      if (lang !== "en") return;
      for (let i = 0; i < mutations.length; i++) {
        const m = mutations[i];
        if (m.type === "characterData") fixNode(m.target);
        else m.addedNodes.forEach(function (n) { walk(n); });
      }
    }).observe(document.body, {
      childList: true, subtree: true, characterData: true
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();

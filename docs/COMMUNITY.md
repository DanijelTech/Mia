# Skupnost in rast projekta

> Angleška različica s celotnim priročnikom: [docs/en/COMMUNITY.md](en/COMMUNITY.md)

Mia se razvija odprto. Cilj tega dokumenta je, da obiskovalec v eni minuti
razume, kje so pravila, kako prispevati in kako projekt deliti naprej.

## Standardi skupnosti

| Zahteva GitHuba | Datoteka |
|---|---|
| README | [`README.md`](../README.md) (angleško), [`README.sl.md`](../README.sl.md) (slovensko) |
| Kodeks ravnanja | [`CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md) |
| Prispevanje | [`CONTRIBUTING.md`](../CONTRIBUTING.md) |
| Licenca | [`LICENSE`](../LICENSE) (MIT) |
| Varnostna politika | [`SECURITY.md`](../SECURITY.md) |
| Predloge issue | [`.github/ISSUE_TEMPLATE/`](../.github/ISSUE_TEMPLATE/) |
| Predloga PR | [`.github/pull_request_template.md`](../.github/pull_request_template.md) |
| Dodatne datoteke | [`SUPPORT.md`](../SUPPORT.md), [`GOVERNANCE.md`](../GOVERNANCE.md), [`ROADMAP.md`](../ROADMAP.md) |
| Dostopnost | [`ACCESSIBILITY.md`](../ACCESSIBILITY.md) |

## GitHub nastavitve (povzetek)

- **About**: kratek opis, povezava na dokumentacijo in teme:
  `voice-assistant`, `local-first`, `offline`, `slovenian`, `hermes-agent`,
  `whisper`, `piper-tts`, `llm`, `privacy`, `accessibility`, `self-hosted`.
- **Discussions**: vklopljene za vprašanja, ideje in “pokaži svojo postavitev”.
- **Branch protection** za `main`: obvezen CI, PR, ena odobritev, brez
  force-pusha (razen maintainerja).
- **Code security**: private vulnerability reporting, Dependabot in secret
  scanning.
- **Social preview**: naloži `docs/images/hud-en.png`.
- **Release**: iz tag-a `v1.1.0`, z zapiski iz `CHANGELOG.md` in priloženim
  `dist/mia-1.1.0.tar.gz`.
- **Pripni** issue “Start here: good first issues” z oznako
  `good first issue`.

## Oznake

`bug`, `enhancement`, `documentation`, `translation`, `accessibility`,
`good first issue`, `help wanted`, `needs-triage`, `security`, `installer`,
`voice`, `hud`, `learning`, `autonomy`, `plugin`.

## Pot prispevkarja

1. **Odkritje**: README s posnetkom HUD-a, 30–60 s demo, teme in release notes.
2. **Zaupanje**: lokalno/privatno delovanje, testi, CI, varnostna politika,
   verzioniranje, licenca.
3. **Preizkus**: `./install.sh --yes`, `--dry-run`, zdravstveni pregledi.
4. **Prispevek**: `good first issue`, roadmap, predloge issue/PR, kodeks.
5. **Obdržanje**: hiter pregled, zahvala, omemba v release notes.

## Objava

- [ ] README ima angleški posnetek HUD-a in kratek demo.
- [ ] Release `v1.1.0` z zapiski in offline paketom.
- [ ] CI zelen na `main`.
- [ ] Vsaj 5 nalog z oznako `good first issue`.
- [ ] Discussions ima kategoriji “Show your setup” in “Q&A”.
- [ ] Objavi enkrat, pošteno, kjer so ljudje za lokalne glasovne asistente
      (r/LocalLLaMA, r/selfhosted, r/slovenia, Show HN, Lemmy/Mastodon).
      Ne spamaj; odgovarjaj na vprašanja.
- [ ] Prosi za konkretno pomoč (“preizkusi installer na Fedori”, “prevedi en
      HUD niz”), ne za splošno “prosim prispevajte”.

Celoten priročnik z vsemi koraki, metrikami in primeri je v
[docs/en/COMMUNITY.md](en/COMMUNITY.md).

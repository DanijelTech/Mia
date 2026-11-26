# Learning protocol (detail)

## Episode schema

```json
{
  "id": 42,
  "ts": 1764000000.0,
  "session": "mia-main",
  "source": "voice | chat | control | cli",
  "intent": "open | music | volume | search | file | system | chat …",
  "request": "odpri mi google in poisci vreme",
  "response": "Odprla sem.",
  "tools": ["mia-ctl"],
  "steps": [
    {"action": "mia-ctl", "args": ["open", "https://google.com"], "ok": true}
  ],
  "outcome": "success | failure | partial | unknown",
  "error": "",
  "duration_s": 4.2,
  "interrupted": false,
  "tags": ["voice", "open"],
  "meta": {
    "entities": [{"kind": "domain", "value": "google.com"}],
    "app": "google",
    "run_id": "…"
  }
}
```

`meta.entities` is what makes habit mining possible. Always add entities when
the request refers to an app, domain, artist, file, project or service.

## Recipe schema

```json
{
  "key": "google-odpri-poisci-vreme",
  "title": "odpri mi google in poisci vreme",
  "steps": [{"action": "mia-ctl", "args": ["open", "https://google.com"]}],
  "tags": ["voice", "open"],
  "success_count": 4,
  "fail_count": 1,
  "confidence": 0.71
}
```

Promotion rules:

- A recipe is created from a successful episode only if it has `steps`, `tools`
  or `meta.remember=true`.
- An explicit positive feedback always promotes the episode.
- `mia-learn remember` forces promotion.
- A failure on a matching request increments `fail_count` and lowers
  confidence.
- Exact key = same normalised token set. Near matches use the similarity score.

## Anti-pattern schema

```json
{
  "key": "ap:zapri-okno:3f9c1a2b7d",
  "symptom": "okno se ne zapre s pkill",
  "cause": "Chrome forwards --app windows into the running instance",
  "fix": "use mia-close <domain>",
  "severity": "high",
  "hits": 3
}
```

Rules:

- Automatic failures create an anti-pattern keyed by request + error hash.
- Explicit `mia-learn mistakes --add` creates a human-authored one with a fix.
- A later success on the same request updates the fix with the working steps.
- The brief lists at most 3 matching anti-patterns, highest hits first.

## Habit schema

```json
{
  "key": "habit:pref:domain:google-com",
  "kind": "preference | routine | fact",
  "subject": "domain: google.com",
  "detail": {
    "count": 12,
    "period": "zjutraj",
    "peak_hour": 7,
    "peak_share": 0.58,
    "routine": "običajno zjutraj (~07:00)",
    "examples": ["odpri mi google", "poisci vreme"]
  },
  "evidence": 12,
  "confidence": 0.82,
  "pinned": false
}
```

Mining is idempotent: running it twice does not double counts. Confidence
decays only when a habit stops appearing.

## Feedback phrases (deterministic)

Positive: `tako je`, `to je prav`, `to je bilo prav`, `zdaj je prav`,
`pravilno`, `odlično`, `bravo`, `super`, `to mi je všeč`, `točno tako`.

Negative: `ni prav`, `to ni prav`, `narobe`, `ne tako`, `ni bilo prav`,
`zmotila si se`, `popravi`, `to ne deluje`, `naslednjič drugače`.

Remember: `zapomni si postopek`, `zapomni si to`, `zapomni si kako`,
`shrani recept`, `naslednjič naredi tako`.

Only short utterances (≤ 12 tokens) are intercepted. A longer sentence that
contains a correction plus a new request reaches the agent, which must both act
and call `mia-learn feedback`.

## Promotion example

1. User: »Mia, odpri mi Google in poišči vreme.«
2. Agent uses `mia-ctl open …`; the turn succeeds.
3. Episode is recorded; a recipe is created because `steps` is non-empty.
4. User: »Tako je.« → server records positive feedback, recipe confidence grows.
5. Next week the same request arrives; the brief shows the recipe and the agent
   reuses it instead of rediscovering the URL.

## Failure example

1. Agent tries `pkill -f 'chrome.*--app=youtube'`; the window survives.
2. Episode ends with an error → anti-pattern created.
3. User: »Ne tako, uporabi mia-close.«
4. Agent records `mia-learn mistakes --add … --fix "mia-close https://www.youtube.com"`.
5. Next time the brief says: **NE PONAVLJAJ** with the fix.

## Retention and backup

- Episodes: 400 days or 200 000 rows (configurable).
- Events: 180 days.
- Stale habits: confidence below 0.12 after 120 days are removed.
- Backup: `mia-learn backup ~/backups/mia-learning.db`.
- Portable export: `mia-learn export ~/backups/mia-learning.json`.

## Privacy

Before storage every text field is redacted for API keys, tokens, passwords,
long opaque blobs, private keys, e-mails and phone/card-like numbers. This is a
safety net: do not deliberately record secrets, clipboard contents or private
messages.

# Changelog

## 0.1.0 (unreleased)

- First version: page views (including single-page apps and hash routers), engaged time and
  scroll depth, custom events with value, `data-exclude`, owner opt-out, queued calls.
- Payload v1 (`schema/event.v1.json`), PRIVACY.md with visitor id test vectors, proxy recipes.
- `collector/`: the server code that sees IP addresses and user agents (beacon validation, the
  daily visitor id, bot and browser detection, the queue message), with tests against
  `data/visitor-id-vectors.json`.

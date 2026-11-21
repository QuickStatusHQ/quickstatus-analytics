# CLAUDE.md

Public repo. Don't put private context here: no customer names, internal URLs, or notes about
the QuickStatus.dev backend beyond what PAYLOAD.md and PRIVACY.md describe.

- `src/qs.js` is the whole tracker: plain ES5-compatible JS, no build step, no dependencies,
  under 3 KB gzipped (CI checks). No cookies, no storage writes, no fingerprinting APIs.
- Payload changes are additive within v1. Update `schema/event.v1.json`, `schema/examples/` and
  PAYLOAD.md in the same change; the QuickStatus.dev server vendors the schema, examples and
  `data/sources.json`.
- PRIVACY.md is a promise. A change to what is sent or how it's processed updates it in the same
  change, including the test vectors.
- `collector/quickstatus_collector/` is the server code that sees IPs and user agents. The
  QuickStatus.dev service vendors it unmodified, so it holds no service-specific code: the salt
  store, queue and geo file are passed in. `sources.json` there is a copy of `data/sources.json`
  (tests check). A change to the visitor id updates `data/visitor-id-vectors.json` and PRIVACY.md.
- Before a change is done: `node --test test/` and, for `collector/`,
  `cd collector && pip install -e '.[test]' && pytest`.
- Version lives in the `/*! ... v X.Y.Z` header of src/qs.js and in CHANGELOG.md; tags are `vX.Y.Z`.

# Changelog

## 0.1.0 (unreleased)

- First version: page views (including single-page apps and hash routers), engaged time and
  scroll depth, custom events with value, `data-exclude`, owner opt-out, queued calls.
- Payload v1 (`schema/event.v1.json`), PRIVACY.md with visitor id test vectors, proxy recipes.
- `collector/`: the server code that sees IP addresses and user agents (beacon validation, the
  daily visitor id, bot and browser detection, the queue message), with tests against
  `data/visitor-id-vectors.json`.
- Before release, from review: engaged time on SPA navigation goes to the page that was left;
  prerendered pages count when opened (`document.prerendering`); the referrer is sent as its
  origin only; long URLs are cut instead of rejected; a bad currency or negative value is left
  out instead of losing the event; the script counts once when loaded twice; `engage` is
  reserved; hash routes keep their route as the path; the rate limit applies to bots and to the
  proxy address of `X-QS-Proxy` requests; `GET /e` lists POST in `Allow`; look-alike
  `google.*` hosts and CUBOT phones are no longer misread. Docs: status codes, value × 100,
  cookies with `sendBeacon`, SRI file.
- Second review: hash mode sends only `#/route` fragments, with their query filtered like the
  page's, and the collector stores the route without its query (and reads its UTM tags); calls
  made during prerender wait until the page is opened; event names are trimmed before the
  reserved-name check; the proxy limit is per proxy address and site; `google.xyz`-style
  hosts are no longer Google; README says a second tag's `data-site` is ignored.
- Third review: a proxy address also has a 5000-per-10-seconds ceiling across all sites (made-up
  site ids no longer get past the per-site limit); a hash route ends at a second `#`
  (`#/callback#access_token=…`); `pushState` and `popstate` during prerender send nothing, and
  opening the page counts the current URL once.

# Payload

`qs.js` sends one `POST` per event to the collector (`https://a.quickstatus.dev/e`, or your
proxy, set with `data-api`). The body is JSON sent as `text/plain` with `navigator.sendBeacon`
(or `fetch` with `keepalive`), so browsers send no CORS preflight. The response is `202` with an
empty body; the script never reads it.

The schema is [`schema/event.v1.json`](schema/event.v1.json); examples are in
[`schema/examples/`](schema/examples/). Version 1 only grows: new optional fields may be added,
nothing is removed or changes meaning.

| Field | Type | Sent on | Meaning |
| --- | --- | --- | --- |
| `s` | string | all | Site id from `data-site`. |
| `n` | string | all | `pageview`, `engage`, or the custom event name. |
| `u` | string | all | Page URL. The query keeps only `utm_source`, `utm_medium`, `utm_campaign`, `utm_content`, `utm_term`, `ref` and `source`; everything else is removed in the browser. The fragment is sent only with `data-hash="true"`. |
| `r` | string or null | all | `document.referrer`. Only its host is stored. |
| `w` | integer | all | `window.innerWidth`, for Desktop / Tablet / Phone. |
| `e` | integer | `engage` | Milliseconds the page was visible since the last page view. |
| `d` | integer | `engage` | Deepest scroll position, percent of the page. |
| `v` | integer | custom events | Value in minor units: `qs("Purchase", { value: 49, currency: "EUR" })` sends `4900`. |
| `c` | string | custom events | ISO 4217 currency of `v`. |

The request also carries what every browser request carries: the IP address and the
`User-Agent` header. [PRIVACY.md](PRIVACY.md) describes what happens to them.

## When events are sent

- `pageview`: on load (after prerender, when the page becomes visible), and on
  `history.pushState` / `popstate` (and `hashchange` with `data-hash="true"`) when the URL changes.
- `engage`: when the tab is hidden or the page is left, and before the next SPA page view, if the
  page was visible for at least a second.
- Custom events: when you call `qs(name, options)`.

Nothing is sent on `localhost`, `127.0.0.1`, `*.localhost`, `*.local`, `*.test` or `file:` pages
(unless `data-local="true"`), when `navigator.webdriver` is true, on paths matching
`data-exclude`, or when `localStorage.qs_ignore` is `"1"` (a switch site owners set in their own
browser by running `localStorage.qs_ignore = "1"` in the developer console on their site; the
script reads it and never writes storage).

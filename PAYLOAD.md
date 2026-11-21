# Payload

`qs.js` sends one `POST` per event to the collector (`https://a.quickstatus.dev/e`, or your
proxy, set with `data-api`). The body is JSON sent as `text/plain` with `navigator.sendBeacon`
(or `fetch` with `keepalive`), so browsers send no CORS preflight. The script never reads the
response.

| Status | When |
| --- | --- |
| `202` | Accepted, with an empty body. Also for bots (counted as a number only) and for unknown site ids (dropped later). |
| `204` | `OPTIONS` preflight. |
| `400` | The body isn't valid payload v1; `{"detail": "…"}` says which field. Also when `n` or `u` holds a control character (a browser never sends one), or an `X-Forwarded-For` entry the collector reads isn't an IP address. |
| `413` | Body over 4096 bytes. |
| `429` | Over 60 requests in 10 seconds from one IP (one /64 for IPv6); through a proxy, over 600 for one site or 5000 in all from one proxy address. |

The schema is [`schema/event.v1.json`](schema/event.v1.json); examples are in
[`schema/examples/`](schema/examples/). Version 1 only grows: new optional fields may be added,
nothing is removed or changes meaning.

| Field | Type | Sent on | Meaning |
| --- | --- | --- | --- |
| `s` | string | all | Site id from `data-site`. |
| `n` | string | all | `pageview`, `engage`, or the custom event name. |
| `u` | string | all | Page URL, at most 2000 characters (the query is dropped first, then the URL is cut). The query keeps only `utm_source`, `utm_medium`, `utm_campaign`, `utm_content`, `utm_term`, `ref` and `source`; everything else is removed in the browser. The fragment is sent only with `data-hash="true"`, and only a hash-router route (`#/…` or `#!/…`, up to any second `#`) with its query filtered the same way; other fragments (`#faq`, `#access_token=…`) are never sent. The route is stored as part of the path, without its query. |
| `r` | string or null | all | Origin of `document.referrer` (`https://news.ycombinator.com/`); its path and query are not sent. Only its host is stored. |
| `w` | integer | all | `window.innerWidth`, for Desktop / Tablet / Phone. |
| `e` | integer | `engage` | Milliseconds the page was visible since the last `engage` or page view. A page can send several (one per time the tab is hidden); add them up per page. |
| `d` | integer | `engage` | Deepest scroll position, percent of the page. |
| `v` | integer | custom events | Value × 100, whatever the currency: `qs("Purchase", { value: 49, currency: "EUR" })` sends `4900`. Not sent for negative values. |
| `c` | string | custom events | ISO 4217 currency of `v`, 3 letters. Not sent when the code given isn't 3 letters. |

The request also carries what every browser request carries: the IP address and the
`User-Agent` header. [PRIVACY.md](PRIVACY.md) describes what happens to them.

## When events are sent

- `pageview`: on load (a prerendered page only once it is opened), and on
  `history.pushState` / `popstate` (and `hashchange` with `data-hash="true"`) when the URL changes.
- `engage`: when the tab is hidden or the page is left, and before the next SPA page view, if the
  page was visible for at least a second. Its `u` is the page that was left.
- Custom events: when you call `qs(name, options)`. On a prerendered page, calls wait until
  it is opened, and are dropped if it never is.

Nothing is sent on `localhost`, `127.0.0.1`, `*.localhost`, `*.local`, `*.test` or `file:` pages
(unless `data-local="true"`), when `navigator.webdriver` is true or the page runs in Cypress,
Nightmare or PhantomJS, on paths matching
`data-exclude`, or when `localStorage.qs_ignore` is `"1"` (a switch site owners set in their own
browser by running `localStorage.qs_ignore = "1"` in the developer console on their site; the
script reads it and never writes storage).

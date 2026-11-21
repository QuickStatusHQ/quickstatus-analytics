# QuickStatus.dev analytics

The script behind [QuickStatus.dev](https://quickstatus.dev) website analytics: cookieless page
views, referrers, UTM campaigns, countries, devices, custom events and engaged time, in under
3 KB.

- No cookies, no device storage, no fingerprinting. [PRIVACY.md](PRIVACY.md) is the exact
  processing, with test vectors for the visitor id.
- Every field the script sends is in [PAYLOAD.md](PAYLOAD.md) and
  [`schema/event.v1.json`](schema/event.v1.json).
- The collector, every step on our servers that sees a visitor's IP address or user agent, is
  in [`collector/`](collector/). QuickStatus.dev runs that package unmodified; its tests check
  the visitor id against [`data/visitor-id-vectors.json`](data/visitor-id-vectors.json) and that
  no queue message or log line holds an IP.
- MIT licensed. The dashboard is part of QuickStatus.dev; this repo is what runs in your
  visitors' browsers and the code that first receives their requests.

## Install

Add a site in the QuickStatus.dev console (Analytics → Add site), then put the tag it shows in
your `<head>`:

```html
<script defer src="https://quickstatus.dev/qs.js" data-site="YOUR_SITE_ID"></script>
```

For production, pin a version and add its SRI hash. Each GitHub release has an `SRI` file with
the `sha384-…` value for `integrity=` (`SHA256SUMS` is for checking downloads, not for SRI):

```html
<script defer src="https://quickstatus.dev/qs@0.1.0.js" data-site="YOUR_SITE_ID"
  integrity="sha384-…" crossorigin="anonymous"></script>
```

### Options

| Attribute | Default | |
| --- | --- | --- |
| `data-site` | (required) | Site id from the console. |
| `data-api` | `https://a.quickstatus.dev/e` | Collector URL, for a [first-party proxy](examples/). |
| `data-hash` | `false` | Count `#/route` changes as pages (hash routers). Other fragments are never sent. |
| `data-exclude` | | Comma-separated paths not to count: `/admin/**, /preview/*`. |
| `data-manual` | `false` | No automatic page views; call `qs("pageview")` yourself. |
| `data-local` | `false` | Count on `localhost`, `127.x`, `[::1]`, `*.localhost`, `*.local` and `*.test` (for trying it out). |
| `data-debug` | `false` | Log to the console why a page isn't counted. |

## Custom events

```html
<script>window.qs = window.qs || function () { (qs.q = qs.q || []).push(arguments) }</script>
```

```js
qs("Signup");
qs("Purchase", { value: 49.0, currency: "EUR" });  // sent as v: 4900, c: "EUR"
```

`value` is sent multiplied by 100 whatever the currency (`{ value: 500, currency: "JPY" }`
sends `50000`). A negative value, or a currency that isn't a 3-letter code, is left out and the
event is still counted. `pageview` and `engage` are reserved names.

Calls made before the script loads are queued by the line above and sent once it loads.

## Single-page apps

Page views are counted on `history.pushState` and `popstate` automatically. With a hash router,
add `data-hash="true"`: `/#/settings` is then stored as its own page. Loading the script twice
counts once: only the first tag runs, so a second tag's `data-site` is ignored and a page counts
for one site.

## First-party proxy

Some ad blockers block third-party analytics hosts. To serve the script and the collector from
your own domain, see [`examples/`](examples/) for Next.js, Netlify, Vercel, Cloudflare Workers,
nginx and Caddy. Each one forwards the visitor's IP in `X-Forwarded-For` and sets
`X-QS-Proxy: 1`, without which every visitor would look like your proxy. Through a proxy, the
collector also limits the proxy's own address (600 requests per 10 seconds per site), because
anyone can send that header. A site sending more than that through one proxy address gets `429`s
for the excess.

## Development

```sh
node --test test/*.test.mjs   # runs src/qs.js in a fake browser; no dependencies
```

## License

MIT

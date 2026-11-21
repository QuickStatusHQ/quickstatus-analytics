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

For production, pin a version and add its SRI hash from the release's `SHA256SUMS`:

```html
<script defer src="https://quickstatus.dev/qs@0.1.0.js" data-site="YOUR_SITE_ID"
  integrity="sha384-…" crossorigin="anonymous"></script>
```

### Options

| Attribute | Default | |
| --- | --- | --- |
| `data-site` | (required) | Site id from the console. |
| `data-api` | `https://a.quickstatus.dev/e` | Collector URL, for a [first-party proxy](examples/). |
| `data-hash` | `false` | Count `#/route` changes as pages (hash routers). |
| `data-exclude` | | Comma-separated paths not to count: `/admin/**, /preview/*`. |
| `data-manual` | `false` | No automatic page views; call `qs("pageview")` yourself. |
| `data-local` | `false` | Count on `localhost` and `*.test` (for trying it out). |
| `data-debug` | `false` | Log to the console why a page isn't counted. |

## Custom events

```html
<script>window.qs = window.qs || function () { (qs.q = qs.q || []).push(arguments) }</script>
```

```js
qs("Signup");
qs("Purchase", { value: 49.0, currency: "EUR" });  // sent as 4900 minor units
```

Calls made before the script loads are queued by the line above and sent once it loads.

## Single-page apps

Page views are counted on `history.pushState` and `popstate` automatically. With a hash router,
add `data-hash="true"`.

## First-party proxy

Some ad blockers block third-party analytics hosts. To serve the script and the collector from
your own domain, see [`examples/`](examples/) for Next.js, Netlify, Vercel, Cloudflare Workers,
nginx and Caddy. Each one forwards the visitor's IP in `X-Forwarded-For` and sets
`X-QS-Proxy: 1`, without which every visitor would look like your proxy.

## Development

```sh
node --test test/*.test.mjs   # runs src/qs.js in a fake browser; no dependencies
```

## License

MIT

# First-party proxy recipes

Serve the script and the collector from your own domain:

- `https://your-site.com/qs.js` → `https://quickstatus.dev/qs.js`
- `https://your-site.com/qs/e` → `https://a.quickstatus.dev/e`

and point the tag at it:

```html
<script defer src="/qs.js" data-site="YOUR_SITE_ID" data-api="/qs/e"></script>
```

Every recipe must:

1. Forward the visitor's IP as the last entry it adds to `X-Forwarded-For` (the collector reads
   the entry before its own load balancer's), and send `X-QS-Proxy: 1`. Without both, every
   visitor looks like your proxy and is counted as one person.
2. Forward the `User-Agent` header unchanged.
3. Pass the body through as is (`text/plain`, a few hundred bytes).

**Status: v0.1.0 recipes are not yet verified against each platform.** After setting one up,
open your site with `data-debug="true"` from two networks and check that the console's Realtime
count shows two visitors.

| Recipe | File |
| --- | --- |
| nginx | [`nginx.conf`](nginx.conf) |
| Caddy | [`Caddyfile`](Caddyfile) |
| Cloudflare Workers | [`cloudflare-worker/worker.js`](cloudflare-worker/worker.js) |
| Next.js (any host, including Vercel) | [`nextjs/`](nextjs/) |
| Netlify | [`netlify.toml`](netlify.toml) |

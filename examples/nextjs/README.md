# Next.js (App Router)

1. Copy `app/qs/e/route.ts` into your app.
2. Add the rewrite for the script from `next.config.js`.
3. Use `<Script defer src="/qs.js" data-site="YOUR_SITE_ID" data-api="/qs/e" />` in your root
   layout (`next/script`, `strategy="afterInteractive"`).

The route handler (not a rewrite) forwards the collector request, because Next.js rewrites
can't add the `X-QS-Proxy` header.

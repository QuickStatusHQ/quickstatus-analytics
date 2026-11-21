# Next.js (App Router)

1. Copy `app/qs.js/route.ts` and `app/qs/e/route.ts` into your app.
2. Use `<Script defer src="/qs.js" data-site="YOUR_SITE_ID" data-api="/qs/e" />` in your root
   layout (`next/script`, `strategy="afterInteractive"`).

Both are route handlers, not rewrites: a Next.js rewrite to another host forwards the visitor's
request headers (your site's cookies included) and can't add the `X-QS-Proxy` header.

# Security

Please report vulnerabilities privately to support@quickstatus.dev (subject "security"), or
through GitHub's private vulnerability reporting on this repository, rather than in a public
issue.

## What the script is designed to guarantee

**Nothing stored on the device.** No cookies, no `localStorage` or `sessionStorage` writes, no
IndexedDB. The only storage access is reading `localStorage.qs_ignore`, a switch the site owner
sets in their own browser.

**No fingerprinting.** The script reads the URL, `document.referrer`, the viewport width,
visibility and scroll position. It does not read canvas, WebGL, audio, fonts, plugins, screen
size, hardware or battery information.

**Minimal URL.** The query string is reduced to `utm_*`, `ref` and `source` in the browser, and
the referrer to its origin. The fragment is sent only when the site opts in with
`data-hash="true"`.

**No reads of the response.** Beacons are fire-and-forget, and the script never evaluates
anything it receives. The `fetch` fallback uses `credentials: "omit"`, but `navigator.sendBeacon`
always sends the cookies the browser has for the collector's host. `a.quickstatus.dev` sets none
and the collector reads none. Behind a first-party proxy on your own domain, your site's cookies
reach your proxy: the nginx, Caddy, Cloudflare and Next.js recipes drop them before forwarding;
Netlify's proxy redirects can't, so they reach the collector, which ignores them.

**Pinned releases.** Each release publishes `SHA256SUMS` and an `SRI` file with the
`integrity=` values. Load `qs@X.Y.Z.js` with
`integrity=` in production so a changed file can't run on your site. Releases are not signed.

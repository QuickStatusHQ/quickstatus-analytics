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

**Minimal URL.** The query string is reduced to `utm_*`, `ref` and `source` in the browser. The
fragment is sent only when the site opts in with `data-hash="true"`.

**No reads of the response, no credentials.** Beacons are fire-and-forget; `fetch` uses
`credentials: "omit"`. The script never evaluates anything it receives.

**Pinned releases.** Each release publishes `SHA256SUMS` and SRI hashes. Load `qs@X.Y.Z.js` with
`integrity=` in production so a changed file can't run on your site. Releases are not signed.

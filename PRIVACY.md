# What QuickStatus.dev does with analytics data

This is the exact processing behind QuickStatus.dev website analytics. The script that runs in
your visitors' browsers is in `src/qs.js`; every field it sends is in [PAYLOAD.md](PAYLOAD.md).
The collector that receives it, the only server code that sees an IP address or user agent, is
[`collector/`](collector/) (`events.py` for the processing, `app.py` for the request handling).

## Summary

- No cookies, no `localStorage` or `sessionStorage` ids, no fingerprinting (canvas, fonts,
  audio, hardware).
- The visitor's IP address and user agent are used in memory by the collector to make a daily
  anonymous id, a country/region/city, and a browser, OS and device name. They are then
  discarded. They are never written to the queue, the database or logs (the web server's access
  log is switched off, because it would print the client address).
- The anonymous id changes every day and can't be linked across days, because the salt that
  makes it is deleted after two days.
- The URL query is reduced in the browser to `utm_*`, `ref` and `source` before anything is
  sent, and the referrer to its origin. Paths are stored without the query and fragment. With
  `data-hash="true"` (hash routers), a `#/route` fragment is sent with its query filtered the
  same way and stored without that query; other fragments are never sent.

## The visitor id

```
visitor_id = first 16 bytes of SHA-256(
    len(salt) ‖ salt ‖ len(site) ‖ site ‖ len(ip) ‖ ip ‖ len(user_agent) ‖ user_agent
)
```

- `len(x)` is the byte length of `x` as a 4-byte big-endian integer (so fields can't run into
  each other).
- `salt` is 32 random bytes, one per UTC day, shared by every collector. It is deleted two days
  later. After that, nobody (including us) can recompute a visitor id from an IP and user agent,
  or tell that two days' ids belong to the same person.
- `site` is the site id from the script tag, so the same person gets different ids on
  different sites.
- `ip` is the client address as text; `user_agent` is the `User-Agent` header.

More cases, including IPv6 and another site, are in
[`data/visitor-id-vectors.json`](data/visitor-id-vectors.json), which the collector's tests run.

Test vectors (`salt` = bytes 0x00…0x1f, `site` = `k3x9mpq2wa`,
`user_agent` = `Mozilla/5.0 (X11; Linux x86_64) Firefox/132.0`):

| ip | visitor_id (hex) |
| --- | --- |
| `203.0.113.7` | `fc0f1012c053ff86d8b7edb9ab3c8ce5` |
| `203.0.113.8` | `55ce4476359220751b9d8bace0cfed64` |

If the collector can't read the shared salt (salt store unreachable at midnight), it uses a random
salt kept only in its own memory, and tries the shared one again every minute. Once it can read
it, it switches back, so a visitor seen before and after the switch is counted twice that day.
Visitors may be counted more than once; nothing is less private.

## Sessions

A session is one visitor id with no more than 30 minutes between events. Sessions are kept in
the ingester's memory and stored as: start and end time, entry and exit path, page count,
engaged time, and the referrer, UTM tags, country, device, browser and OS of the first event.
Sessions end at midnight UTC because the visitor id changes.

## What is stored per event

Site, time, visitor id, session id, event name, hostname, path, referrer host (not the full
referrer URL), source name, UTM tags, country, region, city, device type, OS, browser, and for
custom events a value and currency. See `schema/` and PAYLOAD.md for the browser side.

## Bots

Requests whose user agent looks automated (crawlers, previews, HTTP libraries, headless
browsers, uptime monitors) are counted as a number per site per day and nothing else is kept.

## Retention

Raw events and sessions are kept for at most 90 days (deleted by dropping whole days), and less
on plans with shorter retention. Daily totals per page, referrer, country and so on are kept for
the plan's retention. Deleting a site deletes its events, sessions and totals.

## Where it runs

The collector, queue and database run in the United States (AWS us-west-1). There is no EU-only
processing yet.

## Consent

Because no cookies or device storage are used and no personal data is stored, many site owners
run this without a consent banner. That is a legal judgement for you and your counsel; this
document is the technical description to give them.

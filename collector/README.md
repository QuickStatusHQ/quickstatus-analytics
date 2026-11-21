# quickstatus-collector

The part of QuickStatus.dev analytics that receives `POST /e` from `qs.js`. It is the only
server code that sees a visitor's IP address or user agent, and it is what QuickStatus.dev runs,
unmodified.

What happens to a request, in order (`quickstatus_collector/app.py`, `Collector.collect`):

1. The body is validated against payload v1 (`events.parse_beacon`); unknown keys are ignored.
2. A rate limit held in memory for 10 seconds: 60 requests per client IP, and for requests
   sent with `X-QS-Proxy: 1`, 600 per proxy address and site and 5000 per proxy address. It
   applies to every request, bots included. Only accepted requests are recorded, and through a
   proxy the per-site and per-address limits are checked before the client IP gets an entry.
3. Bots are recognised from the user agent (`events.is_bot`) and counted as a number only.
4. `events.enrich` makes the queue message: the daily visitor id (`events.visitor_id`, see
   [PRIVACY.md](../PRIVACY.md)), country/region/city, browser, OS, device, path, referrer host,
   source and UTM tags. The message holds no IP and no user agent.
5. Messages are buffered and sent every second.

The access log of the web server is switched off at startup, because it would print the client
address.

The service plugs in the three things that are its own: where the daily salt comes from (a store
shared by every collector, which deletes salts after two days), where messages are sent, and an
optional MMDB geo file.

```python
from quickstatus_collector import Collector, DailySalt, create_app
from quickstatus_collector.geo import mmdb_lookup

app = create_app(Collector(salt=DailySalt(load_salt).get, send=send_to_queue, geo=mmdb_lookup(path)))
```

Tests: `pip install -e '.[test]' && pytest`. They check the visitor id against
[`data/visitor-id-vectors.json`](../data/visitor-id-vectors.json) and an independent
implementation of the PRIVACY.md formula, and that no queue message or log line holds an IP.

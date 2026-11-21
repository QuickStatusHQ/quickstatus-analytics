"""Beacon validation, user agent and URL parsing, the visitor id, and the queue message.

This is every step that sees a visitor's IP address or user agent. `enrich()` returns the only
thing that leaves the collector, and it holds neither. PRIVACY.md describes the same steps in
prose; schema/event.v1.json is the payload the browser sends.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .sources import source_for

PAGEVIEW = "pageview"
ENGAGE = "engage"

PUBLIC_ID_RE = re.compile(r"^[a-z0-9]{6,32}$")
EVENT_NAME_MAX = 120
URL_MAX = 2000
PATH_MAX = 512
UTM_MAX = 200
ENGAGED_MAX_MS = 6 * 3600 * 1000
VALUE_MAX = 10**12
UTM_KEYS = ("source", "medium", "campaign", "content", "term")
# Control characters and lone surrogates. A browser never sends them (URLs are percent-encoded),
# and a database downstream can't store them (NUL in text, a surrogate in UTF-8), so one such
# beacon must not reach the queue.
UNSAFE_RE = re.compile("[\x00-\x1f\x7f-\x9f\ud800-\udfff]")


class BeaconError(ValueError):
    pass


@dataclass(frozen=True)
class Beacon:
    site: str
    name: str
    url: str
    referrer: str | None
    width: int | None
    engaged_ms: int | None
    scroll: int | None
    value: int | None
    currency: str | None


def _int(data: dict, key: str, low: int, high: int) -> int | None:
    raw = data.get(key)
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, float) and raw.is_integer():
        raw = int(raw)
    if not isinstance(raw, int):
        raise BeaconError(f"{key} must be an integer")
    return max(low, min(high, raw))


def parse_beacon(data: Any) -> Beacon:
    """Validate a beacon body (schema/event.v1.json). Unknown keys are ignored."""
    if not isinstance(data, dict):
        raise BeaconError("body must be a JSON object")
    site = data.get("s")
    if not isinstance(site, str) or not PUBLIC_ID_RE.match(site):
        raise BeaconError("s must be a site id")
    name = data.get("n", PAGEVIEW)
    if not isinstance(name, str) or not name.strip():
        raise BeaconError("n must be a non-empty string")
    name = " ".join(name.split())[:EVENT_NAME_MAX]
    if UNSAFE_RE.search(name):
        raise BeaconError("n must not hold control characters")
    url = data.get("u")
    if not isinstance(url, str) or len(url) > URL_MAX or UNSAFE_RE.search(url):
        raise BeaconError("u must be a URL")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise BeaconError("u must be an http(s) URL")
    referrer = data.get("r")
    if referrer is not None and not isinstance(referrer, str):
        raise BeaconError("r must be a string")
    if referrer and UNSAFE_RE.search(referrer):
        # Not worth losing the page view for: count it as a direct visit.
        referrer = None
    currency = data.get("c")
    if currency is not None:
        if not isinstance(currency, str) or not re.fullmatch(r"[A-Za-z]{3}", currency):
            raise BeaconError("c must be a 3-letter currency code")
        currency = currency.upper()
    value = _int(data, "v", 0, VALUE_MAX)
    engaged = _int(data, "e", 0, ENGAGED_MAX_MS)
    if name == ENGAGE and engaged is None:
        raise BeaconError("engage needs e; engage is reserved for engaged time")
    return Beacon(
        site=site,
        name=name,
        url=url,
        referrer=(referrer or "")[:URL_MAX] or None,
        width=_int(data, "w", 0, 20000),
        engaged_ms=engaged,
        scroll=_int(data, "d", 0, 100),
        value=value,
        currency=currency if value is not None else None,
    )


# --- user agent -----------------------------------------------------------------------------

# Dropped before anything is counted: common crawlers, link previews, HTTP libraries, headless
# browsers and uptime probes.
BOT_RE = re.compile(
    r"(?<!cu)bot\b|bot/|crawl|spider|slurp|archiver|headless|lighthouse|pagespeed|gtmetrix|pingdom|"
    r"preview|monitor|uptime|statuscake|quickstatus|curl/|wget/|python|go-http|java/|okhttp|"
    r"axios/|node-fetch|undici|httpclient|libwww|scrapy|phantomjs|selenium|puppeteer|"
    r"playwright|facebookexternalhit|embedly|whatsapp|bitlybot|discordbot|slackbot|"
    r"telegrambot|applebot|bingpreview|mediapartners|adsbot|feedfetcher|validator",
    re.IGNORECASE,
)


def is_bot(user_agent: str | None) -> bool:
    ua = (user_agent or "").strip()
    if len(ua) < 20 or not ua.startswith("Mozilla/"):
        return True
    return bool(BOT_RE.search(ua))


_BROWSERS = (
    ("Edge", re.compile(r"Edg(e|A|iOS)?/")),
    ("Opera", re.compile(r"OPR/|Opera")),
    ("Samsung Internet", re.compile(r"SamsungBrowser/")),
    ("Firefox", re.compile(r"Firefox/|FxiOS/")),
    ("Chrome", re.compile(r"Chrome/|CriOS/")),
    ("Safari", re.compile(r"Safari/")),
)

_OSES = (
    ("iOS", re.compile(r"iPhone|iPad|iPod")),
    ("Android", re.compile(r"Android")),
    ("ChromeOS", re.compile(r"CrOS")),
    ("Windows", re.compile(r"Windows")),
    ("macOS", re.compile(r"Mac OS X|Macintosh")),
    ("Linux", re.compile(r"Linux")),
)


def browser_and_os(user_agent: str | None) -> tuple[str, str]:
    ua = user_agent or ""
    browser = next((name for name, pattern in _BROWSERS if pattern.search(ua)), "Other")
    os_name = next((name for name, pattern in _OSES if pattern.search(ua)), "Other")
    return browser, os_name


def device_for(width: int | None, user_agent: str | None) -> str:
    """Desktop / Tablet / Phone, from the viewport width when the script sent it."""
    ua = user_agent or ""
    if width:
        if width < 768:
            return "Phone"
        if width < 1024:
            return "Tablet"
        return "Desktop"
    if "iPad" in ua or ("Android" in ua and "Mobile" not in ua):
        return "Tablet"
    if "Mobi" in ua or "iPhone" in ua:
        return "Phone"
    return "Desktop"


# --- url and referrer ---------------------------------------------------------------------


def split_url(url: str) -> tuple[str, str, dict[str, str]]:
    """(hostname, path, utm). The query is removed from the path. A hash-router fragment
    (`#/settings`, `#!/settings`, sent only with data-hash) is kept as part of the path without
    its query, and UTM tags in that query count. Any other fragment (`#faq`,
    `#access_token=…`) is dropped."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    path = parts.path or "/"
    if not path.startswith("/"):
        path = "/" + path
    search = parts.query
    if parts.fragment.startswith(("/", "!/")):
        # Up to a second "#": /#/callback#access_token=… keeps only /callback.
        route, _, route_query = parts.fragment.split("#", 1)[0].partition("?")
        path = f"{path}#{route}"
        search = "&".join(q for q in (search, route_query) if q)
    path = path[:PATH_MAX]
    query = parse_qs(search, keep_blank_values=False)
    def first(name: str) -> str:
        # parse_qs percent-decodes, so ?utm_source=a%00b arrives here as a control character.
        values = query.get(name)
        return UNSAFE_RE.sub("", values[0]).strip()[:UTM_MAX] if values else ""

    utm: dict[str, str] = {}
    for key in UTM_KEYS:
        value = first(f"utm_{key}")
        if value:
            utm[key] = value
    # ?ref= and ?source= are common on launch sites (Product Hunt, newsletters).
    if "source" not in utm:
        for alias in ("ref", "source"):
            value = first(alias)
            if value:
                utm["source"] = value
                break
    return host, path, utm


def _bare(host: str) -> str:
    host = host.lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def referrer_host(referrer: str | None, page_host: str) -> str | None:
    """The referrer's host, or None for direct visits and links within the same site."""
    if not referrer:
        return None
    try:
        parts = urlsplit(referrer)
    except ValueError:
        return None
    if parts.scheme == "android-app":
        # android-app://com.google.android.gm/ → the app id
        return (parts.netloc or None) and parts.netloc.lower()[:253]
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    host = _bare(parts.hostname)
    if host == _bare(page_host):
        return None
    return host[:253]


# --- visitor id ---------------------------------------------------------------------------


def visitor_id(salt: bytes, site: str, ip: str, user_agent: str) -> bytes:
    """sha256(salt ‖ site ‖ ip ‖ ua), first 16 bytes, each part prefixed by its 4-byte length.
    The salt changes every UTC day and is deleted after 2 days, so ids can't be linked across
    days or reversed. Test vectors: data/visitor-id-vectors.json (and PRIVACY.md)."""
    digest = hashlib.sha256()
    for part in (salt, site.encode(), ip.encode(), user_agent.encode()):
        digest.update(len(part).to_bytes(4, "big"))
        digest.update(part)
    return digest.digest()[:16]


def enrich(
    beacon: Beacon,
    *,
    ip: str,
    user_agent: str,
    salt: bytes,
    ts_ms: int,
    geo: tuple[str | None, str | None, str | None] = (None, None, None),
) -> dict[str, Any]:
    """The queue message for one beacon. Holds no IP and no user agent."""
    host, path, utm = split_url(beacon.url)
    ref = referrer_host(beacon.referrer, host)
    browser, os_name = browser_and_os(user_agent)
    country, region, city = geo
    event: dict[str, Any] = {
        "site": beacon.site,
        "ts": ts_ms,
        "vid": visitor_id(salt, beacon.site, ip, user_agent).hex(),
        "name": beacon.name,
        "host": host,
        "path": path,
        "ref": ref,
        "source": source_for(ref) if ref else None,
        "utm": utm,
        "country": country,
        "region": region,
        "city": city,
        "device": device_for(beacon.width, user_agent),
        "os": os_name,
        "browser": browser,
    }
    if beacon.name == ENGAGE:
        event["engaged_ms"] = beacon.engaged_ms or 0
        event["scroll"] = beacon.scroll
    if beacon.value is not None:
        event["value"] = beacon.value
        event["currency"] = beacon.currency
    return {key: value for key, value in event.items() if value not in (None, {}, "")}

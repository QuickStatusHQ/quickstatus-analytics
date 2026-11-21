"""The collector: `POST /e` answers 202 at once, drops bots, turns the beacon into a queue
message with `events.enrich()` and buffers it; a background task sends the buffer every second.

The IP address and user agent are used in memory in `collect()` and nowhere else. They are not
in the queue message, not stored, and not logged (uvicorn's access log is switched off at
startup, because it would print the client address).

The host service plugs in three things: where the daily salt comes from, where messages go,
and an optional geo lookup.

    app = create_app(Collector(salt=DailySalt(load_from_db).get, send=queue_send))
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from typing import Any, Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from .events import BeaconError, enrich, is_bot, parse_beacon
from .geo import EMPTY, Geo

log = logging.getLogger("quickstatus_collector")

BODY_MAX = 4 * 1024
FLUSH_SECONDS = 1.0
FLUSH_AT = 500
BUFFER_MAX = 20_000
# Per client IP: a page load sends 1-3 beacons, so this only stops scripts.
IP_LIMIT = 60
IP_WINDOW_SECONDS = 10.0
# Per proxy address and site, for requests that say they come through a first-party proxy
# (X-QS-Proxy: 1). Anyone can send that header with any X-Forwarded-For, so the address the
# load balancer saw is limited too. Keyed by site as well, because platform proxies (Workers,
# Netlify, Vercel) may share egress addresses between many sites. Site ids aren't checked here,
# so each proxy address also has a ceiling across all sites.
PROXY_IP_LIMIT = 600
PROXY_EDGE_LIMIT = 5000
SALT_RETRY_SECONDS = 60.0

CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
}

SaltSource = Callable[[datetime], Awaitable[bytes]]
Sink = Callable[[list[dict[str, Any]]], Awaitable[None]]
GeoLookup = Callable[[str], Geo]


def silence_access_log() -> None:
    logging.getLogger("uvicorn.access").disabled = True


class DailySalt:
    """Today's salt from `load(day)` (a store shared by every collector, which also deletes old
    salts). If the store can't be reached, a random salt kept only in memory for that day:
    visitors are then counted more than once across collectors, but nothing is less private."""

    def __init__(self, load: Callable[[date], Awaitable[bytes]]) -> None:
        self._load = load
        self._day: date | None = None
        self._salt: bytes = b""
        self._shared = False
        self._next_try = 0.0

    async def get(self, now: datetime) -> bytes:
        day = now.astimezone(UTC).date()
        if day != self._day:
            self._day, self._salt, self._shared, self._next_try = day, secrets.token_bytes(32), False, 0.0
        if not self._shared and time.monotonic() >= self._next_try:
            try:
                self._salt = await self._load(day)
                self._shared = True
            except Exception:
                self._next_try = time.monotonic() + SALT_RETRY_SECONDS
                log.warning("salt read failed; using a local salt for %s", day)
        return self._salt


class Buffer:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []
        self.dropped = 0

    def add(self, item: dict[str, Any]) -> None:
        if len(self.items) >= BUFFER_MAX:
            # Queue unreachable for a while: keep the newest.
            self.items.pop(0)
            self.dropped += 1
        self.items.append(item)

    def take(self) -> list[dict[str, Any]]:
        items, self.items = self.items, []
        return items

    def put_back(self, items: list[dict[str, Any]]) -> None:
        self.items = (items + self.items)[-BUFFER_MAX:]


def chunks(items: list[dict[str, Any]], max_bytes: int) -> list[list[dict[str, Any]]]:
    """Split a flush into messages under the queue's size cap."""
    out: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    size = 2
    for item in items:
        item_size = len(json.dumps(item, separators=(",", ":"))) + 1
        if current and size + item_size > max_bytes:
            out.append(current)
            current, size = [], 2
        current.append(item)
        size += item_size
    if current:
        out.append(current)
    return out


class IpLimiter:
    """Accepted requests per key (an IP, or proxy address and site) in the last 10 s, in memory
    only. Denied requests aren't recorded, so a sender over its limit doesn't use up a limit it
    shares with others. Swept every minute, or sooner when it holds many keys."""

    MAX_KEYS = 100_000

    def __init__(self, limit: int = IP_LIMIT) -> None:
        self.limit = limit
        self.hits: dict[str, list[float]] = {}
        self._swept = time.monotonic()

    def _window(self, key: str, now: float) -> list[float]:
        if now - self._swept > 60 or len(self.hits) > self.MAX_KEYS:
            self.hits = {k: v for k, v in self.hits.items() if now - v[-1] < IP_WINDOW_SECONDS}
            self._swept = now
        window = [stamp for stamp in self.hits.get(key, ()) if now - stamp < IP_WINDOW_SECONDS]
        if window:
            self.hits[key] = window
        else:
            self.hits.pop(key, None)
        return window

    def ok(self, key: str) -> bool:
        """Would one more request be allowed? Records nothing."""
        return len(self._window(key, time.monotonic())) < self.limit

    def add(self, key: str) -> None:
        self.hits.setdefault(key, []).append(time.monotonic())

    def allow(self, key: str) -> bool:
        if not self.ok(key):
            return False
        self.add(key)
        return True


def allow_all(*checks: tuple[IpLimiter, str]) -> bool:
    """Every limit must have room; only then is the request recorded against each of them."""
    if not all(limiter.ok(key) for limiter, key in checks):
        return False
    for limiter, key in checks:
        limiter.add(key)
    return True


def client_ip(request: Request) -> str:
    """The visitor's IP. The load balancer appends the address it saw as the last
    X-Forwarded-For entry. Behind a first-party proxy recipe (examples/, which sends
    X-QS-Proxy: 1) that address is the proxy, so the entry before it is the visitor. A forged
    entry changes the sender's visitor id; the per-address limits in `Collector.collect` cap
    how many it can make."""
    forwarded = _forwarded(request)
    if forwarded:
        if request.headers.get("x-qs-proxy") == "1" and len(forwarded) >= 2:
            return forwarded[-2]
        return forwarded[-1]
    return request.client.host if request.client else ""


def edge_ip(request: Request) -> str:
    """The address the load balancer saw: a first-party proxy, or the visitor itself."""
    forwarded = _forwarded(request)
    if forwarded:
        return forwarded[-1]
    return request.client.host if request.client else ""


def _forwarded(request: Request) -> list[str]:
    return [part.strip() for part in (request.headers.get("x-forwarded-for") or "").split(",") if part.strip()]


class Collector:
    def __init__(
        self,
        *,
        salt: SaltSource,
        send: Sink,
        geo: GeoLookup | None = None,
        max_message_bytes: int = 256 * 1024,
    ) -> None:
        self.salt = salt
        self.send = send
        self.geo = geo or (lambda _ip: EMPTY)
        self.max_message_bytes = max_message_bytes
        self.buffer = Buffer()
        self.limiter = IpLimiter()
        self.proxy_limiter = IpLimiter(PROXY_IP_LIMIT)
        self.edge_limiter = IpLimiter(PROXY_EDGE_LIMIT)

    async def flush_once(self) -> int:
        items = self.buffer.take()
        if not items:
            return 0
        sent = 0
        for batch in chunks(items, self.max_message_bytes):
            try:
                await self.send(batch)
                sent += len(batch)
            except Exception:
                log.exception("send failed; %s events kept for the next flush", len(items) - sent)
                self.buffer.put_back(items[sent:])
                break
        return sent

    async def flush_loop(self) -> None:
        while True:
            await asyncio.sleep(FLUSH_SECONDS)
            await self.flush_once()

    async def collect(self, request: Request) -> Response:
        body = await _read_body(request)
        if body is None:
            return JSONResponse({"detail": "body too large"}, status_code=413, headers=CORS)
        try:
            beacon = parse_beacon(json.loads(body or b"{}"))
        except (ValueError, BeaconError) as exc:
            return JSONResponse({"detail": str(exc)[:200]}, status_code=400, headers=CORS)
        ip = client_ip(request)
        edge = edge_ip(request)
        # Every request counts against the limits, bots included, and only accepted ones are
        # recorded. Through a proxy, the per-site and per-address limits are checked before the
        # (spoofable) client IP gets a limiter entry.
        if edge != ip:
            allowed = allow_all((self.proxy_limiter, f"{edge} {beacon.site}"), (self.edge_limiter, edge), (self.limiter, ip))
        else:
            allowed = self.limiter.allow(ip)
        if not allowed:
            return Response(status_code=429, headers=CORS)
        user_agent = request.headers.get("user-agent") or ""
        now = datetime.now(UTC)
        ts_ms = int(now.timestamp() * 1000)
        if is_bot(user_agent):
            # Bots are only counted per site per day.
            self.buffer.add({"site": beacon.site, "ts": ts_ms, "bot": 1})
            return Response(status_code=202, headers=CORS)
        salt = await self.salt(now)
        self.buffer.add(enrich(beacon, ip=ip, user_agent=user_agent, salt=salt, ts_ms=ts_ms, geo=self.geo(ip)))
        if len(self.buffer.items) >= FLUSH_AT:
            asyncio.create_task(self.flush_once())
        return Response(status_code=202, headers=CORS)


async def _read_body(request: Request) -> bytes | None:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > BODY_MAX:
        return None
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > BODY_MAX:
            return None
    return bytes(raw)


def create_app(collector: Collector, *, title: str = "QuickStatus.dev collector") -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        silence_access_log()
        task = asyncio.create_task(collector.flush_loop())
        try:
            yield
        finally:
            task.cancel()
            await collector.flush_once()

    app = FastAPI(title=title, lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    # One route for both methods, so a 405 lists both in Allow.
    @app.api_route("/e", methods=["POST", "OPTIONS"])
    async def collect(request: Request) -> Response:
        if request.method == "OPTIONS":
            return Response(status_code=204, headers=CORS)
        return await collector.collect(request)

    @app.get("/health")
    async def health() -> dict:
        return {"ok": True, "buffered": len(collector.buffer.items), "dropped": collector.buffer.dropped}

    return app

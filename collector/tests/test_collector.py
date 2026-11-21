"""The collector does what PRIVACY.md says: the visitor id matches the published formula and
test vectors, and nothing that leaves the collector (queue messages, logs) holds the IP address
or user agent.

    cd collector && pip install -e '.[test]' && pytest
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import socket
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from quickstatus_collector import Collector, DailySalt, create_app, parse_beacon, visitor_id
from quickstatus_collector.app import IP_LIMIT, PROXY_EDGE_LIMIT, PROXY_IP_LIMIT, chunks
from quickstatus_collector.events import enrich, is_bot, split_url
from quickstatus_collector.sources import SOURCES, source_for

REPO = Path(__file__).resolve().parents[2]
VECTORS = json.loads((REPO / "data" / "visitor-id-vectors.json").read_text())["vectors"]
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36"
IP = "198.51.100.7"


def from_spec(salt: bytes, site: str, ip: str, user_agent: str) -> bytes:
    """PRIVACY.md, written out independently of the package."""
    data = b""
    for part in (salt, site.encode("utf-8"), ip.encode("utf-8"), user_agent.encode("utf-8")):
        data += len(part).to_bytes(4, "big") + part
    return hashlib.sha256(data).digest()[:16]


@pytest.mark.parametrize("v", VECTORS, ids=lambda v: v["note"])
def test_visitor_id_vectors(v):
    salt = bytes.fromhex(v["salt_hex"])
    assert visitor_id(salt, v["site"], v["ip"], v["user_agent"]).hex() == v["visitor_id_hex"]
    assert from_spec(salt, v["site"], v["ip"], v["user_agent"]).hex() == v["visitor_id_hex"]


def test_privacy_md_lists_the_same_vectors():
    text = (REPO / "PRIVACY.md").read_text()
    for v in VECTORS[:2]:
        assert f"`{v['ip']}` | `{v['visitor_id_hex']}`" in text


def test_sources_json_is_the_published_list():
    package = json.loads((REPO / "collector" / "quickstatus_collector" / "sources.json").read_text())
    assert package == json.loads((REPO / "data" / "sources.json").read_text())
    assert source_for("news.google.com") == "Google" and source_for("chatgpt.com") == "ChatGPT"
    assert SOURCES["claude.ai"] == ("Claude", True)


@pytest.mark.parametrize("path", sorted((REPO / "schema" / "examples").glob("*.json")), ids=lambda p: p.name)
def test_accepts_every_schema_example(path):
    parse_beacon(json.loads(path.read_text()))


def test_queue_message_holds_no_ip_or_user_agent():
    beacon = parse_beacon({"s": "k3x9mpq2wa", "u": "https://example.com/pricing?utm_source=x&email=a@b.c", "w": 1440})
    item = enrich(beacon, ip=IP, user_agent=UA, salt=b"s" * 32, ts_ms=1, geo=("DE", "Berlin", "Berlin"))
    text = json.dumps(item)
    assert IP not in text and "Mozilla" not in text and "a@b.c" not in text
    assert set(item) <= {"site", "ts", "vid", "name", "host", "path", "ref", "source", "utm", "country", "region",
                         "city", "device", "os", "browser", "engaged_ms", "scroll", "value", "currency"}
    assert is_bot("curl/8.0") and not is_bot(UA)


async def test_daily_salt_shared_then_local_fallback():
    calls: list[date] = []

    async def load(day):
        calls.append(day)
        return b"d" * 32

    salt = DailySalt(load)
    now = datetime(2026, 1, 1, 12, tzinfo=UTC)
    assert await salt.get(now) == b"d" * 32 and await salt.get(now) == b"d" * 32 and calls == [date(2026, 1, 1)]

    async def down(_day):
        raise OSError("store unreachable")

    fallback = DailySalt(down)
    local = await fallback.get(now)
    assert len(local) == 32 and local != b"d" * 32 and await fallback.get(now) == local


@pytest.fixture
def collector():
    sent: list[list[dict]] = []

    async def salt(_now):
        return b"z" * 32

    async def send(batch):
        sent.append(batch)

    c = Collector(salt=salt, send=send)
    c.sent = sent  # type: ignore[attr-defined]
    return c


def test_collect_buffers_an_enriched_event_and_limits_per_ip(collector):
    with TestClient(create_app(collector)) as client:
        body = json.dumps({"s": "k3x9mpq2wa", "u": "https://example.com/", "w": 1440})
        assert client.post("/e", content=body, headers={"user-agent": UA, "x-forwarded-for": IP}).status_code == 202
        (item,) = collector.buffer.items
        assert item["vid"] == visitor_id(b"z" * 32, "k3x9mpq2wa", IP, UA).hex()
        assert client.post("/e", content=body, headers={"user-agent": "curl/8"}).status_code == 202
        assert collector.buffer.items[-1]["bot"] == 1
        codes = [client.post("/e", content=body, headers={"user-agent": UA, "x-forwarded-for": "192.0.2.1"}).status_code
                 for _ in range(IP_LIMIT + 1)]
        assert codes[-1] == 429 and codes[0] == 202
        assert client.post("/e", content=b"x" * 5000).status_code == 413


async def test_flush_keeps_events_when_the_queue_fails(collector):
    for i in range(3):
        collector.buffer.add({"site": "k3x9mpq2wa", "n": i})

    async def boom(_batch):
        raise RuntimeError("queue down")

    good = collector.send
    collector.send = boom
    assert await collector.flush_once() == 0 and len(collector.buffer.items) == 3
    collector.send = good
    assert await collector.flush_once() == 3 and not collector.buffer.items
    assert all(len(json.dumps(c)) <= 200 for c in chunks([{"a": "x" * 50}] * 10, 200))


async def test_no_log_line_holds_the_client_ip(collector, caplog):
    """A real uvicorn server with its access log on, as a careless deploy would start it."""
    access = logging.getLogger("uvicorn.access")
    access.disabled = False
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(collector), host="127.0.0.1", port=port, access_log=True, log_level="debug"))
    task = asyncio.create_task(server.serve())
    access.addHandler(caplog.handler)  # uvicorn's access logger doesn't propagate to root
    try:
        while not server.started:
            await asyncio.sleep(0.02)
        caplog.set_level(logging.DEBUG)
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"http://127.0.0.1:{port}/e",
                content=json.dumps({"s": "k3x9mpq2wa", "u": "https://example.com/"}),
                headers={"user-agent": UA, "x-forwarded-for": IP},
            )
        assert response.status_code == 202
        server_side = [r for r in caplog.records if not r.name.startswith(("httpx", "httpcore"))]
        logged = "\n".join(f"{r.name} {r.getMessage()} {r.args}" for r in server_side)
        assert IP not in logged and "Mozilla" not in logged, logged
        await collector.flush_once()
        assert IP not in json.dumps(collector.sent) and "Mozilla" not in json.dumps(collector.sent)
    finally:
        access.removeHandler(caplog.handler)
        server.should_exit = True
        await task


def test_spoofed_proxy_header_and_bots_stay_under_the_limits(collector):
    body = json.dumps({"s": "k3x9mpq2wa", "u": "https://example.com/", "w": 1440})
    with TestClient(create_app(collector)) as client:
        # A client inventing a visitor per request through X-QS-Proxy is capped by its own address.
        codes = [client.post("/e", content=body, headers={
            "user-agent": UA, "x-qs-proxy": "1", "x-forwarded-for": f"10.0.{i // 250}.{i % 250}, 203.0.113.9"}).status_code
            for i in range(PROXY_IP_LIMIT + 1)]
        assert codes.count(202) == PROXY_IP_LIMIT and codes[-1] == 429
        # Keyed by site too: another site behind the same (possibly shared) proxy address is unaffected.
        other = json.dumps({"s": "othersite01", "u": "https://other.example/", "w": 1440})
        assert client.post("/e", content=other, headers={
            "user-agent": UA, "x-qs-proxy": "1", "x-forwarded-for": "10.9.9.9, 203.0.113.9"}).status_code == 202
        bots = [client.post("/e", content=body, headers={"user-agent": "curl/8.5", "x-forwarded-for": "203.0.113.10"}).status_code
                for _ in range(IP_LIMIT + 1)]
        assert bots[-1] == 429


def test_get_on_e_lists_post_in_allow(collector):
    with TestClient(create_app(collector)) as client:
        response = client.get("/e")
        assert response.status_code == 405
        assert set(response.headers["allow"].replace(" ", "").split(",")) == {"POST", "OPTIONS"}
        assert client.options("/e").status_code == 204


def test_hash_routes_keep_their_route_and_engage_needs_e():
    assert split_url("https://www.example.com/#/settings")[1] == "/#/settings"
    assert split_url("https://www.example.com/#!/settings")[1] == "/#!/settings"
    assert split_url("https://www.example.com/docs?x=1")[1] == "/docs"
    # The route's query is never stored, but its UTM tags count; other fragments are dropped.
    assert split_url("https://www.example.com/#/reset?token=SECRET&utm_source=x") == (
        "www.example.com", "/#/reset", {"source": "x"})
    assert split_url("https://www.example.com/#access_token=ya29.SECRET&token_type=Bearer")[1] == "/"
    assert split_url("https://www.example.com/pricing#faq")[1] == "/pricing"
    assert split_url("https://www.example.com/#/callback#access_token=SECRET")[1] == "/#/callback"
    with pytest.raises(ValueError):
        parse_beacon({"s": "k3x9mpq2wa", "n": "engage", "u": "https://example.com/"})


def test_lookalike_google_hosts_and_cubot_phones():
    for host in ("google.com", "google.de", "www.google.co.uk", "news.google.fr", "google.com.au"):
        assert source_for(host) == "Google", host
    for host in ("google.attacker.example", "google.com.attacker", "google.xyz", "google.top", "google.icu"):
        assert source_for(host) == host, host
    cubot = "Mozilla/5.0 (Linux; Android 12; CUBOT X30) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/23.0 Chrome/115.0 Mobile Safari/537.36"
    assert not is_bot(cubot)
    assert is_bot("Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)")


def test_random_site_ids_through_a_spoofed_proxy_hit_the_address_ceiling(collector):
    with TestClient(create_app(collector)) as client:
        codes = []
        for i in range(PROXY_EDGE_LIMIT + 1):
            body = json.dumps({"s": f"site{i:06d}", "u": "https://example.com/", "w": 1440})
            codes.append(client.post("/e", content=body, headers={
                "user-agent": UA, "x-qs-proxy": "1",
                "x-forwarded-for": f"10.{i // 62500}.{i // 250 % 250}.{i % 250}, 203.0.113.50"}).status_code)
        assert codes.count(202) == PROXY_EDGE_LIMIT and codes[-1] == 429


def test_a_site_over_its_proxy_limit_does_not_block_other_sites(collector):
    """Denied requests aren't recorded, so one site going over 600 doesn't use up the shared
    per-address ceiling, and rejected spoofed IPs leave no limiter entries."""
    proxy = "192.0.2.50"

    def post(client, site, i):
        body = json.dumps({"s": site, "u": "https://example.com/", "w": 1440})
        return client.post("/e", content=body, headers={
            "user-agent": UA, "x-qs-proxy": "1",
            "x-forwarded-for": f"10.{i // 62500}.{i // 250 % 250}.{i % 250}, {proxy}"}).status_code

    with TestClient(create_app(collector)) as client:
        codes = [post(client, "busysite01", i) for i in range(PROXY_IP_LIMIT + 400)]
        assert codes.count(202) == PROXY_IP_LIMIT
        assert len(collector.edge_limiter.hits[proxy]) == PROXY_IP_LIMIT
        assert len(collector.limiter.hits) == PROXY_IP_LIMIT
        assert post(client, "othersite01", 99_999) == 202

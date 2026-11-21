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
from quickstatus_collector.app import IP_LIMIT, chunks
from quickstatus_collector.events import enrich, is_bot
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

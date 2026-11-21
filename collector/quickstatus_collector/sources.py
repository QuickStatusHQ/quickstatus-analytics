"""Referrer host -> source name, from sources.json (a copy of data/sources.json; the tests check
they're identical). Hosts match after a leading `www.` / `m.` is removed, first exactly, then by
parent domain (`news.google.com` -> google.com). AI hosts match exactly only."""

from __future__ import annotations

import json
from pathlib import Path

_DATA = json.loads((Path(__file__).with_name("sources.json")).read_text(encoding="utf-8"))

# host -> (name, is_ai)
SOURCES: dict[str, tuple[str, bool]] = {host: (v["name"], bool(v["ai"])) for host, v in _DATA["sources"].items()}
AI_SOURCES: frozenset[str] = frozenset(name for name, ai in SOURCES.values() if ai)


def _strip(host: str) -> str:
    host = host.lower().strip().rstrip(".")
    for prefix in ("www.", "m."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    return host


def source_for(host: str | None) -> str | None:
    """A display name for a referrer host. Unknown hosts are returned as they are."""
    if not host:
        return None
    host = _strip(host)
    if host in SOURCES:
        return SOURCES[host][0]
    parts = host.split(".")
    for start in range(1, len(parts) - 1):
        parent = ".".join(parts[start:])
        if parent in SOURCES and not SOURCES[parent][1]:
            # AI hosts match exactly only: gemini.google.com must not make every
            # *.google.com an AI source, and the reverse.
            return SOURCES[parent][0]
    # Google ccTLDs (google.de, google.co.uk, news.google.fr).
    if "google" in parts[:-1] and len(parts) - parts.index("google") <= 3:
        return "Google"
    return host


def is_ai_source(name: str | None) -> bool:
    return bool(name) and name in AI_SOURCES

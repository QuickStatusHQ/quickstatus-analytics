"""IP -> (country code, region, city) from an MMDB city database (DB-IP "IP to City Lite" or
MaxMind GeoLite2-City; neither may be bundled here, so you bring the file). Only these three
names are read; the IP is looked up and not kept. Without a file or the `maxminddb` package,
every lookup returns (None, None, None)."""

from __future__ import annotations

import logging
from typing import Any, Callable

log = logging.getLogger("quickstatus_collector.geo")

Geo = tuple[str | None, str | None, str | None]
EMPTY: Geo = (None, None, None)


def _name(node: Any) -> str | None:
    if not isinstance(node, dict):
        return None
    names = node.get("names")
    if isinstance(names, dict) and isinstance(names.get("en"), str):
        return names["en"][:120]
    return None


def from_record(record: Any) -> Geo:
    if not isinstance(record, dict):
        return EMPTY
    country = record.get("country") or {}
    code = country.get("iso_code") if isinstance(country, dict) else None
    subdivisions = record.get("subdivisions") or []
    region = _name(subdivisions[0]) if subdivisions else None
    return (code if isinstance(code, str) else None, region, _name(record.get("city")))


def mmdb_lookup(path: str | None) -> Callable[[str], Geo]:
    """A lookup function for the file at `path`, opened once."""
    reader = None
    if path and path.strip():
        try:
            import maxminddb  # type: ignore[import-not-found]

            reader = maxminddb.open_database(path.strip())
        except Exception:
            log.warning("geo database not available at %s; locations will be Unknown", path)

    def lookup(ip: str) -> Geo:
        if reader is None or not ip:
            return EMPTY
        try:
            return from_record(reader.get(ip))
        except Exception:
            return EMPTY

    return lookup

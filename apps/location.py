"""Approximate country from a local, attributed IP snapshot.

No client address is returned, persisted or sent to a third party. The caller
passes the ASGI client address; proxy headers are handled only by the server's
trusted-proxy configuration, not trusted here.
"""
from __future__ import annotations

import gzip
import ipaddress
import json
from functools import lru_cache
from pathlib import Path

import maxminddb

DATA = Path(__file__).resolve().parents[1] / "domains" / "trips" / "data"
DATABASE = DATA / "dbip-country-lite-2026-10.mmdb.gz"


@lru_cache(maxsize=1)
def _reader():
    try:
        # MODE_FD loads the decompressed database into memory and needs no
        # temporary file; gzip's file object is closed immediately afterwards.
        with gzip.open(DATABASE, "rb") as stream:
            return maxminddb.open_database(stream, maxminddb.MODE_FD)
    except (OSError, ValueError, maxminddb.InvalidDatabaseError):
        return None


@lru_cache(maxsize=1)
def _names() -> dict[str, str]:
    return json.loads((DATA / "countries_ru.json").read_text(encoding="utf-8"))


def visitor_country(host: str | None) -> dict:
    result = {"country_code": None, "country_name": None, "source": None}
    try:
        address = ipaddress.ip_address(host or "")
    except ValueError:
        return result
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    if not address.is_global:
        return result
    reader = _reader()
    if reader is None:
        return result
    try:
        record = reader.get(str(address)) or {}
    except (ValueError, maxminddb.InvalidDatabaseError):
        return result
    code = (record.get("country") or {}).get("iso_code")
    name = _names().get(code)
    if name:
        result.update(country_code=code, country_name=name,
                      source={"name": "DB-IP Lite", "release": "2026-10",
                              "url": "https://db-ip.com/"})
    return result

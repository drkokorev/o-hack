"""Approximate country locally and approximate city via IPinfo.

City lookup sends the address to IPinfo; addresses are not returned or saved by
this application. Proxy headers are handled only by trusted server settings.
"""
from __future__ import annotations

import gzip
import ipaddress
import json
import threading
import time
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

import maxminddb

DATA = Path(__file__).resolve().parents[1] / "domains" / "trips" / "data"
DATABASE = DATA / "dbip-country-lite-2026-10.mmdb.gz"
_public_lock = threading.Lock()
_local_city_cache: tuple[float, dict | None] = (float("-inf"), None)


@lru_cache(maxsize=1)
def _reader():
    try:
        # MODE_FD loads the decompressed database into memory and needs no
        # temporary file; gzip's file object is closed immediately afterwards.
        with gzip.open(DATABASE, "rb") as stream:
            return maxminddb.open_database(stream, maxminddb.MODE_FD)
    except (OSError, ValueError, maxminddb.InvalidDatabaseError):
        return None


def _fetch_city(address: str | None) -> dict | None:
    """Query only a validated address, or the local preview's own egress IP."""
    path = f"/{quote(address, safe='')}/json" if address else "/json"
    try:
        with urlopen("https://ipinfo.io" + path, timeout=4) as response:
            data = json.loads(response.read(8192))
        if not isinstance(data, dict):
            return None
        city = data.get("city")
        return {"city": city} if isinstance(city, str) and city.strip() and len(city) <= 100 else None
    except (OSError, ValueError, UnicodeError, TypeError):
        return None


def _local_city() -> dict | None:
    """Cache only the city, not the public IP, for five minutes."""
    global _local_city_cache
    with _public_lock:
        now = time.monotonic()
        if now - _local_city_cache[0] < 300:
            return _local_city_cache[1]
        value = _fetch_city(None)
        _local_city_cache = (now, value)
        return value


def city_hint(city: str | None) -> dict:
    """Normalise a city from an untrusted IP lookup; only known origins are auto-filled."""
    result = {"city_name": None, "origin": None, "source": None, "approximate": True}
    if (not isinstance(city, str) or not city.strip() or len(city) > 100 or
            any(not (character.isalnum() or character in " .-'’") for character in city)):
        return result
    city = city.strip()
    from domains.trips.geo import ORIGINS
    aliases = {"moscow": "Москва", "saint petersburg": "Санкт-Петербург", "st petersburg": "Санкт-Петербург",
               "kazan": "Казань", "yekaterinburg": "Екатеринбург", "ekaterinburg": "Екатеринбург",
               "novosibirsk": "Новосибирск", "nizhny novgorod": "Нижний Новгород", "samara": "Самара"}
    supported = {origin.name.casefold(): origin.name for origin in ORIGINS}
    supported.update({origin.en.casefold(): origin.name for origin in ORIGINS if origin.en})
    origin = supported.get(city.casefold()) or aliases.get(city.casefold())
    result.update(city_name=origin or city, origin=origin,
                  source={"name": "IPinfo", "url": "https://ipinfo.io/"})
    return result


def visitor_city(host: str | None, *, local_preview: bool = False) -> dict:
    """Approximate IP city; never return or store the address in the result."""
    try:
        address = ipaddress.ip_address(host or "")
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        if address.is_loopback and local_preview:
            record = _local_city()
        elif address.is_global:
            record = _fetch_city(str(address))
        else:
            record = None
    except ValueError:
        record = None
    return city_hint((record or {}).get("city"))


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

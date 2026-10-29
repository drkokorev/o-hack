"""Local IP hints; no visitor addresses are sent to a geolocation service."""
from __future__ import annotations

import gzip
import ipaddress
import json
import os
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
def _city_reader():
    """An optional operator-supplied MMDB; a missing file never enables a network fallback."""
    configured = os.getenv("ODIN_CITY_DATABASE", "").strip()
    if not configured:
        return None
    path = Path(configured).expanduser()
    try:
        opener = gzip.open if path.suffix.lower() == ".gz" else open
        with opener(path, "rb") as stream:
            return maxminddb.open_database(stream, maxminddb.MODE_FD)
    except (OSError, ValueError, maxminddb.InvalidDatabaseError):
        return None


def city_hint(city: str | None, *, source: dict | None = None) -> dict:
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
    result.update(city_name=origin or city, origin=origin, source=source)
    return result


def visitor_city(host: str | None, *, local_preview: bool = False) -> dict:
    """Read only a local database. The legacy preview flag cannot enable external lookup."""
    try:
        address = ipaddress.ip_address(host or "")
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
            address = address.ipv4_mapped
        reader = _city_reader() if address.is_global else None
        record = reader.get(str(address)) if reader else None
        if not isinstance(record, dict):
            return city_hint(None)
        names = (record.get("city") or {}).get("names") or {}
        result = city_hint(names.get("ru") or names.get("en"),
                           source={"name": "Локальная база IP-городов"})
        # A namesake abroad must not become one of the Russian departure cities.
        if (record.get("country") or {}).get("iso_code") != "RU":
            result["origin"] = None
        return result
    except (ValueError, TypeError, AttributeError, maxminddb.InvalidDatabaseError):
        return city_hint(None)


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

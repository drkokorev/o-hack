"""Inventory boundary used by planning; the default provider is explicitly demo.

Provider data and simulation are in providers/, contracts in offer_models.py.
The Ostrovok read-only adapter has a different live contract and is not silently
substituted for a demo provider. No search fallback can claim a live booking.
"""
from functools import lru_cache
from datetime import date
from .geo import Destination, Origin, distance_km  # compatibility for existing callers
from .offer_models import AMENITIES, MEALS, Hotel, Leg, Transfer
from .providers.base import InventoryProvider
from .providers.demo_inventory import (
    DemoInventory, _real, _real_kind_stars, _official_site, _clean_name,
    season_factor, hotel_day_factors, flights, trains,
)

inventory: InventoryProvider = DemoInventory(catalog=lambda: _real())


@lru_cache(maxsize=150)
def _provider_hotels(provider: InventoryProvider, dest_id: str, count: int) -> tuple[Hotel, ...]:
    return provider.hotels_for(dest_id, count)


def hotels_for(dest_id: str, count: int = 12) -> tuple[Hotel, ...]:
    return _provider_hotels(inventory, dest_id, count)


# Retain the cache-control hook used by catalog rebuilds and older callers.
hotels_for.cache_clear = _provider_hotels.cache_clear


def hotel_count() -> int:
    return inventory.hotel_count()


def hotel_price(hotel: Hotel, check_in: date, nights: int, adults: int, children: int) -> int:
    return inventory.hotel_price(hotel, check_in, nights, adults, children)


def transport_options(origin: Origin, dest: Destination, day: date, mode: str | None = None) -> list[Leg]:
    return inventory.transport_options(origin, dest, day, mode)


def transfer(hotel: Hotel, guests: int, train: bool = False, preferred: str | None = None) -> Transfer:
    return inventory.transfer(hotel, guests, train, preferred)

"""Read-only Ostrovok B2B geo search adapter; not connected to the demo UI.

Requires partner credentials and a separately confirmed agreement. It cannot
create bookings or make payments. SERP prices are preliminary; hotelpage and
prebook are required before an actual booking flow can be designed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
import re

import httpx


SEARCH_URL = "https://api.ostrovok.ru/api/b2b/v3/search/serp/geo/"


class OstrovokSearchError(RuntimeError):
    """A safe error without credentials, raw requests, or provider response bodies."""


@dataclass(frozen=True)
class RoomGuests:
    """One explicitly allocated room. Child ages are supplied by the user, not inferred."""
    adults: int
    child_ages: tuple[int, ...] = ()

    def body(self) -> dict:
        if not isinstance(self.adults, int) or isinstance(self.adults, bool) or not 1 <= self.adults <= 6:
            raise ValueError("В каждом номере нужно от 1 до 6 взрослых")
        if not isinstance(self.child_ages, (tuple, list)) or len(self.child_ages) > 4 or any(not isinstance(age, int) or isinstance(age, bool) or not 0 <= age <= 17
                                            for age in self.child_ages):
            raise ValueError("В каждом номере допустимо до 4 детей с возрастом от 0 до 17 лет")
        return {"adults": self.adults, "children": list(self.child_ages)}


@dataclass(frozen=True)
class SearchQuery:
    checkin: date
    checkout: date
    latitude: float
    longitude: float
    adults: int | None = None
    child_ages: tuple[int, ...] = ()
    residency: str | None = None
    radius: int = 10000
    language: str = "ru"
    currency: str = "RUB"
    rooms: tuple[RoomGuests, ...] = ()

    def body(self) -> dict:
        if self.checkout <= self.checkin or (self.checkout - self.checkin).days > 30:
            raise ValueError("Окончание проживания должно быть позже начала, не более 30 дней")
        if not (-90 <= self.latitude <= 90 and -180 <= self.longitude <= 180):
            raise ValueError("Некорректные координаты")
        if not isinstance(self.radius, int) or isinstance(self.radius, bool) or not 1 <= self.radius <= 70000:
            raise ValueError("Некорректный радиус")
        if self.rooms:
            if self.adults is not None or self.child_ages or len(self.rooms) > 9:
                raise ValueError("Укажите только распределение по 1–9 номерам, без общего состава")
            if any(not isinstance(room, RoomGuests) for room in self.rooms):
                raise ValueError("Некорректное распределение гостей по номерам")
            guests = [room.body() for room in self.rooms]
        else:
            guests = [RoomGuests(self.adults, self.child_ages).body()]
        if self.residency is not None and not re.fullmatch(r"[a-zA-Z]{2}", self.residency):
            raise ValueError("Гражданство должно быть двухбуквенным кодом страны")
        if not re.fullmatch(r"[A-Z]{3}", self.currency):
            raise ValueError("Валюта должна быть трёхбуквенным кодом")
        body = {"checkin": self.checkin.isoformat(), "checkout": self.checkout.isoformat(),
                "latitude": self.latitude, "longitude": self.longitude, "radius": self.radius,
                "guests": guests,
                "language": self.language, "currency": self.currency}
        if self.residency:
            body["residency"] = self.residency.lower()
        return body


@dataclass(frozen=True)
class SearchHotel:
    hid: int | None
    hotel_id: str | None
    amount: Decimal | None
    currency: str | None
    # These are search-stage prices, not bookable hotelpage/prebook rates.
    requires_revalidation: bool = True


@dataclass(repr=False)
class OstrovokSearchClient:
    key_id: str = field(repr=False)
    api_key: str = field(repr=False)
    transport: httpx.BaseTransport | None = field(default=None, repr=False)

    def search(self, query: SearchQuery) -> tuple[SearchHotel, ...]:
        if not self.key_id or not self.api_key:
            raise OstrovokSearchError("Для поиска нужен партнёрский доступ Островка")
        body = query.body()  # Validation before network I/O.
        try:
            with httpx.Client(transport=self.transport, timeout=20.0, follow_redirects=False) as client:
                response = client.post(SEARCH_URL, auth=(self.key_id, self.api_key), json=body)
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError):
            raise OstrovokSearchError("Не удалось получить данные поиска Островка") from None
        if (not isinstance(data, dict) or data.get("status") != "ok" or data.get("error") not in (None, "") or
                not isinstance(data.get("data"), dict)):
            raise OstrovokSearchError("Поиск Островка вернул ошибку или некорректный ответ")
        hotels = data["data"].get("hotels")
        if not isinstance(hotels, list):
            raise OstrovokSearchError("В ответе поиска нет списка отелей")
        results = []
        for hotel in hotels:
            if not isinstance(hotel, dict):
                continue
            prices = []
            for rate in hotel.get("rates") or []:
                if not isinstance(rate, dict):
                    continue
                options = rate.get("payment_options") or {}
                if not isinstance(options, dict):
                    continue
                for option in options.get("payment_types") or []:
                    if not isinstance(option, dict):
                        continue
                    amount, currency = option.get("show_amount"), option.get("show_currency_code")
                    try:
                        amount = Decimal(str(amount))
                    except (InvalidOperation, ValueError):
                        continue
                    if amount.is_finite() and amount >= 0 and currency == query.currency:
                        prices.append(amount)
            results.append(SearchHotel(hid=hotel.get("hid"), hotel_id=hotel.get("id"),
                                       amount=min(prices) if prices else None,
                                       currency=query.currency if prices else None))
        return tuple(results)

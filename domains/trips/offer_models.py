"""Offer contracts and labels; provenance is independent from an object name."""
from datetime import datetime
from pydantic import BaseModel, Field

MEALS = {"room_only": "без питания", "breakfast": "завтраки", "half_board": "полупансион",
         "all_inclusive": "всё включено", "meal_included": "питание включено, вид уточняется"}


AMENITIES = {
    "pool": "бассейн", "kids_club": "детский клуб", "spa": "спа", "gym": "фитнес", "parking": "парковка",
    "pets": "питомцы: условия не проверены", "beach_line": "первая линия", "wifi": "Wi-Fi", "kitchen": "кухня в номере",
}


class Hotel(BaseModel):
    id: str
    dest_id: str
    name: str
    kind: str
    stars: int
    area: str
    center_km: float
    beach_km: float | None
    airport_km: float
    rating: float
    reviews: int
    base_price: int                     # за ночь на двоих в средний сезон
    meal: str
    amenities: list[str]
    check_in: str = "14:00"
    check_out: str = "12:00"
    early_checkin_fee: int | None = None   # None — ранний заезд только по наличию
    free_cancel_days: int | None = None    # None — невозвратный тариф
    praise: list[str] = Field(default_factory=list)
    complaints: list[str] = Field(default_factory=list)
    source: str = "model"                  # overture — настоящий объект из Overture Maps, model — синтетика
    website: str | None = None
    map_url: str | None = None
    lat: float | None = None
    lon: float | None = None

    def field_sources(self) -> dict[str, str]:
        """A named catalog object is not evidence for generated commercial facts."""
        return {'identity': self.source, 'price': 'demo', 'rating': 'demo', 'reviews': 'demo',
                'amenities': 'unverified_demo', 'cancellation': 'demo', 'availability': 'not_checked'}


class Leg(BaseModel):
    """Один перелёт или поезд «от двери до двери» между городами (возможна пересадка)."""
    id: str
    mode: str                      # plane | train
    carrier: str
    number: str
    depart: datetime
    arrive: datetime
    stops: int = 0
    via: str | None = None
    layover_min: int = 0
    baggage: bool = True
    seat_class: str = "эконом"
    price_per_person: int = 0
    pets_ok: bool = True
    note: str = ""

    @property
    def minutes(self) -> int:
        return int((self.arrive - self.depart).total_seconds() // 60)


class Transfer(BaseModel):
    kind: str          # taxi | shuttle
    minutes: int
    price: int         # за машину / за всех
    note: str = ""

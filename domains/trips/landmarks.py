"""Достопримечательность → направление каталога: «парковка Дайкоку» → Токио, «Эйфелева башня» → Париж.

Где находится объект, отвечает модель (короткий JSON-запрос). Модели не верим на слово:
- город должен найтись в базе городов мира (GeoNames) в названной моделью стране;
- направление каталога — сам этот город или ближайшее направление той же страны не дальше 250 км.
Пользователю всегда говорим, что место определила модель, и предлагаем поправить.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache

from core.llm import strip_think

from .geo import DESTINATIONS, Destination, distance_km
from .rules import find_destination
from .textparse import norm
from .world_places import find_world_places

log = logging.getLogger(__name__)
MAX_KM = 250

PROMPT = """Пользователь сервиса поездок назвал место. Определи, где оно находится.
Ответь только JSON без пояснений:
{"known": true|false, "what": "что это, 2–5 слов по-русски", "city": "ближайший город по-русски",
 "country": "страна по-русски"}
Если не знаешь места точно — {"known": false}. Не угадывай."""


@dataclass(frozen=True)
class Landmark:
    name: str
    what: str
    city: str
    country: str
    dest: Destination | None
    km: int | None
    nearest: Destination | None = None  # если рядом нет — ближайшее в стране, только как предложение
    nearest_km: int | None = None

    def note(self) -> str:
        # Что это за объект, модель нередко описывает неверно («паркинг Ханэда» вместо Иокогамы); город и страну
        # мы проверили по базе городов — показываем только их
        where = f"{self.city}, {self.country}"
        if self.dest is None:
            far = (f" Ближайшее направление каталога в этой стране — {self.nearest.name} (~{self.nearest_km} км): "
                   f"напишите «{self.nearest.name}», если подходит." if self.nearest else "")
            return (f"«{self.name}» — по данным языковой модели, это {where}. Рядом направлений в каталоге "
                    f"прототипа нет.{far} Или назовите другое место.")
        near = "" if self.km is None or self.km < 30 else f", ~{self.km} км"
        return (f"«{self.name}» — по данным языковой модели, это {where}. Подбираю направление каталога — "
                f"{self.dest.name}{near}. Если имели в виду другое место, поправьте меня.")


def _same_country(a: str, b: str) -> bool:
    a, b = norm(a), norm(b)
    return bool(a) and bool(b) and (a[:5] == b[:5])


def _ask(llm, name: str) -> dict:
    raw = strip_think(llm.complete([{"role": "system", "content": PROMPT},
                                    {"role": "user", "content": f"Место: «{name}»"}]))
    found = re.search(r"\{.*\}", raw, re.S)
    return json.loads(found.group(0)) if found else {}


@lru_cache(maxsize=256)
def _cached(llm, name: str) -> Landmark | None:
    return _resolve(llm, name)


def resolve(llm, name: str) -> Landmark | None:
    """None — модель не знает места, ответила не по форме или её ответ не подтвердился базой городов."""
    if llm is None or not name or len(name) > 80:
        return None
    try:
        return _cached(llm, name)
    except Exception as err:  # недоступна, не JSON — место останется неизвестным; сбой не кешируем
        log.info("Определение места недоступно: %s", type(err).__name__)
        return None


def _resolve(llm, name: str) -> Landmark | None:
    # Два независимых ответа: модель уверенно ошибается (Дайкоку то в Токио, то «в Москве»),
    # а два разных города — признак догадки
    data, again = _ask(llm, name), _ask(llm, name)
    if norm(str(data.get("city") or ""))[:4] != norm(str(again.get("city") or ""))[:4]:
        log.info("Модель назвала разные города для «%s»: %s / %s", name, data.get("city"), again.get("city"))
        return None
    if not data.get("known") or not data.get("city") or not data.get("country"):
        return None
    city, country = str(data["city"]).strip(), str(data["country"]).strip()
    what = str(data.get("what") or "").strip()[:60]
    dest_id = find_destination(norm(city))
    if dest_id:
        dest = next(d for d in DESTINATIONS if d.id == dest_id)
        if _same_country(dest.country, country):
            return Landmark(name, what, city, country, dest, None)
    places = [p for p in find_world_places(city) if _same_country(p.country, country)]
    if not places:
        log.info("Город модели «%s, %s» не найден в базе городов", city, country)
        return None
    place = places[0]
    nearby = sorted((distance_km(place.lat, place.lon, d.lat, d.lon), d) for d in DESTINATIONS
                    if _same_country(d.country, country))
    if nearby and nearby[0][0] <= MAX_KM:
        return Landmark(name, what, city, country, nearby[0][1], round(nearby[0][0]))
    if nearby:
        return Landmark(name, what, city, country, None, None, nearby[0][1], round(nearby[0][0]))
    return Landmark(name, what, city, country, None, None)

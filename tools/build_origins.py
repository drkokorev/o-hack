"""Города отправления: все города России от 50 тыс. жителей с ближайшим аэропортом.

    .venv/bin/python -m tools.build_origins

Источники уже в проекте: domains/trips/data/world_cities.sqlite3 (GeoNames, CC BY 4.0) — название, координаты,
население; domains/trips/data/ourairports.json (OurAirports, public domain) — аэропорты с регулярными рейсами.
Русское название берётся из русских синонимов GeoNames, родительный падеж («из Пензы») — pymorphy2.
Существующие города справочника (Москва, Санкт-Петербург…) и их флаги не меняются.
"""

from __future__ import annotations

import json
import re
import sqlite3
from difflib import SequenceMatcher
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "domains" / "trips" / "data"
MIN_POPULATION = 50_000
# Нет пассажирской железной дороги до материковой сети
NO_RAIL = {"Петропавловск-Камчатский", "Магадан", "Якутск", "Южно-Сахалинск", "Норильск", "Анадырь"}
TRANSLIT = [("shch", "щ"), ("kh", "х"), ("zh", "ж"), ("ts", "ц"), ("ch", "ч"), ("sh", "ш"), ("yu", "ю"), ("ya", "я"),
            ("ye", "е"), ("yo", "ё"), ("ë", "ё"), ("iy", "ий"), ("yy", "ый"), ("a", "а"), ("b", "б"), ("v", "в"),
            ("g", "г"), ("d", "д"), ("e", "е"), ("z", "з"), ("i", "и"), ("y", "ы"), ("k", "к"), ("l", "л"),
            ("m", "м"), ("n", "н"), ("o", "о"), ("p", "п"), ("r", "р"), ("s", "с"), ("t", "т"), ("u", "у"),
            ("f", "ф"), ("'", "ь"), ("’", "ь")]
LOWER_PARTS = {"на", "над", "де", "в", "у"}
# Синонимы GeoNames, которые автоматический выбор передаёт неточно (проверено вручную по списку)
NAME_FIXES = {"Уляновск": "Ульяновск", "Брацк": "Братск", "Норилск": "Норильск", "Южносахалинск": "Южно-Сахалинск",
              "Петропавловск-Камчатски": "Петропавловск-Камчатский", "Артем": "Артём", "Орел": "Орёл",
              "Красная Глинка": None}  # район Самары
GENITIVE_FIXES = {"Лиски": "Лисок", "Туймазы": "Туймазов", "Полевской": "Полевского", "Улан-Удэ": "Улан-Удэ",
                  "Кирово-Чепецк": "Кирово-Чепецка", "Южно-Сахалинск": "Южно-Сахалинска", "Йошкар-Ола": "Йошкар-Олы", "Кумертау": "Кумертау"}


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 6371 * 2 * asin(sqrt(a))


def _translit(name: str) -> str:
    text = name.lower()
    for latin, cyr in TRANSLIT:
        text = text.replace(latin, cyr)
    return text


def _known_place(word: str, morph) -> bool:
    return any(p.tag.case == "nomn" and ({"Geox"} & p.tag.grammemes) and p.normal_form == word
               for p in morph.parse(word))


def _russian_name(english: str, aliases: list[str], morph) -> str | None:
    cyrillic = [a for a in aliases if re.fullmatch(r"[а-яё \-]+", a) and not re.search(r"[іїєґў]", a)]
    if not cyrillic:
        return None
    guess = _translit(english)

    def score(alias: str) -> tuple:
        words = re.split(r"[ \-]", alias)
        known = sum(_known_place(w, morph) for w in words) / len(words)  # «пермь», а не «перм»
        same_shape = re.sub(r"[^ \-]", "", alias) == re.sub(r"[^ \-]", "", english.replace("'", ""))
        return (SequenceMatcher(None, alias.replace("ё", "е"), guess.replace("ё", "е")).ratio() + 0.3 * known
                + 0.1 * same_shape, "ё" in alias, -len(alias))

    best = max(cyrillic, key=score)
    if SequenceMatcher(None, best.replace("ё", "е"), guess.replace("ё", "е")).ratio() < 0.6:
        return None
    parts = re.split(r"([ \-])", best)
    return "".join(p if p in " -" or (p in LOWER_PARTS and i) else p[:1].upper() + p[1:] for i, p in enumerate(parts))


def _genitive(name: str, morph) -> str:
    """«Пенза» → «Пензы», «Великие Луки» → «Великих Лук», «Ростов-на-Дону» → «Ростова-на-Дону».
    Если хоть одно слово словарь не знает («Улан-Удэ», «Йошкар-Ола») — оставляем как есть: «из Улан-Удэ»."""
    def inflect(word: str) -> str | None:
        parses = [p for p in morph.parse(word.lower()) if p.tag.case == "nomn" and p.is_known]
        parses.sort(key=lambda p: ("Geox" not in p.tag.grammemes, p.tag.POS not in {"NOUN", "ADJF"}))
        for parse in parses:
            form = parse.inflect({"gent", parse.tag.number} if parse.tag.number else {"gent"})
            if form:
                return form.word[:1].upper() + form.word[1:] if word[:1].isupper() else form.word
        return None

    tokens = re.split(r"([ \-])", name)
    head_only = "-" in name and any(t in LOWER_PARTS for t in tokens[1:])
    out = []
    for i, token in enumerate(tokens):
        if token in " -" or token in LOWER_PARTS or (head_only and i > 0):
            out.append(token)
            continue
        form = inflect(token)
        if form is None:
            return name
        out.append(form)
    return "".join(out)


def main() -> None:
    from core.privacy import _morph

    morph = _morph()
    geo_path = DATA / "geo.json"
    geo = json.loads(geo_path.read_text(encoding="utf-8"))
    known = {o["name"] for o in geo["origins"]}
    airports = [a for a in json.loads((DATA / "ourairports.json").read_text(encoding="utf-8"))["airports"]
                if a["country"] == "RU" and a["iata"] and a["scheduled_service"] == "yes"]
    db = sqlite3.connect(DATA / "world_cities.sqlite3")
    rows = db.execute("SELECT id, name, lat, lon, population FROM city WHERE country = 'Россия' AND population >= ? "
                      "ORDER BY population DESC", (MIN_POPULATION,)).fetchall()
    added, skipped = [], []
    big = {"Москва": 35, "Санкт-Петербург": 30}
    centers = [(o["lat"], o["lon"], big.get(o["name"], 15)) for o in geo["origins"]]
    for city_id, english, lat, lon, _population in rows:
        aliases = [r[0] for r in db.execute("SELECT name FROM alias WHERE city_id = ?", (city_id,))]
        name = _russian_name(english, aliases, morph)
        name = NAME_FIXES.get(name, name)
        if not name:
            skipped.append(english)
            continue
        if name.replace("ё", "е") in {k.replace("ё", "е") for k in known}:
            continue
        # районы и спутники крупных городов (Марьино, Химки, «Хабаровск Второй») — едут из самого города
        if any(_km(lat, lon, c_lat, c_lon) < radius for c_lat, c_lon, radius in centers):
            continue
        nearest = min(airports, key=lambda a: _km(lat, lon, a["lat"], a["lon"]))
        added.append({"name": name, "iata": nearest["iata"], "lat": round(lat, 4), "lon": round(lon, 4),
                      "hub": False, "rail": name not in NO_RAIL, "gen": GENITIVE_FIXES.get(name) or _genitive(name, morph),
                      "airport_km": round(_km(lat, lon, nearest["lat"], nearest["lon"])), "en": english})
        known.add(name)
        centers.append((lat, lon, 15))
    base = [o for o in geo["origins"] if "airport_km" not in o]
    geo["origins"] = base + added
    geo_path.write_text(json.dumps(geo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Городов отправления: {len(geo['origins'])} (добавлено {len(added)}); без русского названия: {skipped}")


if __name__ == "__main__":
    main()

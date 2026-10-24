"""Собирает климат направлений по месяцам из Open-Meteo (CC BY 4.0) в domains/trips/data/climate.json.

    .venv/bin/python -m tools.build_climate

Берём дневные данные за 2022–2025 годы и усредняем по месяцам: дневная и ночная температура,
дни с заметным дождём (≥ 5 мм), сумма осадков, температура моря у побережья. Агент работает с готовым файлом и сети не требует.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path
from statistics import mean
from urllib.parse import urlencode
from urllib.request import urlopen

from domains.trips.geo import DESTINATIONS

OUT = Path(__file__).resolve().parent.parent / "domains" / "trips" / "data" / "climate.json"
START, END = "2022-01-01", "2025-12-31"


def fetch(url: str, params: dict) -> dict:
    for attempt in range(4):
        try:
            with urlopen(f"{url}?{urlencode(params)}", timeout=60) as resp:
                return json.load(resp)
        except Exception:
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("недостижимо")


def monthly(times: list[str], values: list[float | None]) -> dict[int, list[float]]:
    out: dict[int, list[float]] = defaultdict(list)
    for t, v in zip(times, values):
        if v is not None:
            out[int(t[5:7])].append(v)
    return out


def main() -> None:
    result: dict = {"source": "Open-Meteo Historical Weather & Marine API, open-meteo.com, CC BY 4.0",
                    "period": f"{START}..{END}", "destinations": {}}
    for d in DESTINATIONS:
        air = fetch("https://archive-api.open-meteo.com/v1/archive", {
            "latitude": d.lat, "longitude": d.lon, "start_date": START, "end_date": END,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum", "timezone": "auto",
        })["daily"]
        tmax = monthly(air["time"], air["temperature_2m_max"])
        tmin = monthly(air["time"], air["temperature_2m_min"])
        rain = monthly(air["time"], air["precipitation_sum"])
        sea: dict[int, list[float]] = {}
        if d.sea:
            marine = fetch("https://marine-api.open-meteo.com/v1/marine", {
                "latitude": d.sea[0], "longitude": d.sea[1], "start_date": START, "end_date": END,
                "daily": "sea_surface_temperature_max",
            })["daily"]
            sea = monthly(marine["time"], marine["sea_surface_temperature_max"])
        years = 4
        months = {}
        for m in range(1, 13):
            months[str(m)] = {
                "t_day": round(mean(tmax[m]), 1),
                "t_night": round(mean(tmin[m]), 1),
                "rain_days": round(sum(1 for x in rain[m] if x >= 5.0) / years),
                "rain_mm": round(sum(rain[m]) / years),
                "sea": round(mean(sea[m]), 1) if sea.get(m) else None,
            }
        result["destinations"][d.id] = months
        print(d.name, "ок", months["11"])
        time.sleep(1)  # бережём бесплатный лимит
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Записано:", OUT)


if __name__ == "__main__":
    main()

"""Климат направлений по месяцам (Open-Meteo, 2022–2025)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).parent / "data" / "climate.json"


@dataclass(frozen=True)
class MonthClimate:
    t_day: float
    t_night: float
    rain_days: int
    sea: float | None

    def describe(self) -> str:
        parts = [f"днём {self.t_day:+.0f}°", f"ночью {self.t_night:+.0f}°"]
        if self.sea is not None:
            parts.append(f"море {self.sea:+.0f}°")
        if self.rain_days >= 8:
            parts.append(f"дожди ~{self.rain_days} дн. в месяц")
        elif self.rain_days <= 2:
            parts.append("почти без дождей")
        return ", ".join(parts)

    @property
    def beach_ok(self) -> bool:
        return self.sea is not None and self.sea >= 23 and self.t_day >= 25

    @property
    def warm(self) -> bool:
        return self.t_day >= 22


@lru_cache(maxsize=1)
def _load() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))["destinations"]


def climate(dest_id: str, month: int) -> MonthClimate | None:
    data = _load().get(dest_id)
    if not data:
        return None
    m = data[str(month)]
    return MonthClimate(t_day=m["t_day"], t_night=m["t_night"], rain_days=m["rain_days"], sea=m["sea"])


SOURCE = "Open-Meteo, средние за 2022–2025 годы"

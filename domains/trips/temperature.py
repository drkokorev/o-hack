"""Conservative parsing and historical comparison of explicit temperature preferences."""
from __future__ import annotations

import re

from .climate import MonthClimate
from .textparse import norm

AIR = r"(?:воздух(?:а|е)?|днем|на\s+улице)"
WATER = r"(?:вод[аые]|море|моря)"
OP = r"(?:не\s+ниже|не\s+холоднее|минимум|от|не\s+выше|не\s+жарче|максимум|до)"
NUM = r"[+-]?\d{1,2}(?:[.,]\d)?"
UNIT = r"(?:°\s*[cс]?|градус\w*)"


def temperature_preferences(text: str) -> dict[str, float]:
    """Only explicit air/sea thresholds with degree units, never dates or forecasts."""
    t = norm(text)
    if "?" in text and re.search(r"какая|какой|сколько|будет\s+ли", t) and not re.search(r"хочу|найти|подбер", t):
        return {}
    result = {}
    for subject, prefix in ((AIR, "air"), (WATER, "sea")):
        before = rf"{subject}\s*(?:должн\w*\s+быть\s*)?(?P<op>{OP})\s*(?P<n>{NUM})\s*{UNIT}"
        after = rf"(?P<op>{OP})\s*(?P<n>{NUM})\s*{UNIT}\s*(?:{subject})"
        for match in re.finditer(before + "|" + after.replace("?P<op>", "?P<op2>").replace("?P<n>", "?P<n2>"), t):
            op, number = match.group("op") or match.group("op2"), match.group("n") or match.group("n2")
            value = float(number.replace(",", "."))
            if -60 <= value <= 60:
                minimum = bool(re.match(r"не\s+ниже|не\s+холоднее|минимум|от", op))
                result[f"{prefix}_{'min' if minimum else 'max'}_temp"] = value
    return result


def matches_history(weather: MonthClimate | None, *, air_min_temp=None, air_max_temp=None,
                    sea_min_temp=None, sea_max_temp=None) -> bool | None:
    """True/False for recorded monthly averages; None means insufficient data."""
    if weather is None or ((sea_min_temp is not None or sea_max_temp is not None) and weather.sea is None):
        return None
    if air_min_temp is not None and weather.t_day < air_min_temp:
        return False
    if air_max_temp is not None and weather.t_day > air_max_temp:
        return False
    if sea_min_temp is not None and weather.sea < sea_min_temp:
        return False
    if sea_max_temp is not None and weather.sea > sea_max_temp:
        return False
    return True


TEMP_FIELDS = ("air_min_temp", "air_max_temp", "sea_min_temp", "sea_max_temp")

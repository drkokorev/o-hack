"""Measure local filter overhead for fixed synthetic chat and system prompts."""
from datetime import date
from statistics import median
from time import perf_counter
from core.guard import mask_sensitive_data
from domains.trips.domain import TripsDomain
from domains.trips.state import TripState

d = TripsDomain()
messages = d.extraction_messages(TripState(), [], "Хочу в Сочи на 7 ночей", date(2026, 10, 28))
start = perf_counter()
mask_sensitive_data(messages[1]["content"], d.preserve_place)
cold = perf_counter() - start
elapsed = []
for _ in range(15):
    start = perf_counter()
    mask_sensitive_data(messages[0]["content"], d.preserve_place)
    mask_sensitive_data(messages[1]["content"], d.preserve_place)
    elapsed.append(perf_counter() - start)
print({"cold_short_seconds": round(cold, 4), "median_full_seconds": round(median(elapsed), 4),
       "max_full_seconds": round(max(elapsed), 4), "iterations": len(elapsed),
       "system_chars": len(messages[0]["content"])})

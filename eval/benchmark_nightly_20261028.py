"""Local synthetic timing only; no model, network or personal data."""
from datetime import date
from statistics import median
from time import perf_counter

from core.agent import Agent
from domains.trips.domain import TripsDomain

today = date(2026, 10, 28)
agent = Agent(TripsDomain(today=lambda: today), None, today=lambda: today)
cases = {
    "selected_destination": "Из Москвы в Сочи с 10 по 15 июня 2027 двое взрослых, отель до 6000 рублей за ночь",
    "priced_ideas": "Из Москвы к морю в июне на 5 ночей двое взрослых, отель до 6000 рублей за ночь",
}
for label, prompt in cases.items():
    agent.handle(agent.new_session(), prompt)
    times = []
    for _ in range(3):
        start = perf_counter()
        response = agent.handle(agent.new_session(), prompt)
        times.append(perf_counter() - start)
    print(label, "kind=", (response.payload or {}).get("kind"), "median_ms=", round(median(times) * 1000))

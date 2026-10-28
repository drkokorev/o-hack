from datetime import date

from core.agent import Agent
from domains.trips.arbiter import arbitrate
from domains.trips.climate import climate
from domains.trips.dialogue import ideas
from domains.trips.domain import TripsDomain
from domains.trips.rules import rule_extract
from domains.trips.state import TripState, TripUpdate
from domains.trips.temperature import matches_history, temperature_preferences

TODAY = date(2026, 10, 27)


def test_explicit_air_and_sea_limits_are_separate():
    parsed = temperature_preferences("воздух не ниже +25 градусов, вода от 22 градусов")
    assert parsed == {"air_min_temp": 25, "sea_min_temp": 22}
    assert temperature_preferences("днем не выше 30 °C, море не ниже +23 °C") == {
        "air_max_temp": 30, "sea_min_temp": 23}
    assert temperature_preferences("не холоднее +25 градусов днем") == {"air_min_temp": 25}


def test_dates_and_weather_questions_do_not_become_temperature_preferences():
    assert temperature_preferences("25 июня 2027") == {}
    assert temperature_preferences("Какая температура воздуха будет 25 градусов?") == {}
    assert temperature_preferences("Можно найти, где вода не ниже 22 градусов?") == {"sea_min_temp": 22}


def test_model_cannot_invent_a_temperature_threshold():
    state = TripState()
    text = "Хочу в Сочи летом"
    result, _ = arbitrate(state, text, TripUpdate(air_min_temp=30), rule_extract(state, text, TODAY))
    assert result.air_min_temp is None


def test_unknown_temperature_is_not_a_pass():
    assert matches_history(None, air_min_temp=25) is None
    assert matches_history(climate("kazan", 7), sea_min_temp=22) is None
    assert matches_history(climate("yaroslavl", 7), air_min_temp=30) is False


def test_ideas_filter_only_by_known_historical_monthly_values():
    state = TripState(month=7, air_min_temp=27, trip_types=["mountains"])
    step = ideas(state)
    assert step.payload["kind"] == "ideas" and step.payload["items"]
    assert all(matches_history(climate(item["id"], 7), air_min_temp=27) is True for item in step.payload["items"])
    assert "историческими" in step.reply and "не прогноз" in step.reply


def test_temperature_is_not_applied_without_a_month():
    state = TripState(air_min_temp=27, trip_types=["mountains"])
    step = ideas(state)
    assert step.payload["kind"] == "ideas" and "нужен месяц" in step.reply


def test_generic_water_limit_discloses_it_only_uses_sea_surface_data():
    state = TripState(month=7, sea_min_temp=22)
    step = ideas(state)
    assert step.payload["kind"] == "ideas"
    assert "поверхности моря" in step.reply and "озёра и реки не проверяются" in step.reply


def test_chosen_city_that_misses_limit_is_not_described_as_matching():
    agent = Agent(TripsDomain(today=lambda: TODAY), None, today=lambda: TODAY)
    session = agent.new_session()
    step = agent.handle(session, "Из Москвы в Ярославль с 10 по 14 июля 2027 двое взрослых, воздух от 30 градусов")
    assert session.state.air_min_temp == 30 and step.payload["kind"] == "packages"
    assert "не соответствуют указанному порогу" in step.reply and "не прогноз" in step.reply


def test_missing_sea_history_is_disclosed_for_a_selected_city():
    agent = Agent(TripsDomain(today=lambda: TODAY), None, today=lambda: TODAY)
    session = agent.new_session()
    step = agent.handle(session, "Из Москвы в Казань с 10 по 14 июля 2027 двое взрослых, вода от 22 градусов")
    assert session.state.sea_min_temp == 22 and "нет необходимых исторических данных" in step.reply.lower()


def test_inconsistent_air_limits_request_correction():
    agent = Agent(TripsDomain(today=lambda: TODAY), None, today=lambda: TODAY)
    step = agent.handle(agent.new_session(), "воздух от 30 градусов, воздух до 20 градусов")
    assert step.payload["kind"] == "question" and "выше максимальной" in step.reply


def test_clearing_a_temperature_preference_does_not_erase_other_trip_parameters():
    agent = Agent(TripsDomain(today=lambda: TODAY), None, today=lambda: TODAY)
    session = agent.new_session()
    agent.handle(session, "Хочу в Сочи, воздух от 25 градусов")
    agent.handle(session, "Температура воздуха не важна")
    assert session.state.air_min_temp is None and session.state.dest_id == "sochi"


def test_model_cannot_drop_explicit_temperature_removal():
    state = TripState(air_min_temp=25)
    text = "Температура воздуха не важна, бюджет тоже не важен"
    rules = rule_extract(state, text, TODAY)
    result, _ = arbitrate(state, text, TripUpdate(clear=["budget_total"]), rules)
    assert "air_min_temp" in result.clear and "budget_total" in result.clear

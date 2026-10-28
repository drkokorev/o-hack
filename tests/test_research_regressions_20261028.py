from datetime import date

from core.agent import Agent
from domains.trips.domain import TripsDomain
from domains.trips.arbiter import arbitrate
from domains.trips.rules import rule_extract
from domains.trips.state import TripState, TripUpdate


TODAY = date(2026, 10, 28)


def agent():
    return Agent(TripsDomain(today=lambda: TODAY), None, today=lambda: TODAY)


def test_budget_per_person_is_not_mistaken_for_whole_group():
    a, session = agent(), agent().new_session()
    a.handle(session, "Четверо из Екатеринбурга, семьдесят тысяч на человека, только прямой рейс")
    assert session.state.party_size == 4
    assert session.state.budget_per_person == 70000 and session.state.budget_total == 280000
    assert session.state.direct_only is True
    a.handle(session, "нас трое")
    assert session.state.budget_total == 210000
    a.handle(session, "бюджет 150 тысяч на всех")
    assert session.state.budget_total == 150000 and session.state.budget_per_person is None


def test_per_person_budget_waits_for_number_of_travelers():
    a = agent()
    session = a.new_session()
    a.handle(session, "До 50 тысяч на человека, хочу к морю")
    assert session.state.budget_per_person == 50000 and session.state.budget_total is None
    a.handle(session, "нас трое")
    assert session.state.budget_total == 150000


def test_fear_of_flying_is_a_preference_until_clarified():
    a = agent()
    session = a.new_session()
    a.handle(session, "В Сочи из Москвы на 10–14 июня 2027, 2 взрослых, боюсь летать")
    assert session.state.flight_concern is True and session.state.transport is None
    answer = a.handle(session, "самолет не подходит")
    assert session.state.flight_concern is False and session.state.transport == "train"
    assert answer.payload["kind"] in {"packages", "question"}


def test_excluded_country_stays_excluded_and_visa_is_not_claimed_checked():
    a = agent()
    session = a.new_session()
    step = a.handle(session, "Не Египет, хочу зимой к морю без визы")
    assert "Египет" in session.state.excluded_countries
    assert session.state.visa_free_requested is True
    assert "не проверял" in step.reply and "не фильтровал" in step.reply
    assert all(item["country"] != "Египет" for item in step.payload["items"])
    again = a.handle(session, "покажи ещё")
    assert all(item["country"] != "Египет" for item in again.payload.get("items", []))


def test_common_typos_do_not_turn_a_month_into_a_place_or_invent_a_budget():
    a = agent()
    session = a.new_session()
    step = a.handle(session, "Хачу на мори в дикабре с жиной недорага")
    assert session.state.month == 12 and session.state.destination is None
    assert session.state.party_size == 2 and session.state.economy is True
    assert session.state.budget_total is None and "нет в каталоге" not in step.reply


def test_model_cannot_turn_fear_or_an_excluded_country_into_final_choices():
    state = TripState()
    text = "Не Египет, боюсь летать, хочу к морю"
    rules = rule_extract(state, text, TODAY)
    update, _ = arbitrate(state, text, TripUpdate(destination="Египет", transport="plane"), rules)
    assert update.destination is None and update.transport is None
    assert update.excluded_countries == ["Египет"] and update.flight_concern is True

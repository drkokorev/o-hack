from datetime import date

from core.agent import Agent
from domains.trips.domain import TripsDomain
from domains.trips.arbiter import arbitrate
from domains.trips.rules import rule_extract
from domains.trips.state import TripState, TripUpdate
from domains.trips.geo import BY_ID


TODAY = date(2026, 10, 27)
USER_REQUEST = ("хочу увидеть горы, вайб лета, шашлыка, с другом, денег не много, "
                "главное еда и перелет, проживание в палатках")


def new_agent():
    return Agent(TripsDomain(today=lambda: TODAY), None, today=lambda: TODAY)


def test_user_request_does_not_treat_tent_as_a_city():
    result = rule_extract(TripState(), USER_REQUEST, TODAY)
    assert result.unknown_place is None
    assert result.lodging == "tent"
    assert result.party_size == 2 and result.adults is None
    assert "mountains" in result.trip_types and "food" in result.trip_types
    assert result.economy is True


def test_unspecified_age_composition_is_asked_before_calculating():
    agent = new_agent()
    session = agent.new_session()
    step = agent.handle(session, "В Сочи из Москвы с 5 по 12 декабря вдвоём")
    assert session.state.party_size == 2 and session.state.adults is None
    assert step.payload["kind"] == "question" and "взросл" in step.reply.lower()
    step = agent.handle(session, "2")
    assert session.state.adults == 2 and session.state.children == 0
    assert step.payload["kind"] == "packages"


def test_ambiguous_trip_asks_when_instead_of_inventing_november_and_seven_nights():
    agent = new_agent()
    session = agent.new_session()
    step = agent.handle(session, USER_REQUEST)
    assert step.payload["kind"] == "question"
    assert "когда" in step.reply.lower() or "время года" in step.reply.lower()
    assert session.state.date_from is None and session.state.nights is None
    assert session.state.origin is None


def test_not_knowing_dates_gives_ideas_without_fake_prices():
    agent = new_agent()
    session = agent.new_session()
    agent.handle(session, USER_REQUEST)
    step = agent.handle(session, "пока не знаю")
    assert session.state.date_from is None and session.state.nights is None
    assert "7 ноч" not in step.reply.lower()
    assert "москв" not in step.reply.lower()
    assert step.payload.get("kind") in ("ideas", "question")


def test_empty_inspiration_asks_to_change_constraints_instead_of_blank_choices():
    agent = new_agent()
    session = agent.new_session()
    step = agent.handle(session, "хочу море и горы с ограничением дороги до 1 часа в ноябре")
    assert not (step.payload.get("kind") == "destinations" and not step.payload.get("items"))


def test_generic_types_are_not_fuzzy_corrected_into_cities():
    for text in ("хочу в горы в июле", "хочу на море в феврале"):
        update = rule_extract(TripState(), text, TODAY)
        assert update.destination is None and update.corrected_place is None and update.unknown_place is None


def test_not_knowing_time_with_no_other_preferences_still_gives_ideas():
    agent = new_agent()
    session = agent.new_session()
    agent.handle(session, "хочу отдохнуть")
    answer = agent.handle(session, "не знаю")
    assert answer.payload["kind"] == "ideas" and answer.payload["items"]


def test_model_cannot_turn_generic_type_or_origin_into_destination():
    text = "хочу в горы, с другом, недорого, будем жить в палатках"
    state = TripState()
    rules = rule_extract(state, text, TODAY)
    result, _ = arbitrate(state, text, TripUpdate(destination="mountains"), rules)
    assert result.destination is None and "mountains" in result.trip_types
    text = "хочу отдохнуть, живу в Москве"
    result, _ = arbitrate(state, text, TripUpdate(destination="Москва"), rule_extract(state, text, TODAY))
    assert result.destination is None


def test_model_cannot_invent_origin_when_user_mentions_departure_generally():
    text = "вылет из любого города, я пока не знаю"
    state = TripState()
    result, _ = arbitrate(state, text, TripUpdate(origin="Москва"), rule_extract(state, text, TODAY))
    assert result.origin is None


def test_model_cannot_turn_food_preference_into_specific_hotel_meal_plan():
    state = TripState()
    rules = rule_extract(state, USER_REQUEST, TODAY)
    result, _ = arbitrate(state, USER_REQUEST, TripUpdate(meal="half_board"), rules)
    assert result.meal is None and "food" in result.trip_types


def test_model_cannot_invent_exact_money_duration_or_group_size():
    text = "хочу недорого отдохнуть с семьей"
    state = TripState()
    rules = rule_extract(state, text, TODAY)
    model = TripUpdate(budget_total=100000, nights=7, adults=2, children=1)
    result, _ = arbitrate(state, text, model, rules)
    assert result.budget_total is None and result.nights is None
    assert result.adults is None and result.children is None


def test_model_cannot_invent_return_date_from_departure_date_alone():
    text = "в Сочи из Москвы 5 декабря вдвоём"
    state = TripState()
    rules = rule_extract(state, text, TODAY)
    model = TripUpdate(date_from=date(2026, 12, 5), date_to=date(2026, 12, 12), nights=7)
    result, _ = arbitrate(state, text, model, rules)
    assert result.date_from == date(2026, 12, 5) and result.date_to is None and result.nights is None


def test_ideas_do_not_drop_the_requested_type_of_trip():
    agent = new_agent()
    session = agent.new_session()
    agent.handle(session, USER_REQUEST)
    step = agent.handle(session, "не знаю")
    assert step.payload["items"] and all("mountains" in BY_ID[item["id"]].tags for item in step.payload["items"])

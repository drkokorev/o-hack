from datetime import date

import pytest

from core.agent import Agent
from domains.trips import guides
from domains.trips.arbiter import arbitrate
from domains.trips.domain import TripsDomain
from domains.trips.rules import rule_extract
from domains.trips.state import TripState, TripUpdate


TODAY = date(2026, 10, 27)


@pytest.mark.parametrize("text,adults,children", [
    ("для двух взрослых и двух детей", 2, 2),
    ("с тремя взрослыми и двумя детьми", 3, 2),
    ("на четырех взрослых без детей", 4, 0),
    ("не для двух взрослых, а для трех взрослых", 3, None),
    ("не для 2 взрослых, а для 4 взрослых", 4, None),
    ("двое взрослых, не хочу лететь", 2, None),
    ("двое взрослых и двое детей, не нужна машина", 2, 2),
    ("с двумя детьми", None, 2),
])
def test_inflected_guest_counts_and_corrections(text, adults, children):
    result = rule_extract(TripState(), text, TODAY)
    assert (result.adults, result.children) == (adults, children)


def test_hotel_intent_and_combined_request_are_distinct():
    assert rule_extract(TripState(), "Подбери отель в Казани", TODAY).search_scope == "hotel_only"
    assert rule_extract(TripState(), "Отель и перелет в Казань", TODAY).search_scope != "hotel_only"


@pytest.mark.parametrize("text,topic", [
    ("где поесть в Стамбуле", "food"),
    ("что посмотреть в Казани", "sights"),
    ("where to eat in Istanbul", "food"),
])
def test_question_without_question_mark(text, topic):
    update = rule_extract(TripState(), text, TODAY)
    assert topic in (update.question or "").split("|")


def test_specific_guide_question_cites_relevant_text_in_same_destination():
    found = guides.search_grounded("где попробовать симит?", "istanbul", "food")
    assert found and all(s.dest == "istanbul" and "симит" in s.text.lower() for s in found)


def test_english_named_food_finds_its_russian_equivalent():
    found = guides.search_grounded("where to eat sushi?", "tokyo", "food")
    assert found and "суши" in found[0].text.lower()


def test_specific_dish_with_a_small_typo_uses_evidence_not_generic_food():
    found = guides.search_grounded("где попробовать симмт?", "istanbul", "food")
    assert found and all("симит" in s.text.lower() for s in found)


def test_synonym_and_nearby_area_are_supported_when_the_source_contains_them():
    inexpensive = guides.search_grounded("где переночевать подешевле?", "tokyo", "areas")
    ski = guides.search_grounded("где покататься на лыжах?", "sochi", "sights")
    assert inexpensive and "дешев" in inexpensive[0].text.lower().replace("ё", "е")
    assert ski and "горнолыж" in ski[0].text.lower()


@pytest.mark.parametrize("query,dest,topic", [
    ("есть ли в ресторанах меню на клингонском?", "sochi", "food"),
    ("где в Будве веганская кухня?", "budva", "food"),
    ("где посмотреть Колизей?", "rome", "sights"),
    ("где поесть без глютена?", "istanbul", "food"),
])
def test_specific_missing_or_sensitive_evidence_is_not_replaced_by_generic_section(query, dest, topic):
    assert guides.search_grounded(query, dest, topic) == []


def test_broad_question_still_has_guide_results():
    found = guides.search_grounded("где поесть?", "sochi", "food")
    assert found and all(s.dest == "sochi" and s.tag in {"eat", "drink"} for s in found)


def test_missing_specific_evidence_is_explicit_in_chat():
    agent = Agent(TripsDomain(today=lambda: TODAY), None, today=lambda: TODAY, nlg=False)
    session = agent.new_session()
    agent.handle(session, "Хочу в Будву")
    result = agent.handle(session, "В ресторанах есть меню на клингонском?")
    assert "ответа не нашёл" in result.reply.lower()
    assert not result.sources


def test_place_questions_interrupt_hotel_search_without_losing_trip():
    agent = Agent(TripsDomain(today=lambda: TODAY), None, today=lambda: TODAY, nlg=False)
    session = agent.new_session()
    first = agent.handle(session, "Только отель в Сочи с 12 по 18 ноября 2026 для двух взрослых")
    assert first.payload["kind"] == "service_results"
    before = session.state.params()
    result = agent.handle(session, "Где поесть?")
    assert "Wikivoyage" in result.reply and session.state.params() == before
    missing = agent.handle(session, "В ресторанах есть меню на клингонском?")
    assert "ответа не нашёл" in missing.reply.lower() and session.state.params() == before


def test_model_can_classify_an_unfamiliar_place_question_with_quoted_evidence():
    state = TripState(dest_id="istanbul", destination="Стамбул")
    text = "Интересуют древние сооружения"
    rules = rule_extract(state, text, TODAY)
    assert rules.question is None
    model = TripUpdate(question="sights", evidence={"question": text})
    result, _ = arbitrate(state, text, model, rules)
    assert result.question == "sights"
    missing_quote, _ = arbitrate(state, text, TripUpdate(question="sights"), rules)
    assert missing_quote.question is None
    unknown_city, _ = arbitrate(TripState(), text, model, rule_extract(TripState(), text, TODAY))
    assert unknown_city.question is None
    action, _ = arbitrate(state, text, TripUpdate(question="cancel", evidence={"question": text}), rules)
    assert action.question is None

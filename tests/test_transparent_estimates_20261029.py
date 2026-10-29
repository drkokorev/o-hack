from datetime import date

from core.agent import Agent
from apps.web import understood
from domains.trips.arbiter import arbitrate
from domains.trips.domain import TripsDomain
from domains.trips.rules import rule_extract
from domains.trips.state import TripState, TripUpdate
from core.ru import fmt_money


TODAY = date(2026, 10, 29)


def make_agent():
    return Agent(TripsDomain(today=lambda: TODAY), None, today=lambda: TODAY, nlg=False)


def test_user_flow_explains_missing_price_then_shows_demo_minimum_and_ip_assumption():
    agent = make_agent()
    session = agent.new_session()
    session.state.origin = "Москва"
    session.state.origin_inferred = True
    agent.handle(session, "Хочу в горы, красивый вид и спокойные прогулки. Предложи направления.")
    assert session.state.scenic_views is True and session.state.relaxed_walks is True
    assert "красивые виды: не проверены" in understood(session.state)
    ideas = agent.handle(session, "с 11.11.2027 по 11.12.2027")
    assert ideas.payload["kind"] == "ideas"
    assert "11.11.2027–11.12.2027" in ideas.reply
    assert "состав путешественников" in ideas.reply and "бюджет" in ideas.reply.lower()
    assert "маршруты пока не проверены" in ideas.reply
    assert "даты, стоимость и время в пути пока не рассчитывал" not in ideas.reply.lower()
    assert "примерно по ip" in ideas.reply.lower()
    agent.handle(session, "Хочу в Байкал (Иркутск)")
    plan = agent.handle(session, "2 взрослых")
    assert plan.payload["kind"] == "packages"
    minimum = min(item["total_rub"] for item in plan.payload["items"])
    header = plan.reply.split("\n\n", 1)[0]
    assert fmt_money(minimum) in header and "самый недорогой" in header.lower()
    assert "за всех" in header.lower() and "демо" in header.lower()
    assert "примерно по ip" in header.lower() and "бюджет не указан" in header.lower()
    assert session.state.scenic_views is True and session.state.relaxed_walks is True


def test_unpriced_ideas_do_not_invent_price_and_identify_missing_information():
    agent = make_agent()
    session = agent.new_session()
    agent.handle(session, "Хочу в горы")
    result = agent.handle(session, "предложи сам")
    assert result.payload["kind"] == "ideas" and "цены и время в пути пока не рассчитаны" in result.reply.lower()
    assert "месяц или даты" in result.reply and "город отправления" in result.reply
    assert "₽" not in result.reply and session.state.budget_total is None


def test_budget_can_be_added_after_suggestions_without_blocking_choice():
    agent = make_agent()
    session = agent.new_session()
    agent.handle(session, "Хочу в горы")
    agent.handle(session, "предложи сам")
    result = agent.handle(session, "Бюджет на всю поездку до 300 тысяч рублей")
    assert session.state.budget_total == 300000 and result.payload["kind"] == "ideas"


def test_model_can_capture_an_unfamiliar_view_wish_only_with_evidence():
    state = TripState()
    text = "хочется любоваться живописной панорамой"
    rules = rule_extract(state, text, TODAY)
    assert rules.scenic_views is None
    proposed = TripUpdate(scenic_views=True, evidence={"scenic_views": "любоваться живописной панорамой"})
    result, _ = arbitrate(state, text, proposed, rules)
    assert result.scenic_views is True
    unsupported, _ = arbitrate(state, text, TripUpdate(scenic_views=True), rules)
    assert unsupported.scenic_views is None
    question = "А там есть красивые виды?"
    result, _ = arbitrate(state, question, TripUpdate(scenic_views=True, evidence={"scenic_views": "красивые виды"}),
                          rule_extract(state, question, TODAY))
    assert result.scenic_views is None

from datetime import date

import pytest

from core.agent import Agent
from domains.trips.arbiter import arbitrate
from domains.trips.domain import TripsDomain
from domains.trips.rules import rule_extract
from domains.trips.state import TripState, TripUpdate
from tests.conftest import FakeLLM

TODAY = date(2026,10,29)


@pytest.mark.parametrize('budget', ['100 долларов', '100 USD', '200 евро', '$100', '100€',
                                   'сто долларов', '100 долларов и 5000 рублей'])
def test_foreign_currency_is_not_silently_treated_as_rubles(budget):
    agent = Agent(TripsDomain(today=lambda:TODAY),None,today=lambda:TODAY)
    session = agent.new_session()
    result = agent.handle(session, 'Хочу в Казань, бюджет ' + budget)
    assert session.state.budget_total is None and session.state.budget_currency_issue
    assert result.payload['field'] == 'budget' and 'рублях' in result.reply
    result = agent.handle(session, 'Бюджет 50000 рублей')
    assert session.state.budget_total == 50000 and session.state.budget_currency_issue is None


def test_model_cannot_reintroduce_an_unconverted_foreign_amount():
    text = 'бюджет 100 долларов'
    rules = rule_extract(TripState(),text,TODAY)
    result,_ = arbitrate(TripState(),text,TripUpdate(budget_total=100,evidence={'budget_total':'100 долларов'}),rules)
    assert result.budget_total is None and result.unsupported_budget_currency


def test_explicit_total_and_adults_reconcile_a_complete_child_age_list_locally():
    model = FakeLLM()
    agent = Agent(TripsDomain(today=lambda:TODAY),model,today=lambda:TODAY)
    session=agent.new_session()
    agent.handle(session,'Нас четверо: двое взрослых, дети 4 и 9 лет. В Казань')
    assert session.state.party_size == 4
    assert session.state.adults == 2 and session.state.children == 2
    assert session.state.children_ages == [4,9] and not session.state.children_unknown
    assert not model.calls


def test_a_partial_age_list_does_not_invent_a_total_child_count():
    result=rule_extract(TripState(),'Едем с детьми, детям 4 и 9 лет',TODAY)
    assert result.children is None and result.children_unknown


@pytest.mark.parametrize('text', ['Возможно поедем втроём в Казань', 'Наверное полетим вчетвером'])
def test_uncertain_group_size_remains_tentative(text):
    result=rule_extract(TripState(),text,TODAY)
    assert result.party_size and 'party_size' in result.tentative_fields
    assert result.adults is None


def test_uncertainty_about_month_does_not_make_an_explicit_group_tentative():
    result=rule_extract(TripState(),'Возможно в ноябре, нас трое',TODAY)
    assert result.party_size == 3 and 'party_size' not in (result.tentative_fields or [])


def test_unresolved_currency_can_be_cleared_without_replacing_the_trip():
    agent = Agent(TripsDomain(today=lambda:TODAY),None,today=lambda:TODAY)
    session=agent.new_session()
    agent.handle(session,'В Казань, бюджет 100 долларов')
    agent.handle(session,'бюджет не важен')
    assert session.state.destination == 'Казань'
    assert session.state.budget_total is None and session.state.budget_currency_issue is None


def test_new_search_does_not_drop_a_currency_issue_in_the_same_turn():
    domain = TripsDomain(today=lambda:TODAY)
    state = domain.merge(TripState(),TripUpdate(new_search=True,unsupported_budget_currency='USD'))
    assert state.budget_currency_issue == 'USD'
    assert domain.step(state).payload['field'] == 'budget'

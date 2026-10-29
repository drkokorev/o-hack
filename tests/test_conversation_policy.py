"""Behaviour regressions: conversational turns must not silently edit a trip."""
from datetime import date

import pytest

from core.agent import Agent
from domains.trips.domain import TripsDomain
from domains.trips.state import TripState
from tests.conftest import FakeLLM


def agent_and_session():
    today = lambda: date(2026, 10, 29)
    agent = Agent(TripsDomain(today=today), None, today=today)
    return agent, agent.new_session()


@pytest.mark.parametrize('text,expected', [
    ('Спасибо', 'пожалуйста'),
    ('Что ты умеешь?', 'могу'),
    ('Почему тебе нужны даты?', 'дат'),
    ('Не понял вопрос', 'например'),
    ('Ты меня не понял', 'поправ'),
    ('Спасибо, вернусь позже', 'продолж'),
    ('Это настоящие цены?', 'демонстрац'),
    ('Что ты уже знаешь о моей поездке?', 'казань'),
])
def test_meta_turn_answers_in_context_without_mutation(text, expected):
    agent, session = agent_and_session()
    agent.handle(session, 'Хочу в Казань')
    before = session.state.model_dump()
    step = agent.handle(session, text)
    assert not step.reply.startswith('Не понял сообщение')
    assert expected in step.reply.lower()
    assert session.state.model_dump() == before


@pytest.mark.parametrize('question', ['А если на поезде?', 'Можно ли добраться поездом?',
                                    'А что насчёт Грузии?', 'Я не выбирал Грузию, просто спросил'])
def test_exploration_does_not_commit_a_choice(question):
    agent, session = agent_and_session()
    agent.handle(session, 'В Казань в ноябре')
    before = session.state.model_dump()
    result = agent.handle(session, question)
    assert session.state.model_dump() == before
    assert not result.reply.startswith('Не понял сообщение')


def test_short_followup_keeps_question_topic_without_changing_trip():
    agent, session = agent_and_session()
    agent.handle(session, 'В Казань в ноябре')
    agent.handle(session, 'Какая там погода?')
    before = session.state.model_dump()
    result = agent.handle(session, 'А в Сочи?')
    assert session.state.model_dump() == before
    assert 'Сочи' in result.reply
    assert 'ноябр' in result.reply
    assert 'прогноз' in result.reply


def test_explicit_edit_still_changes_transport():
    agent, session = agent_and_session()
    agent.handle(session, 'В Казань')
    agent.handle(session, 'Выбираю поезд')
    assert session.state.transport == 'train'


@pytest.mark.parametrize('text', ['Выглядит хорошо, но ничего пока не оформляй',
                                 'Пока ничего не бронируй', 'Ничего не оплачивай'])
def test_pause_before_checkout_preserves_state_and_does_not_ask_next_question(text):
    agent, session = agent_and_session()
    session.state = TripState(stage='payment', destination='Казань', dest_id='kazan')
    before = session.state.model_dump()
    result = agent.handle(session, text)
    assert session.state.model_dump() == before
    assert 'продолж' in result.reply.lower() and '?' not in result.reply


def test_mixed_thanks_and_edit_keeps_the_edit():
    agent, session = agent_and_session()
    agent.handle(session, 'В Казань')
    agent.handle(session, 'Спасибо, хочу в Сочи в декабре')
    assert session.state.destination == 'Сочи'
    assert session.state.month == 12


def test_budget_basis_correction_reuses_only_explicit_existing_amount():
    agent, session = agent_and_session()
    agent.handle(session, 'В Казань, бюджет 80000 на двоих')
    agent.handle(session, 'Это на человека, а не на всех')
    assert session.state.budget_per_person == 80000
    assert session.state.budget_total == 160000


def test_budget_basis_question_does_not_change_budget():
    agent, session = agent_and_session()
    agent.handle(session, 'В Казань, бюджет 80000 на двоих')
    before = session.state.params()
    agent.handle(session, 'Это на человека или на всех?')
    assert session.state.params() == before


def test_unknown_turn_does_not_repeat_a_generated_answer_as_a_new_question():
    agent, session = agent_and_session()
    agent.handle(session, 'В Казань')
    agent.handle(session, 'Почему тебе нужны даты?')
    result = agent.handle(session, 'абракадабра')
    assert 'например' in result.reply.lower()
    assert result.reply.count('Не понял сообщение') <= 1


def test_model_understands_a_new_meta_phrase_without_a_new_keyword_rule():
    text = 'Очертите границы того, с чем здесь можно рассчитывать на вашу помощь'
    llm = FakeLLM({'dialogue_act': 'capabilities', 'evidence': {'dialogue_act': text}, 'confirm': True})
    agent = Agent(TripsDomain(), llm)
    session = agent.new_session()
    before = session.state.model_dump()
    result = agent.handle(session, text)
    assert 'Могу' in result.reply and 'бронирование' in result.reply
    assert session.state.model_dump() == before and session.state.order is None


def test_fabricated_meta_evidence_is_rejected():
    llm = FakeLLM({'dialogue_act': 'thanks', 'evidence': {'dialogue_act': 'спасибо'}})
    agent = Agent(TripsDomain(), llm)
    result = agent.handle(agent.new_session(), 'абракадабра')
    assert 'Пожалуйста!' not in result.reply


def test_model_courtesy_classification_cannot_swallow_an_explicit_edit():
    text = 'Спасибо, перенеси поездку на декабрь'
    llm = FakeLLM({'dialogue_act': 'thanks', 'evidence': {'dialogue_act': 'Спасибо'}})
    agent = Agent(TripsDomain(), llm)
    session = agent.new_session()
    agent.handle(session, text)
    assert session.state.month == 12


@pytest.mark.parametrize('stage,pending', [('payment', None), ('booked', 'cancel'), ('cart', None)])
def test_social_turn_does_not_confirm_a_transaction(stage, pending):
    agent, session = agent_and_session()
    session.state = TripState(stage=stage, pending=pending, order={'number': 'DEMO-1'})
    before = session.state.model_dump()
    result = agent.handle(session, 'Спасибо')
    assert 'Пожалуйста' in result.reply
    assert session.state.model_dump() == before


def test_local_courtesy_does_not_spend_a_model_call():
    llm = FakeLLM()
    agent = Agent(TripsDomain(), llm, nlg=True)
    session = agent.new_session()
    agent.handle(session, 'Спасибо')
    assert not llm.calls
    assert session.last_nlu == 'rules' and session.last_answer_by == 'template'


def test_hypothetical_shift_reports_dates_without_committing_them():
    agent, session = agent_and_session()
    session.state = TripState(destination='Казань', dest_id='kazan', date_from=date(2026,12,5), date_to=date(2026,12,12))
    before = session.state.model_dump()
    result = agent.handle(session, 'А если на два дня позже?')
    assert session.state.model_dump() == before
    assert '07.12.2026' in result.reply and '14.12.2026' in result.reply


def test_extraction_prompt_contains_only_actually_displayed_packages():
    state = TripState(showing='packages', package_options=[{'key':'budget', 'title':'Экономный'}])
    text = TripsDomain().extraction_messages(state, [], 'первый', date(2026,10,29))[0]['content']
    assert '1. Экономный' in text
    assert '2. Экономный' not in text and '3. Комфорт' not in text


def test_summary_marks_proposed_dates_as_assumptions():
    agent, session = agent_and_session()
    session.state = TripState(date_from=date(2026,12,5), dates_assumed=True)
    result = agent.handle(session, 'Покажи текущие условия')
    assert 'ещё не ваш выбор' in result.reply


def test_explanation_intent_overrides_incidental_city_holiday_keyword():
    text = 'Объясни, для чего уточнять город старта'
    llm = FakeLLM({'dialogue_act':'explain', 'evidence':{'dialogue_act':text}})
    agent = Agent(TripsDomain(), llm)
    session = agent.new_session()
    session.state = TripState(pending_question='origin')
    before = session.state.model_dump()
    result = agent.handle(session, text)
    assert 'Например' in result.reply and 'Город' in result.reply
    assert session.state.model_dump() == before


def test_polite_verb_is_not_a_person_but_a_real_name_remains_masked():
    from core.guard import mask_sensitive_data
    text, masked = mask_sensitive_data('Благодарствую за подсказку')
    assert text == 'Благодарствую за подсказку' and not masked
    text, masked = mask_sensitive_data('Меня зовут Иван Петров')
    assert masked and 'Иван' not in text and 'Петров' not in text

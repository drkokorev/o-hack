from datetime import date

from core.agent import Agent
from domains.trips.domain import TripsDomain
from domains.trips.textparse import parse_budget


TODAY = date(2026, 10, 27)


def conversation(*messages):
    agent = Agent(TripsDomain(today=lambda: TODAY), None, today=lambda: TODAY)
    session = agent.new_session()
    for message in messages:
        step = agent.handle(session, message)
    return session.state, step


def test_refusal_to_fly_after_mention_of_airplanes_is_respected():
    state, step = conversation('Из Москвы в Казань с 10 по 14 ноября 2027, двое взрослых, '
                               'боюсь самолётов, лететь не буду')
    assert state.transport == 'train' and step.payload['kind'] == 'packages'
    assert all(item[leg]['mode'] == 'train' for item in step.payload['items'] for leg in ('out', 'back'))


def test_change_of_destination_does_not_keep_the_rejected_city():
    state, step = conversation('Сочи из Москвы с 5 по 12 декабря, двое взрослых',
                               'Я передумал насчёт Сочи, поеду в Казань')
    assert state.dest_id == 'kazan' and step.payload['kind'] == 'packages'


def test_interests_exclude_a_postposed_negative():
    state, _ = conversation('Мне нужны горы и природа в июле, море не интересует')
    assert {'mountains', 'nature'} <= set(state.trip_types or ())
    assert 'sea' not in (state.trip_types or ())


def test_person_count_and_pet_do_not_imply_all_are_adults():
    state, _ = conversation('Еду я и два друга, с кошкой')
    assert state.party_size == 3 and state.adults is None and state.pets is True
    family, _ = conversation('В Сочи на неделю в ноябре, едем я, муж, ребёнок и собака')
    assert family.children == 1 and family.adults is None and family.pets is True
    no_children, _ = conversation('Без детей, но со щенком')
    assert no_children.children == 0 and no_children.pets is True


def test_written_budget_is_understood_without_treating_distances_as_money():
    state, _ = conversation('Бюджет на всё путешествие — не дороже ста пятидесяти тысяч рублей')
    assert state.budget_total == 150000
    assert parse_budget('Планирую потратить около ста сорока пяти тысяч рублей')[0] == 145000
    assert parse_budget('Гора высотой пять тысяч метров')[0] is None

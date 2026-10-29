"""Read-only conversation policy, separate from trip changes and checkout.

The LLM can classify new wording in the same extraction call. Local matching is
only the offline fallback. Neither path can turn a discussion into a purchase.
"""
from __future__ import annotations

import re
from datetime import timedelta

from core.agent import Step
from core.ru import fmt_money

from .geo import BY_ID, DESTINATIONS, TAG_NAMES
from .policy_resources import dialogue_policy
from .state import TripState, TripUpdate
from .textparse import norm

EXPLICIT_CHANGE = re.compile(r'\b(?:выбираю|выбери|поменяй|измени|перенеси|оформи|оплати|отмени|добавь|убери)\b')


def local_act(state: TripState, text: str) -> str | None:
    """Conservative whole-utterance recognition; mixed edits go to extraction."""
    t = norm(text).strip(' .!?')
    if re.fullmatch(r'(?:привет|здравствуй(?:те)?|добрый (?:день|вечер)|доброе утро)', t):
        return 'greeting'
    if re.fullmatch(r'(?:спасибо[,! ]*)?(?:пока|вернусь позже|продолжим позже|поговорим потом|пока просто смотрю)', t):
        return 'pause'
    if re.fullmatch(r'(?:(?:выглядит хорошо|спасибо|хорошо)[, ]+(?:но )?)?'
                    r'(?:(?:ничего )?пока (?:ничего )?не|ничего не) '
                    r'(?:оформляй|бронируй|оплачивай)', t):
        return 'pause'
    if re.fullmatch(r'(?:спасибо|благодарю|спс)(?:\s+(?:большое|тебе|вам))?', t):
        return 'thanks'
    if re.fullmatch(r'(?:а )?(?:что (?:ты|вы) (?:умеешь|умеете|можешь|можете)|чем (?:ты |вы )?можешь помочь|что здесь можно сделать)', t):
        return 'capabilities'
    if (re.fullmatch(r'(?:а )?(?:это |у вас )?(?:настоящие|реальные) (?:цены|отели|рейсы|данные)', t)
            or re.fullmatch(r'откуда (?:эти |у тебя |у вас )?(?:цены|данные|информация)', t)):
        return 'data_provenance'
    if re.fullmatch(r'(?:что (?:ты |мы )?(?:уже )?(?:знаешь|знаем|выбрали|учел|учтено|запомнил)(?: о моей поездке)?|покажи (?:мои |текущие )?условия(?: поездки)?|(?:это |бюджет )?на человека или на всех)', t):
        return 'summary'
    if re.fullmatch(r'(?:не понял(?:а)?(?: (?:вопрос|что ты спрашиваешь))?|объясни (?:вопрос|уточнение))', t):
        return 'explain'
    if (state.pending_question and re.fullmatch(
            r'(?:зачем|почему)(?: тебе| вам| ты| вы)?(?: снова| опять)? (?:нужны?|спрашиваешь|спрашиваете|уточняешь|уточняете) [а-я ]+', t)):
        return 'explain'
    if (re.fullmatch(r'(?:ты |вы )?(?:меня )?не (?:понял|поняла|поняли)|вернись к моему вопросу', t)
            or re.fullmatch(r'(?:нет[, ]*)?(?:я )?(?:не выбирал\w* .+[, ]+)?(?:я )?(?:просто )?спрашивал\w* .+[, ]+не меняй пока', t)
            or re.fullmatch(r'я не выбирал\w* .+[, ]+просто спросил\w*', t)):
        return 'repair'
    if not EXPLICIT_CHANGE.search(t) and (re.match(r'^(?:а )?(?:если|что насчет)\b', t)
            or re.fullmatch(r'(?:а )?можно ли (?:доехать|добраться|долететь) .+', t)):
        return 'preview'
    if state.answered_question and re.fullmatch(r'а (?:в|во|на) [а-яa-z -]+', t) and '?' in text:
        return 'preview'
    return None


def contextual_update(state: TripState, text: str, update: TripUpdate) -> TripUpdate:
    """Resolve an explicit change of budget basis without inventing an amount."""
    t = norm(text).strip(' .!')
    if not any(getattr(update, key) is not None for key in ('budget_total', 'budget_per_person', 'budget_night')):
        if re.fullmatch(r'(?:это|бюджет|сумма) на (?:человека|каждого),? а не на всех', t):
            if state.budget_total is not None and state.budget_per_person is None and state.budget_night is None:
                return update.model_copy(update={'budget_per_person': state.budget_total})
        if re.fullmatch(r'(?:это|бюджет|сумма) на всех,? а не на (?:человека|каждого)', t):
            if state.budget_per_person is not None and state.budget_night is None:
                return update.model_copy(update={'budget_total': state.budget_per_person})
    return update


def accepted_model_act(state: TripState, text: str, llm: TripUpdate, rules: TripUpdate) -> str | None:
    if rules.dialogue_act:
        return rules.dialogue_act
    act = llm.dialogue_act
    quote = norm((llm.evidence or {}).get('dialogue_act', '')).strip()
    if not act or len(quote) < 3 or quote not in norm(text):
        return None
    # A courtesy prefix must not swallow an explicit edit, selection or action.
    if EXPLICIT_CHANGE.search(norm(text)) or re.search(r'\b(?:хочу|ищу|поедем|едем|летим)\b', norm(text)):
        return None
    if rules.pick is not None or rules.confirm is not None or rules.after_sale or rules.new_search:
        return None
    if act != 'preview':
        # Words such as "город" in "зачем уточнять город" are not a city-holiday
        # preference. A grounded meta intent outranks these lexical hints.
        substantive = rules.model_dump(exclude_none=True, exclude={
            'evidence', 'wants_ideas', 'question', 'unknown_place', 'trip_types'})
        if substantive:
            return None
    return act


def summary(state: TripState) -> str:
    lines = []
    if state.destination:
        lines.append(f'Направление: {state.destination}.')
    if state.country and not state.destination:
        lines.append(f'Страна: {state.country}.')
    if state.origin:
        suffix = ' (предположение, ещё не подтверждено)' if state.origin_inferred else ''
        lines.append(f'Отправление: {state.origin}{suffix}.')
    if state.month:
        from core.ru import MONTHS_NOM
        lines.append(f'Месяц поездки: {MONTHS_NOM[state.month - 1]}.')
    if state.date_from:
        dates = state.date_from.strftime('%d.%m.%Y')
        if state.date_to:
            dates += '–' + state.date_to.strftime('%d.%m.%Y')
        lines.append(('Предложенные демо-даты, ещё не ваш выбор: ' if state.dates_assumed else 'Даты: ') + dates + '.')
    if state.nights:
        lines.append(f'Ночей: {state.nights}.')
    if state.adults is not None:
        lines.append(f'Взрослых: {state.adults}.')
    elif state.party_size:
        lines.append(f'Путешественников: {state.party_size}; возрастной состав ещё не уточнён.')
    if state.children is not None:
        lines.append(f'Детей: {state.children}.')
    if state.budget_per_person is not None:
        lines.append(f'Бюджет: {fmt_money(state.budget_per_person)} на человека.')
    elif state.budget_total is not None:
        lines.append(f'Бюджет: {fmt_money(state.budget_total)} на всех.')
    if state.budget_night is not None:
        lines.append(f'Жильё: до {fmt_money(state.budget_night)} за ночь.')
    if state.transport in {'train', 'plane'}:
        lines.append('Транспорт: ' + {'train': 'поезд', 'plane': 'самолёт'}[state.transport] + '.')
    if state.trip_types:
        lines.append('Отдых: ' + ', '.join(TAG_NAMES.get(tag, tag) for tag in state.trip_types) + '.')
    if state.excluded_countries:
        lines.append('Исключены страны: ' + ', '.join(state.excluded_countries) + '.')
    return '\n'.join(lines) or dialogue_policy().replies['empty_summary']


def response(domain, state: TripState, update: TripUpdate, text: str, previous: Step | None) -> Step | None:
    act = update.dialogue_act
    if not act:
        return None
    policy = dialogue_policy()
    if act == 'preview':
        return preview(domain, state, update, text)
    if act == 'summary':
        return Step(summary(state))
    if act == 'explain':
        spec = policy.questions.get(state.pending_question or '')
        return Step((spec.why + ' ' + spec.example) if spec else policy.replies['capabilities'],
                    payload={'kind': 'question', 'field': state.pending_question} if spec else None)
    if act == 'repair':
        return Step(policy.replies['repair'] + '\n\n' + summary(state))
    if act in policy.replies:
        return Step(policy.replies[act])
    return None


def unknown_response(state: TripState, previous: Step | None = None) -> Step:
    policy = dialogue_policy()
    spec = policy.questions.get(state.pending_question or '')
    text = policy.replies['unknown'] + ' ' + (spec.example if spec else 'Уточните, что хотите узнать или изменить.')
    payload = {'kind': 'question', 'field': state.pending_question} if spec else (previous.payload if previous else None)
    return Step(text, payload=payload)


def preview(domain, state: TripState, update: TripUpdate, text: str) -> Step:
    """Work exclusively on a deep copy; never merge or execute checkout actions."""
    from .rules import find_destination
    policy = dialogue_policy()
    candidate = state.model_copy(deep=True)
    candidate.asked_text = text
    destination = update.destination or update.unknown_place
    target = (destination if destination in BY_ID else find_destination(norm(destination))) if destination else None
    if target:
        candidate.dest_id = target
        candidate.destination = BY_ID[target].name
        if state.dates_assumed:
            candidate.date_from = candidate.date_to = None
    topic = update.question or state.answered_question
    if target and topic:
        result = domain._answer_incomplete(candidate, topic, followup=False)
        result.reply = policy.replies['preview'] + '\n\n' + result.reply
        return result
    if update.country:
        names = [dest.name for dest in DESTINATIONS if dest.country == update.country]
        detail = (f'Для страны {update.country} в каталоге есть: ' + ', '.join(names[:6]) + '.' if names else
                  f'Для страны {update.country} предложений в каталоге нет.')
        return Step(policy.replies['preview'] + ' ' + detail + ' Если хотите сменить направление, назовите выбранный город.')
    if target:
        dest = BY_ID[target]
        return Step(policy.replies['preview'] + f' {dest.name}, {dest.country}: ' + ', '.join(dest.highlights) +
                    '. Цены и наличие не проверены. Чтобы выбрать это направление, напишите «выбираю ' + dest.name + '».')
    if update.transport:
        label = {'train': 'поезд', 'plane': 'самолёт'}.get(update.transport, 'другой транспорт')
        return Step(policy.replies['preview'] + f' Можно рассмотреть {label}; наличие маршрута, расписание и билеты '
                    'у перевозчика сейчас не проверены. Для пересчёта демонстрационного плана напишите «выбираю ' + label + '».')
    if update.shift_days is not None and state.date_from and abs(update.shift_days) <= 366:
        start = state.date_from + timedelta(days=update.shift_days)
        dates = start.strftime('%d.%m.%Y')
        if state.date_to:
            dates += '–' + (state.date_to + timedelta(days=update.shift_days)).strftime('%d.%m.%Y')
        return Step(policy.replies['preview'] + ' При таком сдвиге даты будут ' + dates +
                    '. Новые цены и наличие не проверены. Если подходит, попросите перенести поездку.')
    if topic:
        result = domain._answer_incomplete(candidate, topic, followup=False)
        result.reply = policy.replies['preview'] + '\n\n' + result.reply
        return result
    return Step(policy.replies['preview'] + ' ' + policy.replies['preview_unresolved'])

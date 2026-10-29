"""Local consistency checks for units, explicit totals and uncertain inputs.

These checks do not convert money, infer ages or fill unspecified passengers.
They run on rule output and are authoritative when a model proposes a value.
"""
import re

from .state import TripState, TripUpdate
from .textparse import NUM, norm, num_word

_FOREIGN = re.compile(r'\b(?:доллар\w*|бакс\w*|евро|фунт\w*|юан\w*|иен\w*|лир\w*|тенге|лари|дирхам\w*|'
                      r'usd|eur|gbp|cny|jpy|try|kzt|gel|aed|chf)\b|[$€£¥]', re.I)


def validate_input(state: TripState, text: str, update: TripUpdate) -> TripUpdate:
    value = norm(text)
    changes = {}
    currency = _FOREIGN.search(value)
    if currency and (re.search(r'\d|бюджет|тысяч|миллион|сот|сто\b', value) or currency.group(0) in '$€£¥'):
        # Reject the whole ambiguous budget clause, including mixed currencies;
        # the application has only RUB estimates and no exchange-rate source.
        changes.update(unsupported_budget_currency=currency.group(0), budget_total=None,
                       budget_per_person=None, budget_night=None)

    total_match = re.search(rf'\bнас\s+(?:всего\s+)?{NUM}\b', value)
    if total_match:
        total = num_word(total_match.group(1))
        if total and not re.search(r'\bне\s+$', value[max(0,total_match.start()-8):total_match.start()]):
            changes['party_size'] = total
            # Ages alone may be a partial list. Only reconcile the explicit
            # total and explicit adult count when they account for every age.
            if (update.children is None and update.adults is not None and update.children_ages
                    and total == update.adults + len(update.children_ages)):
                changes.update(children=len(update.children_ages), children_unknown=False)

    maybe = r'\b(?:возможно|может(?:\s+быть)?|наверное|вероятно)\s*,?\s*'
    party = rf'(?:(?:поеду|поедем|полетим|поехать)\s+)?(?:нас\s+)?(?:вдвоем|втроем|вчетвером|{NUM})\b'
    if update.party_size is not None and re.search(maybe + party, value):
        changes['tentative_fields'] = sorted(set(update.tentative_fields or []) | {'party_size'})
    return update.model_copy(update=changes) if changes else update

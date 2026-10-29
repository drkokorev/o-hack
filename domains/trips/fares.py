"""A provider's per-passenger fare; age alone never establishes free travel or discount."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class FareKind(str, Enum):
    ADULT = "adult"
    CHILD_FREE = "child_free"
    CHILD_DISCOUNTED = "child_discounted"
    CHILD_FULL = "child_full"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PassengerFare:
    kind: FareKind
    amount: Decimal | None
    currency: str | None
    source: str | None
    # None means a supplier did not specify whether the child occupies a seat.
    seat_included: bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, FareKind):
            raise ValueError("Неизвестный вид тарифа")
        if self.kind is FareKind.UNKNOWN:
            if self.amount is not None or self.currency is not None:
                raise ValueError("Непроверенный тариф не может содержать цену")
            return
        if (not isinstance(self.amount, Decimal) or not self.amount.is_finite() or self.amount < 0 or
                not self.currency or len(self.currency) != 3 or not self.currency.isascii() or
                not self.currency.isalpha() or self.currency != self.currency.upper() or not self.source):
            raise ValueError("Нужны цена, валюта и источник тарифа")
        if self.kind is FareKind.CHILD_FREE and self.amount != 0:
            raise ValueError("Бесплатный тариф должен иметь нулевую общую цену")


def total_confirmed_fares(fares: list[PassengerFare]) -> tuple[Decimal, str] | None:
    """Unknown or mixed currencies cannot silently become a complete total."""
    if not fares or any(f.kind is FareKind.UNKNOWN for f in fares):
        return None
    currencies = {f.currency for f in fares}
    if len(currencies) != 1:
        return None
    return sum((f.amount for f in fares if f.amount is not None), Decimal(0)), next(iter(currencies))

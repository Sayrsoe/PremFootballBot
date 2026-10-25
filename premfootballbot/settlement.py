"""Pure selected-side Asian handicap settlement, without feeds or models.

Supply regulation-time final goals, including stoppage time and excluding extra
time and penalties. Administrative voids/abandonments are outside this API.
Handicaps are signed integer quarter units: +3 means the selected side gets
+0.75 goals. All stake fractions, odds and returns use exact rational arithmetic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from fractions import Fraction
from typing import Literal

Side = Literal["home", "away"]


class Outcome(str, Enum):
    """Mutually exclusive outcomes for the full stake."""

    FULL_WIN = "FW"
    HALF_WIN = "HW"
    PUSH = "P"
    HALF_LOSS = "HL"
    FULL_LOSS = "FL"


# Half-stake counts in the order: won, refunded, lost.
_STAKE_UNITS: dict[Outcome, tuple[int, int, int]] = {
    Outcome.FULL_WIN: (2, 0, 0),
    Outcome.HALF_WIN: (1, 1, 0),
    Outcome.PUSH: (0, 2, 0),
    Outcome.HALF_LOSS: (0, 1, 1),
    Outcome.FULL_LOSS: (0, 0, 2),
}
_OUTCOMES_BY_UNITS = {units: outcome for outcome, units in _STAKE_UNITS.items()}
_DECIMAL_TEXT = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)")


@dataclass(frozen=True, slots=True)
class Settlement:
    """An outcome with its exact stake fractions; independent of prices."""

    outcome: Outcome
    win: Fraction = field(init=False)
    refund: Fraction = field(init=False)
    loss: Fraction = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, Outcome):
            raise TypeError("outcome must be an Outcome enum member")
        win, refund, loss = _STAKE_UNITS[self.outcome]
        object.__setattr__(self, "win", Fraction(win, 2))
        object.__setattr__(self, "refund", Fraction(refund, 2))
        object.__setattr__(self, "loss", Fraction(loss, 2))


@dataclass(frozen=True, slots=True)
class Payout:
    """Unrounded exact amounts for the supplied stake, including unit returns."""

    odds: Fraction
    stake: Fraction
    net: Fraction
    gross: Fraction

    @property
    def net_per_unit(self) -> Fraction:
        return self.net / self.stake

    @property
    def gross_per_unit(self) -> Fraction:
        return self.gross / self.stake


def _integer(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer, not bool or another type")


def _decimal(text: str, name: str) -> Fraction:
    if not isinstance(text, str):
        raise TypeError(f"{name} must be a decimal string; no numeric coercion")
    if _DECIMAL_TEXT.fullmatch(text) is None:
        raise ValueError(
            f"{name} must be finite plain decimal text "
            "(no whitespace, exponents, separators or fractions)"
        )
    # String-to-Fraction conversion is exact and independent of Decimal context.
    return Fraction(text)


def parse_handicap(decimal_text: str) -> int:
    """Parse a finite plain decimal string into signed integer quarter units.

    For example, "-0.75" -> -3 and ".25" -> 1. No float/Decimal coercion,
    approximate-quarter rounding, exponent notation or whitespace is accepted.
    """
    quarters = _decimal(decimal_text, "handicap") * 4
    if quarters.denominator != 1:
        raise ValueError("handicap must be an exact multiple of 0.25 goals")
    return quarters.numerator


def settle_handicap(
    home_goals: int, away_goals: int, side: Side, handicap_q: int
) -> Settlement:
    """Classify a full-time result from the selected side's perspective.

    Goals must be nonnegative integers; handicap_q is an integer (bool rejected).
    Positive handicaps help the selected side. Odd q splits equally between
    q-1 and q+1; even q settles one full stake. Invalid types raise TypeError;
    invalid goal values or side strings raise ValueError.
    """
    _integer(home_goals, "home_goals")
    _integer(away_goals, "away_goals")
    if home_goals < 0:
        raise ValueError("home_goals must be nonnegative")
    if away_goals < 0:
        raise ValueError("away_goals must be nonnegative")
    if not isinstance(side, str):
        raise TypeError("side must be the string 'home' or 'away'")
    if side not in ("home", "away"):
        raise ValueError("side must be exactly 'home' or 'away'")
    _integer(handicap_q, "handicap_q")

    difference = home_goals - away_goals
    if side == "away":
        difference = -difference

    if handicap_q % 2:
        components = (handicap_q - 1, handicap_q + 1)
        weight = 1
    else:
        components = (handicap_q,)
        weight = 2

    win = refund = loss = 0
    for component_q in components:
        margin = 4 * difference + component_q
        if margin > 0:
            win += weight
        elif margin == 0:
            refund += weight
        else:
            loss += weight

    return Settlement(_OUTCOMES_BY_UNITS[(win, refund, loss)])


def calculate_payout(
    settlement: Settlement, *, decimal_odds: str, stake: str = "1"
) -> Payout:
    """Return exact unrounded net/gross amounts, defaulting to a unit stake.

    Odds and stake must be finite plain decimal strings, with odds > 1 and
    stake > 0. Passing floats, Decimal objects or fractions is rejected.
    No per-component or currency rounding is performed.
    """
    if not isinstance(settlement, Settlement):
        raise TypeError("settlement must be a Settlement result")
    odds_value = _decimal(decimal_odds, "decimal_odds")
    if odds_value <= 1:
        raise ValueError("decimal_odds must be greater than 1")
    stake_value = _decimal(stake, "stake")
    if stake_value <= 0:
        raise ValueError("stake must be greater than 0")

    net = stake_value * (settlement.win * (odds_value - 1) - settlement.loss)
    gross = stake_value * (settlement.win * odds_value + settlement.refund)
    return Payout(odds=odds_value, stake=stake_value, net=net, gross=gross)

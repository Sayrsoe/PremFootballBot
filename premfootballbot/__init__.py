"""Exact, offline Asian handicap settlement for regulation-time results."""

from .settlement import (
    Outcome,
    Payout,
    Settlement,
    Side,
    calculate_payout,
    parse_handicap,
    settle_handicap,
)

__all__ = [
    "Outcome",
    "Payout",
    "Settlement",
    "Side",
    "calculate_payout",
    "parse_handicap",
    "settle_handicap",
]

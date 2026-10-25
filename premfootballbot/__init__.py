"""Offline Asian handicap settlement and fixed-rate Poisson probabilities."""

from .settlement import (
    Outcome,
    Payout,
    Settlement,
    Side,
    calculate_payout,
    parse_handicap,
    settle_handicap,
)
from .poisson import (
    DEFAULT_TOLERANCE,
    MAX_DISTRIBUTION_RATE,
    MAX_GOAL_CAP,
    AsianHandicapProbabilities,
    GoalCapError,
    MassSummary,
    OneXTwoProbabilities,
    PoissonDistribution,
    poisson_distribution,
    poisson_pmf,
    truncated_poisson_distribution,
)

__all__ = [
    "Outcome",
    "Payout",
    "Settlement",
    "Side",
    "calculate_payout",
    "parse_handicap",
    "settle_handicap",
    "DEFAULT_TOLERANCE",
    "MAX_DISTRIBUTION_RATE",
    "MAX_GOAL_CAP",
    "AsianHandicapProbabilities",
    "GoalCapError",
    "MassSummary",
    "OneXTwoProbabilities",
    "PoissonDistribution",
    "poisson_distribution",
    "poisson_pmf",
    "truncated_poisson_distribution",
]

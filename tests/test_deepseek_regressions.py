"""Thirty named regression tests from the independent Phase 1A review.

The CSV contains the supplied expected outcomes and exact decimal unit returns.
Expectations are never computed using the settlement implementation.
"""

import csv
import unittest
from fractions import Fraction
from pathlib import Path
from typing import Callable

from premfootballbot import calculate_payout, settle_handicap


_FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "deepseek_30_regression_fixtures.csv"
)
_FIELDS = [
    "case_id", "home_goals", "away_goals", "side", "handicap_q",
    "decimal_odds", "outcome", "net_per_unit",
]


def _reviewed_cases() -> list[dict[str, str]]:
    with _FIXTURE_PATH.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != _FIELDS:
            raise ValueError("DeepSeek regression fixture columns changed")
        cases = list(reader)

    expected_ids = {f"DS{number:02d}" for number in range(1, 31)}
    ids = [case["case_id"] for case in cases]
    if len(cases) != 30 or set(ids) != expected_ids:
        raise ValueError("DeepSeek fixtures must contain DS01-DS30 exactly once")
    return cases


def _regression_test(
    case: dict[str, str],
) -> Callable[[unittest.TestCase], None]:
    def check(self: unittest.TestCase) -> None:
        result = settle_handicap(
            int(case["home_goals"]),
            int(case["away_goals"]),
            case["side"],
            int(case["handicap_q"]),
        )
        payout = calculate_payout(result, decimal_odds=case["decimal_odds"])
        expected_net = Fraction(case["net_per_unit"])

        self.assertEqual(result.outcome.value, case["outcome"])
        self.assertIsInstance(payout.net_per_unit, Fraction)
        self.assertEqual(payout.net_per_unit, expected_net)
        self.assertEqual(payout.gross_per_unit, 1 + expected_net)

    return check


class DeepSeekRegressionTests(unittest.TestCase):
    """Each reviewed CSV row is independently discoverable by unittest."""


for _case in _reviewed_cases():
    setattr(
        DeepSeekRegressionTests,
        f"test_{_case['case_id'].lower()}",
        _regression_test(_case),
    )


if __name__ == "__main__":
    unittest.main()

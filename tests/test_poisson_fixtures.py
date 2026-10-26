"""Independent nine-decimal fixtures supplied with the Phase 1B handoff."""

import csv
from pathlib import Path
from typing import Callable
import unittest

from premfootballbot import poisson_distribution, truncated_poisson_distribution


_ROOT = Path(__file__).parent / "fixtures"


def _rows(name: str, count: int) -> list[dict[str, str]]:
    with (_ROOT / name).open(encoding="utf-8", newline="") as stream:
        result = list(csv.DictReader(stream))
    if len(result) != count:
        raise ValueError(f"{name} must retain all {count} independent rows")
    return result


_X_ROWS = _rows("deepseek_24_1x2_fixtures.csv", 24)
_AH_ROWS = _rows("deepseek_49_ah_fixtures.csv", 49)
if {row["case_id"] for row in _X_ROWS} != {f"C{i}" for i in range(1, 25)}:
    raise ValueError("1X2 fixture identifiers must be C1-C24 exactly once")
if len({(r["case_id"], r["side"], r["handicap_q"]) for r in _AH_ROWS}) != 49:
    raise ValueError("AH fixture identifiers must remain unique")


class IndependentPoissonFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Reuse each difference distribution across that case's multiple lines.
        cls.models = {}
        for row in _X_ROWS:
            home, away = float(row["lambda_home"]), float(row["lambda_away"])
            cap = int(row["cap_N"])
            cls.models[row["case_id"]] = (
                poisson_distribution(home, away),
                truncated_poisson_distribution(home, away, home_cap=cap, away_cap=cap),
            )


def _one_x_two_test(row: dict[str, str]) -> Callable:
    def check(self: IndependentPoissonFixtureTests) -> None:
        for index, model in enumerate(self.models[row["case_id"]]):
            with self.subTest(mode=("adaptive", "reference cap")[index]):
                result = model.one_x_two()
                for actual, field in (
                    (result.home_win, "prob_home"), (result.draw, "prob_draw"),
                    (result.away_win, "prob_away"),
                    (result.mass.retained_mass, "retained_mass"),
                ):
                    self.assertAlmostEqual(actual, float(row[field]), delta=1e-9)
    return check


def _asian_handicap_test(row: dict[str, str]) -> Callable:
    def check(self: IndependentPoissonFixtureTests) -> None:
        # Source uses Unicode minus; preserve source bytes and normalize only q.
        q = int(row["handicap_q"].replace("\u2212", "-"))
        for index, model in enumerate(self.models[row["case_id"]]):
            with self.subTest(mode=("adaptive", "reference cap")[index]):
                result = model.asian_handicap(row["side"], q)
                actual = (result.fw, result.hw, result.push, result.hl, result.fl)
                for probability, field in zip(
                    actual, ("prob_fw", "prob_hw", "prob_p", "prob_hl", "prob_fl")
                ):
                    self.assertAlmostEqual(probability, float(row[field]), delta=1e-9)
                self.assertAlmostEqual(sum(actual), float(row["sum"]), delta=1e-9)
    return check


for _row in _X_ROWS:
    setattr(
        IndependentPoissonFixtureTests,
        f"test_1x2_{_row['case_id'].lower()}",
        _one_x_two_test(_row),
    )
for _index, _row in enumerate(_AH_ROWS, 1):
    setattr(
        IndependentPoissonFixtureTests,
        f"test_ah_{_index:02d}_{_row['case_id'].lower()}_{_row['side']}",
        _asian_handicap_test(_row),
    )

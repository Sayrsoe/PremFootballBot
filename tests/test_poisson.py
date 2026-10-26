"""Numerical and integration checks independent of the supplied fixture values."""

from dataclasses import FrozenInstanceError
from decimal import Decimal
from fractions import Fraction
from itertools import product
import math
import unittest
from unittest.mock import patch

from premfootballbot import (
    GoalCapError,
    MAX_GOAL_CAP,
    Outcome,
    poisson_distribution,
    poisson_pmf,
    settle_handicap,
    truncated_poisson_distribution,
)


def small_pmf(k: int, rate: float) -> float:
    # Safe direct formula is an independent oracle for small k/rates only.
    return math.exp(-rate) * rate**k / math.factorial(k)


def ah_values(result):
    return (result.fw, result.hw, result.push, result.hl, result.fl)


class ScalarPoissonTests(unittest.TestCase):
    def test_zero_rate(self):
        self.assertEqual(poisson_pmf(0, 0), 1)
        self.assertEqual(poisson_pmf(1, 0), 0)
        self.assertEqual(poisson_pmf(800, 0), 0)

    def test_small_count_direct_formula(self):
        for rate, k in product((0.1, 1.4, 2.5), range(7)):
            with self.subTest(rate=rate, k=k):
                self.assertAlmostEqual(poisson_pmf(k, rate), small_pmf(k, rate), delta=1e-15)

    def test_mode_at_800_is_finite_and_does_not_underflow(self):
        # Independent 70-digit Decimal exp/recurrence oracle, not project code.
        expected = 0.014103270421583719427677804365102089
        self.assertEqual(math.exp(-800), 0)
        actual = poisson_pmf(800, 800)
        self.assertTrue(math.isfinite(actual))
        self.assertGreater(actual, 0)
        self.assertAlmostEqual(actual, expected, delta=2e-14)
        self.assertAlmostEqual(poisson_pmf(799, 800), actual, delta=2e-14)
        self.assertLess(poisson_pmf(801, 800), actual)

    def test_real_fraction_rate(self):
        self.assertAlmostEqual(poisson_pmf(0, Fraction(1, 2)), math.exp(-0.5))

    def test_invalid_rate_types(self):
        for rate in (True, False, "1", None, 1j, Decimal("1")):
            with self.subTest(rate=rate):
                with self.assertRaises(TypeError):
                    poisson_pmf(0, rate)

    def test_invalid_rate_values(self):
        for rate in (-1, Fraction(-1, 10**1000), math.nan, math.inf, -math.inf, 10**1000):
            with self.subTest(rate=rate):
                with self.assertRaises(ValueError):
                    poisson_pmf(0, rate)

    def test_invalid_goals(self):
        for k in (True, False, 1.0, None, "1"):
            with self.subTest(k=k):
                with self.assertRaises(TypeError):
                    poisson_pmf(k, 1)
        with self.assertRaises(ValueError):
            poisson_pmf(-1, 1)

    def test_unrepresentable_goal_input_has_clear_error(self):
        with self.assertRaisesRegex(ValueError, "floating-point range"):
            poisson_pmf(10**1000, 1)


class DistributionTests(unittest.TestCase):
    def test_zero_zero_is_exact(self):
        model = poisson_distribution(0, 0)
        self.assertEqual((model.home_cap, model.away_cap), (0, 0))
        self.assertEqual(model.difference_pmf, (1.0,))
        result = model.one_x_two()
        self.assertEqual((result.home_win, result.draw, result.away_win), (0, 1, 0))
        self.assertEqual(model.mass.retained_mass, 1)
        self.assertEqual(model.mass.omitted_mass, 0)
        self.assertEqual(model.mass.omitted_mass_bound, 0)
        self.assertEqual(ah_values(model.asian_handicap("home", 1)), (0, 1, 0, 0, 0))
        self.assertEqual(ah_values(model.asian_handicap("away", -1)), (0, 0, 0, 1, 0))

    def test_separate_caps_for_asymmetric_rates(self):
        model = poisson_distribution(10, 0.1)
        self.assertGreater(model.home_cap, model.away_cap)
        self.assertEqual(poisson_distribution(5, 0).away_cap, 0)

    def test_adaptive_bound_and_reported_mass(self):
        for rates, tolerance in product(((0, 2), (1.4, 1.1), (10, 1), (100, 100)), (1e-6, 1e-10, 1e-12)):
            with self.subTest(rates=rates, tolerance=tolerance):
                model = poisson_distribution(*rates, tolerance=tolerance)
                self.assertLessEqual(model.mass.omitted_mass_bound, tolerance)
                self.assertLessEqual(model.mass.omitted_mass, model.mass.omitted_mass_bound)
                self.assertAlmostEqual(
                    model.mass.retained_mass + model.mass.omitted_mass, 1, delta=3e-16
                )
                self.assertAlmostEqual(
                    math.fsum(model.difference_pmf), model.mass.retained_mass, delta=5e-12
                )

    def test_tiny_tail_not_inferred_from_rounded_cdf(self):
        normal = poisson_distribution(1, 1)
        tiny = poisson_distribution(1, 1, tolerance=1e-25)
        self.assertEqual(tiny.mass.retained_mass, 1.0)
        self.assertGreater(tiny.mass.omitted_mass, 0)
        self.assertGreater(tiny.mass.omitted_mass_bound, 0)
        self.assertLessEqual(tiny.mass.omitted_mass_bound, 1e-25)
        self.assertGreater(tiny.home_cap, normal.home_cap)

    def test_unrepresentable_tail_target_fails_explicitly(self):
        with self.assertRaises(GoalCapError):
            poisson_distribution(1, 1, tolerance=math.nextafter(0.0, 1.0))

    def test_insufficient_cap_raises(self):
        with self.assertRaisesRegex(GoalCapError, "max_goals=2"):
            poisson_distribution(10, 1, max_goals=2)

    def test_fixed_cap_exposes_missing_mass_without_normalization(self):
        model = truncated_poisson_distribution(1.4, 1.1, home_cap=0, away_cap=0)
        expected = math.exp(-2.5)
        self.assertAlmostEqual(model.score_probability(0, 0), expected, delta=1e-16)
        self.assertAlmostEqual(model.mass.retained_mass, expected, delta=1e-16)
        self.assertAlmostEqual(model.mass.omitted_mass, 1 - expected, delta=2e-16)
        self.assertAlmostEqual(model.one_x_two().draw, expected, delta=1e-16)
        self.assertAlmostEqual(model.asian_handicap("home", 1).hw, expected, delta=1e-16)
        self.assertLess(model.one_x_two().draw, 0.1)

    def test_small_rectangular_cdf_product(self):
        model = truncated_poisson_distribution(1, 1.5, home_cap=2, away_cap=1)
        expected = math.fsum(small_pmf(k, 1) for k in range(3)) * math.fsum(
            small_pmf(k, 1.5) for k in range(2)
        )
        self.assertAlmostEqual(model.mass.retained_mass, expected, delta=1e-15)
        self.assertAlmostEqual(model.mass.omitted_mass, 1 - expected, delta=2e-16)

    def test_small_lower_tail_is_not_lost_to_one_minus_tail(self):
        model = truncated_poisson_distribution(100, 100, home_cap=0, away_cap=0)
        self.assertGreater(model.mass.retained_mass, 0)
        self.assertAlmostEqual(model.mass.retained_mass / math.exp(-200), 1, delta=1e-14)

    def test_zero_rate_fixed_caps_have_zero_positive_goals(self):
        model = truncated_poisson_distribution(0, 0, home_cap=4, away_cap=3)
        self.assertEqual(model.home_pmf, (1, 0, 0, 0, 0))
        self.assertEqual(model.away_pmf, (1, 0, 0, 0))
        self.assertEqual(model.mass.retained_mass, 1)

    def test_exact_score_values_and_absent_scores(self):
        model = poisson_distribution(1.4, 1.1)
        for home, away in ((0, 0), (1, 0), (1, 1), (2, 1)):
            self.assertAlmostEqual(
                model.score_probability(home, away),
                small_pmf(home, 1.4) * small_pmf(away, 1.1),
                delta=2e-16,
            )
        self.assertIsNotNone(model.score_probability(model.home_cap, model.away_cap))
        self.assertIsNone(model.score_probability(model.home_cap + 1, 0))
        self.assertIsNone(model.score_probability(0, model.away_cap + 1))

    def test_score_query_validation(self):
        model = poisson_distribution(1, 1)
        for home, away in ((True, 0), (0, False), (1.0, 0), (0, "1")):
            with self.assertRaises(TypeError):
                model.score_probability(home, away)
        with self.assertRaises(ValueError):
            model.score_probability(-1, 0)

    def test_inputs_reject_bool_and_nonfinite_rates(self):
        for invalid in (True, "1", None, Decimal("1")):
            for pair in ((invalid, 1), (1, invalid)):
                with self.assertRaises(TypeError):
                    poisson_distribution(*pair)
        for invalid in (-1, math.nan, math.inf, -math.inf):
            for pair in ((invalid, 1), (1, invalid)):
                with self.assertRaises(ValueError):
                    poisson_distribution(*pair)

    def test_joint_rate_limit_is_explicit(self):
        self.assertGreater(poisson_distribution(100, 0).home_cap, 100)
        for rate in (100.01, 800):
            with self.assertRaisesRegex(ValueError, "joint calculation limit"):
                poisson_distribution(rate, 1)

    def test_tolerance_validation(self):
        for tolerance in (True, "1e-10", None, Decimal(".01")):
            with self.assertRaises(TypeError):
                poisson_distribution(1, 1, tolerance=tolerance)
        for tolerance in (0, -1, 1, 2, math.nan, math.inf):
            with self.assertRaises(ValueError):
                poisson_distribution(1, 1, tolerance=tolerance)

    def test_cap_validation(self):
        for cap in (True, 2.0, None, "2"):
            with self.assertRaises(TypeError):
                poisson_distribution(1, 1, max_goals=cap)
            with self.assertRaises(TypeError):
                truncated_poisson_distribution(1, 1, home_cap=cap, away_cap=2)
        for cap in (-1, MAX_GOAL_CAP + 1):
            with self.assertRaises(ValueError):
                poisson_distribution(1, 1, max_goals=cap)
            with self.assertRaises(ValueError):
                truncated_poisson_distribution(1, 1, home_cap=2, away_cap=cap)

    def test_outputs_and_nested_probabilities_are_immutable(self):
        model = poisson_distribution(1, 1)
        for target, field in ((model, "lambda_home"), (model.mass, "retained_mass"), (model.one_x_two(), "draw"), (model.asian_handicap("home", 1), "hw")):
            with self.assertRaises(FrozenInstanceError):
                setattr(target, field, 7)
        with self.assertRaises(TypeError):
            model.home_pmf[0] = 7

    def test_mass_roundoff_is_visible_not_a_normalization(self):
        model = poisson_distribution(50, 100)
        raw = math.fsum(model.difference_pmf)
        self.assertEqual(model.mass.mass_roundoff, raw - model.mass.retained_mass)
        self.assertLess(abs(model.mass.mass_roundoff), 5e-12)
        self.assertEqual(
            model.score_probability(1, 1), model.home_pmf[1] * model.away_pmf[1]
        )


class ProbabilityIntegrationTests(unittest.TestCase):
    def test_difference_distribution_matches_independent_small_matrix(self):
        for rates in ((0, 0), (0, 2), (1.4, 1.1), (2.5, 0.5)):
            for home_cap, away_cap in ((0, 0), (2, 4), (4, 3)):
                model = truncated_poisson_distribution(*rates, home_cap=home_cap, away_cap=away_cap)
                for index, actual in enumerate(model.difference_pmf):
                    d = index - away_cap
                    expected = math.fsum(
                        small_pmf(i, rates[0]) * small_pmf(j, rates[1])
                        for i in range(home_cap + 1)
                        for j in range(away_cap + 1)
                        if i - j == d
                    )
                    self.assertAlmostEqual(actual, expected, delta=2e-15)

    def test_ah_aggregation_matches_score_pairs_classified_by_phase1a(self):
        model = truncated_poisson_distribution(1.4, 1.1, home_cap=4, away_cap=3)
        labels = (Outcome.FULL_WIN, Outcome.HALF_WIN, Outcome.PUSH, Outcome.HALF_LOSS, Outcome.FULL_LOSS)
        for side, q in product(("home", "away"), range(-9, 10)):
            expected = {label: [] for label in labels}
            for i, j in product(range(5), range(4)):
                category = settle_handicap(i, j, side, q).outcome
                expected[category].append(small_pmf(i, 1.4) * small_pmf(j, 1.1))
            for actual, label in zip(ah_values(model.asian_handicap(side, q)), labels):
                self.assertAlmostEqual(actual, math.fsum(expected[label]), delta=2e-15)

    def test_each_result_exposes_same_mass_accounting(self):
        model = poisson_distribution(1.4, 1.1)
        self.assertIs(model.one_x_two().mass, model.mass)
        for side, q in product(("home", "away"), range(-12, 13)):
            result = model.asian_handicap(side, q)
            self.assertIs(result.mass, model.mass)
            self.assertAlmostEqual(math.fsum(ah_values(result)), model.mass.retained_mass, delta=5e-12)
            for value in ah_values(result):
                self.assertGreaterEqual(value, 0)
                self.assertLessEqual(value, model.mass.retained_mass + 5e-12)

    def test_phase1a_classifier_is_used_for_nonzero_differences(self):
        model = poisson_distribution(1.4, 1.1)
        with patch("premfootballbot.poisson.settle_handicap", wraps=settle_handicap) as classifier:
            model.asian_handicap("away", -3)
            self.assertTrue(any(call.args[0] != call.args[1] for call in classifier.call_args_list))

    def test_handicap_validation_remains_phase1a_policy(self):
        model = poisson_distribution(1, 1)
        for side, q, error in ((True, 1, TypeError), ("Home", 1, ValueError), ("home", True, TypeError), ("home", 1.0, TypeError)):
            with self.assertRaises(error):
                model.asian_handicap(side, q)

    def test_quarter_sign_and_residue_sparsity(self):
        model = poisson_distribution(0.7, 1.5)
        allowed = {0: {0, 2, 4}, 1: {0, 1, 4}, 2: {0, 4}, 3: {0, 3, 4}}
        for q in range(-12, 13):
            values = ah_values(model.asian_handicap("home", q))
            for index, value in enumerate(values):
                if index not in allowed[q % 4]:
                    self.assertEqual(value, 0)
        self.assertGreater(model.asian_handicap("home", -3).hw, 0)
        self.assertGreater(model.asian_handicap("home", 3).hl, 0)

    def test_symmetric_rates(self):
        model = poisson_distribution(1.5, 1.5)
        self.assertAlmostEqual(model.one_x_two().home_win, model.one_x_two().away_win, delta=1e-15)
        for q in range(-8, 9):
            for first, second in zip(ah_values(model.asian_handicap("home", q)), ah_values(model.asian_handicap("away", q))):
                self.assertAlmostEqual(first, second, delta=1e-15)

    def test_rate_and_side_mirror(self):
        first = poisson_distribution(1.4, 1.1)
        mirror = poisson_distribution(1.1, 1.4)
        self.assertEqual((first.home_cap, first.away_cap), (mirror.away_cap, mirror.home_cap))
        self.assertAlmostEqual(first.one_x_two().home_win, mirror.one_x_two().away_win, delta=1e-15)
        for q in range(-8, 9):
            for x, y in zip(ah_values(first.asian_handicap("home", q)), ah_values(mirror.asian_handicap("away", q))):
                self.assertAlmostEqual(x, y, delta=1e-15)

    def test_opposite_side_and_line_complement(self):
        model = poisson_distribution(1.4, 1.1)
        for q in range(-12, 13):
            home = ah_values(model.asian_handicap("home", q))
            away = ah_values(model.asian_handicap("away", -q))
            for actual, expected in zip(away, reversed(home)):
                self.assertAlmostEqual(actual, expected, delta=1e-15)

    def test_whole_zero_line_matches_1x2(self):
        model = poisson_distribution(1.4, 1.1)
        ah = model.asian_handicap("home", 0)
        x = model.one_x_two()
        self.assertEqual((ah.fw, ah.push, ah.fl), (x.home_win, x.draw, x.away_win))

    def test_increasing_caps_only_adds_mass_and_bounds_the_change(self):
        small = truncated_poisson_distribution(1.4, 1.1, home_cap=2, away_cap=3)
        large = truncated_poisson_distribution(1.4, 1.1, home_cap=5, away_cap=6)
        self.assertGreater(large.mass.retained_mass, small.mass.retained_mass)
        for i, j in product(range(3), range(4)):
            self.assertEqual(small.score_probability(i, j), large.score_probability(i, j))
        for q in range(-8, 9):
            for old, new in zip(ah_values(small.asian_handicap("home", q)), ah_values(large.asian_handicap("home", q))):
                self.assertGreaterEqual(new + 1e-15, old)
                self.assertLessEqual(new - old, small.mass.omitted_mass + 1e-15)

    def test_larger_handicap_improves_full_win_and_full_loss_masses(self):
        model = poisson_distribution(1.4, 1.1)
        last_fw, last_fl = 0.0, math.inf
        for q in range(-12, 13):
            result = model.asian_handicap("home", q)
            self.assertGreaterEqual(result.fw + 1e-15, last_fw)
            self.assertLessEqual(result.fl, last_fl + 1e-15)
            last_fw, last_fl = result.fw, result.fl

    def test_many_lines_reuse_unchanged_distribution(self):
        model = poisson_distribution(1.4, 1.1)
        cached = model.difference_pmf
        for q in range(-20, 21):
            model.asian_handicap("home", q)
            self.assertIs(model.difference_pmf, cached)


if __name__ == "__main__":
    unittest.main()

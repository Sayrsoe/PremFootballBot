"""Independent golden oracles plus exhaustive small-domain invariants."""

import unittest
from dataclasses import FrozenInstanceError
from decimal import Decimal, localcontext
from fractions import Fraction
from itertools import product

from premfootballbot import (
    Outcome,
    Settlement,
    calculate_payout,
    parse_handicap,
    settle_handicap,
)
from tests.golden_cases import GOLDEN_CASES


# Separate mathematical outcome table; do not import private implementation data.
EXPECTED_FRACTIONS = {
    "FW": (Fraction(1), Fraction(0), Fraction(0)),
    "HW": (Fraction(1, 2), Fraction(1, 2), Fraction(0)),
    "P": (Fraction(0), Fraction(1), Fraction(0)),
    "HL": (Fraction(0), Fraction(1, 2), Fraction(1, 2)),
    "FL": (Fraction(0), Fraction(0), Fraction(1)),
}
BAD_DECIMAL_TEXT = (
    "", " ", " 1.90", "1.90 ", "1.90\n", "NaN", "sNaN", "Infinity",
    "-Infinity", "inf", "1e2", "1E-2", "1/4", "1_000", "1,90", ".",
    "1.", "--1", "１２.５０",
)


class GoldenCaseTests(unittest.TestCase):
    def test_all_26_golden_cases(self):
        self.assertEqual(len(GOLDEN_CASES), 26)
        self.assertEqual(len({case.case_id for case in GOLDEN_CASES}), 26)
        for case in GOLDEN_CASES:
            with self.subTest(case=case.case_id):
                result = settle_handicap(
                    case.home, case.away, case.side, case.handicap_q
                )
                self.assertEqual(result.outcome.value, case.outcome)
                self.assertEqual(
                    (result.win, result.refund, result.loss),
                    EXPECTED_FRACTIONS[case.outcome],
                )
                payout = calculate_payout(result, decimal_odds=case.odds)
                self.assertEqual(payout.net, Fraction(case.net))
                self.assertEqual(payout.gross, Fraction(1) + Fraction(case.net))

    def test_approved_boundary_corrections_for_both_sides(self):
        # Selected margin, line, outcome: independently worked boundary cases.
        boundaries = (
            (-1, 3, Outcome.HALF_LOSS),
            (1, 4, Outcome.FULL_WIN),
            (1, -3, Outcome.HALF_WIN),
            (1, -5, Outcome.HALF_LOSS),
        )
        for margin, q, expected in boundaries:
            selected, opponent = (1, 0) if margin == 1 else (0, 1)
            for side in ("home", "away"):
                home, away = (
                    (selected, opponent) if side == "home" else (opponent, selected)
                )
                with self.subTest(margin=margin, q=q, side=side):
                    self.assertEqual(
                        settle_handicap(home, away, side, q).outcome, expected
                    )

    def test_negative_quarter_split_examples(self):
        # Explicit draw/one-goal boundaries catch signed-rounding mistakes.
        examples = (
            (0, -1, Outcome.HALF_LOSS),
            (1, -3, Outcome.HALF_WIN),
            (1, -5, Outcome.HALF_LOSS),
            (2, -7, Outcome.HALF_WIN),
        )
        for margin, q, outcome in examples:
            with self.subTest(q=q):
                self.assertEqual(
                    settle_handicap(margin, 0, "home", q).outcome, outcome
                )


class ExactPayoutTests(unittest.TestCase):
    def test_100_stake_returns_for_all_five_outcomes(self):
        cases = (
            ((1, 0, "home", 0), 90, 190),
            ((0, 0, "home", 1), 45, 145),
            ((0, 0, "home", 0), 0, 100),
            ((0, 0, "home", -1), -50, 50),
            ((0, 1, "home", 0), -100, 0),
        )
        for inputs, net, gross in cases:
            with self.subTest(inputs=inputs):
                result = calculate_payout(
                    settle_handicap(*inputs), decimal_odds="1.90", stake="100"
                )
                self.assertEqual(result.net, Fraction(net))
                self.assertEqual(result.gross, Fraction(gross))
                self.assertEqual(result.net_per_unit, Fraction(net, 100))
                self.assertEqual(result.gross_per_unit, Fraction(gross, 100))

    def test_tiny_stake_half_win_is_not_rounded(self):
        result = calculate_payout(
            settle_handicap(0, 0, "home", 1),
            decimal_odds="1.90",
            stake="0.01",
        )
        self.assertEqual(result.net, Fraction("0.0045"))
        self.assertEqual(result.gross, Fraction("0.0145"))

    def test_default_stake_is_one(self):
        result = calculate_payout(
            settle_handicap(1, 0, "home", 0), decimal_odds="1.90"
        )
        self.assertEqual(result.stake, Fraction(1))
        self.assertEqual(result.odds, Fraction(19, 10))

    def test_odds_change_returns_without_changing_settlement(self):
        settlement = settle_handicap(0, 0, "home", 1)
        before = (settlement.outcome, settlement.win, settlement.refund, settlement.loss)
        for odds, expected in (("1.80", "0.40"), ("1.90", "0.45"), ("2.20", "0.60")):
            with self.subTest(odds=odds):
                self.assertEqual(
                    calculate_payout(settlement, decimal_odds=odds).net,
                    Fraction(expected),
                )
                self.assertEqual(
                    (settlement.outcome, settlement.win, settlement.refund, settlement.loss),
                    before,
                )

    def test_exact_precision_is_independent_of_decimal_context(self):
        with localcontext() as context:
            context.prec = 2
            result = calculate_payout(
                settle_handicap(1, 0, "home", 0),
                decimal_odds="1." + "0" * 40 + "1",
                stake="100",
            )
        self.assertEqual(result.net, Fraction(100, 10**41))
        self.assertEqual(result.gross, Fraction(100) + Fraction(100, 10**41))

    def test_linear_stake_scaling(self):
        for outcome in Outcome:
            unit = calculate_payout(Settlement(outcome), decimal_odds="2.20")
            for stake in ("0.01", "2.5", "100"):
                with self.subTest(outcome=outcome, stake=stake):
                    scaled = calculate_payout(
                        Settlement(outcome), decimal_odds="2.20", stake=stake
                    )
                    self.assertEqual(scaled.net, unit.net * Fraction(stake))
                    self.assertEqual(scaled.gross, unit.gross * Fraction(stake))

    def test_results_are_immutable(self):
        settlement = settle_handicap(0, 0, "home", 1)
        payout = calculate_payout(settlement, decimal_odds="1.90")
        for result, field in ((settlement, "outcome"), (settlement, "win"), (payout, "net")):
            with self.subTest(field=field):
                with self.assertRaises(FrozenInstanceError):
                    setattr(result, field, None)

    def test_all_return_fields_are_exact_fractions(self):
        settlement = settle_handicap(0, 0, "home", 1)
        payout = calculate_payout(settlement, decimal_odds="1.90", stake=".01")
        for value in (
            settlement.win, settlement.refund, settlement.loss,
            payout.odds, payout.stake, payout.net, payout.gross,
            payout.net_per_unit, payout.gross_per_unit,
        ):
            self.assertIsInstance(value, Fraction)


class HandicapParserTests(unittest.TestCase):
    def test_valid_exact_quarter_strings(self):
        cases = (
            ("0", 0), ("-0.00", 0), ("+.25", 1), ("-0.75", -3),
            ("+0.75", 3), ("1.00", 4), ("-1.25", -5), ("0001.50", 6),
            ("+2.25", 9), ("-2.25", -9),
        )
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(parse_handicap(text), expected)

    def test_large_handicap_does_not_round(self):
        text = "123456789012345678901234567890.25"
        self.assertEqual(parse_handicap(text), 4 * 123456789012345678901234567890 + 1)

    def test_nonquarter_increments_are_rejected(self):
        for text in ("0.1", "-.01", "0.249999999999999999999", "1.250000001"):
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, "multiple of 0.25"):
                    parse_handicap(text)

    def test_decimal_context_cannot_round_a_near_quarter_into_acceptance(self):
        with localcontext() as context:
            context.prec = 2
            with self.assertRaises(ValueError):
                parse_handicap("0.249999999999999999999")

    def test_nonstring_handicaps_are_rejected(self):
        for value in (True, 1, 0.25, Decimal("0.25"), Fraction(1, 4), None):
            with self.subTest(value=value):
                with self.assertRaisesRegex(TypeError, "decimal string"):
                    parse_handicap(value)

    def test_invalid_decimal_syntax_is_rejected(self):
        for text in BAD_DECIMAL_TEXT:
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, "finite plain decimal"):
                    parse_handicap(text)


class ValidationTests(unittest.TestCase):
    def test_goal_types_reject_bool_and_numeric_coercion(self):
        for value in (True, False, 1.0, "1", None, Fraction(1), Decimal("1")):
            for field in ("home_goals", "away_goals"):
                inputs = dict(home_goals=0, away_goals=0, side="home", handicap_q=0)
                inputs[field] = value
                with self.subTest(field=field, value=value):
                    with self.assertRaisesRegex(TypeError, field):
                        settle_handicap(**inputs)

    def test_negative_goals_are_rejected(self):
        for home, away in ((-1, 0), (0, -1), (-1, -1)):
            with self.subTest(home=home, away=away):
                with self.assertRaisesRegex(ValueError, "nonnegative"):
                    settle_handicap(home, away, "home", 0)

    def test_invalid_side_types_are_rejected(self):
        for side in (True, 1, None):
            with self.subTest(side=side):
                with self.assertRaisesRegex(TypeError, "side"):
                    settle_handicap(0, 0, side, 0)

    def test_invalid_side_values_are_rejected(self):
        for side in ("Home", "HOME", "draw", "", "home "):
            with self.subTest(side=side):
                with self.assertRaisesRegex(ValueError, "exactly 'home' or 'away'"):
                    settle_handicap(0, 0, side, 0)

    def test_handicap_q_types_are_rejected(self):
        for q in (True, False, 1.0, 0.25, "1", None, Fraction(1), Decimal("1")):
            with self.subTest(q=q):
                with self.assertRaisesRegex(TypeError, "handicap_q"):
                    settle_handicap(0, 0, "home", q)

    def test_odds_must_be_decimal_strings(self):
        settlement = settle_handicap(0, 0, "home", 0)
        for odds in (True, 2, 1.9, Decimal("1.90"), Fraction(19, 10), None):
            with self.subTest(odds=odds):
                with self.assertRaisesRegex(TypeError, "decimal_odds"):
                    calculate_payout(settlement, decimal_odds=odds)

    def test_odds_must_be_greater_than_one(self):
        settlement = settle_handicap(0, 0, "home", 0)
        for odds in ("1", "1.00", "0.99", "0", "-1"):
            with self.subTest(odds=odds):
                with self.assertRaisesRegex(ValueError, "greater than 1"):
                    calculate_payout(settlement, decimal_odds=odds)

    def test_invalid_odds_syntax_is_rejected(self):
        settlement = settle_handicap(0, 0, "home", 0)
        for odds in BAD_DECIMAL_TEXT:
            with self.subTest(odds=odds):
                with self.assertRaisesRegex(ValueError, "decimal_odds"):
                    calculate_payout(settlement, decimal_odds=odds)

    def test_stakes_must_be_positive(self):
        settlement = settle_handicap(0, 0, "home", 0)
        for stake in ("0", "-0.00", "-1"):
            with self.subTest(stake=stake):
                with self.assertRaisesRegex(ValueError, "greater than 0"):
                    calculate_payout(settlement, decimal_odds="1.90", stake=stake)

    def test_stake_types_are_not_coerced(self):
        settlement = settle_handicap(0, 0, "home", 0)
        for stake in (True, 100, 0.01, Decimal(".01"), Fraction(1, 100), None):
            with self.subTest(stake=stake):
                with self.assertRaisesRegex(TypeError, "stake"):
                    calculate_payout(settlement, decimal_odds="1.90", stake=stake)

    def test_invalid_stake_syntax_is_rejected(self):
        settlement = settle_handicap(0, 0, "home", 0)
        for stake in BAD_DECIMAL_TEXT:
            with self.subTest(stake=stake):
                with self.assertRaisesRegex(ValueError, "stake"):
                    calculate_payout(settlement, decimal_odds="1.90", stake=stake)

    def test_payout_requires_a_settlement(self):
        for value in (None, "HW", {}, Outcome.HALF_WIN):
            with self.subTest(value=value):
                with self.assertRaisesRegex(TypeError, "Settlement"):
                    calculate_payout(value, decimal_odds="1.90")

    def test_settlement_constructor_requires_an_enum(self):
        with self.assertRaisesRegex(TypeError, "Outcome"):
            Settlement("HW")


class SettlementInvariantTests(unittest.TestCase):
    def test_fraction_and_return_invariants_across_small_domain(self):
        # 1,800 settlements × 3 prices, independent of any generated expectations.
        for home, away, q, side in product(range(6), range(6), range(-12, 13), ("home", "away")):
            result = settle_handicap(home, away, side, q)
            with self.subTest(home=home, away=away, q=q, side=side):
                self.assertEqual(result.win + result.refund + result.loss, 1)
                self.assertTrue(all(0 <= f <= 1 for f in (result.win, result.refund, result.loss)))
                self.assertEqual(
                    (result.win, result.refund, result.loss),
                    EXPECTED_FRACTIONS[result.outcome.value],
                )
                for odds in ("1.01", "1.90", "2.20"):
                    payout = calculate_payout(result, decimal_odds=odds)
                    self.assertEqual(payout.net, payout.gross - 1)
                    self.assertGreaterEqual(payout.gross, 0)

    def test_switching_home_away_labels_preserves_selected_result(self):
        for home, away, q in product(range(6), range(6), range(-12, 13)):
            self.assertEqual(
                settle_handicap(home, away, "home", q),
                settle_handicap(away, home, "away", q),
            )

    def test_quarter_return_equals_two_half_component_returns(self):
        for home, away, q, side in product(range(5), range(5), range(-11, 12, 2), ("home", "away")):
            whole = settle_handicap(home, away, side, q)
            lower = settle_handicap(home, away, side, q - 1)
            upper = settle_handicap(home, away, side, q + 1)
            for odds in ("1.90", "2.20"):
                payout = calculate_payout(whole, decimal_odds=odds)
                first = calculate_payout(lower, decimal_odds=odds, stake="0.5")
                second = calculate_payout(upper, decimal_odds=odds, stake="0.5")
                self.assertEqual(payout.net, first.net + second.net)
                self.assertEqual(payout.gross, first.gross + second.gross)

    def test_reversing_side_and_line_reverses_fractions(self):
        inverse = {"FW": "FL", "HW": "HL", "P": "P", "HL": "HW", "FL": "FW"}
        for home, away, q in product(range(5), range(5), range(-12, 13)):
            first = settle_handicap(home, away, "home", q)
            second = settle_handicap(home, away, "away", -q)
            self.assertEqual(second.outcome.value, inverse[first.outcome.value])
            self.assertEqual((second.win, second.refund, second.loss), (first.loss, first.refund, first.win))
            self.assertEqual(
                calculate_payout(first, decimal_odds="2.00").net,
                -calculate_payout(second, decimal_odds="2.00").net,
            )

    def test_larger_handicap_cannot_reduce_payout(self):
        for home, away, side in product(range(5), range(5), ("home", "away")):
            previous = None
            for q in range(-12, 13):
                net = calculate_payout(
                    settle_handicap(home, away, side, q), decimal_odds="1.90"
                ).net
                if previous is not None:
                    self.assertGreaterEqual(net, previous)
                previous = net

    def test_adding_equal_goals_preserves_settlement(self):
        for home, away, q in product(range(5), range(5), range(-12, 13)):
            self.assertEqual(
                settle_handicap(home, away, "home", q),
                settle_handicap(home + 3, away + 3, "home", q),
            )

    def test_half_lines_have_no_refund_and_quarter_lines_no_full_push(self):
        for home, away, q in product(range(5), range(5), range(-12, 13)):
            result = settle_handicap(home, away, "home", q)
            if q % 4 == 2:
                self.assertEqual(result.refund, 0)
            elif q % 2:
                self.assertNotEqual(result.outcome, Outcome.PUSH)

    def test_large_integer_goals_and_lines_do_not_overflow(self):
        large = 10**50
        self.assertEqual(
            settle_handicap(large, 0, "home", -4 * large).outcome, Outcome.PUSH
        )
        self.assertEqual(
            settle_handicap(0, large, "home", 4 * large + 1).outcome, Outcome.HALF_WIN
        )


if __name__ == "__main__":
    unittest.main()

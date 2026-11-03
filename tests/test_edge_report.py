"""Independent numerical checks on invented demonstration inputs only."""
import math
import re
import unittest
from unittest.mock import patch

from premfootballbot.edge_report import render_report


def demo(**updates):
    return dict(dict(status="INVENTED_DEMONSTRATION", fixture_id="toy:demo",
                     home="Example Town", away="Example Albion", statistics={"Shots": "12 (invented)"},
                     home_rate=0, away_rate=0, side="home", handicap="+0.25", decimal_odds="2"), **updates)


def values(report, prefix):
    line = next(s for s in report.splitlines() if s.startswith(prefix))
    return tuple(float(x) for x in re.findall(r"[-+]?[0-9]+(?:\.[0-9]+)?(?:e[-+]?[0-9]+)?",
                                               line.removeprefix(prefix)))


class EdgeReportTests(unittest.TestCase):
    def test_deterministic_zero_rates_settlement(self):
        for line, expected in (("+0.5", (1, 0, 0, 0, 0)), ("+0.25", (0, 1, 0, 0, 0)),
                               ("0", (0, 0, 1, 0, 0)), ("-0.25", (0, 0, 0, 1, 0)),
                               ("-0.5", (0, 0, 0, 0, 1))):
            with self.subTest(line=line):
                out = render_report(demo(handicap=line))
                self.assertEqual(values(out, "AH probabilities:"), expected)
                self.assertEqual(values(out, "Expected net return per unit (retained estimate):"),
                                 (expected[0] + expected[1] / 2 - expected[3] / 2 - expected[4],))

    def test_1x2_and_selected_side_against_analytic_oracle(self):
        # Away scores exactly zero; home scores 0 with exp(-1), 1 with exp(-1).
        # Away +0.75 wins at 0-0, half loses at 1-0, full loses otherwise.
        out = render_report(demo(home_rate=1, side="away", handicap="+0.75", decimal_odds="3"))
        p = math.exp(-1)
        for got, expected in zip(values(out, "1X2 probabilities:"), (1-p, p, 0)):
            self.assertAlmostEqual(got, expected, places=9)
        for got, expected in zip(values(out, "AH probabilities:"), (p, 0, 0, p, 1-2*p)):
            self.assertAlmostEqual(got, expected, places=9)
        loss = 1 - 1.5*p
        self.assertAlmostEqual(values(out, "Model-implied fair decimal odds (retained mass):")[0],
                               1 + loss/p, places=9)
        self.assertAlmostEqual(values(out, "Expected net return per unit (retained estimate):")[0],
                               2*p - loss, places=9)
        self.assertIn("Verdict: DEMONSTRATION_POSITIVE_EV", out)

    def test_zero_ev_and_negative_ev(self):
        zero = render_report(demo(handicap="0"))
        self.assertIn("Break-even", zero)
        self.assertIn("Verdict: DEMONSTRATION_NON_POSITIVE_EV", zero)
        self.assertIn("Verdict: DEMONSTRATION_NON_POSITIVE_EV", render_report(demo(handicap="-0.25")))
        symmetric = render_report(demo(home_rate=1.2, away_rate=1.2, handicap="0"))
        self.assertIn("Break-even", symmetric)

    def test_mass_and_asymmetric_1x2_against_factorial_grid(self):
        rates = (2.4, 1.1)
        cells = [(h, a, math.exp(-sum(rates)) * rates[0]**h * rates[1]**a /
                  (math.factorial(h) * math.factorial(a)))
                 for h in range(36) for a in range(36)]
        expected = [math.fsum(p for h, a, p in cells if (h > a) - (h < a) == sign)
                    for sign in (1, 0, -1)]
        out = render_report(demo(home_rate=rates[0], away_rate=rates[1]))
        one_x_two = values(out, "1X2 probabilities:")
        for got, want in zip(one_x_two, expected):
            self.assertAlmostEqual(got, want, places=9)
        self.assertAlmostEqual(sum(one_x_two), sum(values(out, "AH probabilities:")), places=9)

    def test_missing_and_invalid_price(self):
        for odds in (None, "1", "-100", "NaN", "2e0", 2):
            with self.subTest(odds=odds):
                out = render_report(demo(decimal_odds=odds))
                self.assertIn("Verdict: INSUFFICIENT_DATA", out)
                self.assertNotIn("Expected net return per unit", out)
                self.assertIn("Model-implied fair", out)

    def test_bad_rates_and_handicaps(self):
        for change in ({"home_rate": float("nan")}, {"away_rate": float("inf")}, {"home_rate": -1},
                       {"home_rate": True}, {"handicap": "0.3"}, {"handicap": "-100"}, {"side": "draw"}):
            with self.subTest(change=change):
                self.assertIn("Verdict: INSUFFICIENT_DATA", render_report(demo(**change)))

    def test_goal_cap_and_excess_tail_fail_closed(self):
        out = render_report(demo(home_rate=2), max_goals=0)
        self.assertIn("Verdict: INSUFFICIENT_DATA", out)
        self.assertNotIn("Expected net return per unit", out)
        with patch("premfootballbot.edge_report.poisson_distribution") as dist:
            dist.return_value.mass.omitted_mass_bound = 0.01
            self.assertIn("Omitted mass exceeds", render_report(demo()))
            dist.return_value.asian_handicap.assert_not_called()

    def test_tail_can_make_ev_sign_unresolved(self):
        # At home rate 1 and home -0.5, near the break-even price omitted
        # wins can move a slightly negative retained estimate above zero.
        odds = f"{1 / (1-math.exp(-1)):.17f}"
        out = render_report(demo(home_rate=1, handicap="-0.5", decimal_odds=odds))
        self.assertIn("Verdict: INSUFFICIENT_DATA", out)

    def test_deterministic_labels_and_statistics_do_not_affect_rates(self):
        first = render_report(demo(statistics={"Shots": "12", "Corners": "4"}, source_reference="Invented book"))
        second = render_report(demo(statistics={"Corners": "4", "Shots": "12"}, source_reference="Invented book"))
        self.assertEqual(first, second)
        self.assertIn("caller supplied, unverified", first)
        self.assertIn("INVENTED DEMONSTRATION", first)
        self.assertEqual(values(first, "1X2 probabilities:"), (0, 1, 0))

    def test_reject_non_demo_and_postmatch_information(self):
        for change in ({"status": "REAL"}, {"fixture_id": "real:fixture"}, {"result": "2-1"},
                       {"observed_at_utc": "2027-01-01T12:00:00Z"},
                       {"observed_at_utc": "2027-01-01T12:00:01Z", "kickoff_utc": "2027-01-01T12:00:00Z"}):
            with self.subTest(change=change):
                out = render_report(demo(**change))
                self.assertIn("Verdict: INSUFFICIENT_DATA", out)
                self.assertNotIn("1X2 probabilities", out)

    def test_observation_labels_and_strict_time(self):
        data = demo(observed_at_utc="2027-01-01T11:59:00Z", kickoff_utc="2027-01-01T12:00:00Z")
        self.assertIn("Observation (caller supplied, unverified)", render_report(data))
        data["observed_at_utc"] = "2027-01-01T11:59:00"
        self.assertIn("Verdict: INSUFFICIENT_DATA", render_report(data))

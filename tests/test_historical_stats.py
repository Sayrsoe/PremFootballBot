"""Descriptive statistics checks against the existing pinned archives."""
import ast
from dataclasses import asdict, replace
from datetime import date, datetime
import inspect
import unittest
from unittest.mock import patch

from premfootballbot import historical_stats as stats
from premfootballbot.completed_epl import import_completed_epl
from tests.test_completed_epl import FIXTURE, inputs


class HistoricalStatsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archives = inputs()
        cls.license = (FIXTURE / "LICENSE.md").read_bytes()

    def report(self, **overrides):
        args = dict(inputs=self.archives, license_bytes=self.license,
                    home_team="arsenal", away_team="liverpool", season_start_year=2024,
                    analysis_date=date(2025, 4, 12))
        args.update(overrides)
        return stats.historical_report(**args)

    def test_first_two_arsenal_results_and_home_away_orientation(self):
        # Arsenal 2–0 Wolves on Aug 17 and Villa 0–2 Arsenal on Aug 24.
        report = self.report(analysis_date=date(2024, 8, 26), away_team="aston-villa")
        home = report.home
        self.assertEqual((home.overall.matches, home.overall.wins, home.overall.draws,
                          home.overall.losses, home.overall.points), (2, 2, 0, 0, 6))
        self.assertEqual((home.overall.goals_for, home.overall.goals_against,
                          home.overall.goal_difference, home.overall.goals_for_per_match), (4, 0, 4, 2))
        self.assertEqual((home.home.matches, home.home.goals_for, home.away.matches, home.away.goals_for),
                         (1, 2, 1, 2))
        villa_home = report.away.home
        self.assertEqual((villa_home.matches, villa_home.losses, villa_home.goals_for,
                          villa_home.goals_against, villa_home.goals_against_per_match), (1, 1, 0, 2, 2))
        self.assertEqual(home.status, "INSUFFICIENT_SAMPLE")

    def test_draw_arithmetic(self):
        # Forest's first eligible match ended 1–1 against Bournemouth.
        report = self.report(home_team="nottingham-forest", analysis_date=date(2024, 8, 19))
        self.assertEqual(report.home.overall, stats.Sample(1, 0, 1, 0, 1, 1, 1, 0, 1, 1))

    def test_recent_windows_and_result_only_table(self):
        report = self.report()
        windows = report.home.last_10
        self.assertEqual(len(windows), 10)
        self.assertEqual(report.home.last_5, windows[-5:])
        self.assertEqual(windows[-1].match_date, date(2025, 4, 5))
        self.assertEqual([r.match_date for r in windows], sorted(r.match_date for r in windows))
        self.assertEqual([(r.goals_for, r.goals_against) for r in windows],
                         [(2, 2), (1, 0), (5, 1), (2, 0), (0, 1),
                          (0, 0), (1, 1), (1, 0), (2, 1), (1, 1)])
        for result in windows:
            self.assertRegex(result.source_locator, r"/2024-25/1-premierleague\.txt#L[0-9]+$")
        table = dict(report.computed_historical_standings)
        self.assertEqual(table["arsenal"], report.home.overall)
        self.assertEqual(sum(row.matches for row in table.values()), 2 * report.included_matches)
        self.assertEqual(sum(row.goals_for for row in table.values()), sum(row.goals_against for row in table.values()))

    def test_cutoff_and_exclusion_counts(self):
        # Only Aug 16 qualifies on Aug 18. Six Aug 17 results and two
        # Aug 18 results lie around the embargo boundary.
        report = self.report(analysis_date=date(2024, 8, 18))
        self.assertEqual(report.eligible_through, date(2024, 8, 16))
        self.assertEqual(report.included_matches, 1)
        self.assertEqual(dict(report.exclusions), {"AFTER_ANALYSIS_DATE": 371, "DATE_EMBARGO": 8})
        self.assertEqual(report.last_eligible_date, date(2024, 8, 16))
        self.assertEqual(report.home.overall, stats.Sample(0))
        self.assertIsNone(report.home.overall.goals_for_per_match)
        self.assertEqual(self.report(analysis_date=date(2024, 8, 19)).included_matches, 7)

    def test_absent_club_and_promotion_within_selected_season(self):
        older = self.report(home_team="leeds")
        newer = self.report(home_team="leeds", season_start_year=2025, analysis_date=date(2026, 3, 1))
        self.assertEqual(older.home.status, "TEAM_ABSENT")
        self.assertIsNone(older.home.overall.points)
        self.assertEqual(newer.home.status, "AVAILABLE")
        self.assertGreater(newer.home.overall.matches, 5)
        self.assertEqual((older.minimum_matches, older.stale_after_days), (newer.minimum_matches, newer.stale_after_days))

    def test_future_season_provides_no_team_or_standings_information(self):
        report = self.report(home_team="leeds", season_start_year=2025)
        self.assertEqual(report.included_matches, 0)
        self.assertEqual(report.home.status, "INSUFFICIENT_SAMPLE")
        self.assertEqual(report.computed_historical_standings, ())
        self.assertIsNone(report.last_eligible_date)
        self.assertEqual(dict(report.exclusions)["AFTER_ANALYSIS_DATE"], 380)

    def test_reordered_input_archives_and_validated_rows(self):
        expected = self.report()
        self.assertEqual(self.report(inputs=self.archives[::-1]), expected)
        imported = import_completed_epl(self.archives, license_bytes=self.license)
        with patch.object(stats, "import_completed_epl", return_value=replace(imported, rows=imported.rows[::-1])):
            self.assertEqual(self.report(), expected)

    def test_source_gate_rejects_bad_bytes_and_missing_season(self):
        bad = replace(self.archives[0], raw_bytes=self.archives[0].raw_bytes[:-1])
        report = self.report(inputs=(bad, self.archives[1]))
        self.assertEqual((report.source_status, report.source_detail), ("INVALID_SOURCE_COVERAGE", "SOURCE_SHA256"))
        self.assertIsNone(report.home)
        self.assertIsNone(report.included_matches)
        self.assertEqual(self.report(inputs=self.archives[:1]).source_status, "UNSUPPORTED_SOURCE")
        self.assertEqual(self.report(license_bytes=b"wrong").source_detail, "LICENCE")
        self.assertEqual(self.report(season_start_year=2023).source_status, "UNSUPPORTED_SOURCE")

    def test_stale_november_archive_retains_descriptive_results(self):
        report = self.report(season_start_year=2025, analysis_date=date(2026, 11, 4))
        self.assertTrue(report.stale)
        self.assertTrue(report.home.stale)
        self.assertEqual(report.included_matches, 380)
        self.assertEqual(report.last_eligible_date.month, 5)
        age = (report.analysis_date - report.last_eligible_date).days
        self.assertFalse(self.report(season_start_year=2025, analysis_date=report.analysis_date,
                                     stale_after_days=age).stale)
        self.assertTrue(self.report(season_start_year=2025, analysis_date=report.analysis_date,
                                    stale_after_days=age - 1).stale)

    def test_assurance_and_isolation(self):
        report = self.report()
        self.assertEqual(report.evidence_status, "EXPLORATORY_DATE_LEVEL_RECONSTRUCTION")
        self.assertEqual(report.historical_availability, "UNVERIFIED")
        self.assertEqual(report.purpose, "RETROSPECTIVE_DESCRIPTIVE_ONLY")
        self.assertFalse(report.strict_point_in_time_eligible)
        self.assertIsNone(report.historical_available_at)
        self.assertIsNone(report.kickoff_utc)
        self.assertEqual(report.licence, "CC0-1.0")
        self.assertEqual(report.source_commit, "9ee7a0c351805c99cc334478a9bf04b7d0432fec")
        forbidden = {"xg", "shots", "possession", "injuries", "lineups", "probabilities", "odds"}
        self.assertFalse(forbidden & asdict(report).keys())
        self.assertFalse(forbidden & asdict(report.home.overall).keys())
        imports = {node.module for node in ast.walk(ast.parse(inspect.getsource(stats)))
                   if isinstance(node, ast.ImportFrom)}
        self.assertEqual(imports, {"__future__", "dataclasses", "datetime", "typing",
                                   "completed_epl", "openfootball_exploratory"})

    def test_invalid_policy_and_implicit_timestamps_rejected(self):
        for args in (dict(analysis_date=datetime(2025, 4, 12)), dict(embargo_days=1),
                     dict(minimum_matches=True), dict(stale_after_days=1)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.report(**args)

import ast
from datetime import date
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

from dashboard.services import ARCHIVE, load_report, report_statuses


class DashboardServicesTests(unittest.TestCase):
    def report(self, when=date(2025, 4, 12), season=2024, home="arsenal", **kwargs):
        return load_report(home, "liverpool", season, when, **kwargs)

    def test_selected_season_teams_and_assurance(self):
        result = self.report()
        self.assertEqual((result.home.team_id, result.away.team_id), ("arsenal", "liverpool"))
        self.assertEqual((result.source_path, result.included_matches), ("2024-25/1-premierleague.txt", 309))
        self.assertEqual(report_statuses(result), ("HISTORICAL_DATA_AVAILABLE",))
        self.assertFalse(result.strict_point_in_time_eligible)
        self.assertIsNone(result.kickoff_utc)
        self.assertEqual(result.historical_availability, "UNVERIFIED")

    def test_stale_absent_empty_and_unsupported_source(self):
        stale = self.report(date(2026, 11, 5), 2025)
        self.assertIn("STALE_HISTORICAL_DATA", report_statuses(stale))
        self.assertEqual(stale.included_matches, 380)
        self.assertIn("TEAM_ABSENT", report_statuses(self.report(home="leeds")))
        self.assertIn("INSUFFICIENT_SAMPLE", report_statuses(self.report(date(2024, 8, 1))))
        self.assertEqual(report_statuses(self.report(season=2026)), ("SOURCE_INVALID",))

    def test_content_key_detects_tampering_even_on_same_query(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            for path in ARCHIVE.iterdir():
                if path.is_file():
                    shutil.copyfile(path, folder / path.name)
            before = {p.name: p.read_bytes() for p in folder.iterdir()}
            self.assertEqual(self.report(folder=folder).included_matches, 309)
            self.assertEqual({p.name: p.read_bytes() for p in folder.iterdir()}, before)
            (folder / "2025-26.txt").write_bytes(b"changed")
            invalid = self.report(folder=folder)
            self.assertEqual(report_statuses(invalid), ("SOURCE_INVALID",))
            self.assertIsNone(invalid.home)
            (folder / "SOURCES.json").unlink()
            self.assertEqual(self.report(folder=folder).source_detail, "ARCHIVE_LOAD_FAILED")

    def test_cache_separates_team_and_date(self):
        self.assertEqual(self.report(home="chelsea").home.team_id, "chelsea")
        self.assertEqual(self.report(date(2024, 8, 18)).included_matches, 1)

    def test_isolated_imports(self):
        root = ARCHIVE.parents[2]
        expected = {
            "dashboard/app.py": {"dataclasses", "datetime", "html", "streamlit",
                                 "dashboard.services", "premfootballbot.manual_notebook"},
            "dashboard/services.py": {"datetime", "functools", "json", "pathlib",
                                      "premfootballbot.completed_epl", "premfootballbot.historical_stats",
                                      "premfootballbot.openfootball_exploratory"},
            "premfootballbot/manual_notebook.py": {"contextlib", "dataclasses", "datetime", "os", "pathlib",
                                                    "re", "sqlite3", "uuid", "odds_observations", "settlement"},
        }
        for file, allowed in expected.items():
            tree = ast.parse((root / file).read_text(encoding="utf-8"))
            modules = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
            modules.update(a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names)
            self.assertLessEqual(modules, allowed)

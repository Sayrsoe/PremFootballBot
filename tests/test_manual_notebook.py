from contextlib import closing
from datetime import date
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from premfootballbot.manual_notebook import Notebook, NotebookError, ROOT

CAPTURE = "2026-11-05T13:00:00.000000Z"


class NotebookTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "notes.sqlite3"
        self.notebook = Notebook(self.path)
        clock = patch("premfootballbot.manual_notebook._now", return_value=CAPTURE)
        clock.start()
        self.addCleanup(clock.stop)

    def fixture(self, **changes):
        args = dict(home="Arsenal", away="Liverpool", season=2026, match_date=date(2026, 11, 5))
        return self.notebook.save_fixture(**(args | changes))

    def quote(self, **changes):
        args = dict(bookmaker="Invented Example", side="AWAY", line="+0.25", odds="1.950",
                    invented=True)
        return self.notebook.save_observation(self.notebook.fixtures()[0], **(args | changes))

    def test_fixture_persists_and_duplicate_identity_is_stable(self):
        identity = self.fixture()
        self.assertEqual(self.fixture(home="arsenal", away="LIVERPOOL"), identity)
        self.assertEqual(self.fixture(kickoff="2026-11-05T20:00:00Z"), identity)
        row, = Notebook(self.path).fixtures()
        self.assertEqual((row.id, row.revision, row.home, row.away, row.kickoff),
                         (identity, 1, "arsenal", "liverpool", ""))

    def test_invalid_fixture_inputs(self):
        for changes in ({"away": "ARSENAL"}, {"season": 2025},
                        {"kickoff": "2026-11-06T12:00:00Z"}, {"home": "a'); DROP TABLE fixtures;--"}):
            with self.subTest(changes=changes), self.assertRaises(NotebookError):
                self.fixture(**changes)

    def test_exact_price_quarters_and_reopen(self):
        fixture = self.fixture()
        for line, quarter in (("-0.75", -3), ("-0.25", -1), ("+0.25", 1), ("+0.75", 3)):
            identity = self.quote(line=line)
            self.assertEqual(self.quote(line=line, odds="1.95"), identity)
            row = Notebook(self.path).observations(fixture)[0]
            self.assertEqual((row["raw_odds"], row["exact_odds"], row["quarters"]), ("1.950", "39/20", quarter))
            self.assertEqual((row["claimed"], row["captured"], row["timing"]), ("", CAPTURE, "TIMING_UNKNOWN"))
            self.assertEqual(row["format"], "MANUAL_UNVERIFIED")
            self.assertEqual(row["assurance"], "MANUAL_ODDS_UNVERIFIED")
        self.assertEqual(Notebook(self.path).fixtures()[0].observation_count, 4)

    def test_invalid_prices_lines_and_times_leave_database_unchanged(self):
        fixture = self.fixture()
        for changes in ({"line": "0.3"}, {"line": "100"}, {"odds": "1"}, {"odds": "NaN"},
                        {"odds": "1e1"}, {"odds": 2}, {"claimed": "2026-11-05T14:00:00Z"}):
            with self.subTest(changes=changes), self.assertRaises(NotebookError):
                self.quote(**changes)
        self.assertEqual(self.notebook.observations(fixture), ())

    def test_capture_at_kickoff_is_late_even_with_earlier_claim(self):
        fixture = self.fixture(kickoff="2026-11-05T13:00:00Z")
        self.quote(claimed="2026-11-05T12:00:00Z")
        row, = self.notebook.observations(fixture)
        self.assertEqual(row["timing"], "LATE_FOR_PREMATCH_RESEARCH")
        self.assertEqual(row["claimed"], "2026-11-05T12:00:00.000000Z")

    def test_corrections_preserve_quote_and_fixture_history(self):
        identity = self.fixture(kickoff="2026-11-05T15:00:00Z")
        first = self.quote()
        second = self.quote(odds="2", replaces=first)
        self.assertEqual(self.quote(odds="2", replaces=first), second)
        original = self.notebook.fixtures()[0]
        self.fixture(kickoff="2026-11-05T12:00:00Z", previous=original)
        latest, = self.notebook.fixtures()
        self.assertEqual((latest.id, latest.revision, latest.observation_count), (identity, 2, 2))
        rows = self.notebook.observations(identity)
        self.assertEqual([r["revision"] for r in rows], [1, 1])
        self.assertEqual([r["timing"] for r in rows], ["BEFORE_CLAIMED_KICKOFF_UNVERIFIED"] * 2)
        self.assertEqual((rows[0]["replaces"], rows[1]["superseded"]), (first, 1))
        with self.assertRaises(NotebookError):
            self.notebook.save_observation(original, bookmaker="X", side="HOME", line="0", odds="2")

    def test_conflicting_fixture_correction_rolls_back(self):
        first = self.fixture()
        other = self.fixture(home="Chelsea")
        fixture = next(f for f in self.notebook.fixtures() if f.id == other)
        with self.assertRaises(NotebookError):
            self.fixture(previous=fixture)
        self.assertEqual({f.id for f in self.notebook.fixtures()}, {first, other})

    def test_parameterized_input_and_corrupt_database_handling(self):
        identity = self.fixture()
        text = "O'Brien'); DROP TABLE fixtures; --"
        self.quote(bookmaker=text)
        self.assertEqual(self.notebook.observations(identity)[0]["bookmaker"], text)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE observations SET exact_odds = 'broken'")
        with self.assertRaisesRegex(NotebookError, "invalid observation"):
            self.notebook.observations(identity)
        invalid = self.path.with_name("invalid.sqlite3")
        invalid.write_bytes(b"bad SQLite file")
        with self.assertRaises(NotebookError):
            Notebook(invalid).fixtures()
        self.assertEqual(invalid.read_bytes(), b"bad SQLite file")

    def test_repository_paths_are_refused_before_opening(self):
        with self.assertRaisesRegex(NotebookError, "outside the repository"):
            Notebook(ROOT / "tests" / "fixtures" / "completed_epl" / "notebook.sqlite3")

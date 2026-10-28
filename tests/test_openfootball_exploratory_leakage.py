"""Independent adversarial boundary tests; every match score here is invented."""
from dataclasses import replace
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from premfootballbot.openfootball_exploratory import (
    OpenFootballError, parse_openfootball_epl, select_exploratory_prior_dates,
    summarize_exploratory_coverage, exploratory_json,
)
from premfootballbot.match_data import parse_synthetic_json
from premfootballbot.backtesting import BacktestError, parse_target_manifest, generate_forecasts
from premfootballbot.expected_goals import ExpectedGoalsError, fit_expected_goals, fit_rate_ratio
from tests.test_openfootball_exploratory import parse, invented, source_for
from tests.match_data_cases import document, encode
from tests.backtesting_cases import targets, manifest, batch

BODY = ("Aug 11\nArsenal FC 1-0 Chelsea FC\n"
        "Aug 12\nLiverpool FC 2-0 Fulham FC\n"
        "Aug 13\nBrentford FC 0-0 Burnley FC\n"
        "Aug 14\nEverton FC 0-1 Luton Town FC\n")


class ExploratoryLeakageTests(unittest.TestCase):
    def test_embargo_d_minus_two_candidate_only(self):
        result = select_exploratory_prior_dates(parse(BODY), date(2023, 8, 13))
        self.assertEqual([r.match_date for r in result.rows], [date(2023, 8, 11)])
        self.assertFalse(result.strict_point_in_time_eligible)
        self.assertIn("NOT observed availability", result.policy)
        self.assertIn("EXPLORATORY_DATE_LEVEL_RECONSTRUCTION", exploratory_json(result).decode())

    def test_same_previous_day_and_future_excluded(self):
        result = select_exploratory_prior_dates(parse(BODY), date(2023, 8, 12))
        self.assertFalse(result.rows)

    def test_no_embargo_override_below_two_or_bool(self):
        for bad in (-1, 0, 1, True, 2.0, "2", 10**100):
            with self.subTest(bad=bad), self.assertRaises(OpenFootballError) as caught:
                select_exploratory_prior_dates(parse(BODY), date(2023, 8, 13), embargo_calendar_days=bad)
            self.assertEqual(caught.exception.code, "EMBARGO")

    def test_unknown_target_and_calendar_underflow_fail(self):
        for target in (None, "2023-08-13", datetime(2023, 8, 13), date.min):
            with self.subTest(target=target), self.assertRaises(OpenFootballError) as caught:
                select_exploratory_prior_dates(parse(BODY), target)
            self.assertEqual(caught.exception.code, "TARGET_DATE")

    def test_target_identity_self_excluded_even_if_wrong_caller_date(self):
        imported = parse(BODY)
        result = select_exploratory_prior_dates(imported, date(2023, 8, 20), target_fixture_id=imported.rows[0].fixture_id)
        self.assertNotIn(imported.rows[0].fixture_id, {r.fixture_id for r in result.rows})
        with self.assertRaises(OpenFootballError):
            select_exploratory_prior_dates(imported, date(2023, 8, 20), target_fixture_id="synthetic:fake")

    def test_future_append_changes_full_hash_but_candidate_bytes_identical(self):
        a = parse("Aug 11\nArsenal FC 1-0 Chelsea FC\n")
        b = parse(BODY + "May 19\nManchester City FC 99-0 West Ham United FC\n")
        self.assertNotEqual(a.source.expected_sha256, b.source.expected_sha256)
        self.assertNotEqual(a.sha256, b.sha256)
        before = select_exploratory_prior_dates(a, date(2023, 8, 13))
        after = select_exploratory_prior_dates(b, date(2023, 8, 13))
        self.assertEqual(before, after)
        self.assertEqual(exploratory_json(before), exploratory_json(after))

    def test_future_score_poison_does_not_affect_candidates(self):
        a = select_exploratory_prior_dates(parse(BODY), date(2023, 8, 13))
        b = select_exploratory_prior_dates(parse(BODY.replace("Liverpool FC 2-0", "Liverpool FC 99-98")), date(2023, 8, 13))
        self.assertEqual(a, b)

    def test_row_reordering_preserves_candidate_list_and_digest(self):
        body = "Aug 11\nArsenal FC 1-0 Chelsea FC\nJan 1\nLiverpool FC 2-0 Fulham FC\n"
        reverse = "Jan 1\nLiverpool FC 2-0 Fulham FC\nAug 11\nArsenal FC 1-0 Chelsea FC\n"
        self.assertEqual(select_exploratory_prior_dates(parse(body), date(2024, 1, 3)),
                         select_exploratory_prior_dates(parse(reverse), date(2024, 1, 3)))

    def test_retrieval_and_new_commit_do_not_impute_old_availability(self):
        raw = invented(BODY)
        src = source_for(raw)
        later = replace(src, retrieved_at_utc=datetime(2099, 1, 1, tzinfo=timezone.utc),
                        repository_commit_sha="a" * 40,
                        licence_evidence_url=src.licence_evidence_url.replace(src.repository_commit_sha, "a" * 40))
        a = parse_openfootball_epl(raw, source=src)
        b = parse_openfootball_epl(raw, source=later)
        self.assertNotEqual(a.sha256, b.sha256)
        self.assertEqual(select_exploratory_prior_dates(a, date(2023, 8, 13)),
                         select_exploratory_prior_dates(b, date(2023, 8, 13)))
        for r in b.rows:
            self.assertIsNone(r.kickoff_utc)
            self.assertIsNone(r.historical_available_at)
            self.assertEqual(r.clock_timezone_status, "UNKNOWN")
            self.assertFalse(r.strict_point_in_time_eligible)
            self.assertFalse(hasattr(r, "available_at_utc"))
            self.assertFalse(hasattr(r, "is_synthetic"))

    def test_conflicting_past_fixture_is_invalidated_not_silently_updated(self):
        imported = parse(BODY + "Aug 20\nArsenal FC 2-0 Chelsea FC\n")
        self.assertFalse(select_exploratory_prior_dates(imported, date(2023, 8, 13)).rows)
        self.assertIn("REPEATED_PAIR_IDENTITY", {q.reason for q in imported.quarantined})

    def test_unknown_other_season_rows_not_accepted(self):
        value = parse(BODY + "Aug 11 2025\nManchester City FC 2-0 West Ham United FC\n")
        self.assertEqual(value.quarantined[-1].reason, "SEASON_DATE")
        self.assertEqual(select_exploratory_prior_dates(value, date(2023, 8, 13)),
                         select_exploratory_prior_dates(parse(BODY), date(2023, 8, 13)))

    def test_strict_synthetic_import_rejects_real_source(self):
        payload = document()
        payload["namespace"] = "openfootball:epl"
        self.assertFalse(parse_synthetic_json(encode(payload)).valid)
        payload = document()
        payload["source_documents"][0]["is_synthetic"] = False
        self.assertFalse(parse_synthetic_json(encode(payload)).valid)
        payload = document()
        payload["records"][0]["is_synthetic"] = False
        self.assertFalse(parse_synthetic_json(encode(payload)).valid)
        raw = exploratory_json(parse(BODY))
        self.assertFalse(parse_synthetic_json(raw).valid)

    def test_strict_target_manifest_rejects_real_namespace_and_flag(self):
        for field, value in (("namespace", "openfootball:epl"), ("is_synthetic", False)):
            payload = targets()
            payload[field] = value
            with self.assertRaises(BacktestError):
                parse_target_manifest(json.dumps(payload).encode())

    def test_fitting_functions_reject_new_real_dataclasses(self):
        imported = parse(BODY)
        for fitting in (fit_expected_goals, fit_rate_ratio):
            for data in (imported, imported.rows[0], select_exploratory_prior_dates(imported, date(2023, 8, 13))):
                with self.subTest(fitting=fitting.__name__, type=type(data)), self.assertRaises(ExpectedGoalsError):
                    fitting(data, datetime(2023, 8, 13, tzinfo=timezone.utc))

    def test_synthetic_backtester_rejects_adapter_input_without_calling_fitter(self):
        with patch("premfootballbot.backtesting.fit_expected_goals") as fitter:
            with self.assertRaises(BacktestError):
                generate_forecasts(parse(BODY), manifest())
            fitter.assert_not_called()
        with self.assertRaises(BacktestError):
            generate_forecasts(batch(), parse(BODY))

    def test_no_adapter_dependency_on_synthetic_or_io_modules(self):
        import ast
        module_path = Path(__file__).parents[1] / "premfootballbot" / "openfootball_exploratory.py"
        tree = ast.parse(module_path.read_text(encoding="utf8"))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(n.name for n in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.assertNotIn(node.func.attr, ("now", "utcnow", "today", "read_bytes", "write_bytes", "urlopen"))
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotEqual(node.func.id, "open")
        self.assertLessEqual(imports, {"__future__", "collections", "dataclasses", "datetime", "hashlib", "json", "re"})
        with patch("socket.socket", side_effect=AssertionError("network forbidden")):
            imported = parse(BODY)
            summarize_exploratory_coverage(imported)

    def test_snapshot_tamper_cannot_change_candidates(self):
        value = parse(BODY)
        changed_row = replace(value.rows[0], match_date=date(2020, 1, 1), home_goals_ft90=99)
        with self.assertRaises(OpenFootballError) as caught:
            select_exploratory_prior_dates(replace(value, rows=(changed_row,)), date(2023, 8, 13))
        self.assertEqual(caught.exception.code, "SNAPSHOT_TAMPERED")

    def test_protected_source_fingerprints_remain_frozen(self):
        # Baseline main272ad046; normalize only checkout line endings for Windows.
        expected = {
            "backtesting.py": "733b4a6cb4f167635c4fda14bcf4dc561352d9fa8a8f672b9f3aa902ca490882",
            "expected_goals.py": "3b68aa595848795a1c9948b06ba921d7dca7859c5aa7ad5d33281d8ae3d69b1a",
            "match_data.py": "fef3fa129a51fe804c5ddfa0791cd284461a8f5c14bb6beda685709f73d34861",
            "poisson.py": "e07157a230986841309d9feb650029a4ca5776a84e92376566de0f859b06be93",
            "settlement.py": "31b0fabe952b427045efd95088d62ccb50d129b86368138aa2eff08b4b5d3438",
            "__init__.py": "e12238125aa503254b57998daec06339d618949803978ef2665af88e5f58b9a1",
        }
        for name, digest in expected.items():
            content = (Path(__file__).parents[1] / "premfootballbot" / name).read_bytes().replace(b"\r\n", b"\n")
            self.assertEqual(hashlib.sha256(content).hexdigest(), digest, name)


if __name__ == "__main__":
    unittest.main()

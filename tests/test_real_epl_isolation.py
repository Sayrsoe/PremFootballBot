"""Adversarial real/synthetic, temporal, coverage and module boundary checks."""
import ast
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from premfootballbot import real_epl_training as rt
from premfootballbot import openfootball_exploratory as adapter
from premfootballbot.match_data import parse_synthetic_json
from premfootballbot.expected_goals import ExpectedGoalsError, fit_expected_goals, fit_rate_ratio
from premfootballbot.backtesting import BacktestError, generate_forecasts, parse_target_manifest
from premfootballbot.prospective_evidence import EvidenceError, freeze_packet
from tests.backtesting_cases import manifest, batch
from tests.test_real_epl_training import inputs, fit


class RealIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw, cls.source, cls.license_bytes = inputs()
        cls.model = fit()

    def test_synthetic_importer_rejects_real_artifact_json(self):
        self.assertFalse(parse_synthetic_json(rt.retrospective_json(self.model)).valid)

    def test_synthetic_fitters_reject_model_and_real_import(self):
        for fitting in (fit_expected_goals, fit_rate_ratio):
            for value in (self.model, self.model.source_import, self.model.source_import.rows[0]):
                with self.subTest(fitting=fitting.__name__, value=type(value)), self.assertRaises(ExpectedGoalsError):
                    fitting(value, datetime(2026, 1, 1, tzinfo=timezone.utc))

    def test_synthetic_backtest_rejects_real_input_before_fit(self):
        with patch("premfootballbot.backtesting.fit_expected_goals") as fitter:
            with self.assertRaises(BacktestError):
                generate_forecasts(self.model, manifest())
            fitter.assert_not_called()
        with self.assertRaises(BacktestError):
            parse_target_manifest(rt.retrospective_json(self.model))

    def test_real_trainer_rejects_synthetic_batch(self):
        with self.assertRaises(rt.RealTrainingError) as caught:
            rt.fit_real_epl(batch(), source=self.source, license_bytes=self.license_bytes)
        self.assertEqual(caught.exception.code, "INPUT_TYPE")

    def test_real_trainer_never_calls_synthetic_pipeline(self):
        with patch("premfootballbot.expected_goals.fit_expected_goals", side_effect=AssertionError), \
             patch("premfootballbot.match_data.parse_synthetic_json", side_effect=AssertionError), \
             patch("premfootballbot.backtesting.generate_forecasts", side_effect=AssertionError):
            self.assertEqual(fit().sha256, self.model.sha256)

    def test_no_cutoff_target_or_prediction_api(self):
        for keyword in ("cutoff_utc", "target_fixture_id", "target_kickoff_utc", "training_end_date"):
            with self.assertRaises(TypeError):
                fit(**{keyword: "2023-01-01"})
        for name in ("predict", "predict_expected_goals", "probabilities", "backtest"):
            self.assertFalse(hasattr(rt, name))
            self.assertFalse(hasattr(self.model, name))

    def test_artifact_cannot_be_frozen_as_prospective_packet(self):
        with self.assertRaises(EvidenceError):
            freeze_packet(rt.retrospective_json(self.model))

    def test_serialized_retrospective_labels_and_no_accuracy_metrics(self):
        payload = json.loads(rt.retrospective_json(self.model))
        self.assertEqual(payload["status"], "RETROSPECTIVE_DESCRIPTIVE_ONLY")
        self.assertFalse(payload["strict_point_in_time_eligible"])
        self.assertIsNone(payload["historical_available_at"])
        self.assertNotIn("accuracy", payload["diagnostics"])
        self.assertNotIn("roi", payload["diagnostics"])
        self.assertNotIn("predictions", payload)

    def test_pure_runtime_with_network_and_file_access_denied(self):
        with patch("socket.socket", side_effect=AssertionError("network")), \
             patch("builtins.open", side_effect=AssertionError("filesystem")), \
             patch.object(Path, "read_bytes", side_effect=AssertionError("filesystem")):
            model = rt.fit_real_epl(self.raw, source=self.source, license_bytes=self.license_bytes)
            self.assertEqual(model.sha256, self.model.sha256)

    def test_imports_are_restricted_and_no_clock_or_publication_calls(self):
        source = Path(rt.__file__).read_text(encoding="utf8")
        imports = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imports.update(n.name for n in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module)
            elif isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                self.assertNotIn(name, {"now", "utcnow", "today", "open", "read_bytes", "write_bytes", "urlopen", "eval", "exec"})
        self.assertLessEqual(imports, {"__future__", "collections", "dataclasses", "datetime", "hashlib",
                                       "json", "math", "sys", "openfootball_exploratory"})

    def coverage_rejects(self, imported, code):
        # Simulate a future parser regression; public API still pins original raw bytes.
        imported = adapter._seal(imported)
        with patch.object(rt, "parse_openfootball_epl", return_value=imported), self.assertRaises(rt.RealTrainingError) as caught:
            rt.fit_real_epl(self.raw, source=self.source, license_bytes=self.license_bytes)
        self.assertEqual(caught.exception.code, code)

    def test_missing_result_is_not_imputed(self):
        imported = self.model.source_import
        self.coverage_rejects(replace(imported, rows=imported.rows[:-1]), "TRAINING_COVERAGE")

    def test_quarantined_result_is_not_silently_dropped(self):
        imported = self.model.source_import
        row = imported.rows[0]
        quarantine = adapter.QuarantinedRow(row.source_line_number, row.raw_row, "TEAM_IDENTITY", None, None, None)
        self.coverage_rejects(replace(imported, quarantined=(quarantine,)), "TRAINING_COVERAGE")

    def test_header_issue_is_not_silently_dropped(self):
        imported = self.model.source_import
        issue = adapter.QuarantinedRow(1, "unknown", "MISSING_DATE", None, None, None)
        self.coverage_rejects(replace(imported, header_issues=(issue,)), "TRAINING_COVERAGE")

    def test_contradictory_pair_coverage_rejected(self):
        imported = self.model.source_import
        self.coverage_rejects(replace(imported, rows=imported.rows[:-1] + (imported.rows[0],)), "TRAINING_COVERAGE")

    def test_parser_cannot_certify_historical_availability(self):
        imported = self.model.source_import
        row = replace(imported.rows[0], strict_point_in_time_eligible=True,
                      historical_available_at=datetime(2023, 1, 1, tzinfo=timezone.utc))
        self.coverage_rejects(replace(imported, rows=(row,) + imported.rows[1:]), "TRAINING_METADATA")

    def test_resealed_normalized_score_tamper_fails_replay(self):
        imported = self.model.source_import
        row = replace(imported.rows[0], home_goals_ft90=99)
        changed = replace(self.model, source_import=adapter._seal(replace(imported, rows=(row,) + imported.rows[1:])))
        changed = replace(changed, sha256=rt._digest(changed))
        with self.assertRaises(rt.RealTrainingError) as caught:
            rt.verify_retrospective_fit(changed, self.raw, license_bytes=self.license_bytes)
        self.assertEqual(caught.exception.code, "REPLAY_MISMATCH")

    def test_parser_and_prospective_source_fingerprints_unchanged(self):
        # Other six protected modules are already hash-locked in the existing tests.
        expected = {
            "openfootball_exploratory.py": "6c1ec7d4b1bccf8d7b9810eab0e41a4b4b8788d8b5486df1229495538daf9b2d",
            "prospective_evidence.py": "fba21fc4ef5341c41fa5679d2b598baa7f3913b832f319bb904a7aee94e324fa",
        }
        for name, sha in expected.items():
            raw = (Path(rt.__file__).parent / name).read_bytes().replace(b"\r\n", b"\n")
            self.assertEqual(hashlib.sha256(raw).hexdigest(), sha)


if __name__ == "__main__":
    unittest.main()

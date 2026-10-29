"""Pinned real archive integration plus explicitly invented numerical examples."""
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timezone
from decimal import Decimal, localcontext
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from premfootballbot import real_epl_training as rt
from premfootballbot.openfootball_exploratory import OpenFootballSource

FIXTURE = Path(__file__).parent / "fixtures" / "openfootball_2023_24"


def inputs():
    fields = json.loads((FIXTURE / "SOURCE.json").read_text(encoding="utf8"))
    fields["retrieved_at_utc"] = datetime.fromisoformat(fields["retrieved_at_utc"])
    return ((FIXTURE / "1-premierleague.txt").read_bytes(), OpenFootballSource(**fields),
            (FIXTURE / "LICENSE.md").read_bytes())


def fit(**changes):
    raw, source, license_bytes = inputs()
    arguments = dict(source=source, license_bytes=license_bytes)
    arguments.update(changes)
    return rt.fit_real_epl(raw, **arguments)


def invented_rows(home=2, away=1):
    # Private numerical-kernel inputs only. Never passed through the public real-data gate.
    return tuple(SimpleNamespace(home_team_raw=h, away_team_raw=a,
                                  home_goals_ft90=home, away_goals_ft90=away,
                                  match_date=date(2000, 1, 1), fixture_id=h + a)
                 for h in ("A", "B", "C") for a in ("A", "B", "C") if h != a)


class ApprovedArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw, cls.source, cls.license_bytes = inputs()
        cls.model = fit()

    def reject(self, code, raw=None, **changes):
        arguments = dict(source=self.source, license_bytes=self.license_bytes)
        arguments.update(changes)
        with self.assertRaises(rt.RealTrainingError) as caught:
            rt.fit_real_epl(self.raw if raw is None else raw, **arguments)
        self.assertEqual(caught.exception.code, code)

    def test_exact_source_and_license_git_blobs(self):
        for raw, sha, blob in ((self.raw, rt.APPROVED_SHA256, rt.APPROVED_BLOB),
                               (self.license_bytes, rt.LICENSE_SHA256, self.source.licence_blob_sha)):
            self.assertEqual(hashlib.sha256(raw).hexdigest(), sha)
            self.assertEqual(hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest(), blob)

    def test_complete_training_counts_and_exclusions(self):
        m = self.model
        self.assertEqual((m.training_matches, m.training_goal_observations, len(m.teams)), (380, 760, 20))
        self.assertEqual(dict(m.exclusions), {"quarantined": 0, "header_issues": 0, "filtered": 0})
        self.assertTrue(all((t.home_matches, t.away_matches) == (19, 19) for t in m.teams))
        self.assertEqual(m.source_import.semantic_sha256, rt.SEMANTIC_SHA256)

    def test_retains_source_rows_identity_and_unknown_timestamps(self):
        imported = self.model.source_import
        self.assertEqual(imported.printed_clocks, 235)
        self.assertEqual(sum(r.raw_clock_text is None for r in imported.rows), 145)
        self.assertEqual(len({r.fixture_id for r in imported.rows}), 380)
        for r in imported.rows:
            self.assertIsNone(r.kickoff_utc)
            self.assertIsNone(r.historical_available_at)
            self.assertFalse(r.strict_point_in_time_eligible)
            self.assertEqual(r.clock_timezone_status, "UNKNOWN")
            self.assertEqual(r.source_sha256, rt.APPROVED_SHA256)
            self.assertIn(rt.APPROVED_COMMIT, r.source_locator)
            self.assertEqual(self.raw.decode().splitlines()[r.source_line_number - 1], r.raw_row)

    def test_independent_score_line_spot_checks(self):
        by_line = {r.source_line_number: r for r in self.model.source_import.rows}
        for line, h, a, hg, ag in ((11, "Burnley FC", "Manchester City FC", 0, 3),
                                    (317, "Crystal Palace FC", "Brentford FC", 3, 1),
                                    (634, "Crystal Palace FC", "Aston Villa FC", 5, 0)):
            row = by_line[line]
            self.assertEqual((row.home_team_raw, row.away_team_raw, row.home_goals_ft90, row.away_goals_ft90), (h, a, hg, ag))

    def test_convergence_objective_and_gradient(self):
        d = self.model.diagnostics
        self.assertLessEqual(d.gradient_inf_norm, self.model.config.gradient_tolerance)
        self.assertEqual(d.iterations, len(d.objective_trace) - 1)
        self.assertTrue(all(b <= a for a, b in zip(d.objective_trace, d.objective_trace[1:])))
        self.assertAlmostEqual(d.objective, d.negative_log_likelihood + d.penalty, places=10)
        self.assertGreater(d.in_sample_poisson_deviance, 0)

    def test_intercept_score_equations_reproduce_observed_totals(self):
        d = self.model.diagnostics
        self.assertEqual((d.observed_home_goals, d.observed_away_goals), (684, 562))
        self.assertAlmostEqual(d.fitted_home_goals, 684, places=6)
        self.assertAlmostEqual(d.fitted_away_goals, 562, places=6)
        self.assertAlmostEqual(sum(t.attack for t in self.model.teams), 0, places=7)
        self.assertAlmostEqual(sum(t.defense_vulnerability for t in self.model.teams), 0, places=7)

    def test_diagnostics_recomputed_independently_from_team_effects(self):
        m = self.model
        teams = {t.team: t for t in m.teams}
        nll, deviance = [], []
        for r in m.source_import.rows:
            h, a = teams[r.home_team_raw], teams[r.away_team_raw]
            for eta, y in ((m.intercept + m.home_advantage + h.attack + a.defense_vulnerability, r.home_goals_ft90),
                           (m.intercept + a.attack + h.defense_vulnerability, r.away_goals_ft90)):
                rate = math.exp(eta)
                nll.append(rate - y * eta + math.log(math.factorial(y)))
                deviance.append(2 * ((y * math.log(y / rate) if y else 0) - y + rate))
        self.assertAlmostEqual(math.fsum(nll), m.diagnostics.negative_log_likelihood, places=9)
        self.assertAlmostEqual(math.fsum(deviance), m.diagnostics.in_sample_poisson_deviance, places=9)

    def test_repeat_fit_byte_identical(self):
        self.assertEqual(rt.retrospective_json(fit()), rt.retrospective_json(self.model))

    def test_integer_config_canonicalization(self):
        self.assertEqual(rt.retrospective_json(fit(config=rt.RealFitConfig(ridge=4))), rt.retrospective_json(self.model))

    def test_retrieval_changes_provenance_but_not_fitted_parameters(self):
        changed = fit(source=replace(self.source, retrieved_at_utc=datetime(2030, 1, 1, tzinfo=timezone.utc)))
        self.assertEqual(changed.teams, self.model.teams)
        self.assertEqual(changed.diagnostics, self.model.diagnostics)
        self.assertNotEqual(changed.sha256, self.model.sha256)
        self.assertIsNone(changed.historical_available_at)

    def test_replay_verification(self):
        self.assertTrue(rt.verify_retrospective_fit(self.model, self.raw, license_bytes=self.license_bytes))

    def test_frozen_nested_artifact(self):
        for obj, field, value in ((self.model, "intercept", 10), (self.model.teams[0], "attack", 10),
                                  (self.model.config, "ridge", 100), (self.source, "licence_id", "unknown")):
            with self.assertRaises(FrozenInstanceError):
                setattr(obj, field, value)

    def test_unsealed_parameter_tamper_rejected(self):
        with self.assertRaises(rt.RealTrainingError) as caught:
            rt.retrospective_json(replace(self.model, intercept=99))
        self.assertEqual(caught.exception.code, "ARTIFACT_TAMPERED")

    def test_resealed_parameter_tamper_rejected_by_replay(self):
        changed = replace(self.model, intercept=self.model.intercept + 0.1)
        changed = replace(changed, sha256=rt._digest(changed))
        with self.assertRaises(rt.RealTrainingError) as caught:
            rt.verify_retrospective_fit(changed, self.raw, license_bytes=self.license_bytes)
        self.assertEqual(caught.exception.code, "REPLAY_MISMATCH")

    def test_resealed_training_count_tamper_rejected_by_replay(self):
        changed = replace(self.model, training_matches=379)
        changed = replace(changed, sha256=rt._digest(changed))
        with self.assertRaises(rt.RealTrainingError) as caught:
            rt.verify_retrospective_fit(changed, self.raw, license_bytes=self.license_bytes)
        self.assertEqual(caught.exception.code, "REPLAY_MISMATCH")

    def test_resealed_exante_labels_rejected(self):
        for changes in ({"status": "EX_ANTE"}, {"strict_point_in_time_eligible": True},
                         {"historical_available_at": "2023-01-01"}, {"prediction_api_available": True},
                         {"record_kind": "SYNTHETIC"}, {"version": "other"}):
            changed = replace(self.model, **changes)
            changed = replace(changed, sha256=rt._digest(changed))
            with self.assertRaises(rt.RealTrainingError):
                rt.retrospective_json(changed)

    def test_nonfinite_artifact_rejected(self):
        with self.assertRaises(rt.RealTrainingError):
            rt.retrospective_json(replace(self.model, intercept=math.nan))

    def test_different_raw_source_cannot_be_self_pinned(self):
        changed = self.raw.replace(b"0-3", b"9-3", 1)
        new_source = replace(self.source, expected_sha256=hashlib.sha256(changed).hexdigest())
        self.reject("UNAPPROVED_SOURCE", changed, source=new_source)

    def test_modified_score_future_append_and_reorder_all_rejected(self):
        for changed in (self.raw.replace(b"0-3", b"9-3", 1), self.raw + b"\nMay 30\nArsenal FC 99-0 Chelsea FC\n",
                         b"\r\n".join(reversed(self.raw.split(b"\r\n")))):
            with self.subTest(length=len(changed)):
                self.reject("SOURCE_SHA256_MISMATCH", changed)

    def test_deleted_result_and_empty_source_rejected(self):
        self.reject("SOURCE_SHA256_MISMATCH", self.raw.replace(self.raw.splitlines(keepends=True)[10], b"", 1))
        self.reject("SOURCE_INPUT_SIZE", b"")

    def test_malformed_encoding_and_line_endings_rejected(self):
        for changed in (b"\xff" + self.raw, self.raw.replace(b"\r\n", b"\n"), self.raw + b"\0"):
            self.reject("SOURCE_SHA256_MISMATCH", changed)

    def test_raw_input_size_limit(self):
        self.reject("SOURCE_INPUT_SIZE", b"x" * (4 * 1024 * 1024 + 1))

    def test_unsupported_season_including_2025_is_denied(self):
        for path in ("2025-26/1-premierleague.txt", "2024-25/1-premierleague.txt"):
            self.reject("UNAPPROVED_SOURCE", source=replace(self.source, path=path))

    def test_commit_blob_repository_or_sha_contradiction(self):
        for field, value in (("repository_commit_sha", "a" * 40), ("expected_git_blob_sha", "b" * 40),
                              ("repository_url", "https://example.com"), ("expected_sha256", "c" * 64)):
            self.reject("UNAPPROVED_SOURCE", source=replace(self.source, **{field: value}))

    def test_unknown_license_or_false_evidence(self):
        for field, value in (("licence_id", "unknown"), ("licence_blob_sha", "d" * 40),
                              ("licence_evidence_url", "https://example.com/CC0")):
            self.reject("LICENCE", source=replace(self.source, **{field: value}))

    def test_license_bytes_required_and_pinned(self):
        for data in (b"", b"CC0-1.0", self.license_bytes + b"\n", b"x" * 20001):
            self.reject("LICENCE", license_bytes=data)
        self.reject("INPUT_TYPE", license_bytes=None)

    def test_naive_retrieval_rejected(self):
        self.reject("SOURCE_RETRIEVAL", source=replace(self.source, retrieved_at_utc=datetime(2026, 1, 1)))

    def test_wrong_input_types_and_caller_imports_rejected(self):
        for data in (self.raw.decode(), bytearray(self.raw), self.model.source_import, self.model.source_import.rows):
            self.reject("INPUT_TYPE", data)
        self.reject("INPUT_TYPE", source={})

    def test_bad_config_values(self):
        for name, values in (("ridge", (True, 0, -1, math.nan, math.inf, "4", 10001)),
                              ("gradient_tolerance", (True, 0, 1e-12, 0.1, math.inf)),
                              ("max_iterations", (True, 0, 1.5, 201))):
            for value in values:
                with self.subTest(name=name, value=value), self.assertRaises(rt.RealTrainingError):
                    rt.RealFitConfig(**{name: value})
        self.reject("BAD_CONFIG", config={})

    def test_iteration_exhaustion_has_no_artifact_fallback(self):
        self.reject("NOT_CONVERGED", config=rt.RealFitConfig(max_iterations=1))

    def test_stronger_ridge_shrinks_team_parameters(self):
        strong = fit(config=rt.RealFitConfig(ridge=1000))
        size = lambda m: sum(t.attack ** 2 + t.defense_vulnerability ** 2 for t in m.teams)
        self.assertLess(size(strong), size(self.model))
        self.assertNotEqual(strong.sha256, self.model.sha256)


class NumericalKernelTests(unittest.TestCase):
    def test_balanced_toy_has_closed_form_solution(self):
        mu, h, teams, diagnostics = rt._fit_rows(invented_rows(), rt.RealFitConfig())
        self.assertAlmostEqual(mu, 0, places=12)
        self.assertAlmostEqual(h, math.log(2), places=12)
        self.assertTrue(all(t.attack == t.defense_vulnerability == 0 for t in teams))
        self.assertAlmostEqual(diagnostics.negative_log_likelihood, 18 - 6 * math.log(2), places=12)

    def test_home_advantage_may_be_negative(self):
        _, h, _, _ = rt._fit_rows(invented_rows(home=1, away=2), rt.RealFitConfig())
        self.assertAlmostEqual(h, -math.log(2), places=12)

    def test_zero_goal_venue_and_empty_training_fail(self):
        for rows in ((), invented_rows(0, 0), invented_rows(0, 1), invented_rows(1, 0)):
            with self.assertRaises(rt.RealTrainingError) as caught:
                rt._fit_rows(rows, rt.RealFitConfig())
            self.assertEqual(caught.exception.code, "DEGENERATE_TRAINING")

    def test_gradient_and_hessian_against_central_differences(self):
        _, data = rt._design(invented_rows())
        theta = [0.2, -0.1, 0.4, 0.1, -0.3, 0.2, -0.2, 0.5]
        gradient, hessian = rt._derivatives(theta, data, 4)
        eps = 1e-5
        for i in range(len(theta)):
            plus, minus = theta.copy(), theta.copy()
            plus[i] += eps
            minus[i] -= eps
            numerical = (rt._objective(plus, data, 4) - rt._objective(minus, data, 4)) / (2 * eps)
            self.assertAlmostEqual(gradient[i], numerical, delta=1e-7)
            gp = rt._derivatives(plus, data, 4)[0]
            gm = rt._derivatives(minus, data, 4)[0]
            for j in range(len(theta)):
                self.assertAlmostEqual(hessian[j][i], (gp[j] - gm[j]) / (2 * eps), delta=1e-7)

    def test_objective_against_high_precision_decimal(self):
        _, data = rt._design(invented_rows(3, 0))
        theta = [0.2, -0.1, 0.4, 0.1, -0.3, 0.2, -0.2, 0.5]
        with localcontext() as context:
            context.prec = 50
            ts = [Decimal(str(x)) for x in theta]
            oracle = sum((sum(ts[j] for j in active).exp() - y * sum(ts[j] for j in active)
                          + Decimal(math.factorial(y)).ln()) for active, y in data)
            oracle += 2 * sum(t * t for t in ts[2:])
        self.assertAlmostEqual(rt._objective(theta, data, 4), float(oracle), places=12)

    def test_zero_score_terms_and_overflow_trials(self):
        data = (((0,), 0),)
        self.assertEqual(rt._objective([0.0, 0.0], data, 4), 1.0)
        self.assertEqual(rt._objective([1000, 0], data, 4), math.inf)
        self.assertEqual(rt._objective([math.nan, 0], data, 4), math.inf)

    def test_cholesky_known_solution_and_bad_pivot(self):
        self.assertEqual(rt._solve([[4.0, 2.0], [2.0, 5.0]], [8.0, 12.0]), [1.0, 2.0])
        with self.assertRaises(rt.RealTrainingError):
            rt._solve([[0.0]], [1.0])

    def test_row_order_does_not_affect_fit(self):
        rows = list(invented_rows())
        rows[0] = SimpleNamespace(**{**vars(rows[0]), "home_goals_ft90": 5})
        self.assertEqual(rt._fit_rows(rows, rt.RealFitConfig()), rt._fit_rows(list(reversed(rows)), rt.RealFitConfig()))

    def test_failed_line_search_raises(self):
        rows = list(invented_rows())
        rows[0] = SimpleNamespace(**{**vars(rows[0]), "home_goals_ft90": 5})
        with patch.object(rt, "_objective", return_value=math.inf), self.assertRaises(rt.RealTrainingError) as caught:
            rt._fit_rows(rows, rt.RealFitConfig())
        self.assertEqual(caught.exception.code, "NOT_CONVERGED")


if __name__ == "__main__":
    unittest.main()

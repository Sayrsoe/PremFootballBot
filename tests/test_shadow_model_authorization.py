"""Portable authorization tests; runtime/libm variations are simulated explicitly."""
from dataclasses import replace
from datetime import datetime, timezone
import json
import math
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from premfootballbot import real_epl_training as rt
from premfootballbot import shadow_pilot as sp
from tests.test_real_epl_training import inputs, fit
from tests.test_shadow_pilot import request


def seal(model):
    return replace(model, sha256=rt._digest(model))


class PortableAuthorizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw, cls.source, cls.license = inputs()
        cls.model = fit()

    def decision(self, model):
        return sp.forecast_shadow(model, self.raw, license_bytes=self.license, **request())

    def rejected(self, model):
        decision = self.decision(model)
        self.assertEqual(decision.status, "ABSTAIN")
        self.assertEqual(decision.packet.forecast_kind, "NO_FORECAST")

    def test_reviewed_local_artifact_approved(self):
        self.assertTrue(sp._approved_model_semantics(self.model))
        self.assertEqual(self.decision(self.model).status, "SHADOW_FORECAST")

    def test_simulated_cpython3135_recomputes_and_authorizes_without_hash_allowlist(self):
        # Select the other QA runtime so this test also runs on actual 3.13.5.
        minor, micro = (12, 14) if self.model.runtime == "cpython 3.13.5" else (13, 5)
        runtime = SimpleNamespace(implementation=SimpleNamespace(name="cpython"),
                                  version_info=SimpleNamespace(major=3, minor=minor, micro=micro))
        with patch.object(rt, "sys", runtime):
            model = fit()
            self.assertNotEqual(model.sha256, self.model.sha256)
            self.assertTrue(rt.verify_retrospective_fit(model, self.raw, license_bytes=self.license))
            self.assertEqual(self.decision(model).status, "SHADOW_FORECAST")

    def test_simulated_libm_roundoff_retains_exact_local_replay(self):
        original = rt._fit_rows
        def alternate(rows, config):
            mu, home, teams, diag = original(rows, config)
            teams = tuple(replace(t, attack=math.nextafter(t.attack, math.inf),
                                  defense_vulnerability=math.nextafter(t.defense_vulnerability, -math.inf)) for t in teams)
            return (math.nextafter(mu, math.inf), math.nextafter(home, -math.inf), teams,
                    replace(diag, objective=math.nextafter(diag.objective, math.inf)))
        with patch.object(rt, "_fit_rows", alternate):
            model = fit()
            self.assertNotEqual(model.sha256, self.model.sha256)
            self.assertEqual(self.decision(model).status, "SHADOW_FORECAST")
            self.assertEqual(self.decision(model), self.decision(model))
        self.rejected(model)  # Foreign bytes do not bypass unchanged exact replay.

    def test_outside_fixed_parameter_envelope_rejected_even_with_local_replay(self):
        original = rt._fit_rows
        def drifted(rows, config):
            mu, home, teams, diag = original(rows, config)
            return mu + 1e-8, home, teams, diag
        with patch.object(rt, "_fit_rows", drifted):
            model = fit()
            self.assertTrue(rt.verify_retrospective_fit(model, self.raw, license_bytes=self.license))
            self.assertEqual(self.decision(model).reason, "UNAPPROVED_MODEL_ARTIFACT")

    def test_one_ulp_parameter_tamper_fails_exact_replay(self):
        changed = seal(replace(self.model, intercept=math.nextafter(self.model.intercept, math.inf)))
        self.assertTrue(sp._approved_model_semantics(changed))
        self.rejected(changed)

    def test_each_parameter_is_bound_to_fixed_reference(self):
        mutations = [replace(self.model, intercept=self.model.intercept + 1e-7),
                     replace(self.model, home_advantage=self.model.home_advantage + 1e-7)]
        for i, team in enumerate(self.model.teams):
            for field in ("attack", "defense_vulnerability"):
                teams = list(self.model.teams)
                teams[i] = replace(team, **{field: getattr(team, field) + 1e-7})
                mutations.append(replace(self.model, teams=tuple(teams)))
        for model in mutations:
            with self.subTest(model=model.intercept, teams=model.teams):
                self.assertFalse(sp._approved_model_semantics(seal(model)))

    def test_unsealed_parameter_tamper_rejected(self):
        self.rejected(replace(self.model, home_advantage=0.8))

    def test_resealed_diagnostics_tamper_rejected(self):
        changed = seal(replace(self.model, diagnostics=replace(self.model.diagnostics, iterations=99)))
        self.assertTrue(sp._approved_model_semantics(changed))
        self.rejected(changed)

    def test_runtime_relabel_alone_does_not_bypass_replay(self):
        self.rejected(seal(replace(self.model, runtime="forged-runtime")))

    def test_recomputed_changed_acquisition_provenance_rejected(self):
        source = replace(self.source, retrieved_at_utc=datetime(2024, 6, 1, tzinfo=timezone.utc))
        model = rt.fit_real_epl(self.raw, source=source, license_bytes=self.license)
        self.assertFalse(sp._approved_model_semantics(model))
        self.rejected(model)

    def test_recomputed_different_configuration_rejected(self):
        for config in (rt.RealFitConfig(ridge=5), rt.RealFitConfig(max_iterations=99),
                       rt.RealFitConfig(gradient_tolerance=1e-6)):
            model = rt.fit_real_epl(self.raw, source=self.source, license_bytes=self.license, config=config)
            self.assertFalse(sp._approved_model_semantics(model))
            self.rejected(model)

    def test_all_source_identity_fields_remain_bound(self):
        for field, value in (("repository_url", "https://example.org"), ("repository_commit_sha", "a"*40),
                             ("expected_sha256", "b"*64), ("expected_git_blob_sha", "c"*40),
                             ("licence_id", "UNKNOWN"), ("licence_evidence_url", "https://example.org"),
                             ("licence_blob_sha", "d"*40), ("path", "2025-26/1-premierleague.txt")):
            source = replace(self.source, **{field: value})
            model = seal(replace(self.model, source_import=replace(self.model.source_import, source=source)))
            self.assertFalse(sp._approved_model_semantics(model), field)
            self.rejected(model)

    def test_team_order_identity_counts_and_warning_remain_exact(self):
        for changed in (replace(self.model, teams=tuple(reversed(self.model.teams))),
                        replace(self.model, training_matches=379), replace(self.model, exclusions=()),
                        replace(self.model, warnings=())):
            self.assertFalse(sp._approved_model_semantics(seal(changed)))
        with self.assertRaises(rt.RealTrainingError):
            sp._approved_model_semantics(seal(replace(self.model, version="unapproved")))

    def test_nonfinite_parameter_never_authorized(self):
        for value in (float('nan'), float('inf'), -float('inf')):
            self.rejected(replace(self.model, intercept=value))

    def test_report_binds_authorization_policy_and_exact_artifact(self):
        report = json.loads(self.decision(self.model).report_bytes)
        self.assertEqual(report['model_authorization'], sp.MODEL_AUTHORIZATION_VERSION)
        self.assertEqual(report['approved_semantic_sha256'], sp.APPROVED_MODEL_SEMANTIC_SHA256)
        self.assertEqual(report['model_sha256'], self.model.sha256)


if __name__ == '__main__':
    unittest.main()

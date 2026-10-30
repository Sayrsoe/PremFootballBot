"""INVENTED future fixtures/review pins, never real independent kickoff evidence."""
from dataclasses import replace
from decimal import localcontext, Decimal
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from premfootballbot import shadow_pilot as sp
from premfootballbot import real_epl_training as rt
from premfootballbot.prospective_evidence import freeze_packet
from premfootballbot.match_data import parse_synthetic_json
from premfootballbot.expected_goals import fit_expected_goals, ExpectedGoalsError
from premfootballbot.backtesting import generate_forecasts, BacktestError
from tests.test_real_epl_training import inputs, fit
from tests.backtesting_cases import manifest


def invented():
    snapshot = {"fixture_id": "INVENTED-2027-A", "league": "EPL", "home": "Arsenal",
                "away": "Chelsea", "kickoff_utc": "2027-01-10T15:00:00Z", "status": "SCHEDULED"}
    review = {"fixture": snapshot, "snapshot_sha256": "", "source_url": "https://example.org/INVENTED-fixture",
              "license_status": "CLEARED", "license_reference": "https://example.org/INVENTED-permission",
              "acquired_at_utc": "2027-01-10T10:00:00Z", "reviewed_at_utc": "2027-01-10T11:00:00Z",
              "valid_until_utc": "2027-01-10T15:00:00Z", "reviewer": "independent-demo"}
    return snapshot, review


def request(snapshot=None, review=None):
    default_snapshot, default_review = invented()
    snapshot = default_snapshot if snapshot is None else snapshot
    review = default_review if review is None else review
    raw = sp._json(snapshot)
    review = dict(review, fixture=snapshot, snapshot_sha256=hashlib.sha256(raw).hexdigest())
    proof = sp._json(review)
    # INVENTED trust root for unit tests only. Production pins require external review.
    return dict(snapshot_bytes=raw, review_bytes=proof,
                approved_review_sha256=(hashlib.sha256(proof).hexdigest(),),
                team_mapping=(("Arsenal", "Arsenal FC"), ("Chelsea", "Chelsea FC")),
                cutoff_utc="2027-01-10T12:00:00Z", model_acquired_at_utc="2026-10-30T10:00:00Z", operator="demo-operator")


class ShadowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw, cls.source, cls.license = inputs()
        cls.model = fit()

    def call(self, args=None, model=None, raw=None):
        return sp.forecast_shadow(self.model if model is None else model, self.raw if raw is None else raw,
                                  license_bytes=self.license, **(request() if args is None else args))

    def abstains(self, args, reason=None):
        result = self.call(args)
        self.assertEqual(result.status, "ABSTAIN")
        if reason:
            self.assertEqual(result.reason, reason)
        if result.packet:
            self.assertEqual(result.packet.forecast_kind, "NO_FORECAST")
        return result

    def test_eligible_invented_fixture_is_local_only(self):
        result = self.call()
        self.assertEqual(result.status, "SHADOW_FORECAST", result.reason)
        self.assertEqual(result.packet.assurance, "LOCAL_ONLY")
        self.assertEqual(result.packet.forecast_kind, "ONE_X_TWO")
        self.assertTrue(json.loads(result.report_bytes)["external_audit_required"])

    def test_independent_replay_preserves_recorder_packet(self):
        p = self.call().packet
        self.assertEqual(p, freeze_packet(p.canonical_bytes))

    def test_deterministic_decision(self):
        self.assertEqual(self.call(), self.call())

    def test_model_labels_and_bytes_unchanged(self):
        original = rt.retrospective_json(self.model)
        self.call()
        self.assertEqual(original, rt.retrospective_json(self.model))
        self.assertEqual(self.model.status, "RETROSPECTIVE_DESCRIPTIVE_ONLY")
        self.assertFalse(self.model.prediction_api_available)

    def test_rates_match_separate_equations(self):
        report = json.loads(self.call().report_bytes)
        import math
        teams = {t.team: t for t in self.model.teams}
        h, a = teams["Arsenal FC"], teams["Chelsea FC"]
        self.assertEqual(report["rates"], [math.exp(self.model.intercept + self.model.home_advantage + h.attack + a.defense_vulnerability),
                                           math.exp(self.model.intercept + a.attack + h.defense_vulnerability)])

    def test_tail_and_quantization_bounds(self):
        report = json.loads(self.call().report_bytes)
        self.assertLessEqual(report["mass"]["omitted_mass_bound"], 1e-10)
        values = report["emitted_probabilities"]
        self.assertEqual(sum(Decimal(p) for p in values), Decimal(1))
        self.assertLess(report["maximum_adjustment"], 1.1e-10)

    def test_report_and_model_bound_into_receipt(self):
        result = self.call()
        data = json.loads(result.packet.canonical_bytes)
        refs = {r["source_id"]: r for r in data["inputs"]}
        self.assertEqual(refs["shadow-audit"]["content_sha256"], hashlib.sha256(result.report_bytes).hexdigest())
        self.assertEqual(refs["model-artifact"]["content_sha256"], hashlib.sha256(rt.retrospective_json(self.model)).hexdigest())
        self.assertTrue(all(r["source_available_at_utc"] is None for r in data["inputs"]))

    def test_no_trust_pin_means_no_forecast_or_receipt(self):
        args = request()
        args["approved_review_sha256"] = ()
        result = self.abstains(args, "UNAPPROVED_REVIEW")
        self.assertIsNone(result.packet)

    def test_changed_review_cannot_use_old_pin(self):
        args = request()
        args["review_bytes"] += b" "
        self.abstains(args, "UNAPPROVED_REVIEW")

    def test_changed_snapshot_rejected(self):
        args = request()
        args["snapshot_bytes"] += b" "
        self.abstains(args, "SNAPSHOT_MISMATCH")

    def test_inconsistent_review_fixture(self):
        args = request()
        proof = json.loads(args["review_bytes"])
        proof["fixture"]["home"] = "Other"
        args["review_bytes"] = sp._json(proof)
        args["approved_review_sha256"] = (sp._sha(args["review_bytes"]),)
        self.abstains(args, "FIXTURE_MISMATCH")

    def test_uncertain_kickoff_types(self):
        for kickoff in (None, "TBC", "2027-01-10T15:00:00", "2027-01-10T15:00:00+01:00", "2027-01-10", True):
            f, r = invented()
            f["kickoff_utc"] = kickoff
            self.abstains(request(f, r))

    def test_postponed_cancelled_or_started_fixture(self):
        for status in ("POSTPONED", "CANCELLED", "LIVE", "FINISHED", "UNKNOWN"):
            f, r = invented()
            f["status"] = status
            self.abstains(request(f, r), "UNSUPPORTED_FIXTURE")

    def test_other_league_denied(self):
        f, r = invented()
        f["league"] = "CHAMPIONSHIP"
        self.abstains(request(f, r), "UNSUPPORTED_FIXTURE")

    def test_at_or_after_kickoff(self):
        for cutoff in ("2027-01-10T15:00:00Z", "2027-01-11T00:00:00Z"):
            args = request()
            args["cutoff_utc"] = cutoff
            self.abstains(args, "EVIDENCE_TIMING")

    def test_late_acquisition_review_and_expiry(self):
        for key, value in (("acquired_at_utc", "2027-01-10T13:00:00Z"),
                            ("reviewed_at_utc", "2027-01-10T13:00:00Z"),
                            ("valid_until_utc", "2027-01-10T12:00:00Z"),
                            ("valid_until_utc", "2027-01-10T16:00:00Z")):
            f, r = invented()
            r[key] = value
            self.abstains(request(f, r), "EVIDENCE_TIMING")

    def test_stale_review_abstains(self):
        f, r = invented()
        r.update(acquired_at_utc="2027-01-08T10:00:00Z", reviewed_at_utc="2027-01-08T11:00:00Z")
        self.abstains(request(f, r), "STALE_REVIEW")

    def test_operator_cannot_self_review(self):
        f, r = invented()
        r["reviewer"] = "DEMO-OPERATOR"
        self.abstains(request(f, r), "INDEPENDENT_REVIEW_REQUIRED")

    def test_unknown_or_blocked_rights(self):
        for rights in ("UNKNOWN", "BLOCKED", None):
            f, r = invented()
            r["license_status"] = rights
            self.abstains(request(f, r), "RIGHTS_NOT_CLEARED")

    def test_unsafe_or_missing_source_reference(self):
        for url in ("http://example.org", "https://a:b@example.org", "https://example.org?token=secret", None):
            f, r = invented()
            r["source_url"] = url
            self.abstains(request(f, r))

    def test_duplicate_json_postmatch_fields_or_size(self):
        for raw in (b'{"home":"A","home":"B"}', b'{"result":1}', b'x' * 65537, b'\xff'):
            args = request()
            args["review_bytes"] = raw
            args["approved_review_sha256"] = (sp._sha(raw),)
            self.abstains(args)

    def test_unknown_or_promoted_team_no_fallback(self):
        args = request()
        args["team_mapping"] = (("Arsenal", "Leeds United FC"), ("Chelsea", "Chelsea FC"))
        result = self.abstains(args, "UNSUPPORTED_TEAM")
        self.assertEqual(result.packet.forecast_kind, "NO_FORECAST")

    def test_missing_mapping_no_fuzzy_alias(self):
        args = request()
        args["team_mapping"] = (("ARSENAL", "Arsenal FC"), ("Chelsea", "Chelsea FC"))
        self.abstains(args, "UNSUPPORTED_TEAM")

    def test_duplicate_alias_or_model_target(self):
        for mapping in ((("Arsenal", "Arsenal FC"), ("arsenal", "Chelsea FC")),
                         (("Arsenal", "Arsenal FC"), ("Chelsea", "Arsenal FC")), [], (), (("Arsenal",),)):
            args = request()
            args["team_mapping"] = mapping
            self.abstains(args, "TEAM_MAPPING")

    def test_mapping_order_is_canonical(self):
        args = request()
        args["team_mapping"] = tuple(reversed(args["team_mapping"]))
        self.assertEqual(self.call(args), self.call())

    def test_mapping_change_changes_commitment(self):
        args = request()
        args["team_mapping"] = (("Arsenal", "Chelsea FC"), ("Chelsea", "Arsenal FC"))
        self.assertNotEqual(self.call(args).packet.commitment_sha256, self.call().packet.commitment_sha256)

    def test_model_acquired_after_cutoff_or_before_source(self):
        for time in ("2027-01-10T12:00:01Z", "2024-01-01T00:00:00Z"):
            args = request()
            args["model_acquired_at_utc"] = time
            self.abstains(args, "MODEL_ACQUISITION")

    def test_tampered_resealed_model_is_recomputed(self):
        model = replace(self.model, intercept=9)
        model = replace(model, sha256=rt._digest(model))
        self.assertEqual(self.call(model=model).status, "ABSTAIN")

    def test_tampered_raw_source_abstains(self):
        self.assertEqual(self.call(raw=self.raw + b'\n').status, "ABSTAIN")

    def test_numeric_failure_abstains_without_probability_packet(self):
        with patch.object(sp, "poisson_distribution", side_effect=ValueError("cap failure")):
            result = self.call()
        self.assertEqual(result.status, "ABSTAIN")
        self.assertEqual(result.packet.forecast_kind, "NO_FORECAST")

    def test_bad_tail_and_nan_mass_abstain(self):
        real = sp.poisson_distribution(1, 1)
        for mass in (replace(real.mass, omitted_mass_bound=0.1), replace(real.mass, retained_mass=float('nan')),
                     replace(real.mass, mass_roundoff=0.1)):
            with patch.object(sp, "poisson_distribution", return_value=replace(real, mass=mass)):
                self.assertEqual(self.call().status, "ABSTAIN")

    def test_extreme_rate_abstains(self):
        with patch.object(sp.math, "exp", return_value=float('inf')):
            # Replaying the model also fails safely under this corrupt numeric environment.
            self.assertEqual(self.call().status, "ABSTAIN")

    def test_decimal_context_does_not_change_output(self):
        baseline = self.call()
        with localcontext() as ctx:
            ctx.prec = 3
            self.assertEqual(self.call(), baseline)

    def test_quantization_tie_and_exact_partition(self):
        values = sp._quantize((1/3, 1/3, 1/3))
        self.assertEqual(values, ('0.333333333333334', '0.333333333333333', '0.333333333333333'))

    def test_no_network_filesystem_or_publication(self):
        args = request()
        with patch("socket.socket", side_effect=AssertionError), patch("builtins.open", side_effect=AssertionError), \
             patch.object(Path, "read_bytes", side_effect=AssertionError):
            self.assertEqual(self.call(args).status, "SHADOW_FORECAST")

    def test_synthetic_paths_still_reject_shadow_decision(self):
        result = self.call()
        self.assertFalse(parse_synthetic_json(result.report_bytes).valid)
        with self.assertRaises(ExpectedGoalsError):
            fit_expected_goals(result, None)
        with self.assertRaises(BacktestError):
            generate_forecasts(result, manifest())

    def test_invalid_fixture_never_reaches_poisson(self):
        args = request()
        args["approved_review_sha256"] = ()
        with patch.object(sp, "poisson_distribution") as calc:
            self.abstains(args)
            calc.assert_not_called()

    def test_historical_target_cannot_be_replayed_as_future(self):
        f, r = invented()
        f["kickoff_utc"] = "2024-01-10T15:00:00Z"
        self.abstains(request(f, r), "EVIDENCE_TIMING")

    def test_unreviewed_model_provenance_change_rejected(self):
        from datetime import datetime, timezone
        changed_source = replace(self.source, retrieved_at_utc=datetime(2026, 10, 30, tzinfo=timezone.utc))
        changed = rt.fit_real_epl(self.raw, source=changed_source, license_bytes=self.license)
        result = self.call(model=changed)
        self.assertEqual(result.reason, "UNAPPROVED_MODEL_ARTIFACT")
        self.assertEqual(result.packet.forecast_kind, "NO_FORECAST")

    def test_earlier_model_provenance_does_not_create_exante_evidence(self):
        from datetime import datetime, timezone
        changed_source = replace(self.source, retrieved_at_utc=datetime(2024, 6, 1, tzinfo=timezone.utc))
        changed = rt.fit_real_epl(self.raw, source=changed_source, license_bytes=self.license)
        self.assertEqual(self.call(model=changed).reason, "UNAPPROVED_MODEL_ARTIFACT")

    def test_unapproved_tuning_rejected(self):
        changed = rt.fit_real_epl(self.raw, source=self.source, license_bytes=self.license, config=rt.RealFitConfig(ridge=5))
        self.assertEqual(self.call(model=changed).reason, "UNAPPROVED_MODEL_CONFIG")


if __name__ == '__main__':
    unittest.main()

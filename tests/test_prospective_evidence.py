"""Fabricated fixture references only; no real EPL forecasts or third-party I/O."""
import copy
from dataclasses import FrozenInstanceError
import hashlib
import importlib
import json
import unittest

from premfootballbot.prospective_evidence import (
    DOMAIN, VERSION, EvidenceError, freeze_packet, manual_comment_template,
    assess_untrusted_comment_metadata, manual_external_audit_worksheet,
)

SHA = "a" * 64
SHA2 = "b" * 64


def sample():
    return {
        "protocol": VERSION, "league": "EPL", "assurance": "LOCAL_ONLY",
        "fixture": {
            "fixture_id": "DEMO-FAKE-2027-01", "home": "Example Town FC", "away": "Example Albion FC",
            "kickoff_utc": "2027-01-10T15:00:00Z",
            "kickoff_source_url": "https://example.org/fixtures/demo",
            "kickoff_observed_at_utc": "2027-01-09T10:00:00Z",
        },
        "cutoff_utc": "2027-01-10T14:00:00Z",
        "inputs": [{
            "source_id": "demo-input", "source_url": "local://operator/example",
            "content_sha256": SHA, "license_status": "UNKNOWN", "license_reference": None,
            "acquired_at_utc": "2027-01-09T10:30:00Z",
            "source_available_at_utc": None,
            "verified_by_external_observer_at_utc": None,
        }],
        "model": None,
        "forecast": {"kind": "NO_FORECAST"},
        "capture": {"captured_at_utc": "2027-01-09T11:00:00Z",
                    "operator": "demo", "method": "manual", "local_only": True},
    }


def metadata(frozen):
    return {"id": 1234, "html_url": "https://github.com/sample/repo/issues/1#issuecomment-1234",
            "body": manual_comment_template(frozen), "created_at": "2027-01-09T12:00:00Z",
            "updated_at": "2027-01-09T12:00:00Z"}


class PacketTests(unittest.TestCase):
    def reject(self, change):
        p = sample()
        change(p)
        with self.assertRaises(EvidenceError):
            freeze_packet(p)

    def test_no_forecast_local_only(self):
        f = freeze_packet(sample())
        self.assertEqual(f.assurance, "LOCAL_ONLY")
        self.assertEqual(f.forecast_kind, "NO_FORECAST")
        self.assertIn(b'"model":null', f.canonical_bytes)
        self.assertNotIn(b'"score"', f.canonical_bytes)
        self.assertIn("NOT INDEPENDENTLY CERTIFIED", manual_comment_template(f))
        self.assertIn("Independent audit required: YES", manual_external_audit_worksheet(f))

    def test_digest_is_domain_separated_sha256(self):
        f = freeze_packet(sample())
        self.assertEqual(f.commitment_sha256, hashlib.sha256(DOMAIN + f.canonical_bytes).hexdigest())
        self.assertNotEqual(f.commitment_sha256, hashlib.sha256(f.canonical_bytes).hexdigest())

    def test_canonical_key_order_and_source_order(self):
        p = sample()
        p["inputs"].append({**p["inputs"][0], "source_id":"z-other", "content_sha256":SHA2})
        q = json.loads(json.dumps(p))
        q = dict(reversed(list(q.items())))
        q["fixture"] = dict(reversed(list(q["fixture"].items())))
        q["inputs"].reverse()
        self.assertEqual(freeze_packet(p), freeze_packet(q))

    def test_canonicalization_round_trip(self):
        f = freeze_packet(sample())
        self.assertEqual(freeze_packet(f.canonical_bytes), f)

    def test_any_substantive_change_changes_hash(self):
        f = freeze_packet(sample())
        for key, val in (("fixture_id", "DEMO-FAKE-2027-02"),
                         ("home", "Another Team"), ("kickoff_utc", "2027-01-10T16:00:00Z")):
            p = sample()
            p["fixture"][key] = val
            self.assertNotEqual(freeze_packet(p).commitment_sha256, f.commitment_sha256)
        p = sample(); p["inputs"][0]["license_status"] = "CLEARED"
        self.assertNotEqual(freeze_packet(p).commitment_sha256, f.commitment_sha256)
        p = sample(); p["inputs"][0]["content_sha256"] = SHA2
        self.assertNotEqual(freeze_packet(p).commitment_sha256, f.commitment_sha256)

    def test_frozen_dataclass(self):
        with self.assertRaises(FrozenInstanceError):
            freeze_packet(sample()).assurance = "EXTERNALLY_CHECKED"

    def test_reject_duplicate_json_keys(self):
        with self.assertRaisesRegex(EvidenceError, "duplicate"):
            freeze_packet('{"protocol":"a","protocol":"b"}')
        raw = json.dumps(sample()).replace('"league": "EPL"', '"league": "EPL", "league": "EPL"')
        with self.assertRaisesRegex(EvidenceError, "duplicate"):
            freeze_packet(raw)

    def test_reject_nonobject_or_bad_encoding(self):
        for value in ('[]', '"a"', b"\xff", '{', 'null'):
            with self.subTest(value=value), self.assertRaises(EvidenceError):
                freeze_packet(value)

    def test_reject_oversize(self):
        with self.assertRaises(EvidenceError):
            freeze_packet(" " * 65536 + "{}")
        self.reject(lambda p: p["fixture"].update(home="X" * 200))

    def test_no_postmatch_fields_at_any_level(self):
        for container, key, val in (("root", "final_goals", [2,1]),
                                    ("fixture", "score", "2-0"),
                                    ("source", "outcome", "home")):
            def inject(p):
                d = p if container == "root" else (p["fixture"] if container=="fixture" else p["inputs"][0])
                d[key] = val
            self.reject(inject)

    def test_reject_bogus_assurance(self):
        for bad in ("EXTERNALLY_CHECKED", "EXTERNAL_COMMITMENT_CLAIMED", None):
            self.reject(lambda p: p.update(assurance=bad))

    def test_reject_bad_version_or_league(self):
        self.reject(lambda p: p.update(protocol="v999"))
        self.reject(lambda p: p.update(league="LaLiga"))

    def test_reject_same_teams_confusables_and_controls(self):
        self.reject(lambda p: p["fixture"].update(away="example town fc"))
        self.reject(lambda p: p["fixture"].update(home="Arsеnal"))  # Cyrillic e
        self.reject(lambda p: p["fixture"].update(home="Example\u200bTown"))
        self.reject(lambda p: p["fixture"].update(home="Example\nTown"))
        self.reject(lambda p: p["fixture"].update(fixture_id="../fixture"))

    def test_reject_naive_or_offset_or_invalid_timestamps(self):
        for bad in ("2027-01-10T15:00:00", "2027-01-10T15:00:00+07:00",
                    "2027-02-30T15:00:00Z", "2027-01-10T15:00Z", "2027-01-10 15:00:00Z"):
            self.reject(lambda p: p["fixture"].update(kickoff_utc=bad))

    def test_cutoff_must_precede_kickoff(self):
        for stamp in ("2027-01-10T15:00:00Z", "2027-01-10T16:00:00Z"):
            self.reject(lambda p: p.update(cutoff_utc=stamp))

    def test_reject_acquisition_after_cutoff(self):
        self.reject(lambda p: p["inputs"][0].update(acquired_at_utc="2027-01-10T14:30:00Z"))
        self.reject(lambda p: p["inputs"][0].update(source_available_at_utc="2027-01-10T14:30:00Z"))
        self.reject(lambda p: p["inputs"][0].update(verified_by_external_observer_at_utc="2027-01-10T14:30:00Z"))
        self.reject(lambda p: p["capture"].update(captured_at_utc="2027-01-10T14:30:00Z"))
        self.reject(lambda p: p["fixture"].update(kickoff_observed_at_utc="2027-01-10T14:30:00Z"))
        self.reject(lambda p: p["inputs"][0].update(source_available_at_utc="2027-01-09T10:45:00Z"))
        self.reject(lambda p: p["inputs"][0].update(acquired_at_utc="2027-01-09T12:00:00Z"))
        self.reject(lambda p: p["fixture"].update(kickoff_observed_at_utc="2027-01-09T12:00:00Z"))

    def test_reject_bad_source_rights_or_credential_leak(self):
        self.reject(lambda p: p["inputs"][0].update(license_status="ASSUMED_CLEARED"))
        self.reject(lambda p: p["inputs"][0].update(source_url="https://user:pass@example.org/item"))
        self.reject(lambda p: p["inputs"][0].update(source_url="https://example.org?api_key=secret"))
        self.reject(lambda p: p["fixture"].update(kickoff_source_url="http://example.org/item"))
        self.reject(lambda p: p["inputs"][0].update(content_sha256="ABCDEF"))

    def test_unknown_blocked_never_silently_cleared(self):
        for rights in ("UNKNOWN", "BLOCKED"):
            p = sample(); p["inputs"][0]["license_status"] = rights
            self.assertIn(('"license_status":"'+rights+'"').encode(), freeze_packet(p).canonical_bytes)

    def test_duplicate_or_too_many_sources(self):
        self.reject(lambda p: p["inputs"].append(copy.deepcopy(p["inputs"][0])))
        self.reject(lambda p: p.update(inputs=[{**p["inputs"][0], "source_id":f"source-{i}"} for i in range(33)]))

    def test_no_fake_probabilities_or_model_for_abstention(self):
        self.reject(lambda p: p["forecast"].update(probabilities={"home":"1","draw":"0","away":"0"}))
        self.reject(lambda p: p.update(model={"name":"fake","version":"1","config_sha256":SHA}))

    def test_valid_exact_1x2_supplied_only(self):
        p = sample(); p["forecast"]={"kind":"ONE_X_TWO","probabilities":{"home":"0.40","draw":"0.30","away":"0.30"}}
        p["model"]={"name":"externally_supplied","version":"v1","config_sha256":SHA}
        f = freeze_packet(p)
        self.assertEqual(f.forecast_kind, "ONE_X_TWO")
        self.assertIn(b'"home":"0.4"', f.canonical_bytes)

    def test_decimal_rejects_rounding_ambiguity_and_types(self):
        for bad in (True, 0.4, "NaN", "Infinity", "-0.1", "1.1", "0.3333333333333333333", "0.3333333333333333e0"):
            def mutate(p):
                p["model"]={"name":"supplied","version":"v1","config_sha256":SHA}
                p["forecast"]={"kind":"ONE_X_TWO", "probabilities":{"home":bad,"draw":"0.3","away":"0.3"}}
            self.reject(mutate)
        def bad_total(p):
            p["model"]={"name":"supplied","version":"v1","config_sha256":SHA}
            p["forecast"]={"kind":"ONE_X_TWO", "probabilities":{"home":"0.333333333333333333","draw":"0.333333333333333333","away":"0.333333333333333333"}}
        self.reject(bad_total)

    def test_float_json_rejected_explicitly(self):
        raw=json.dumps(sample()).replace('"local_only": true', '"local_only": 1.0')
        with self.assertRaises(EvidenceError): freeze_packet(raw)

    def test_disallowed_nested_field_injection(self):
        self.reject(lambda p: p["inputs"][0].update(final_score="4-1"))
        self.reject(lambda p: p["capture"].update(new_field="x"))

    def test_no_network_or_clock_import_at_import_time(self):
        # The module intentionally exposes no transport, scheduling, or current-clock APIs.
        module=importlib.import_module("premfootballbot.prospective_evidence")
        self.assertFalse(hasattr(module,"requests"))
        self.assertFalse(hasattr(module,"urlopen"))
        self.assertFalse(hasattr(module,"now"))


class ClaimTests(unittest.TestCase):
    def setUp(self):
        self.f = freeze_packet(sample())

    def test_plausible_not_independently_verified(self):
        a=assess_untrusted_comment_metadata(self.f,metadata(self.f))
        self.assertEqual(a.status,"PLAUSIBLE_CLAIM_UNVERIFIED")
        self.assertTrue(a.external_audit_required)

    def test_fabricated_metadata_never_certifies(self):
        copied=metadata(self.f)
        copied["created_at"]="2027-01-08T00:00:00Z"
        copied["updated_at"]=copied["created_at"]
        self.assertNotEqual(assess_untrusted_comment_metadata(self.f,copied).status,"EXTERNALLY_CHECKED")

    def test_edited_or_late_comments_rejected(self):
        for change in (
            lambda m: m.update(updated_at="2027-01-09T13:00:00Z"),
            lambda m: m.update(created_at="2027-01-10T14:00:00Z",updated_at="2027-01-10T14:00:00Z"),
            lambda m: m.update(created_at="2027-01-10T15:00:00Z",updated_at="2027-01-10T15:00:00Z"),
            lambda m: m.update(body=m["body"].replace(self.f.commitment_sha256,SHA2)),
            lambda m: m.update(id="1234"),
            lambda m: m.update(html_url="https://otherhost.test/issues/1#issuecomment-1234"),
        ):
            m=metadata(self.f); change(m)
            self.assertEqual(assess_untrusted_comment_metadata(self.f,m).status,"REJECTED")

    def test_canceled_or_rescheduled_rejected(self):
        for status in ("CANCELLED","RESCHEDULED","POSTPONED"):
            self.assertEqual(assess_untrusted_comment_metadata(self.f,metadata(self.f),fixture_status=status).status,"REJECTED")

    def test_permalink_id_mismatch_rejected(self):
        m=metadata(self.f);m["id"]=9999
        self.assertEqual(assess_untrusted_comment_metadata(self.f,m).status,"REJECTED")

    def test_external_flag_is_not_accepted_as_independent_proof(self):
        a=assess_untrusted_comment_metadata(self.f,metadata(self.f),fixture_status="SCHEDULED")
        self.assertTrue(a.external_audit_required)
        self.assertNotEqual(a.status,"EXTERNALLY_CHECKED")

    def test_extraneous_comment_evidence_rejected(self):
        m=metadata(self.f);m["verified"]="by_me"
        self.assertEqual(assess_untrusted_comment_metadata(self.f,m).status,"REJECTED")


if __name__ == "__main__":
    unittest.main()
"""Phase 4C2-C0 invented/placeholder cases; no external feeds or predictions."""
import ast
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from premfootballbot import prospective_evidence as pe
from premfootballbot import odds_observations as oo
from premfootballbot import prematch_recorder as c0
from tests.test_prospective_evidence import sample
from tests.odds_evaluation_cases import quote, RAW

COMMIT = "a" * 40
TREE = "b" * 40


def invented_packet(*, cleared=False, forecast=False):
    p = sample()
    if cleared:
        p["inputs"][0].update(source_url="https://example.org/INVENTED",
                                content_sha256=hashlib.sha256(RAW).hexdigest(),
                                license_status="CLEARED")
    if forecast:
        p["forecast"] = {"kind": "ONE_X_TWO", "probabilities": {"home": "0.4", "draw": "0.3", "away": "0.3"}}
        p["model"] = {"name": "test", "version": "v1", "config_sha256": "a" * 64}
    return pe.freeze_packet(p)


def row(packet=None, odds=(), reason="NO_AUTHORIZED_MODEL", commit=COMMIT, tree=TREE, previous=None):
    return c0.capture_abstention(packet or invented_packet(), repo_commit=commit,
                                repo_tree=tree, reason=reason, odds=odds,
                                previous_sha256=previous)


class RecorderValidationTests(unittest.TestCase):
    def test_c0_only_no_forecast(self):
        r = row()
        p = c0.checked_capture(r)
        self.assertEqual(p["forecast_status"], "NO_FORECAST")
        self.assertIsNone(p["result_data"])
        self.assertEqual(p["assurance"], c0.ASSURANCE)
        self.assertEqual(p["timing_assurance"], "SELF_REPORTED_UNVERIFIED")
        self.assertEqual(p["source_rights"], "UNCLEARED_OR_EMPTY_REFERENCE_ONLY")
        self.assertEqual(p["evidence_packet"]["forecast"], {"kind": "NO_FORECAST"})
        self.assertIsNone(p["evidence_packet"]["model"])

    def test_blocked_source_not_recorded(self):
        p = sample()
        p["inputs"][0]["license_status"] = "BLOCKED"
        with self.assertRaises(c0.RecorderError): row(pe.freeze_packet(p))

    def test_existing_model_forecast_rejected(self):
        with self.assertRaises(c0.RecorderError): row(invented_packet(forecast=True))

    def test_no_fabricated_result_or_market_values(self):
        r = row()
        raw = json.loads(r.canonical_bytes)
        self.assertNotIn("probabilities", r.canonical_bytes.decode())
        self.assertNotIn("home_goals", r.canonical_bytes.decode())
        for patch in ({"result_data": {"home_goals": 2}},
                      {"forecast_status": "ONE_X_TWO"},
                      {"timing_assurance": "PROVEN"},
                      {"assurance": "EXTERNALLY_VERIFIED"}):
            p = dict(raw, **patch)
            with self.subTest(patch=patch), self.assertRaises(c0.RecorderError):
                c0.checked_capture_payload(p)

    def test_canonical_replay_and_source_identifiers(self):
        a = row()
        b = row()
        self.assertEqual(a, b)
        self.assertEqual(a.sha256, hashlib.sha256(c0.DOMAIN + a.canonical_bytes).hexdigest())
        self.assertEqual(c0.checked_capture_payload(json.loads(a.canonical_bytes)), a)
        self.assertEqual(c0.checked_capture(a)["repo_commit"], COMMIT)
        self.assertEqual(c0.checked_capture(a)["repo_tree"], TREE)

    def test_reject_changed_git_identity(self):
        for bad in ("main", "A" * 40, "a" * 39, "a" * 41, "z" * 40, None, True):
            with self.subTest(bad=bad), self.assertRaises(c0.RecorderError): row(commit=bad)
            with self.subTest(bad=bad), self.assertRaises(c0.RecorderError): row(tree=bad)

    def test_reason_allowlist(self):
        for reason in c0.REASONS:
            self.assertEqual(c0.checked_capture(row(reason=reason))["reason"], reason)
        for bad in ("FORECAST", "BET", "SUCCESS", "", 2, None):
            with self.assertRaises(c0.RecorderError): row(reason=bad)

    def test_reject_packet_changed_after_freeze(self):
        frozen = invented_packet()
        with self.assertRaises(c0.RecorderError): row(replace(frozen, commitment_sha256="0" * 64))
        with self.assertRaises(c0.RecorderError): c0.checked_capture(replace(row(), sha256="1" * 64))

    def test_packet_late_capture_rejected_by_existing_validator(self):
        p = sample()
        p["capture"]["captured_at_utc"] = "2027-01-10T14:01:00Z"
        with self.assertRaises(pe.EvidenceError): pe.freeze_packet(p)

    def test_immutability(self):
        with self.assertRaises(FrozenInstanceError):
            row().sha256 = "a" * 64


class QuoteBindingTests(unittest.TestCase):
    def ok(self, **kwargs):
        return oo.freeze_odds(quote(**kwargs))

    def test_cleared_quote_reuses_existing_odds_schema(self):
        q = self.ok()
        r = row(invented_packet(cleared=True), odds=(q,))
        p = c0.checked_capture(r)
        self.assertEqual(p["source_rights"], "ALL_CLEARED_CLAIMED")
        self.assertEqual(len(p["odds"]), 1)
        self.assertEqual(p["odds"][0]["market"], "1X2")
        self.assertEqual(oo.freeze_odds(p["odds"][0]), q)

    def test_ah_quote_retained_as_reference_not_scored(self):
        q = self.ok(market="AH", selection="AWAY", handicap_q=3)
        p = c0.checked_capture(row(invented_packet(cleared=True), odds=(q,)))
        self.assertEqual(p["odds"][0]["handicap_q"], 3)
        self.assertIsNone(p["result_data"])

    def test_unknown_and_blocked_odds_rejected(self):
        for value in ("UNKNOWN", "BLOCKED"):
            with self.subTest(value=value), self.assertRaises(c0.RecorderError):
                row(invented_packet(cleared=True), odds=(self.ok(rights_status=value),))

    def test_unknown_source_cannot_attach_quote(self):
        with self.assertRaises(c0.RecorderError): row(odds=(self.ok(),))

    def test_quote_without_source_digest_rejected(self):
        with self.assertRaises(c0.RecorderError):
            row(invented_packet(cleared=True), odds=(self.ok(source_content_sha256=None),))

    def test_wrong_fixture_and_roster_rejected(self):
        for change in ({"fixture_id": "WRONG"}, {"home": "Other FC"},
                       {"away": "Other FC"}, {"kickoff_utc": "2027-01-10T16:00:00Z"}):
            q = self.ok(**change)
            with self.subTest(change=change), self.assertRaises(c0.RecorderError):
                row(invented_packet(cleared=True), odds=(q,))

    def test_after_capture_or_cutoff_quote_denied(self):
        for time in ("2027-01-09T11:01:00Z", "2027-01-10T14:30:00Z"):
            q = self.ok(captured_at_utc=time, claimed_observed_at_utc=time,
                        independent_observed_at_utc=None)
            with self.subTest(time=time), self.assertRaises(c0.RecorderError):
                row(invented_packet(cleared=True), odds=(q,))

    def test_external_observation_after_cutoff_denied(self):
        q = self.ok(independent_observed_at_utc="2027-01-10T14:01:00Z")
        with self.assertRaises(c0.RecorderError):
            row(invented_packet(cleared=True), odds=(q,))

    def test_observation_after_packet_freeze_before_cutoff_denied(self):
        # The packet was frozen at 11:00; 12:00 remains before tomorrow's
        # cutoff, but its observation cannot be inside the earlier packet.
        q = self.ok(independent_observed_at_utc="2027-01-09T12:00:00Z")
        p = invented_packet(cleared=True)
        with self.assertRaises(c0.RecorderError):
            row(p, odds=(q,))
        valid = c0.checked_capture(row(p, odds=(self.ok(),)))
        valid["odds"][0]["independent_observed_at_utc"] = "2027-01-09T12:00:00Z"
        with self.assertRaises(c0.RecorderError):
            c0.checked_capture_payload(valid)

    def test_same_snapshot_selection_different_capture_time_denied(self):
        first = self.ok()
        second = self.ok(raw_price="3", captured_at_utc="2027-01-09T10:31:00Z")
        with self.assertRaises(c0.RecorderError):
            row(invented_packet(cleared=True), odds=(first, second))
        original = c0.checked_capture(row(invented_packet(cleared=True),
                                         odds=(first,)))
        original["odds"].append(oo.checked(second))
        with self.assertRaises(c0.RecorderError):
            c0.checked_capture_payload(original)

    def test_same_snapshot_distinct_selection_metadata_must_match(self):
        first = self.ok(selection="HOME")
        changed_time = self.ok(selection="AWAY", raw_price="3",
                               captured_at_utc="2027-01-09T10:31:00Z")
        with self.assertRaises(c0.RecorderError):
            row(invented_packet(cleared=True), odds=(first, changed_time))
        changed_snapshot = self.ok(selection="AWAY", raw_price="3",
                                   snapshot_id="INVENTED-SECOND",
                                   captured_at_utc="2027-01-09T10:31:00Z")
        accepted = row(invented_packet(cleared=True),
                       odds=(first, changed_snapshot))
        self.assertEqual(len(c0.checked_capture(accepted)["odds"]), 2)

    def test_quote_bound_to_unique_source_reference(self):
        p = sample()
        p["inputs"][0].update(content_sha256=hashlib.sha256(RAW).hexdigest(),
                                source_url="https://example.org/INVENTED", license_status="CLEARED")
        extra = dict(p["inputs"][0], source_id="other", license_status="BLOCKED")
        p["inputs"].append(extra)
        with self.assertRaises(c0.RecorderError):
            row(pe.freeze_packet(p), odds=(self.ok(),))

    def test_duplicate_quote_or_selection_denied(self):
        q = self.ok()
        with self.assertRaises(c0.RecorderError): row(invented_packet(cleared=True), odds=(q,q))
        with self.assertRaises(c0.RecorderError):
            row(invented_packet(cleared=True), odds=(q,self.ok(raw_price="3")))

    def test_invalid_odds_type_and_shape(self):
        for wrong in ([self.ok()], ("not-odds",), (row(),)):
            with self.assertRaises(c0.RecorderError): row(invented_packet(cleared=True), odds=wrong)
        with self.assertRaises(c0.RecorderError):
            row(invented_packet(cleared=True), odds=(self.ok(),)*33)


class LedgerTests(unittest.TestCase):
    def test_append_verify_and_roundtrip(self):
        first = c0.append_capture((), invented_packet(), repo_commit=COMMIT,
                                  repo_tree=TREE, reason="NO_AUTHORIZED_MODEL")
        next_packet = sample()
        next_packet["fixture"]["fixture_id"] = "DEMO-FAKE-2027-02"
        next_packet = pe.freeze_packet(next_packet)
        second = c0.append_capture(first, next_packet, repo_commit=COMMIT,
                                   repo_tree=TREE, reason="MISSING_PERMITTED_INPUTS",
                                   expected_head=first[-1].sha256)
        self.assertTrue(c0.verify_ledger(second, expected_head=second[-1].sha256))
        self.assertEqual(c0.load_ledger(c0.ledger_json(second),expected_head=second[-1].sha256),second)
        self.assertNotEqual(first[-1].sha256, second[-1].sha256)
        self.assertEqual(second[1].previous_sha256, first[0].sha256)

    def test_duplicate_fixture_model_cutoff_denied(self):
        first = (row(),)
        with self.assertRaises(c0.RecorderError):
            c0.append_capture(first, invented_packet(), repo_commit=COMMIT,
                              repo_tree=TREE, reason="NO_AUTHORIZED_MODEL")

    def test_new_model_version_same_fixture_allowed(self):
        first = (row(),)
        second = c0.append_capture(first, invented_packet(), repo_commit="c" * 40,
                                   repo_tree="d" * 40, reason="NO_AUTHORIZED_MODEL")
        self.assertEqual(len(second),2)

    def test_reject_missing_root_reorder_and_external_pin_mismatch(self):
        first = (row(),)
        second = c0.append_capture(first, invented_packet(), repo_commit="c" * 40,
                                   repo_tree="d" * 40, reason="OTHER_ABSTENTION")
        for entries in (second[1:],second[::-1],second+(second[0],)):
            with self.subTest(entries=entries), self.assertRaises(c0.RecorderError):
                c0.verify_ledger(entries)
        with self.assertRaises(c0.RecorderError):
            c0.verify_ledger(first,expected_head=second[-1].sha256)

    def test_resealed_full_ledger_still_needs_external_head(self):
        first = (row(),)
        fake = (row(reason="OTHER_ABSTENTION"),)
        self.assertTrue(c0.verify_ledger(fake))
        with self.assertRaises(c0.RecorderError):
            c0.verify_ledger(fake, expected_head=first[0].sha256)

    def test_corruption_or_noncanonical_input_rejected(self):
        raw = c0.ledger_json((row(),))
        for bad in (raw+b" ",raw.replace(b'"head_sha256"', b'"head_sha2562"'),
                    raw.replace(b'"NO_FORECAST"',b'"ONE_X_TWO"'),
                    b'{"protocol":"x","protocol":"y"}',b'{"a":NaN}',b'\xff'):
            with self.subTest(bad=bad[:30]), self.assertRaises((ValueError,KeyError)):
                c0.load_ledger(bad)

    def test_empty_ledger_explicit(self):
        self.assertEqual(c0.load_ledger(c0.ledger_json(())), ())
        with self.assertRaises(c0.RecorderError):
            c0.verify_ledger((),expected_head="a"*64)

    def test_rescheduled_kickoff_requires_new_fixture_capture(self):
        first = (row(),)
        new_packet = sample()
        new_packet["fixture"]["kickoff_utc"] = "2027-01-11T15:00:00Z"
        new_packet["cutoff_utc"] = "2027-01-11T14:00:00Z"
        next_ledger = c0.append_capture(first, pe.freeze_packet(new_packet), repo_commit=COMMIT,
                                        repo_tree=TREE, reason="UNKNOWN_FIXTURE")
        self.assertEqual(len(next_ledger), 2)
        self.assertNotEqual(first[0].kickoff_utc,next_ledger[-1].kickoff_utc)


class LocalCliTests(unittest.TestCase):
    def test_invented_file_record_then_verify_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            packet = p/"packet.json"
            packet.write_bytes(invented_packet().canonical_bytes)
            output = p/"first-ledger.json"
            result = c0.main(["record", "--packet",str(packet),"--out",str(output),
                              "--repo-commit",COMMIT,"--repo-tree",TREE,
                              "--reason","NO_AUTHORIZED_MODEL"])
            self.assertEqual(result,0)
            first = c0.load_ledger(output.read_bytes())
            self.assertEqual(len(first),1)
            self.assertEqual(c0.main(["verify","--ledger",str(output),
                                       "--expected-head",first[0].sha256]),0)
            with self.assertRaises(FileExistsError):
                c0.main(["record","--packet",str(packet),"--out",str(output),
                         "--repo-commit",COMMIT,"--repo-tree",TREE,
                         "--reason","NO_AUTHORIZED_MODEL"])
            self.assertEqual(c0.load_ledger(output.read_bytes()),first)

    def test_only_new_snapshot_file_allowed_and_previous_untouched(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)
            pkt= p/"packet.json"
            pkt.write_bytes(invented_packet().canonical_bytes)
            a=p/"a.json"
            c0.main(["record","--packet",str(pkt),"--out",str(a),"--repo-commit",COMMIT,
                     "--repo-tree",TREE,"--reason","NO_AUTHORIZED_MODEL"])
            before=a.read_bytes()
            newer=p/"b.json"
            with self.assertRaises(c0.RecorderError):
                c0.main(["record","--packet",str(pkt),"--out",str(newer),"--previous",str(a),
                         "--expected-head","f"*64,"--repo-commit","c"*40,"--repo-tree","d"*40,
                         "--reason","OTHER_ABSTENTION"])
            self.assertFalse(newer.exists())
            c0.main(["record","--packet",str(pkt),"--out",str(newer),"--previous",str(a),
                     "--expected-head",c0.load_ledger(before)[0].sha256,
                     "--repo-commit","c"*40,"--repo-tree","d"*40,"--reason","OTHER_ABSTENTION"])
            self.assertEqual(a.read_bytes(),before)
            self.assertEqual(len(c0.load_ledger(newer.read_bytes())),2)

    def test_writer_rejects_repository_path(self):
        with self.assertRaises(c0.RecorderError):
            c0._save_exclusive(Path(c0.__file__).parent.parent/"PRIVATE-SNAPSHOT.json",b'no')

    def test_no_network_clock_or_model_import(self):
        source=Path(c0.__file__).read_text(encoding="utf8")
        tree=ast.parse(source, feature_version=(3,10))
        imports=[x.module for x in ast.walk(tree) if isinstance(x,ast.ImportFrom)]
        for banned in ("weighted_poisson", "real_epl_training", "expected_goals", "shadow_pilot"):
            self.assertNotIn(banned, imports)
        for banned in ("requests", "urllib", "http.client", "datetime.now(", "date.today(",
                       "fit_invented_matches(", "fit_real_epl(", "score_1x2("):
            self.assertNotIn(banned,source)


if __name__ == "__main__":
    unittest.main()

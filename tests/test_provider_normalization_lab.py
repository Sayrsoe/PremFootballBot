"""All fixture IDs, clubs, odds and timestamps are fabricated for C1-A only."""
from dataclasses import FrozenInstanceError, replace
import copy
import hashlib
import json
import unittest
from unittest.mock import patch

from premfootballbot import provider_normalization_lab as lab

ALIAS = {"Example Town": "toy:town", "Example Albion": "toy:albion", "Example United": "toy:united"}
MAP_1X2 = {"toy:1": "HOME", "toy:x": "DRAW", "toy:2": "AWAY"}
MAP_AH = {"toy:1": "HOME", "toy:2": "AWAY"}


def fixture(**overrides):
    p = dict(record_kind=lab.STATUS, fixture_id="toy:fixture01", league="EPL",
             home="Example Town", away="Example Albion", kickoff_utc="2027-01-10T15:00:00Z",
             status="SCHEDULED", provider="toy:source1", source_url="https://example.invalid/fake-fixture",
             source_content_sha256="a" * 64, locally_observed_at_utc="2027-01-10T11:30:00Z")
    p.update(overrides)
    return p


def source_fixture(**overrides):
    return lab.normalize_fixture(fixture(**overrides), team_aliases=ALIAS)


def market(market="1X2", **overrides):
    p = dict(record_kind=lab.STATUS, fixture_id="toy:fixture01", home="toy:town",
             away="toy:albion", kickoff_utc="2027-01-10T15:00:00Z",
             provider="toy:source1", bookmaker="toy:book01", snapshot_id="toy:snap01",
             market=market, period="REGULATION_90", price_format="DECIMAL",
             quotes=([{"outcome_id": "toy:1", "line": None, "price": "2.125"},
                      {"outcome_id": "toy:x", "line": None, "price": "3.50"},
                      {"outcome_id": "toy:2", "line": None, "price": "3.20"}]
                     if market == "1X2" else
                     [{"outcome_id": "toy:1", "line": "-0.25", "price": "1.95"},
                      {"outcome_id": "toy:2", "line": "+0.25", "price": "1.93"}]),
             source_url="https://example.invalid/fake-snapshot",
             source_content_sha256="b" * 64,
             provider_ingested_at_utc="2027-01-10T12:56:00Z",
             bookmaker_claimed_updated_at_utc="2027-01-10T12:55:00Z",
             locally_acquired_at_utc="2027-01-10T12:57:00Z",
             snapshot_captured_at_utc="2027-01-10T12:59:00Z",
             independent_observed_at_utc="2027-01-10T12:58:00Z",
             cutoff_utc="2027-01-10T13:00:00Z")
    p.update(overrides)
    return p


def go(raw=None, *, fixture_record=None, outcome_map=None):
    p = raw if raw is not None else market()
    m = outcome_map if outcome_map is not None else (MAP_1X2 if p["market"] == "1X2" else MAP_AH)
    return lab.normalize_market(p, fixture=fixture_record or source_fixture(), outcome_map=m)


class FixtureTests(unittest.TestCase):
    def fail(self, change, code):
        raw = fixture()
        change(raw)
        with self.assertRaises(lab.NormalizationError) as error:
            lab.normalize_fixture(raw, team_aliases=ALIAS)
        self.assertEqual(error.exception.code, code)

    def test_canonical_stable_and_toy_only(self):
        a = source_fixture()
        b = source_fixture()
        self.assertEqual(a, b)
        self.assertEqual(a.sha256, hashlib.sha256(lab.DOMAIN + a.canonical_bytes).hexdigest())
        p = json.loads(a.canonical_bytes)
        self.assertEqual(p["home"], "toy:town")
        self.assertEqual(p["rights_status"], "UNKNOWN")
        self.assertEqual(p["assurance"], lab.ASSURANCE)
        self.assertNotIn("home_goals", p)

    def test_alias_casefold_determinism(self):
        p = source_fixture(home="example town", away="EXAMPLE ALBION")
        self.assertEqual(json.loads(p.canonical_bytes)["home"], "toy:town")

    def test_ambiguous_duplicate_mapping(self):
        aliases = {"Example Town": "toy:town", "EXAMPLE TOWN": "toy:united", "Example Albion": "toy:albion"}
        with self.assertRaisesRegex(lab.NormalizationError, "AMBIGUOUS_ALIAS"):
            lab.normalize_fixture(fixture(), team_aliases=aliases)

    def test_missing_alias_fails(self):
        self.fail(lambda p: p.update(away="Unknown Club"), "AMBIGUOUS_FIXTURE")

    def test_equal_home_away_fails(self):
        self.fail(lambda p: p.update(away="Example Town"), "AMBIGUOUS_FIXTURE")

    def test_bad_case_label_and_control_fail(self):
        for v in (" Example Town", "Example\nTown", "Example\u200bTown"):
            with self.subTest(v=v): self.fail(lambda p, v=v: p.update(home=v), "AMBIGUOUS_ALIAS")

    def test_reject_non_toy_fixture_provider(self):
        for key in ("fixture_id", "provider"):
            self.fail(lambda p, key=key: p.update({key: "real:epl-id"}), "NON_SYNTHETIC_ID")

    def test_reject_real_source_url(self):
        for value in ("https://the-odds-api.com/abc", "https://example.invalid/x?api_key=secret",
                      "http://example.invalid/a", "https://user:pass@example.invalid/a"):
            self.fail(lambda p, val=value: p.update(source_url=val), "SOURCE_URL")

    def test_disallow_clearance_and_blocked_rights(self):
        self.fail(lambda p: p.update(rights_status="CLEARED"), "RIGHTS_UNVERIFIED")
        self.fail(lambda p: p.update(rights_status="BLOCKED"), "RIGHTS_BLOCKED")
        self.fail(lambda p: p.update(rights_status="UNREVIEWED"), "RIGHTS_UNKNOWN")

    def test_unknown_rights_only(self):
        self.assertEqual(json.loads(source_fixture(rights_status="UNKNOWN").canonical_bytes)["rights_status"], "UNKNOWN")

    def test_results_and_unauthorized_fields_disallowed(self):
        for key in ("home_goals", "away_goals", "score", "result", "model", "forecast", "odds"):
            self.fail(lambda p, key=key: p.update({key: "no"}), "FORBIDDEN_FIELD")

    def test_unsupported_fixture_status(self):
        for status in ("FINISHED", "AWARDED", "ABANDONED", "POSTPONED", "CANCELLED"):
            self.fail(lambda p, status=status: p.update(status=status), "UNSUPPORTED_STATUS")

    def test_timestamp_strict_utc_and_before_kickoff(self):
        for value in ("2027-01-10T16:00:00Z", "2027-01-10T15:00:00Z"):
            self.fail(lambda p, v=value: p.update(locally_observed_at_utc=v), "FUTURE_INFORMATION")
        for value in ("2027-01-10T11:30:00+00:00", "2027-02-30T11:30:00Z", "2027-01-10", None):
            self.fail(lambda p, v=value: p.update(locally_observed_at_utc=v), "INVALID_UTC")

    def test_missing_fields(self):
        self.fail(lambda p: p.pop("kickoff_utc"), "MISSING_FIELD")

    def test_duplicate_ids_and_fixture_pair(self):
        a = fixture()
        with self.assertRaisesRegex(lab.NormalizationError, "DUPLICATE_FIXTURE"):
            lab.normalize_fixture_set((a, copy.deepcopy(a)), team_aliases=ALIAS)
        same_pair_other_id = fixture(fixture_id="toy:fixture02", home="Example Albion", away="Example Town")
        with self.assertRaisesRegex(lab.NormalizationError, "DUPLICATE_FIXTURE"):
            lab.normalize_fixture_set((a, same_pair_other_id), team_aliases=ALIAS)
        other = fixture(fixture_id="toy:fixture02", home="Example United", away="Example Albion")
        self.assertEqual(len(lab.normalize_fixture_set((a, other), team_aliases=ALIAS)), 2)

    def test_duplicate_set_type(self):
        with self.assertRaisesRegex(lab.NormalizationError, "INPUT_TYPE"):
            lab.normalize_fixture_set([fixture()], team_aliases=ALIAS)

    def test_forged_dataclass_rejected(self):
        rec = source_fixture()
        with self.assertRaisesRegex(lab.NormalizationError, "FORGED_FIXTURE"):
            go(fixture_record=replace(rec, sha256="0" * 64))
        with self.assertRaises(FrozenInstanceError):
            rec.sha256 = "0" * 64


class MarketTests(unittest.TestCase):
    def fail(self, change, code, market_kind="1X2", outcome_map=None):
        p = market(market_kind)
        change(p)
        with self.assertRaises(lab.NormalizationError) as error:
            go(p, outcome_map=outcome_map)
        self.assertEqual(error.exception.code, code)

    def test_1x2_canonical_and_no_forecast(self):
        x = go()
        self.assertEqual(x, go())
        p = json.loads(x.canonical_bytes)
        self.assertEqual(p["coverage"], "SYNTHETIC_NO_FORECAST_OR_MODEL")
        self.assertEqual(p["rights_status"], "UNKNOWN")
        self.assertEqual([q["selection"] for q in p["quotes"]], ["AWAY", "DRAW", "HOME"])
        self.assertEqual(p["quotes"][-1]["decimal_price"], "2.125")
        self.assertEqual(x.fixture_sha256, source_fixture().sha256)
        self.assertNotIn("probabilities", p)

    def test_order_invariance(self):
        a = market()
        b = market()
        b["quotes"].reverse()
        self.assertEqual(go(a), go(b))

    def test_explicit_outcome_map_mandatory(self):
        for mapping in ({"toy:1": "HOME", "toy:2": "AWAY"},
                        {"toy:1": "HOME", "toy:x": "HOME", "toy:2": "AWAY"},
                        {"toy:1": "HOME", "toy:x": "DRAW", "toy:2": "DRAW"}):
            with self.subTest(mapping=mapping), self.assertRaisesRegex(lab.NormalizationError, "AMBIGUOUS_OUTCOME"):
                go(outcome_map=mapping)
        with self.assertRaisesRegex(lab.NormalizationError, "NON_SYNTHETIC_ID"):
            lab.normalize_market(market(), fixture=source_fixture(), outcome_map={"1":"HOME","X":"DRAW","2":"AWAY"})

    def test_stale_claimed_publication_fails(self):
        self.fail(lambda p: p.update(provider_ingested_at_utc="2027-01-10T12:00:00Z",
                                     bookmaker_claimed_updated_at_utc="2027-01-10T11:59:00Z"), "STALE_SNAPSHOT")

    def test_stale_bookmaker_claim_fails(self):
        self.fail(lambda p: p.update(bookmaker_claimed_updated_at_utc="2027-01-10T12:00:00Z"),
                  "STALE_SNAPSHOT")

    def test_unhashable_outcome_is_structured_denial(self):
        self.fail(lambda p: p["quotes"][0].update(outcome_id={"evil":"object"}),
                  "NON_SYNTHETIC_ID")

    def test_reverse_fixture_identity(self):
        self.fail(lambda p: p.update(home="toy:albion",away="toy:town"), "FIXTURE_MISMATCH")

    def test_wrong_kickoff_or_fixture(self):
        self.fail(lambda p: p.update(kickoff_utc="2027-01-10T14:00:00Z"), "FIXTURE_MISMATCH")
        self.fail(lambda p: p.update(fixture_id="toy:other"), "FIXTURE_MISMATCH")

    def test_unknown_bookie_or_real_id(self):
        self.fail(lambda p: p.update(bookmaker="Pinnacle"), "NON_SYNTHETIC_ID")
        self.fail(lambda p: p.update(snapshot_id="real-id"), "NON_SYNTHETIC_ID")

    def test_no_real_feed_url_and_blocked_rights(self):
        self.fail(lambda p: p.update(source_url="https://oddspapi.io/v4/odds"), "SOURCE_URL")
        self.fail(lambda p: p.update(rights_status="CLEARED"), "RIGHTS_UNVERIFIED")
        self.fail(lambda p: p.update(rights_status="BLOCKED"), "RIGHTS_BLOCKED")

    def test_missing_and_invalid_price_notation(self):
        for value in (1.75, True, "1e2", "1,50", "-110", "0.9", "1.0", "NaN", " 1.5", "+1.5", "10001"):
            self.fail(lambda p, val=value: p["quotes"][0].update(price=val), "PRICE_FORMAT")

    def test_no_ambiguous_price_format(self):
        self.fail(lambda p: p.update(price_format="AMERICAN"), "PRICE_FORMAT")
        self.fail(lambda p: p.pop("price_format"), "MISSING_FIELD")

    def test_missing_1x2_or_duplicate(self):
        self.fail(lambda p: p["quotes"].pop(), "INCOMPLETE_MARKET")
        self.fail(lambda p: p["quotes"][2].update(outcome_id="toy:1"), "AMBIGUOUS_OUTCOME")

    def test_quote_injection_or_mixed_bookmakers(self):
        for name in ("bookmaker", "result", "model", "final_score", "captured_at_utc"):
            self.fail(lambda p, name=name: p["quotes"][0].update({name:"toy:evil"}), "FORBIDDEN_FIELD")

    def test_no_future_data_or_bad_order(self):
        for key,value in (
            ("provider_ingested_at_utc", "2027-01-10T13:03:00Z"),
            ("bookmaker_claimed_updated_at_utc", "2027-01-10T13:02:00Z"),
            ("locally_acquired_at_utc", "2027-01-10T12:54:00Z"),
            ("snapshot_captured_at_utc", "2027-01-10T13:01:00Z"),
            ("independent_observed_at_utc", "2027-01-10T13:10:00Z"),
            ("cutoff_utc", "2027-01-10T15:00:00Z"),
        ):
            self.fail(lambda p, k=key, v=value: p.update({k:v}), "FUTURE_INFORMATION")

    def test_timestamp_semantics_retained(self):
        p = json.loads(go().canonical_bytes)
        self.assertEqual(p["bookmaker_claimed_updated_at_utc"],"2027-01-10T12:55:00.000000Z")
        self.assertEqual(p["provider_ingested_at_utc"],"2027-01-10T12:56:00.000000Z")
        self.assertEqual(p["independent_timestamp_assurance"],"UNVERIFIED_CLAIM_ONLY")
        self.assertIsNone(json.loads(go(market(bookmaker_claimed_updated_at_utc=None,
                                              independent_observed_at_utc=None)).canonical_bytes)["independent_observed_at_utc"])

    def test_no_snapshot_after_independent_observation_claim(self):
        self.fail(lambda p: p.update(independent_observed_at_utc="2027-01-10T13:01:00Z"), "FUTURE_INFORMATION")

    def test_snapshot_age_max(self):
        with self.assertRaisesRegex(lab.NormalizationError,"STALE_SNAPSHOT"):
            lab.normalize_market(market(), fixture=source_fixture(), outcome_map=MAP_1X2,
                                 max_staleness_seconds=50)
        with self.assertRaisesRegex(lab.NormalizationError,"STALE_SNAPSHOT"):
            lab.normalize_market(market(), fixture=source_fixture(), outcome_map=MAP_1X2,
                                 max_staleness_seconds=1000)

    def test_results_or_unauthorized_prediction_fields(self):
        for field in ("result", "home_goals", "forecast", "model", "trained_model", "outcome"):
            self.fail(lambda p, f=field: p.update({f:None}), "FORBIDDEN_FIELD")

    def test_malformed_utc(self):
        for val in ("2027-01-10T12:56:00+07:00", "2027-02-30T12:56:00Z", 12345):
            self.fail(lambda p, v=val:p.update(provider_ingested_at_utc=v), "INVALID_UTC")

    def test_valid_ah_quarter_lines(self):
        for home,away,q in (("-0.25", "+0.25",-1),("+0.25", "-0.25",1),
                            ("-0.75", "+0.75",-3),("+0.75", "-0.75",3),
                            ("-1.50","+1.50",-6)):
            p = market("AH")
            p["quotes"][0]["line"] = home
            p["quotes"][1]["line"] = away
            r = go(p)
            values = {x["selection"]: x["line_q"] for x in json.loads(r.canonical_bytes)["quotes"]}
            self.assertEqual(values,{"HOME":q,"AWAY":-q})

    def test_wrong_ah_sign_and_missing_side(self):
        self.fail(lambda p: p["quotes"][1].update(line="-0.25"), "HANDICAP_SIGN", "AH")
        self.fail(lambda p: p["quotes"].pop(), "INCOMPLETE_MARKET", "AH")
        self.fail(lambda p: p["quotes"][0].update(line="-0.3"), "HANDICAP_LINE", "AH")
        self.fail(lambda p: p["quotes"][0].update(line=0.25), "HANDICAP_LINE", "AH")

    def test_mismatched_period(self):
        self.fail(lambda p: p.update(period="EXTRA_TIME"), "SCOPE", "AH")

    def test_1x2_line_forbidden(self):
        self.fail(lambda p: p["quotes"][0].update(line="0"), "HANDICAP_LINE")

    def test_ah_explicit_mapping_side_not_assumed(self):
        p = market("AH")
        with self.assertRaisesRegex(lab.NormalizationError,"AMBIGUOUS_OUTCOME"):
            go(p, outcome_map={"toy:1":"HOME","toy:2":"HOME"})
        flip={"toy:1":"AWAY","toy:2":"HOME"}
        r=go(p,outcome_map=flip)
        lines={v["selection"]:v["line_q"] for v in json.loads(r.canonical_bytes)["quotes"]}
        self.assertEqual(lines,{"HOME":1,"AWAY":-1})

    def test_malformed_fixture_reseal_fails(self):
        original=source_fixture()
        raw=json.loads(original.canonical_bytes)
        raw["fixture_id"]="real:fixture"
        encoded=lab._canon(raw)
        forged=lab.InventedFixture(encoded,hashlib.sha256(lab.DOMAIN+encoded).hexdigest(),"real:fixture",original.kickoff_utc)
        with self.assertRaisesRegex(lab.NormalizationError,"NON_SYNTHETIC_ID"):
            go(fixture_record=forged)

    def test_pure_offline_module(self):
        import ast
        from pathlib import Path
        source=Path(lab.__file__).read_text()
        for forbidden in ("requests", "urllib.request", "open(", "fit_real_epl", "fit_invented_matches",
                          "score_1x2", "current_time", "datetime.now", "time.time", "ProspectiveEvidence", "freeze_packet"):
            self.assertNotIn(forbidden,source)
        imports=[n.module for n in ast.walk(ast.parse(source)) if isinstance(n,ast.ImportFrom)]
        for name in ("weighted_poisson", "real_epl_training", "prematch_recorder", "shadow_pilot", "result_evaluation"):
            self.assertNotIn(name,imports)

if __name__ == "__main__":
    unittest.main()

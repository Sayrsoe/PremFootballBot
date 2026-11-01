"""Phase C1-C1 purely invented off-line security, identity and market regressions."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from decimal import Inexact, ROUND_DOWN, ROUND_HALF_UP, localcontext
import copy
import hashlib
import json
import unittest
from unittest.mock import patch

from premfootballbot import provider_contracts as c
from premfootballbot import provider_quarantine as q
from premfootballbot import fixture_crosswalk as f
from premfootballbot import provider_schema_lab as lab

SHA = "a" * 64
SOURCE = "toy:provider1"
BOOK = "toy:book1"
F_ID = "toy:fixture1"
KICK = "2026-11-10T15:00:00Z"
ACQUIRED = "2026-11-10T13:30:00Z"
CUTOFF = "2026-11-10T14:00:00Z"


def decision(*, status="CLEARED", purposes=("MARKET_QUALIFICATION",), previous_chain=(),
             reviewed="2026-11-09T10:00:00Z", effective="2026-11-09T11:00:00Z",
             expires="2026-12-01T00:00:00Z", subject=SOURCE):
    return q.new_rights_decision(subject=subject, status=status, purposes=purposes if status=="CLEARED" else (),
                                 reviewer="toy:reviewer", reviewed_utc=reviewed,
                                 effective_utc=effective, expires_utc=expires,
                                 evidence_sha256=SHA, previous_chain=previous_chain)


def profile(kind="AH"):
    outcomes = {"toy:one":"HOME", "toy:two":"AWAY"}
    if kind == "1X2":
        outcomes["toy:draw"] = "DRAW"
    return lab.make_market_profile(provider=SOURCE, bookmaker=BOOK, market=kind,
                                   market_id=("toy:ah" if kind=="AH" else "toy:result"),
                                   period="REGULATION_90", outcomes=outcomes,
                                   reviewer="toy:reviewer")


def fixture_rev(*, namespace=SOURCE, fixture_id=F_ID, kickoff=KICK,
                revision="1", status="TIMED"):
    return f.make_fixture_revision(namespace=namespace, provider_fixture_id=fixture_id,
                                   canonical_fixture_id="toy:canonical1",
                                   home_team_id="toy:home1", away_team_id="toy:away1",
                                   kickoff_utc=kickoff, status=status, revision=revision,
                                   season="2026-27", source_sha256=SHA)


def market_payload(p=None, kind="AH"):
    pr = p or profile(kind)
    return {
        "protocol":c.VERSION,"assurance":c.ASSURANCE,"provider":SOURCE,
        "fixture_id":F_ID,"fixture_revision":"1","bookmaker":BOOK,
        "market":kind,"market_id":("toy:ah" if kind=="AH" else "toy:result"),
        "period":"REGULATION_90","snapshot_id":"toy:snap1","kickoff_utc":KICK,
        "locally_acquired_at_utc":ACQUIRED,
        "snapshot_captured_at_utc":"2026-11-10T13:32:00Z",
        "source_observed_at_utc":"2026-11-10T13:31:00Z",
        "snapshot_reviewed_at_utc":"2026-11-10T13:35:00Z",
        "cutoff_utc":CUTOFF,
        "provider_updated_claim_utc":"2026-11-10T13:28:00Z",
        "bookmaker_published_claim_utc":"",
        "historical_created_claim_utc":"",
        "quotes":[
            dict(outcome_id="toy:one", bookmaker=BOOK, market_id="toy:ah" if kind=="AH" else "toy:result",
                 period="REGULATION_90", snapshot_id="toy:snap1", price="1.95",
                 line="-0.25" if kind=="AH" else None),
            dict(outcome_id="toy:two", bookmaker=BOOK, market_id="toy:ah" if kind=="AH" else "toy:result",
                 period="REGULATION_90", snapshot_id="toy:snap1", price="1.97",
                 line="+0.25" if kind=="AH" else None)
        ] + ([dict(outcome_id="toy:draw",bookmaker=BOOK,market_id="toy:result",
                  period="REGULATION_90",snapshot_id="toy:snap1",price="3.50",line=None)]
             if kind=="1X2" else [])
    }


def raw_market(p):
    return c.canonical(p)


def subject(*, kind="AH", payload=None, rights_chain=None):
    prof=profile(kind)
    history=rights_chain if rights_chain is not None else (decision(),)
    obj = payload if payload is not None else market_payload(prof,kind)
    bytes_=raw_market(obj)
    envelope=c.make_source_envelope(invented_bytes=bytes_,provider=SOURCE,fixture_id=F_ID,
                                     request_id="toy:req1",source_url="https://example.invalid/synthetic",
                                     acquisition_utc=ACQUIRED,rights_sha256=history[-1].sha256,
                                     profile_sha256=prof.sha256)
    return dict(raw_bytes=bytes_,source=envelope,profile=prof,
                fixture=fixture_rev(),rights_chain=history,pinned_rights_head=history[-1].sha256)


class ContractsTests(unittest.TestCase):
    def code(self, func, error):
        with self.assertRaises(c.ProviderContractError) as exc:
            func()
        self.assertEqual(exc.exception.code, error)

    def test_exact_price(self):
        self.assertEqual(c.exact_price("1.01000"),"1.01")
        self.assertEqual(c.exact_price("9999.999999999999"),"9999.999999999999")

    def test_exact_price_boundaries(self):
        for bad in ("1", "1.0000", "0.99", "10000.000000000001", "1e3", " 1.95", "+1.95", "1,95"):
            with self.subTest(bad=bad):
                self.code(lambda: c.exact_price(bad),"PRICE_FORMAT")

    def test_numeric_types_refused(self):
        for x in (float("nan"),float("inf"),1.95,True,None,[],{}):
            with self.subTest(x=repr(x)):
                self.code(lambda: c.exact_price(x),"PRICE_FORMAT")

    def test_quarter_signs(self):
        for text,expect in (("-19.75",-79),("+19.75",79),("+0.25",1),("-0.75",-3),("0",0)):
            self.assertEqual(c.quarter_units(text),expect)

    def test_quarter_bounds(self):
        for x in ("-0.3", "-0", "-0.00", "20.25", "-20.25", "1.234", "+.25", "1e3", "nan"):
            with self.subTest(line=x):
                self.code(lambda: c.quarter_units(x),"HANDICAP_LINE")

    def test_decimal_ambient_context_irrelevant(self):
        normal=(c.exact_price("1.01"), c.exact_price("9999.999999999999"),c.quarter_units("-19.75"))
        for prec in (1,2,6,28):
            for rounding in (ROUND_DOWN,ROUND_HALF_UP):
                with self.subTest(prec=prec,rounding=rounding), localcontext() as ctx:
                    ctx.prec=prec
                    ctx.rounding=rounding
                    ctx.traps[Inexact]=True
                    self.assertEqual((c.exact_price("1.01"),c.exact_price("9999.999999999999"),
                                      c.quarter_units("-19.75")),normal)

    def test_non_toy_ids(self):
        for x in ("real:123", "toy:UPPER", "toy:", "toy:abc?", None):
            self.code(lambda: c.toy(x),"NON_SYNTHETIC_ID")

    def test_source_url_restricted(self):
        for u in ("https://google.com/x", "http://example.invalid/x", "https://example.invalid/",
                  "https://example.invalid/x?key=secret", "https://user@example.invalid/x",
                  "https://example.invalid:443/x", "https://example.invalid/x#f"):
            self.code(lambda:c.invented_url(u),"SOURCE_URL")

    def test_utc_only(self):
        for dt in ("2026-11-10T15:00:00+00:00","2026-11-10T15:00:00","2026-02-30T01:00:00Z",KICK.lower()):
            self.code(lambda: c.utc(dt),"INVALID_UTC")

    def test_malformed_json(self):
        for raw in (b'{"x":1}',b'{"x":1e999}',b'{"x":NaN}',b'{"x":Infinity}',
                    b'{"x":1,"x":2}',b'["x"]',b'{"x":}',b'\xff',b''):
            self.code(lambda: c.decode_invented_json(raw),"MALFORMED_JSON")

    def test_nested_json_decode_rejected_with_code(self):
        for nested in (b'['*2000+b'"x"'+b']'*2000,
                       b'{"x":'*1000+b'"x"'+b'}'*1000):
            raw=b'{"assurance":'+nested+b'}'
            self.assertLess(len(raw),c.MAX_BYTES)
            self.code(lambda:c.decode_invented_json(raw),"MALFORMED_JSON")

    def test_nested_encoder_rejected(self):
        nested=[]
        cursor=nested
        for i in range(50):
            more=[]
            cursor.append(more)
            cursor=more
        self.code(lambda:c.canonical({"items":nested}),"MALFORMED_JSON")

    def test_oversize_json_rejected(self):
        self.code(lambda:c.decode_invented_json(b'{"x":"'+b'a'*c.MAX_BYTES+b'"}'),"MALFORMED_JSON")

    def test_canonical_replay(self):
        p={"protocol":c.VERSION,"assurance":c.ASSURANCE,"x":"hello"}
        self.assertEqual(c.decode_invented_json(c.canonical(p)),p)
        self.assertEqual(c.seal(p)[1],c.seal(copy.deepcopy(p))[1])

    def test_immutable_envelope(self):
        s=subject()
        with self.assertRaises(FrozenInstanceError):
            s["source"].sha256="bad"

    def test_source_envelope_replay(self):
        s=subject()
        self.assertEqual(c.verify_source_envelope(s["source"],s["raw_bytes"])["raw_sha256"],
                         hashlib.sha256(s["raw_bytes"]).hexdigest())

    def test_source_bytes_tamper(self):
        s=subject()
        self.code(lambda:c.verify_source_envelope(s["source"],s["raw_bytes"]+b' '),"SOURCE_MISMATCH")

    def test_envelope_metadata_tamper(self):
        s=subject()
        forged=replace(s["source"], fixture_id="toy:other")
        self.code(lambda:c.verify_source_envelope(forged,s["raw_bytes"]),"FORGED_ENVELOPE")

    def test_envelope_resealed_non_toy(self):
        s=subject()
        p=c.decode_invented_json(s["source"].canonical_bytes)
        p["provider"]="https://real-provider.io"
        raw,sha=c.seal(p)
        forged=replace(s["source"], canonical_bytes=raw,sha256=sha,provider=p["provider"])
        self.code(lambda:c.verify_source_envelope(forged,s["raw_bytes"]),"NON_SYNTHETIC_ID")

    def test_source_genuine_flag_refused(self):
        obj=market_payload();obj["assurance"]="GENUINE_EPL"
        self.code(lambda:subject(payload=obj),"NON_SYNTHETIC_SOURCE")


class QuarantineTests(unittest.TestCase):
    def code(self,func,error):
        with self.assertRaises(c.ProviderContractError) as exc:
            func()
        self.assertEqual(exc.exception.code,error)

    def test_purpose_specific_toy_clearance(self):
        d=decision()
        v=q.evaluate_rights(chain=(d,),expected_head=d.sha256,
                            subject=SOURCE,purpose="MARKET_QUALIFICATION",as_of_utc=ACQUIRED)
        self.assertEqual(v.status,"SIMULATED_ELIGIBLE_ONLY")
        self.assertEqual(v.assurance,c.ASSURANCE)

    def test_unknown_denied(self):
        d=decision(status="UNKNOWN")
        self.code(lambda:q.evaluate_rights(chain=(d,),expected_head=d.sha256,subject=SOURCE,
                         purpose="MARKET_QUALIFICATION",as_of_utc=ACQUIRED),"RIGHTS_UNKNOWN")

    def test_blocked_denied(self):
        d=decision(status="BLOCKED")
        self.code(lambda:q.evaluate_rights(chain=(d,),expected_head=d.sha256,subject=SOURCE,
                         purpose="MARKET_QUALIFICATION",as_of_utc=ACQUIRED),"RIGHTS_BLOCKED")

    def test_wrong_purpose_denied(self):
        d=decision(purposes=("FIXTURE_MAPPING",))
        self.code(lambda:q.evaluate_rights(chain=(d,),expected_head=d.sha256,subject=SOURCE,
                         purpose="MARKET_QUALIFICATION",as_of_utc=ACQUIRED),"RIGHTS_PURPOSE")

    def test_model_training_not_authorized(self):
        d=decision()
        self.code(lambda:q.evaluate_rights(chain=(d,),expected_head=d.sha256,subject=SOURCE,
                         purpose="MODEL_FITTING",as_of_utc=ACQUIRED),"RIGHTS_PURPOSE")

    def test_expired_denied(self):
        d=decision(expires="2026-11-10T12:00:00Z")
        self.code(lambda:q.evaluate_rights(chain=(d,),expected_head=d.sha256,subject=SOURCE,
                         purpose="MARKET_QUALIFICATION",as_of_utc=ACQUIRED),"RIGHTS_EXPIRED")

    def test_revoke_without_rewriting(self):
        first=decision()
        second=decision(status="BLOCKED",previous_chain=(first,),reviewed="2026-11-10T11:00:00Z",
                        effective="2026-11-10T11:01:00Z")
        self.assertEqual(len(q.verify_rights_chain((first,second),expected_head=second.sha256)),2)
        self.code(lambda:q.evaluate_rights(chain=(first,second),expected_head=second.sha256,
                         subject=SOURCE,purpose="MARKET_QUALIFICATION",as_of_utc=ACQUIRED),"RIGHTS_BLOCKED")

    def test_wrong_head_denied(self):
        d=decision()
        self.code(lambda:q.verify_rights_chain((d,),expected_head="f"*64),"RIGHTS_LINEAGE")

    def test_removed_revoke_detected_by_anchor(self):
        first=decision()
        second=decision(status="UNKNOWN",previous_chain=(first,),reviewed="2026-11-10T11:00:00Z",
                        effective="2026-11-10T11:02:00Z")
        self.code(lambda:q.verify_rights_chain((first,),expected_head=second.sha256),"RIGHTS_LINEAGE")

    def test_forged_decision_content(self):
        d=decision()
        bad=replace(d,sha256="f"*64)
        self.code(lambda:q.verify_rights_chain((bad,),expected_head="f"*64),"RIGHTS_LINEAGE")

    def test_rights_subject_not_copied(self):
        d=decision()
        self.code(lambda:q.evaluate_rights(chain=(d,),expected_head=d.sha256,
                         subject="toy:other",purpose="MARKET_QUALIFICATION",as_of_utc=ACQUIRED),"RIGHTS_SUBJECT")

    def test_cannot_backdate_new_clearance(self):
        self.code(lambda:decision(reviewed="2026-11-12T00:00:00Z",effective="2026-11-10T00:00:00Z"),
                  "RIGHTS_TIME")

    def test_revocation_metadata_not_introspectable_as_real_clearance(self):
        d=decision()
        self.assertEqual(c.decode_invented_json(d.canonical_bytes)["assurance"],c.ASSURANCE)
        self.assertEqual(d.status,"CLEARED")

    def test_three_decisions_chain(self):
        d1=decision()
        d2=decision(status="UNKNOWN",previous_chain=(d1,), reviewed="2026-11-10T09:00:00Z",
                    effective="2026-11-10T09:00:00Z")
        d3=decision(previous_chain=(d1,d2),reviewed="2026-11-10T10:00:00Z",
                    effective="2026-11-10T10:01:00Z")
        self.assertEqual(len(q.verify_rights_chain((d1,d2,d3),expected_head=d3.sha256)),3)

    def test_rights_effective_time_must_not_recede(self):
        old=decision()
        self.code(lambda:decision(previous_chain=(old,),
                  reviewed="2026-11-10T00:00:00Z", effective="2026-11-09T10:30:00Z"),
                  "RIGHTS_TIME")

    def test_resealed_wrong_purpose_cannot_grant_model(self):
        old=decision()
        payload=c.decode_invented_json(old.canonical_bytes)
        payload["purposes"]=["MODEL_FITTING"]
        raw,sha=c.seal(payload)
        forged=replace(old,canonical_bytes=raw,sha256=sha)
        self.code(lambda:q.verify_rights_chain((forged,),expected_head=sha),"RIGHTS_PURPOSE")

    def test_future_rights_decision_does_not_upgrade_previous_time(self):
        old=decision(status="UNKNOWN")
        later=decision(previous_chain=(old,), reviewed="2026-11-10T13:40:00Z",
                       effective="2026-11-10T13:41:00Z")
        self.code(lambda:q.evaluate_rights(chain=(old,later),expected_head=later.sha256,
                  subject=SOURCE,purpose="MARKET_QUALIFICATION",as_of_utc=ACQUIRED),
                  "RIGHTS_UNKNOWN")

    def test_empty_rights_history(self):
        self.code(lambda:q.verify_rights_chain((),expected_head=SHA),"RIGHTS_LINEAGE")


class CrosswalkTests(unittest.TestCase):
    def code(self,func,error):
        with self.assertRaises(c.ProviderContractError) as exc:
            func()
        self.assertEqual(exc.exception.code,error)

    def maps(self):
        return tuple(f.make_team_crosswalk(namespace=ns,provider_team_id=src,
                                           canonical_team_id=dest,season="2026-27",
                                           reviewer="toy:reviewer")
                     for ns in (SOURCE,"toy:provider2")
                     for src,dest in (("toy:home1","toy:town"),("toy:away1","toy:albion")))

    def test_match_explicit_mapping(self):
        left=fixture_rev()
        right=fixture_rev(namespace="toy:provider2")
        self.assertEqual(f.match_fixture_revisions(left,right,team_crosswalks=self.maps()),
                         "toy:canonical1")

    def test_reversed_orientation_denied(self):
        right=replace(fixture_rev(namespace="toy:provider2"),home_team_id="toy:away1",
                      away_team_id="toy:home1")
        self.code(lambda:f.match_fixture_revisions(fixture_rev(),right,team_crosswalks=self.maps()),
                  "FIXTURE_ORIENTATION")

    def test_ambiguous_alias_denied(self):
        maps=list(self.maps());maps.append(maps[-1])
        self.code(lambda:f.match_fixture_revisions(fixture_rev(),fixture_rev(namespace="toy:provider2"),
                    team_crosswalks=tuple(maps)),"AMBIGUOUS_CROSSWALK")

    def test_noninjective_mapping_denied(self):
        maps=list(self.maps()); maps[-1]=replace(maps[-1],canonical_team_id="toy:town")
        self.code(lambda:f.match_fixture_revisions(fixture_rev(),fixture_rev(namespace="toy:provider2"),
                  team_crosswalks=tuple(maps)),"AMBIGUOUS_CROSSWALK")

    def test_unknown_mapping_denied(self):
        maps=tuple(x for x in self.maps() if x.provider_team_id!="toy:away1")
        self.code(lambda:f.match_fixture_revisions(fixture_rev(),fixture_rev(namespace="toy:provider2"),
                  team_crosswalks=maps),"AMBIGUOUS_CROSSWALK")

    def test_postponed_denied(self):
        left=fixture_rev(status="POSTPONED")
        self.code(lambda:f.match_fixture_revisions(left,fixture_rev(namespace="toy:provider2"),
                  team_crosswalks=self.maps()),"FIXTURE_STATUS")

    def test_schedule_kickoff_disagreement(self):
        right=fixture_rev(namespace="toy:provider2",kickoff="2026-11-11T15:00:00Z")
        self.code(lambda:f.match_fixture_revisions(fixture_rev(),right,team_crosswalks=self.maps()),
                  "FIXTURE_REVISION")

    def test_revision_mismatch(self):
        right=fixture_rev(namespace="toy:provider2",revision="2")
        self.code(lambda:f.match_fixture_revisions(fixture_rev(),right,team_crosswalks=self.maps()),
                  "FIXTURE_REVISION")

    def test_second_fixture_conflict(self):
        right=replace(fixture_rev(namespace="toy:provider2"),canonical_fixture_id="toy:other")
        self.code(lambda:f.match_fixture_revisions(fixture_rev(),right,team_crosswalks=self.maps()),
                  "FIXTURE_IDENTITY")

    def test_revision_history_good(self):
        a=fixture_rev();b=fixture_rev(kickoff="2026-11-11T15:00:00Z",revision="2")
        self.assertIsNone(f.verify_revision_history((a,b)))

    def test_revision_history_duplicates(self):
        a=fixture_rev()
        self.code(lambda:f.verify_revision_history((a,a)),"FIXTURE_REVISION")

    def test_revision_history_wrong_fixture(self):
        a=fixture_rev(); b=fixture_rev(fixture_id="toy:another",revision="2")
        self.code(lambda:f.verify_revision_history((a,b)),"FIXTURE_IDENTITY")

    def test_forged_team_crosswalk_denied(self):
        entries=list(self.maps())
        entries[0]=replace(entries[0],provider_team_id="real:team")
        self.code(lambda:f.match_fixture_revisions(fixture_rev(),fixture_rev(namespace="toy:provider2"),
                  team_crosswalks=tuple(entries)),"NON_SYNTHETIC_ID")

    def test_forged_fixture_identity_denied(self):
        bad=replace(fixture_rev(),home_team_id="real:club")
        self.code(lambda:f.match_fixture_revisions(bad,fixture_rev(namespace="toy:provider2"),
                  team_crosswalks=self.maps()),"NON_SYNTHETIC_ID")

    def test_disallows_real_source(self):
        self.code(lambda:fixture_rev(namespace="real:provider"),"NON_SYNTHETIC_ID")


class MarketSchemaTests(unittest.TestCase):
    def code(self,func,error):
        with self.assertRaises(c.ProviderContractError) as exc:
            func()
        self.assertEqual(exc.exception.code,error)

    def evaluate(self,kwargs=None):
        return lab.normalize_invented_market(**(kwargs or subject()))

    def corrupt(self,change,code,kind="AH"):
        data=market_payload(kind=kind)
        change(data)
        self.code(lambda:self.evaluate(subject(kind=kind,payload=data)),code)

    def test_valid_ah_invented_only(self):
        val=self.evaluate()
        payload=c.decode_invented_json(val.canonical_bytes)
        self.assertEqual(payload["eligibility"],"SIMULATED_ONLY_NOT_C0_OR_MODEL")
        self.assertEqual({r["selection"]:int(r["line_q"]) for r in payload["quotes"]},
                         {"HOME":-1,"AWAY":1})
        self.assertEqual(val.assurance,c.ASSURANCE)

    def test_valid_1x2_invented_only(self):
        result=self.evaluate(subject(kind="1X2"))
        p=c.decode_invented_json(result.canonical_bytes)
        self.assertEqual({r["selection"] for r in p["quotes"]},{"HOME","DRAW","AWAY"})
        self.assertTrue(all(r["line_q"]=="" for r in p["quotes"]))

    def test_real_numeric_json_token_denied(self):
        ctx=subject()
        malicious=ctx["raw_bytes"].replace(b'"price":"1.95"',b'"price":1e999')
        self.code(lambda:lab.normalize_invented_market(malicious,source=ctx["source"],
                  profile=ctx["profile"],fixture=ctx["fixture"],
                  rights_chain=ctx["rights_chain"],pinned_rights_head=ctx["pinned_rights_head"]),
                  "MALFORMED_JSON")

    def test_quote_order_invariance(self):
        data=market_payload()
        x=self.evaluate(subject(payload=data))
        data["quotes"].reverse()
        y=self.evaluate(subject(payload=data))
        self.assertEqual(c.decode_invented_json(x.canonical_bytes)["quotes"],
                         c.decode_invented_json(y.canonical_bytes)["quotes"])

    def test_missing_ah_side(self):
        self.corrupt(lambda p:p["quotes"].pop(),"INCOMPLETE_MARKET")

    def test_duplicate_selection(self):
        self.corrupt(lambda p:p["quotes"][1].update(outcome_id="toy:one"),"AMBIGUOUS_OUTCOME")

    def test_wrong_selection_id(self):
        self.corrupt(lambda p:p["quotes"][1].update(outcome_id="toy:unknown"),"AMBIGUOUS_OUTCOME")

    def test_inverted_signs(self):
        self.corrupt(lambda p:p["quotes"][1].update(line="-0.25"),"HANDICAP_SIGN")

    def test_unsupported_ah_line(self):
        self.corrupt(lambda p:p["quotes"][1].update(line="0.3"),"HANDICAP_LINE")

    def test_mixed_books(self):
        self.corrupt(lambda p:p["quotes"][1].update(bookmaker="toy:book2"),"MIXED_SNAPSHOT")

    def test_mixed_snapshots(self):
        self.corrupt(lambda p:p["quotes"][1].update(snapshot_id="toy:snap2"),"MIXED_SNAPSHOT")

    def test_market_period_mismatch(self):
        self.corrupt(lambda p:p["quotes"][1].update(period="HALF_TIME"),"MIXED_SNAPSHOT")

    def test_market_id_mismatch(self):
        self.corrupt(lambda p:p.update(market_id="toy:other"),"MARKET_SCOPE")

    def test_no_1x2_handicap(self):
        self.corrupt(lambda p:p["quotes"][0].update(line="0"),"HANDICAP_LINE",kind="1X2")

    def test_forbidden_result_injection(self):
        self.corrupt(lambda p:p.update(home_goals="4"),"FORBIDDEN_FIELD")

    def test_forbidden_predictions_injection(self):
        self.corrupt(lambda p:p.update(model_probabilities={"home":"0.5"}),"FORBIDDEN_FIELD")

    def test_post_kickoff_acquisition(self):
        data=market_payload()
        data["locally_acquired_at_utc"]="2026-11-10T16:00:00Z"
        self.code(lambda:self.evaluate(subject(payload=data)),"SOURCE_MISMATCH")
        # Even when the source metadata matches, a post-kickoff acquisition is denied.
        src=subject(payload=data)
        env=src["source"]
        src["source"]=c.make_source_envelope(invented_bytes=src["raw_bytes"],provider=SOURCE,fixture_id=F_ID,
                                               request_id="toy:req1",source_url="https://example.invalid/example",
                                               acquisition_utc=data["locally_acquired_at_utc"],
                                               rights_sha256=src["pinned_rights_head"],
                                               profile_sha256=src["profile"].sha256)
        self.code(lambda:self.evaluate(src),"TEMPORAL_LEAKAGE")

    def test_review_before_capture(self):
        self.corrupt(lambda p:p.update(snapshot_reviewed_at_utc="2026-11-10T13:29:00Z"),
                     "TEMPORAL_LEAKAGE")

    def test_source_observation_after_capture(self):
        self.corrupt(lambda p:p.update(source_observed_at_utc="2026-11-10T13:34:00Z"),
                     "TEMPORAL_LEAKAGE")

    def test_review_after_cutoff(self):
        self.corrupt(lambda p:p.update(snapshot_reviewed_at_utc="2026-11-10T14:01:00Z"),
                     "TEMPORAL_LEAKAGE")

    def test_false_bookmaker_claim_future(self):
        self.corrupt(lambda p:p.update(bookmaker_published_claim_utc="2026-11-10T14:55:00Z"),
                     "TEMPORAL_LEAKAGE")

    def test_historical_created_claim_is_not_pre_kickoff_proof(self):
        data=market_payload();data["historical_created_claim_utc"]="2026-11-10T12:00:00Z"
        val=self.evaluate(subject(payload=data))
        self.assertEqual(c.decode_invented_json(val.canonical_bytes)["eligibility"],
                         "SIMULATED_ONLY_NOT_C0_OR_MODEL")

    def test_unknown_rights_denied(self):
        bad=subject(rights_chain=(decision(status="UNKNOWN"),))
        self.code(lambda:self.evaluate(bad),"RIGHTS_UNKNOWN")

    def test_blocked_rights_denied(self):
        bad=subject(rights_chain=(decision(status="BLOCKED"),))
        self.code(lambda:self.evaluate(bad),"RIGHTS_BLOCKED")

    def test_expired_rights_denied(self):
        bad=subject(rights_chain=(decision(expires="2026-11-10T12:00:00Z"),))
        self.code(lambda:self.evaluate(bad),"RIGHTS_EXPIRED")

    def test_changed_rights_head_denied(self):
        bad=subject();bad["pinned_rights_head"]="f"*64
        self.code(lambda:self.evaluate(bad),"SOURCE_MISMATCH")

    def test_changed_profile_sha_denied(self):
        bad=subject();bad["profile"]=replace(bad["profile"],sha256="f"*64)
        self.code(lambda:self.evaluate(bad),"FORGED_PROFILE")

    def test_reversed_profile_mapping_prohibited_if_ambiguous(self):
        self.code(lambda:lab.make_market_profile(provider=SOURCE,bookmaker=BOOK,
                  market="AH",market_id="toy:ah",period="REGULATION_90",
                  outcomes={"toy:one":"HOME","toy:two":"HOME"},reviewer="toy:reviewer"),
                  "AMBIGUOUS_OUTCOME")

    def test_forged_market_profile_denied(self):
        original=profile()
        self.code(lambda:lab.verify_market_profile(replace(original,sha256="f"*64)),"FORGED_PROFILE")

    def test_rejected_non_toy_bookmaker(self):
        self.corrupt(lambda p:p.update(bookmaker="real:pinnacle"),"NON_SYNTHETIC_ID")

    def test_rescheduled_fixture_denied(self):
        obj=subject();obj["fixture"]=fixture_rev(kickoff="2026-11-11T15:00:00Z",revision="2")
        self.code(lambda:self.evaluate(obj),"FIXTURE_REVISION")

    def test_provider_data_never_called_into_existing_models(self):
        obj=subject()
        with patch("premfootballbot.provider_normalization_lab.normalize_market",side_effect=AssertionError("C1-A called")), \
             patch("premfootballbot.prospective_evidence.freeze_packet",side_effect=AssertionError("evidence called")), \
             patch("premfootballbot.odds_observations.freeze_odds",side_effect=AssertionError("odds called")):
            self.assertEqual(self.evaluate(obj).assurance,c.ASSURANCE)

    def test_pure_modules_no_io_imports(self):
        import ast
        from pathlib import Path
        for module in (c,q,f,lab):
            source=Path(module.__file__).read_text()
            tree=ast.parse(source)
            imports={x.module for x in ast.walk(tree) if isinstance(x,ast.ImportFrom)}
            imports.update(x.names[0].name for x in ast.walk(tree)
                           if isinstance(x,ast.Import) and x.names)
            for forbidden in ("requests","httpx","socket","subprocess","os","time", "pathlib"):
                self.assertNotIn(forbidden,imports)
            for unsafe in ("datetime.now(","time.time(","open(","fit_real_epl", "score_1x2(",
                           "freeze_packet(","freeze_odds(","requests.get("):
                self.assertNotIn(unsafe,source)


if __name__ == "__main__":
    unittest.main()

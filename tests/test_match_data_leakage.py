"""Independent as-of scenarios; expected histories do not use production filters."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest

from premfootballbot.match_data import parse_synthetic_json, select_as_of
from tests.match_data_cases import document, encode, one_result

def at(text):
    return datetime.fromisoformat(text.replace("Z","+00:00"))

def chosen(payload,cutoff,**kwargs):
    batch=parse_synthetic_json(encode(payload)).require_valid()
    return select_as_of(batch,at(cutoff),**kwargs)

class IndependentLeakageTests(unittest.TestCase):
    def test_before_and_after_result_publication(self):
        payload=one_result()
        for time,expected in (("2026-08-01T13:00:00Z",0),
                              ("2026-08-01T15:59:59Z",0),
                              ("2026-08-01T16:00:00Z",0),
                              ("2026-08-01T16:00:00.000001Z",1)):
            self.assertEqual(len(chosen(payload,time).observations),expected,time)

    def test_correction_never_leaks_into_old_cutoff(self):
        payload=document()
        old=chosen(payload,"2026-08-02T00:00:00Z").observations
        new=chosen(payload,"2026-08-04T00:00:00Z").observations
        self.assertEqual([(r.revision,r.home_goals_90) for r in old],[(1,0)])
        self.assertEqual([(r.revision,r.home_goals_90) for r in new],[(2,1)])

    def test_sweep_cutoffs_against_hand_written_publication_history(self):
        payload=document()
        payload["records"]=payload["records"][:3]
        start=at("2026-08-01T00:00:00Z")
        batch=parse_synthetic_json(encode(payload)).require_valid()
        for minute in range(0,4*24*60,7):
            cutoff=start+timedelta(minutes=minute)
            expected=[] if cutoff<=at("2026-08-01T16:00:00Z") else [
                1 if cutoff<=at("2026-08-03T09:00:00Z") else 2]
            self.assertEqual([r.revision for r in select_as_of(batch,cutoff).observations],expected)

    def test_latest_observed_withdrawal_does_not_resurrect_old_result(self):
        payload=one_result()
        correction=deepcopy(payload["records"][0])
        correction.update(revision=1,supersedes_revision=0,status="AWARDED",
                          home_goals_90=None,away_goals_90=None,result_basis=None,
                          available_at_utc="2026-08-02T10:00:00Z")
        payload["records"].append(correction)
        self.assertEqual(len(chosen(payload,"2026-08-02T09:00:00Z").observations),1)
        result=chosen(payload,"2026-08-02T11:00:00Z")
        self.assertFalse(result.observations)
        self.assertIn("NOT_FINISHED_FT90",{e.reason for e in result.exclusions})

    def test_latest_coarse_revision_cannot_fall_back_to_precise(self):
        payload=one_result()
        revised=deepcopy(payload["records"][0])
        revised.update(revision=1,supersedes_revision=0,kickoff_utc=None,
                       kickoff_precision="date_only",match_date="2026-08-01",
                       available_at_utc="2026-08-02T10:00:00Z")
        payload["records"].append(revised)
        self.assertFalse(chosen(payload,"2026-09-01T00:00:00Z").observations)

    def test_latest_blocked_revision_cannot_fall_back_to_cleared(self):
        payload=one_result()
        doc=deepcopy(payload["source_documents"][0])
        doc.update(source_document_id="synthetic:demo:document:blocked",
                   licence_status="BLOCKED")
        payload["source_documents"].append(doc)
        revised=deepcopy(payload["records"][0])
        revised.update(revision=1,supersedes_revision=0,available_at_utc="2026-08-02T10:00:00Z",
                       source_document_id=doc["source_document_id"],licence_status="BLOCKED")
        payload["records"].append(revised)
        self.assertFalse(chosen(payload,"2026-08-03T00:00:00Z").observations)

    def test_unknown_higher_revision_quarantines_older_result(self):
        payload=one_result()
        revised=deepcopy(payload["records"][0])
        revised.update(revision=1,supersedes_revision=0,available_at_utc=None,
                       home_goals_90=2)
        payload["records"].append(revised)
        result=chosen(payload,"2026-09-01T00:00:00Z")
        self.assertFalse(result.observations)
        self.assertIn("UNCERTAIN_REVISION",{e.reason for e in result.exclusions})

    def test_known_successor_can_resolve_unknown_earlier_revision(self):
        payload=one_result(available_at_utc=None)
        revised=deepcopy(payload["records"][0])
        revised.update(revision=1,supersedes_revision=0,
                       available_at_utc="2026-08-02T10:00:00Z",home_goals_90=2)
        payload["records"].append(revised)
        self.assertEqual([r.revision for r in chosen(payload,"2026-08-03T00:00:00Z").observations],[1])

    def test_null_availability_never_uses_retrieved_or_kickoff(self):
        result=chosen(one_result(available_at_utc=None),"2027-01-01T00:00:00Z")
        self.assertFalse(result.observations)
        self.assertIn("UNKNOWN_AVAILABILITY",{e.reason for e in result.exclusions})

    def test_all_nonfinished_statuses_excluded(self):
        for status in ("SCHEDULED","TIMED","IN_PLAY","POSTPONED","CANCELLED",
                       "ABANDONED","AWARDED","SUSPENDED"):
            payload=one_result(record_type="fixture",status=status,
                               home_goals_90=None,away_goals_90=None,result_basis=None)
            self.assertFalse(chosen(payload,"2027-01-01T00:00:00Z").observations,status)

    def test_coarse_result_never_enters_exact_cutoff_selection(self):
        for precision,date in (("date_only","2026-08-01"),("unknown",None)):
            payload=one_result(kickoff_utc=None,kickoff_precision=precision,match_date=date)
            self.assertFalse(chosen(payload,"2027-01-01T00:00:00Z").observations)

    def test_all_licence_states_gate_selection(self):
        for state in ("CLEARED","UNKNOWN","BLOCKED"):
            payload=one_result(licence_status=state)
            payload["source_documents"][0]["licence_status"]=state
            self.assertEqual(len(chosen(payload,"2027-01-01T00:00:00Z").observations),
                             1 if state=="CLEARED" else 0)

    def test_synthetic_results_cannot_enter_real_selection(self):
        self.assertFalse(chosen(one_result(),"2027-01-01T00:00:00Z",
                                include_synthetic=False).observations)
        with self.assertRaises(TypeError):
            chosen(one_result(),"2027-01-01T00:00:00Z",include_synthetic=1)

    def test_cutoff_requires_aware_datetime(self):
        batch=parse_synthetic_json(encode(one_result())).require_valid()
        for bad in (datetime(2026,9,1),"2026-09-01",None):
            with self.assertRaises((TypeError,ValueError)):
                select_as_of(batch,bad)
        first=select_as_of(batch,at("2026-09-01T00:00:00Z"))
        other=select_as_of(batch,at("2026-09-01T07:00:00+07:00"))
        self.assertEqual(first,other)

    def test_postponed_and_future_fixtures_never_supply_outcomes(self):
        payload=document()
        payload["records"]=[r for r in payload["records"] if r["fixture_id"].endswith(":b")]
        self.assertFalse(chosen(payload,"2026-08-05T00:00:00Z").observations)

if __name__=="__main__":
    unittest.main()

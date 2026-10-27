"""Independent chronological selection and estimator boundary regressions."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from premfootballbot.expected_goals import (
    ExpectedGoalsError, ModelConfig, fit_expected_goals, fit_rate_ratio, predict_expected_goals,
)
from premfootballbot.match_data import parse_synthetic_json, select_as_of
from tests.expected_goals_cases import batch, payload, parse, team, target, CUTOFF, NS

def stamp(text):
    return datetime.fromisoformat(text.replace("Z","+00:00"))

def corrected(raw, **updates):
    new=deepcopy(raw["records"][0])
    new.update(revision=1,supersedes_revision=0,available_at_utc="2026-09-01T10:00:00Z")
    new.update(updates)
    raw["records"].append(new)
    return new

class ExpectedGoalsLeakageTests(unittest.TestCase):
    def test_strict_result_publication_boundary(self):
        raw=payload([("a","b",2,1)])
        t=stamp(raw["records"][0]["available_at_utc"])
        for cutoff in (t-timedelta(microseconds=1),t):
            with self.assertRaises(ExpectedGoalsError) as caught:
                fit_expected_goals(parse(raw),cutoff)
            self.assertEqual(caught.exception.code,"EMPTY_TRAINING")
        model=fit_expected_goals(parse(raw),t+timedelta(microseconds=1))
        self.assertEqual(len(model.training.rows),1)

    def test_future_rows_do_not_enter_fit(self):
        raw=payload()
        cutoff=stamp("2026-08-03T00:00:00Z")
        model=fit_expected_goals(parse(raw),cutoff)
        self.assertEqual(len(model.training.rows),2)
        self.assertTrue(all(r.available_at_utc<cutoff for r in model.training.rows))
        self.assertEqual(dict(model.training.excluded_reasons)["NOT_YET_AVAILABLE"],4)

    def test_late_correction_is_visible_only_after_publication(self):
        raw=payload()
        corrected(raw,home_goals_90=2,away_goals_90=2)
        cutoff=stamp("2026-09-01T10:00:00Z")
        before=fit_expected_goals(parse(raw),cutoff)
        after=fit_expected_goals(parse(raw),cutoff+timedelta(microseconds=1))
        old=next(r for r in before.training.rows if r.fixture_id==raw["records"][0]["fixture_id"])
        new=next(r for r in after.training.rows if r.fixture_id==old.fixture_id)
        self.assertEqual((old.revision,old.away_goals_90),(0,1))
        self.assertEqual((new.revision,new.away_goals_90),(1,2))
        self.assertNotEqual(before.training.row_hash,after.training.row_hash)
        self.assertNotEqual(before.theta,after.theta)
        # No assertion about an unproved individual-parameter direction.

    def test_withdrawn_result_is_removed_without_fallback(self):
        raw=payload()
        row=corrected(raw,status="AWARDED",home_goals_90=None,away_goals_90=None,result_basis=None)
        model=fit_expected_goals(parse(raw),CUTOFF)
        self.assertNotIn(row["fixture_id"],{r.fixture_id for r in model.training.rows})
        self.assertEqual(len(model.training.rows),5)
        reasons=dict(model.training.excluded_reasons)
        self.assertEqual(reasons["NOT_FINISHED_FT90"],1)
        self.assertEqual(reasons["SUPERSEDED"],1)

    def test_unknown_higher_revision_quarantines_old_result(self):
        raw=payload()
        row=corrected(raw,available_at_utc=None,away_goals_90=2)
        model=fit_expected_goals(parse(raw),CUTOFF)
        self.assertNotIn(row["fixture_id"],{r.fixture_id for r in model.training.rows})
        self.assertIn("UNCERTAIN_REVISION",dict(model.training.excluded_reasons))

    def test_unknown_initial_availability_never_uses_retrieval(self):
        raw=payload()
        raw["records"][0]["available_at_utc"]=None
        model=fit_expected_goals(parse(raw),CUTOFF)
        self.assertEqual(len(model.training.rows),5)
        self.assertEqual(dict(model.training.excluded_reasons)["UNKNOWN_AVAILABILITY"],1)

    def test_licence_unknown_or_blocked_excludes_latest(self):
        for state in ("UNKNOWN","BLOCKED"):
            raw=payload()
            doc=deepcopy(raw["source_documents"][0])
            doc.update(source_document_id=NS+":document:blocked",licence_status=state)
            raw["source_documents"].append(doc)
            row=corrected(raw,source_document_id=doc["source_document_id"],licence_status=state)
            model=fit_expected_goals(parse(raw),CUTOFF)
            self.assertNotIn(row["fixture_id"],{r.fixture_id for r in model.training.rows})
            self.assertEqual(dict(model.training.excluded_reasons)["LICENCE_NOT_CLEARED"],1)

    def test_coarse_and_unknown_kickoffs_excluded(self):
        for precision,day in (("date_only","2026-08-01"),("unknown",None)):
            raw=payload()
            raw["records"][0].update(kickoff_precision=precision,kickoff_utc=None,match_date=day)
            model=fit_expected_goals(parse(raw),CUTOFF)
            self.assertEqual(len(model.training.rows),5)
            self.assertEqual(dict(model.training.excluded_reasons)["COARSE_KICKOFF"],1)

    def test_non_ft90_statuses_excluded(self):
        for status in ("SCHEDULED","POSTPONED","ABANDONED","AWARDED","SUSPENDED","CANCELLED"):
            raw=payload()
            raw["records"][0].update(record_type="fixture",status=status,home_goals_90=None,
                                     away_goals_90=None,result_basis=None)
            model=fit_expected_goals(parse(raw),CUTOFF)
            self.assertEqual(len(model.training.rows),5,status)

    def test_retrieval_changes_do_not_affect_fit_or_hashes(self):
        raw=payload()
        first=fit_expected_goals(parse(raw),CUTOFF)
        for row in raw["records"]:
            row["retrieved_at_utc"]="2027-01-01T00:00:00Z"
        second=fit_expected_goals(parse(raw),CUTOFF)
        self.assertEqual(first.theta,second.theta)
        self.assertEqual(first.training.row_hash,second.training.row_hash)
        self.assertEqual(first.training.batch_hash,second.training.batch_hash)

    def test_inter_availability_cutoffs_preserve_training(self):
        raw=payload()
        first=fit_expected_goals(parse(raw),stamp("2026-08-07T00:00:00Z"))
        second=fit_expected_goals(parse(raw),stamp("2026-08-30T00:00:00Z"))
        self.assertEqual(first.theta,second.theta)
        self.assertEqual(first.training.row_hash,second.training.row_hash)

    def test_cutoff_must_strictly_precede_target(self):
        model=fit_expected_goals(batch(),CUTOFF)
        for kickoff in (CUTOFF,CUTOFF-timedelta(microseconds=1)):
            with self.assertRaises(ExpectedGoalsError) as caught:
                predict_expected_goals(model,**target(target_kickoff_utc=kickoff))
            self.assertEqual(caught.exception.code,"CUTOFF_AFTER_KICKOFF")

    def test_prediction_cannot_relabel_a_later_fit_as_earlier_cutoff(self):
        model=fit_expected_goals(batch(),CUTOFF)
        for cutoff in (CUTOFF-timedelta(days=1),CUTOFF+timedelta(hours=1)):
            with self.assertRaises(ExpectedGoalsError) as caught:
                predict_expected_goals(model,**target(cutoff_utc=cutoff))
            self.assertEqual(caught.exception.code,"CUTOFF_MISMATCH")

    def test_target_fixture_cannot_be_in_training(self):
        model=fit_expected_goals(batch(),CUTOFF)
        with self.assertRaises(ExpectedGoalsError) as caught:
            predict_expected_goals(model,**target(target_fixture_id=model.training.rows[0].fixture_id))
        self.assertEqual(caught.exception.code,"TARGET_IN_TRAINING")

    def test_metadata_provenance_warning_always_present(self):
        result=predict_expected_goals(fit_expected_goals(batch(),CUTOFF),**target())
        self.assertIn("TARGET_METADATA_UNVERIFIED",result.warnings)

    def test_naive_or_non_utc_time_rejected(self):
        for cutoff in (datetime(2040,1,1),stamp("2040-01-01T07:00:00+07:00"),"2040-01-01",True):
            with self.assertRaises(ExpectedGoalsError) as caught:
                fit_expected_goals(batch(),cutoff)
            self.assertEqual(caught.exception.code,"INPUT_INVALID")
        model=fit_expected_goals(batch(),CUTOFF)
        with self.assertRaises(ExpectedGoalsError):
            predict_expected_goals(model,**target(target_kickoff_utc=datetime(2040,1,2)))

    def test_changed_fabricated_batch_hash_or_rows_fail_revalidation(self):
        data=batch()
        for modified in (replace(data,content_sha256="0"*64),
                         replace(data,observations=(replace(data.observations[0],is_synthetic=False),*data.observations[1:])),
                         replace(data,observations=(replace(data.observations[0],home_goals_90=True),*data.observations[1:]))):
            with self.assertRaises(ExpectedGoalsError) as caught:
                fit_expected_goals(modified,CUTOFF)
            self.assertEqual(caught.exception.code,"INPUT_INVALID")

    def test_invalid_raw_batch_does_not_return_partial_fit(self):
        result=parse_synthetic_json(b"{}")
        for fitter in (fit_expected_goals,fit_rate_ratio):
            with self.assertRaises(ExpectedGoalsError):
                fitter(result,CUTOFF)
            with self.assertRaises(ExpectedGoalsError):
                fitter(b"{}",CUTOFF)

    def test_selected_row_safety_reasserted_independently(self):
        data=batch()
        selected=select_as_of(data,CUTOFF)
        for update in (dict(is_synthetic=False),dict(licence_status="UNKNOWN"),
                       dict(kickoff_utc=datetime.max.replace(tzinfo=timezone.utc)),
                       dict(home_goals_90=True),dict(available_at_utc=CUTOFF),
                       dict(available_at_utc=selected.observations[0].kickoff_utc+timedelta(minutes=89))):
            forged=replace(selected,observations=(replace(selected.observations[0],**update),))
            with patch("premfootballbot.expected_goals.select_as_of",return_value=forged):
                with self.assertRaises(ExpectedGoalsError) as caught:
                    fit_expected_goals(data,CUTOFF)
            self.assertEqual(caught.exception.code,"INPUT_INVALID")

    def test_cross_namespace_and_real_labels_are_not_fit_input(self):
        data=batch()
        with self.assertRaises(ExpectedGoalsError):
            fit_expected_goals(replace(data,namespace="real:epl"),CUTOFF)

if __name__=="__main__":
    unittest.main()

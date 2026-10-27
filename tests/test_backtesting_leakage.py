"""Independent negative controls for forecast/label/time separation."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta, timezone
import unittest
from unittest.mock import patch

from premfootballbot.backtesting import (
    BacktestError, generate_forecasts, select_labels, evaluate_forecasts, snapshot_json,
)
from premfootballbot.expected_goals import fit_expected_goals, fit_rate_ratio, predict_expected_goals
from premfootballbot.match_data import select_as_of
from tests.backtesting_cases import (
    observations,targets,batch,manifest,fixture,stamp,EVALUATION,NS,
)

class BacktestingLeakageTests(unittest.TestCase):
    def test_target_future_score_poison_does_not_change_forecast(self):
        schedule=manifest(names=["home"])
        before=generate_forecasts(batch(),schedule)
        raw=observations()
        for row in raw["records"]:
            if row["fixture_id"]==fixture("home") and row["record_type"]=="result":
                row.update(home_goals_90=999,away_goals_90=998)
        after=generate_forecasts(batch(raw),schedule)
        self.assertEqual(before,after)
        self.assertEqual(snapshot_json(before),snapshot_json(after))

    def test_future_historical_correction_is_not_passed_or_hashed(self):
        schedule=manifest(names=["home"]);raw=observations()
        before=generate_forecasts(batch(raw),schedule)
        revised=deepcopy(next(r for r in raw["records"] if r["fixture_id"].endswith(":history-0")))
        revised.update(revision=1,supersedes_revision=0,home_goals_90=999,away_goals_90=998,
                       available_at_utc="2026-09-01T12:00:00Z")
        raw["records"].append(revised)
        self.assertEqual(before,generate_forecasts(batch(raw),schedule))

    def test_added_future_fixture_and_unused_team_do_not_change_forecast(self):
        raw=observations();schedule=manifest(names=["home"])
        before=generate_forecasts(batch(raw),schedule)
        extra=deepcopy(raw["records"][0])
        extra.update(fixture_id=NS+":fixture:future-extra",source_record_id=NS+":record:future-extra",
                     home_team_id=NS+":team:z",home_team_name_raw="Invented Z",
                     kickoff_utc="2028-01-01T14:00:00Z",available_at_utc="2028-01-01T16:00:00Z",
                     home_goals_90=100,away_goals_90=99)
        raw["teams"].append(dict(team_id=NS+":team:z",aliases=["Invented Z"]))
        raw["records"].append(extra)
        self.assertEqual(before,generate_forecasts(batch(raw),schedule))

    def test_fitters_receive_only_valid_historical_prefixes(self):
        schedule=manifest(names=["home"]);cutoff=schedule.targets[0].prediction_cutoff_utc
        calls=[]
        def ridge(data,c,**kwargs):
            calls.append(data)
            self.assertEqual(c,cutoff)
            self.assertNotIn(fixture("home"),{r.fixture_id for r in data.observations})
            self.assertTrue(all(r.available_at_utc is None or r.available_at_utc<c for r in data.observations))
            return fit_expected_goals(data,c,**kwargs)
        def ratio(data,c,**kwargs):
            calls.append(data)
            self.assertNotIn(fixture("home"),{r.fixture_id for r in data.observations})
            return fit_rate_ratio(data,c,**kwargs)
        with (patch("premfootballbot.backtesting.fit_expected_goals",side_effect=ridge),
              patch("premfootballbot.backtesting.fit_rate_ratio",side_effect=ratio)):
            generate_forecasts(batch(),schedule)
        self.assertEqual(len(calls),3)
        self.assertTrue(all(len(c.observations)==7 for c in calls))

    def test_intentionally_leaky_selector_fails_hard(self):
        data=batch();schedule=manifest(names=["home"]);c=schedule.targets[0].prediction_cutoff_utc
        selected=select_as_of(data,c)
        future=next(r for r in data.observations if r.fixture_id==fixture("home") and r.record_type=="result")
        poisoned=replace(selected,observations=selected.observations+(future,))
        with patch("premfootballbot.backtesting.select_as_of",return_value=poisoned):
            with self.assertRaises(BacktestError) as caught:generate_forecasts(data,schedule)
        self.assertEqual(caught.exception.code,"LEAKAGE_DETECTED")

    def test_intentionally_leaky_fitter_fails_hard(self):
        data=batch();schedule=manifest(names=["home"]);future_fit=fit_expected_goals(data,EVALUATION)
        with patch("premfootballbot.backtesting.fit_expected_goals",return_value=future_fit):
            with self.assertRaises(BacktestError) as caught:generate_forecasts(data,schedule)
        self.assertEqual(caught.exception.code,"LEAKAGE_DETECTED")

    def test_prior_driven_substitute_cannot_pass_as_supported_forecast(self):
        def poisoned(*args,**kwargs):
            return replace(predict_expected_goals(*args,**kwargs),prior_driven=True)
        with patch("premfootballbot.backtesting.predict_expected_goals",side_effect=poisoned):
            with self.assertRaises(BacktestError) as caught:generate_forecasts(batch(),manifest(names=["home"]))
        self.assertEqual(caught.exception.code,"LEAKAGE_DETECTED")

    def test_forged_precutoff_target_result_is_rejected(self):
        raw=observations()
        forged=deepcopy(next(r for r in raw["records"] if r["fixture_id"]==fixture("home") and r["record_type"]=="result"))
        forged.update(revision=0,supersedes_revision=None,kickoff_utc="2026-08-02T14:00:00Z",
                      available_at_utc="2026-08-02T16:00:00Z")
        raw["records"]=[r for r in raw["records"] if r["fixture_id"]!=fixture("home")]+[forged]
        forecasts=generate_forecasts(batch(raw),manifest(names=["home"]))
        self.assertTrue(all(r.status=="abstained" and r.reason=="TARGET_RESULT_BEFORE_CUTOFF" for r in forecasts.records))
        self.assertTrue(all(not r.training_refs for r in forecasts.records))

    def test_other_future_target_cannot_be_forged_into_history(self):
        raw=observations()
        fake=deepcopy(next(r for r in raw["records"] if r["fixture_id"]==fixture("draw") and r["record_type"]=="result"))
        fake.update(revision=0,supersedes_revision=None,kickoff_utc="2026-08-02T14:00:00Z",
                    available_at_utc="2026-08-02T16:00:00Z")
        raw["records"]=[r for r in raw["records"] if r["fixture_id"]!=fixture("draw")]+[fake]
        with self.assertRaises(BacktestError) as caught:generate_forecasts(batch(raw),manifest(names=["home","draw"]))
        self.assertEqual(caught.exception.code,"LEAKAGE_DETECTED")

    def test_available_equal_cutoff_does_not_enter_training(self):
        raw=observations()
        row=next(r for r in raw["records"] if r["fixture_id"].endswith(":history-0"))
        row["available_at_utc"]="2026-08-10T12:00:00Z"
        forecasts=generate_forecasts(batch(raw),manifest(names=["home"]))
        for forecast in forecasts.records:
            self.assertNotIn((row["fixture_id"],0),forecast.training_refs)
            self.assertEqual(len(forecast.training_refs),6)

    def test_correction_changes_later_labels_not_predictions(self):
        data=batch();schedule=manifest(names=["revised"]);predictions=generate_forecasts(data,schedule)
        before=select_labels(data,predictions,evaluation_cutoff_utc=stamp("2026-09-01T00:00:00Z"))
        later=select_labels(data,predictions,evaluation_cutoff_utc=EVALUATION)
        self.assertEqual((before.labels[0].revision,before.labels[0].actual),(1,"H"))
        self.assertEqual((later.labels[0].revision,later.labels[0].actual),(2,"A"))
        frozen=snapshot_json(predictions)
        self.assertNotEqual(evaluate_forecasts(predictions,before).sha256,evaluate_forecasts(predictions,later).sha256)
        self.assertEqual(snapshot_json(predictions),frozen)
        raw=observations()
        raw["records"]=[r for r in raw["records"] if not (r["fixture_id"]==fixture("revised") and r["revision"]==2)]
        self.assertEqual(generate_forecasts(batch(raw),schedule),predictions)

    def test_retracted_label_does_not_fall_back(self):
        data=batch();predictions=generate_forecasts(data,manifest(names=["retracted"]))
        labels=select_labels(data,predictions,evaluation_cutoff_utc=EVALUATION);label=labels.labels[0]
        self.assertEqual(label.reason,"NOT_FINISHED_FT90")
        self.assertIsNone(label.actual);self.assertIsNone(label.home_goals_90)
        self.assertTrue(all(m.paired.n==0 for m in evaluate_forecasts(predictions,labels).methods))

    def test_unknown_higher_revision_quarantines_forecast_and_label(self):
        data=batch();predictions=generate_forecasts(data,manifest(names=["uncertain"]))
        self.assertTrue(all(r.reason=="TARGET_HISTORY_UNCERTAIN" for r in predictions.records))
        labels=select_labels(data,predictions,evaluation_cutoff_utc=EVALUATION)
        self.assertEqual(labels.labels[0].reason,"UNCERTAIN_REVISION");self.assertIsNone(labels.labels[0].actual)

    def test_unknown_higher_historical_revision_has_no_old_fallback(self):
        raw=observations()
        changed=deepcopy(next(r for r in raw["records"] if r["fixture_id"].endswith(":history-0")))
        changed.update(revision=1,supersedes_revision=0,available_at_utc=None,home_goals_90=999)
        raw["records"].append(changed)
        predictions=generate_forecasts(batch(raw),manifest(names=["home"]))
        for forecast in predictions.records:
            self.assertNotIn((changed["fixture_id"],0),forecast.training_refs)
            self.assertIn("UNCERTAIN_REVISION",dict(forecast.training_exclusions))

    def test_known_schedule_mismatch_and_coarse_history_abstain(self):
        for coarse in (False,True):
            raw=observations()
            row=next(r for r in raw["records"] if r["fixture_id"]==fixture("home") and r["revision"]==0)
            if coarse:row.update(kickoff_utc=None,kickoff_precision="date_only",match_date="2026-08-11")
            else:row["kickoff_utc"]="2026-08-12T14:00:00Z"
            predictions=generate_forecasts(batch(raw),manifest(names=["home"]))
            expected="TARGET_HISTORY_UNCERTAIN" if coarse else "TARGET_METADATA_MISMATCH"
            self.assertTrue(all(r.reason==expected for r in predictions.records))

    def test_later_reschedule_does_not_retrofit_target_kickoff(self):
        data=batch();predictions=generate_forecasts(data,manifest(names=["reschedule"]))
        self.assertTrue(all(r.status=="predicted" for r in predictions.records))
        labels=select_labels(data,predictions,evaluation_cutoff_utc=EVALUATION)
        self.assertEqual(labels.labels[0].reason,"KICKOFF_CHANGED")
        self.assertEqual(predictions.manifest.targets[0].intended_kickoff_utc,stamp("2026-08-27T14:00:00Z"))

    def test_finality_boundary_and_frozen_evaluation_clock(self):
        data=batch();predictions=generate_forecasts(data,manifest(names=["home"]));at=stamp("2026-08-11T16:00:00Z")
        before=select_labels(data,predictions,evaluation_cutoff_utc=at)
        after=select_labels(data,predictions,evaluation_cutoff_utc=at+timedelta(microseconds=1))
        self.assertEqual(before.labels[0].status,"excluded");self.assertEqual(after.labels[0].actual,"H")
        with self.assertRaises(BacktestError):select_labels(data,predictions,evaluation_cutoff_utc=at.replace(tzinfo=None))

    def test_label_identity_is_canonical_not_names(self):
        data=batch();predictions=generate_forecasts(data,manifest(names=["home"]));raw=observations()
        for row in raw["records"]:
            if row["fixture_id"]==fixture("home"):
                row["home_team_id"],row["away_team_id"]=row["away_team_id"],row["home_team_id"]
                row["home_team_name_raw"],row["away_team_name_raw"]=row["away_team_name_raw"],row["home_team_name_raw"]
        labels=select_labels(batch(raw),predictions,evaluation_cutoff_utc=EVALUATION)
        self.assertEqual(labels.labels[0].reason,"LABEL_IDENTITY_MISMATCH")

    def test_blocked_or_unknown_final_label_excluded(self):
        data=batch();predictions=generate_forecasts(data,manifest(names=["home"]))
        for status in ("UNKNOWN","BLOCKED"):
            raw=observations();doc=deepcopy(raw["source_documents"][0])
            doc.update(source_document_id=NS+":document:restricted",licence_status=status)
            raw["source_documents"].append(doc)
            for row in raw["records"]:
                if row["fixture_id"]==fixture("home") and row["record_type"]=="result":
                    row.update(source_document_id=doc["source_document_id"],licence_status=status)
            labels=select_labels(batch(raw),predictions,evaluation_cutoff_utc=EVALUATION)
            self.assertEqual(labels.labels[0].reason,"LICENCE_NOT_CLEARED");self.assertIsNone(labels.labels[0].actual)

    def test_no_unknown_or_coarse_historical_result_enters_projection(self):
        for mode in ("unknown","coarse"):
            raw=observations();row=next(r for r in raw["records"] if r["fixture_id"].endswith(":history-0"))
            if mode=="unknown":row["available_at_utc"]=None
            else:row.update(kickoff_utc=None,kickoff_precision="date_only",match_date="2026-08-01")
            predictions=generate_forecasts(batch(raw),manifest(names=["home"]))
            self.assertTrue(all((row["fixture_id"],0) not in r.training_refs for r in predictions.records))

    def test_utc_equivalent_observation_offsets_preserve_forecasts(self):
        raw=observations();schedule=manifest(names=["home"]);before=generate_forecasts(batch(raw),schedule)
        for row in raw["records"]:
            for field in ("kickoff_utc","available_at_utc","retrieved_at_utc"):
                if row[field] is not None:row[field]=stamp(row[field]).astimezone(timezone(timedelta(hours=7))).isoformat()
        self.assertEqual(before,generate_forecasts(batch(raw),schedule))

    def test_source_hash_namespace_and_manifest_tampering_rejected(self):
        data=batch();schedule=manifest(names=["home"])
        for bad in (replace(data,content_sha256="0"*64),replace(data,namespace="real:epl")):
            with self.assertRaises(BacktestError):generate_forecasts(bad,schedule)
        with self.assertRaises(BacktestError):generate_forecasts(data,replace(schedule,team_ids=()))

    def test_snapshot_label_join_cannot_use_another_forecast(self):
        data=batch();first=generate_forecasts(data,manifest(names=["home"]))
        second=generate_forecasts(data,manifest(names=["draw"]))
        labels=select_labels(data,first,evaluation_cutoff_utc=EVALUATION)
        with self.assertRaises(BacktestError):evaluate_forecasts(second,labels)

if __name__=="__main__":
    unittest.main()

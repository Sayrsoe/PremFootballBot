"""Handwritten categorical scoring, manifest and report regressions."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta, timezone
import json
import math
import unittest
from unittest.mock import patch

from premfootballbot.backtesting import (
    BANNER, BacktestConfig, BacktestError, ProbabilityMass, parse_target_manifest,
    score_1x2, generate_forecasts, select_labels, evaluate_forecasts, snapshot_json,
)
from premfootballbot.expected_goals import ModelConfig
from premfootballbot.poisson import truncated_poisson_distribution
from tests.backtesting_cases import (
    observations,targets,encode,batch,manifest,fixture,target_row,stamp,EVALUATION,
)

class ReplayReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=batch()
        cls.predictions=generate_forecasts(cls.data,manifest())
        cls.labels=select_labels(cls.data,cls.predictions,evaluation_cutoff_utc=EVALUATION)
        cls.report=evaluate_forecasts(cls.predictions,cls.labels)

    def test_three_actual_methods_and_full_coverage(self):
        report=self.report
        self.assertEqual(report.manifest_n,13)
        self.assertEqual(len(self.predictions.records),39)
        self.assertEqual({m.method for m in report.methods},{"ridge","rate_ratio","league"})
        for method in report.methods:
            self.assertEqual(method.model_version,"phase3a-league-v1" if method.method=="league" else "phase2b-v1")
            self.assertEqual((method.forecasted_n,method.abstained_n),(8,5))
            self.assertEqual(method.forecasted_n+method.abstained_n,report.manifest_n)
            self.assertEqual(method.predicted_missing_label_n,3)
            self.assertEqual(method.forecasted_n,method.predicted_missing_label_n+
                             method.scoring_error_n+method.unpaired.n)

    def test_all_methods_use_same_explicit_paired_population(self):
        expected={fixture(n) for n in ("home","draw","away","revised","next-season")}
        self.assertEqual(set(self.report.paired_ids),expected)
        for method in self.report.methods:
            self.assertEqual(method.paired.n,len(expected))
            rows=[r for r in self.report.rows if r.method==method.method and r.target_id in expected]
            self.assertAlmostEqual(method.paired.log_loss,sum(r.scores.log_loss for r in rows)/5)
            self.assertAlmostEqual(method.paired.brier,sum(r.scores.brier for r in rows)/5)
            self.assertAlmostEqual(method.paired.rps,sum(r.scores.rps for r in rows)/5)

    def test_abstentions_and_missing_labels_are_separate(self):
        method=self.report.methods[0]
        self.assertEqual(dict(method.abstention_reasons),{
            "EMPTY_TRAINING":1,"NO_HISTORY":1,"CROSS_COMPONENT":1,
            "TARGET_HISTORY_UNCERTAIN":1,"TARGET_NOT_SCHEDULED":1})
        labels=dict(self.report.label_exclusion_reasons)
        self.assertEqual(labels["KICKOFF_CHANGED"],1)
        self.assertEqual(labels["MISSING_LABEL"],1)
        self.assertEqual(labels["UNCERTAIN_REVISION"],1)
        self.assertEqual(self.report.eligible_label_n,7)

    def test_per_season_paired_metrics_and_counts(self):
        self.assertEqual([s.season_start_year for s in self.report.per_season],[2026,2027])
        for season,n in zip(self.report.per_season,(4,1)):
            self.assertEqual(len(season.paired_ids),n)
            self.assertTrue(all(summary.n==n for _,summary in season.methods))
        self.assertEqual(sum(s.manifest_n for s in self.report.per_season),13)

    def test_fixed_calibration_bins_conserve_class_counts(self):
        self.assertEqual(len(self.report.calibration),3*3*5)
        labels={r.target_id:r for r in self.labels.labels}
        forecasts={(r.target_id,r.method):r for r in self.predictions.records}
        for method in ("ridge","rate_ratio","league"):
            for category in ("H","D","A"):
                bins=[b for b in self.report.calibration if b.method==method and b.category==category]
                self.assertEqual(sum(b.n for b in bins),5)
                for bucket in bins:
                    expected=[]
                    for target_id in self.report.paired_ids:
                        p=forecasts[target_id,method].probabilities
                        value={"H":p.home,"D":p.draw,"A":p.away}[category]
                        if bucket.lower<=value<bucket.upper or value==1 and bucket.upper==1:
                            expected.append((value,labels[target_id].actual==category))
                    self.assertEqual(bucket.n,len(expected))
                    self.assertEqual(bucket.evidence,"INSUFFICIENT_EVIDENCE")
                    if expected:
                        self.assertAlmostEqual(bucket.mean_forecast,sum(v for v,_ in expected)/len(expected))
                        self.assertAlmostEqual(bucket.observed_frequency,sum(v for _,v in expected)/len(expected))
                    else:
                        self.assertIsNone(bucket.mean_forecast)
                        self.assertIsNone(bucket.observed_frequency)

    def test_all_outputs_labelled_synthetic_and_no_nonfinite_json(self):
        for snapshot in (self.predictions,self.labels,self.report):
            data=snapshot_json(snapshot)
            self.assertNotIn(b"NaN",data)
            self.assertNotIn(b"Infinity",data)
            self.assertEqual(json.loads(data)["banner"],BANNER)
            self.assertEqual(len(snapshot.sha256),64)
        self.assertTrue(all(m.paired.evidence=="INSUFFICIENT_EVIDENCE" for m in self.report.methods))

    def test_no_ground_truth_keys_in_forecast_tree(self):
        forbidden={"actual","outcome","label","labels","home_goals_90","away_goals_90",
                   "final_score","goal_difference","scores"}
        def inspect(value):
            if isinstance(value,dict):
                self.assertFalse(forbidden.intersection(value))
                for child in value.values():inspect(child)
            elif isinstance(value,list):
                for child in value:inspect(child)
        inspect(json.loads(snapshot_json(self.predictions)))

    def test_tampered_forecast_and_labels_fail_closed(self):
        altered=replace(self.predictions,records=self.predictions.records[:-1])
        with self.assertRaises(BacktestError) as caught:
            select_labels(self.data,altered,evaluation_cutoff_utc=EVALUATION)
        self.assertEqual(caught.exception.code,"SNAPSHOT_TAMPERED")
        changed=replace(self.labels,evaluation_batch_hash="0"*64)
        with self.assertRaises(BacktestError):evaluate_forecasts(self.predictions,changed)
        with self.assertRaises(FrozenInstanceError):self.predictions.records[0].status="predicted"

    def test_forecast_failures_do_not_force_fallback_or_comparison_population(self):
        predictions=generate_forecasts(self.data,manifest(),config=BacktestConfig(model=ModelConfig(max_iterations=1)))
        labels=select_labels(self.data,predictions,evaluation_cutoff_utc=EVALUATION)
        report=evaluate_forecasts(predictions,labels)
        ridge,ratio,league=report.methods
        self.assertEqual(ridge.forecasted_n,0)
        self.assertIn("NOT_CONVERGED",dict(ridge.abstention_reasons))
        self.assertGreater(ratio.unpaired.n,0)
        self.assertGreater(league.unpaired.n,0)
        self.assertEqual(report.paired_ids,())
        self.assertTrue(all(m.paired.n==0 and m.paired.log_loss is None for m in report.methods))

    def test_low_cap_records_tail_guard_and_no_fake_scores(self):
        predictions=generate_forecasts(self.data,manifest(names=["home"]),config=BacktestConfig(max_goals=0))
        self.assertTrue(all(r.reason=="TAIL_GUARD" for r in predictions.records))
        labels=select_labels(self.data,predictions,evaluation_cutoff_utc=EVALUATION)
        report=evaluate_forecasts(predictions,labels)
        self.assertTrue(all(m.paired.n==0 and m.unpaired.log_loss is None for m in report.methods))

    def test_scoring_zero_error_is_counted_and_shrinks_paired_set(self):
        from premfootballbot.backtesting import _seal
        predictions=generate_forecasts(self.data,manifest(names=["home"]))
        records=list(predictions.records)
        records[0]=replace(records[0],probabilities=ProbabilityMass(0,.5,.5))
        manufactured=_seal(replace(predictions,records=tuple(records)))
        labels=select_labels(self.data,manufactured,evaluation_cutoff_utc=EVALUATION)
        report=evaluate_forecasts(manufactured,labels)
        self.assertEqual(report.methods[0].scoring_error_n,1)
        self.assertEqual(dict(report.methods[0].scoring_error_reasons),{"ZERO_OBSERVED_MASS":1})
        self.assertEqual(report.methods[1].unpaired.n,1)
        self.assertEqual(report.paired_ids,())

    def test_league_baseline_uses_only_prior_goals(self):
        first=next(r for r in self.predictions.records if r.target_id==fixture("home") and r.method=="league")
        self.assertAlmostEqual(first.lambda_home,10/7)
        self.assertAlmostEqual(first.lambda_away,6/7)
        self.assertEqual(len(first.training_refs),7)
        self.assertIn("LEAGUE_PRIOR_AVERAGES",first.warnings)

    def test_permissible_input_permutations_keep_all_digests(self):
        import random
        raw=observations();schedule=targets()
        for seed in (3,17,101):
            random.Random(seed).shuffle(raw["records"])
            raw["teams"].reverse();schedule["targets"].reverse()
            forecasts=generate_forecasts(batch(raw),manifest(schedule))
            labels=select_labels(batch(raw),forecasts,evaluation_cutoff_utc=EVALUATION)
            report=evaluate_forecasts(forecasts,labels)
            self.assertEqual(forecasts,self.predictions)
            self.assertEqual(labels,self.labels)
            self.assertEqual(report,self.report)

    def test_report_stage_never_calls_fitters(self):
        with (patch("premfootballbot.backtesting.fit_expected_goals",side_effect=AssertionError("refit")),
              patch("premfootballbot.backtesting.fit_rate_ratio",side_effect=AssertionError("refit"))):
            self.assertEqual(evaluate_forecasts(self.predictions,self.labels),self.report)
class ScoreOracleTests(unittest.TestCase):
    def test_unrepresentable_numbers_return_typed_failures(self):
        from fractions import Fraction
        for p in (ProbabilityMass(10**1000,0,0),ProbabilityMass(Fraction(1,10**1000),.4,.6)):
            with self.assertRaises(BacktestError):score_1x2(p,"H")
        with self.assertRaises(BacktestError):BacktestConfig(tail_tolerance=10**1000)
        with self.assertRaises(BacktestError):
            score_1x2(ProbabilityMass(.6,.3,.1),"H",tail_tolerance=10**1000)

    def test_handwritten_home_draw_away_scores(self):
        p=ProbabilityMass(.6,.3,.1)
        # Independently expanded squares: H=.16+.09+.01, D=.36+.49+.01,
        # A=.36+.09+.81; RPS boundaries at A and D.
        for actual,logloss,brier,rps in (("H",.5108256237659907,.26,.17),
                                        ("D",1.2039728043259361,.86,.37),
                                        ("A",2.302585092994046,1.26,1.17)):
            result=score_1x2(p,actual)
            self.assertAlmostEqual(result.log_loss,logloss,delta=1e-14)
            self.assertAlmostEqual(result.brier,brier,delta=1e-14)
            self.assertAlmostEqual(result.rps,rps,delta=1e-14)
            self.assertEqual(result.banner,BANNER)

    def test_perfect_and_maximum_wrong_brier(self):
        for actual,p in (("H",(1.,0.,0.)),("D",(0.,1.,0.)),("A",(0.,0.,1.))):
            result=score_1x2(ProbabilityMass(*p),actual)
            self.assertEqual((result.log_loss,result.brier,result.rps),(0.,0.,0.))
        # Wrong but nonzero truth mass: approaches unscaled maximum2.
        result=score_1x2(ProbabilityMass(1-1e-12,0,1e-12),"A")
        self.assertGreater(result.brier,1.99)
        self.assertGreater(result.rps,1.99)

    def test_zero_observed_probability_is_typed_not_clipped(self):
        with self.assertRaises(BacktestError) as caught:
            score_1x2(ProbabilityMass(1,0,0),"D")
        self.assertEqual(caught.exception.code,"ZERO_OBSERVED_MASS")

    def test_tiny_positive_probability_and_error_bound_stay_finite(self):
        result=score_1x2(ProbabilityMass(math.nextafter(0.,1.),.4,.6,omitted_bound=1e-10),"H")
        self.assertTrue(math.isfinite(result.log_loss))
        self.assertTrue(math.isfinite(result.log_loss_truncation_bound))
        self.assertGreater(result.log_loss_truncation_bound,700)

    def test_raw_mass_is_never_renormalized(self):
        values=(.5,.3,.19999999995)
        p=ProbabilityMass(*values,retained_mass=.99999999995,omitted_mass=5e-11,omitted_bound=5e-11)
        result=score_1x2(p,"A")
        self.assertEqual(result.log_loss,-math.log(values[2]))
        self.assertNotEqual(result.log_loss,-math.log(values[2]/sum(values)))
        self.assertGreater(result.log_loss_truncation_bound,0)

    def test_insufficient_rectangular_tail_rejected(self):
        d=truncated_poisson_distribution(1,1,home_cap=0,away_cap=0)
        x=d.one_x_two()
        p=ProbabilityMass(x.home_win,x.draw,x.away_win,d.mass.retained_mass,
                          d.mass.omitted_mass,d.mass.omitted_mass_bound)
        with self.assertRaises(BacktestError) as caught:
            score_1x2(p,"D")
        self.assertEqual(caught.exception.code,"TAIL_GUARD")

    def test_nonfinite_negative_and_inconsistent_mass_rejected(self):
        for p in (ProbabilityMass(math.nan,.3,.1),ProbabilityMass(-.1,.5,.6),
                  ProbabilityMass(.7,.3,.2),ProbabilityMass(.6,.3,.1,omitted_mass=.01),
                  ProbabilityMass(True,0,0)):
            with self.assertRaises(BacktestError):
                score_1x2(p,"H")
        for actual in ("draw",None,1):
            with self.assertRaises(BacktestError):
                score_1x2(ProbabilityMass(.6,.3,.1),actual)

    def test_tail_tolerance_is_strict_and_not_loosened(self):
        for tolerance in (True,0,-1,math.inf,1e-5):
            with self.assertRaises(BacktestError):
                score_1x2(ProbabilityMass(.6,.3,.1),"H",tail_tolerance=tolerance)

class ManifestTests(unittest.TestCase):
    def test_target_kickoff_datetime_range_checked(self):
        raw=targets()
        row=raw["targets"][0]
        row.update(intended_kickoff_utc="9999-12-31T23:59:59Z",
                   prediction_cutoff_utc="9999-12-31T21:00:00Z",
                   declared_at_utc="9999-12-31T20:00:00Z")
        with self.assertRaises(BacktestError):parse_target_manifest(encode(raw))

    def test_manifest_is_separate_predeclared_and_chronological(self):
        m=manifest()
        self.assertEqual(len(m.targets),13)
        self.assertEqual(list(m.targets),sorted(m.targets,key=lambda t:(t.prediction_cutoff_utc,t.fixture_id)))
        self.assertTrue(all(t.declared_at_utc<t.prediction_cutoff_utc<t.intended_kickoff_utc for t in m.targets))
        self.assertEqual(m.banner,BANNER)

    def test_equal_or_late_cutoff_rejected(self):
        raw=targets()
        for delta in (timedelta(0),timedelta(seconds=1)):
            changed=deepcopy(raw)
            row=changed["targets"][0]
            row["prediction_cutoff_utc"]=(stamp(row["intended_kickoff_utc"])+delta).isoformat()
            with self.assertRaises(BacktestError) as caught:
                parse_target_manifest(encode(changed))
            self.assertEqual(caught.exception.code,"NOT_EX_ANTE")

    def test_duplicate_ids_rejected_even_identical(self):
        raw=targets()
        raw["targets"].append(deepcopy(raw["targets"][0]))
        with self.assertRaises(BacktestError) as caught:
            parse_target_manifest(encode(raw))
        self.assertEqual(caught.exception.code,"DUPLICATE_TARGET")

    def test_label_fields_are_forbidden_in_manifest(self):
        for field in ("home_goals_90","actual","score","final_score"):
            raw=targets()
            raw["targets"][0][field]=2
            with self.assertRaises(BacktestError):
                parse_target_manifest(encode(raw))

    def test_undeclared_or_postmatch_only_target_not_ex_ante(self):
        for mode in ("missing","late"):
            raw=targets()
            row=raw["targets"][0]
            if mode=="missing":del row["declared_at_utc"]
            else:row["declared_at_utc"]=row["intended_kickoff_utc"]
            with self.assertRaises(BacktestError):
                parse_target_manifest(encode(raw))

    def test_bad_identity_competition_season_and_self_match(self):
        for field,value in (("competition_code","EFL"),("season_start_year",True),
                            ("season_start_year",1991),("home_team_id","real:team:a"),
                            ("home_team_id","synthetic:phase3a:team:missing")):
            raw=targets();raw["targets"][0][field]=value
            with self.assertRaises(BacktestError):parse_target_manifest(encode(raw))
        raw=targets();raw["targets"][0]["home_team_id"]=raw["targets"][0]["away_team_id"]
        with self.assertRaises(BacktestError):parse_target_manifest(encode(raw))

    def test_naive_unknown_offset_and_date_only_times_rejected(self):
        for value in ("2026-07-01","2026-07-01T12:00:00","2026-07-01T12:00:00-00:00",True):
            raw=targets();raw["targets"][0]["prediction_cutoff_utc"]=value
            with self.assertRaises(BacktestError):parse_target_manifest(encode(raw))

    def test_equivalent_offsets_and_reordering_preserve_digest(self):
        raw=targets();before=parse_target_manifest(encode(raw))
        raw["targets"].reverse();raw["team_ids"].reverse()
        for row in raw["targets"]:
            row["prediction_cutoff_utc"]=stamp(row["prediction_cutoff_utc"]).astimezone(
                timezone(timedelta(hours=7))).isoformat()
        after=parse_target_manifest(encode(raw))
        self.assertEqual(before,after)

    def test_malformed_json_duplicates_types_and_size(self):
        for data in (b"[]",b"{",b"\xff",b'{"schema_version":1,"schema_version":1}',
                     b'{"schema_version":NaN}',b" "* (4*1024*1024+1)):
            with self.assertRaises(BacktestError):parse_target_manifest(data)
        with self.assertRaises(BacktestError):parse_target_manifest("{}")

    def test_frozen_manifest_and_config(self):
        m=manifest()
        with self.assertRaises(FrozenInstanceError):m.namespace="real:epl"
        with self.assertRaises(FrozenInstanceError):m.targets[0].fixture_id="other"
        for args in (dict(tail_tolerance=0),dict(tail_tolerance=1e-3),dict(max_goals=True),
                     dict(model=None),dict(calibration_bins=0)):
            with self.assertRaises(BacktestError):BacktestConfig(**args)

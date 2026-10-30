"""Pinned retrospective studies and explicitly simulated leakage/tampering attacks."""
from dataclasses import replace, FrozenInstanceError
from datetime import date, datetime, timedelta, timezone
import json
import math
from pathlib import Path
import unittest
from unittest.mock import patch

from premfootballbot import chronological_epl as ce
from premfootballbot import completed_epl as data
from premfootballbot import real_epl_training as numeric
from premfootballbot.expected_goals import fit_expected_goals, ExpectedGoalsError
from premfootballbot.match_data import parse_synthetic_json
from premfootballbot.prospective_evidence import freeze_packet, EvidenceError
from tests.test_completed_epl import inputs,FIXTURE


class ChronologicalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs=inputs(); cls.license=(FIXTURE/'LICENSE.md').read_bytes()
        cls.dataset=data.import_completed_epl(cls.inputs,license_bytes=cls.license)
        cls.model=ce.fit_development(cls.dataset,cls.inputs,license_bytes=cls.license)
        cls.forecasts=ce.forecast_holdout(cls.model,cls.dataset,cls.inputs,license_bytes=cls.license)
        cls.evaluation=ce.evaluate_holdout(cls.model,cls.forecasts,cls.dataset,cls.inputs,license_bytes=cls.license)

    def fit(self,dataset=None,values=None,license=None):
        return ce.fit_development(self.dataset if dataset is None else dataset,
            self.inputs if values is None else values,license_bytes=self.license if license is None else license)

    def test_exact_source_replay_and_training_only_counts(self):
        self.assertEqual(len(self.model.training_rows),380)
        self.assertTrue(all(r.match_date.year in (2024,2025) for r in self.model.training_rows))
        self.assertEqual(self.model.training_source.path,'2024-25/1-premierleague.txt')
        self.assertEqual(self.model.frequency_counts,(155,93,132))
        self.assertEqual(self.model.config.ridge,4)
        self.assertEqual(self.model.config,numeric.RealFitConfig())

    def test_train_and_test_ids_disjoint_chronological(self):
        train={r.fixture_id for r in self.model.training_rows}
        holdout={r.fixture_id for r in self.forecasts.rows}
        self.assertFalse(train & holdout)
        self.assertLess(max(r.match_date for r in self.model.training_rows),min(r.match_date for r in self.forecasts.rows))

    def test_date_groups_are_complete_and_never_split(self):
        for rows,groups in ((self.model.training_rows,self.model.training_date_groups),
                            (self.forecasts.rows,self.forecasts.date_groups)):
            self.assertEqual(sum(len(ids) for _,ids in groups),380)
            for d,ids in groups:
                self.assertEqual(ids,tuple(r.fixture_id for r in rows if r.match_date==d))

    def test_numeric_kernel_receives_only_development(self):
        original=numeric._fit_rows
        seen=[]
        def spy(rows,config):
            seen.extend(rows)
            self.assertEqual(len(rows),380)
            self.assertTrue(all(r.fixture_id.startswith('openfootball:epl:2024:') for r in rows))
            return original(rows,config)
        with patch.object(numeric,'_fit_rows',spy): self.fit()
        self.assertEqual(tuple(seen),self.model.training_rows)

    def test_holdout_goal_poison_cannot_change_training_or_predictions(self):
        poisoned=[]
        for r in self.dataset.rows:
            if r.original.season_start_year==2025:
                r=replace(r,original=replace(r.original,home_goals_ft90=99,away_goals_ft90=98))
            poisoned.append(r)
        # Deliberately invalid source snapshot used only to test internal separation.
        attacked=replace(self.dataset,rows=tuple(poisoned))
        self.assertEqual(ce._fit(attacked),self.model)
        self.assertEqual(ce._forecast(self.model,attacked),self.forecasts)
        with self.assertRaises(data.CompletedEplError): self.fit(data._seal(attacked))

    def test_holdout_only_change_does_not_enter_baseline(self):
        other=replace(self.dataset,rows=tuple(r for r in self.dataset.rows if r.original.season_start_year==2024))
        self.assertEqual(ce._fit(other),self.model)

    def test_fold_same_day_groups_and_two_calendar_day_embargo(self):
        by_id={r.original.fixture_id:r for r in self.dataset.rows}
        dates=tuple(sorted({r.match_date for r in self.model.training_rows})[5:10])
        folds=ce.development_folds(self.dataset,self.inputs,license_bytes=self.license,target_dates=dates)
        for fold in folds:
            self.assertTrue(all(by_id[i].original.match_date<=fold.target_date-timedelta(days=2) for i in fold.training_ids))
            self.assertEqual(set(fold.target_ids),{r.fixture_id for r in self.model.training_rows if r.match_date==fold.target_date})
            self.assertTrue(all(by_id[i].original.season_start_year==2024 for i in fold.training_ids))

    def test_embargo_future_and_same_day_poison_invariant(self):
        target=date(2025,1,1)
        # Kernel fold utility only; immutable date metadata simulates additional future results.
        before=ce._folds(self.dataset.rows,(target,),2)
        original=next(r for r in self.dataset.rows if r.original.season_start_year==2024 and r.original.match_date==target)
        extra=replace(original,original=replace(original.original,fixture_id='INVENTED-FUTURE',match_date=date(2025,1,2)))
        after=ce._folds(self.dataset.rows+(extra,),(target,),2)
        self.assertEqual(before,after)
        self.assertFalse(set(before[0].training_ids)&set(before[0].target_ids))

    def test_holdout_fold_and_invalid_embargo_rejected(self):
        for dates in ((self.forecasts.rows[0].match_date,), (datetime(2025,1,1,tzinfo=timezone.utc),),
                      (date(2025,1,1),date(2025,1,1)), ('2025-01-01',)):
            with self.assertRaises(ce.ChronologicalError):
                ce.development_folds(self.dataset,self.inputs,license_bytes=self.license,target_dates=dates)
        for embargo in (0,1,True,2.5,367):
            with self.assertRaises(ce.ChronologicalError): ce._folds(self.dataset.rows,(date(2025,1,1),),embargo)

    def test_promoted_team_counts_derived_from_identity(self):
        known={t.team for t in self.model.teams}
        unknown={t for r in self.forecasts.rows for t in (r.home_team_id,r.away_team_id) if t not in known}
        self.assertEqual(unknown,{'burnley','leeds','sunderland'})
        expected=sum(r.home_team_id not in known or r.away_team_id not in known for r in self.forecasts.rows)
        self.assertEqual(expected,108)
        self.assertEqual(self.evaluation.scored,272)
        self.assertEqual(self.evaluation.abstentions,(('UNSEEN_PROMOTED_TEAM',expected),))

    def test_abstentions_have_no_invented_probabilities(self):
        for r in self.forecasts.rows:
            if r.decision=='ABSTAIN':
                self.assertEqual((r.probabilities,r.baseline,r.rates,r.mass),((),(),(),()))

    def test_no_results_in_forecast_artifact(self):
        p=json.loads(ce.artifact_json(self.forecasts))
        for row in p['rows']:
            self.assertFalse({'actual','home_goals','away_goals','outcome'} & set(row))
        train=json.loads(ce.artifact_json(self.model))
        self.assertNotIn('holdout',train)

    def test_same_matches_for_model_and_baseline(self):
        ids={r.fixture_id for r in self.forecasts.rows if r.decision=='FORECAST'}
        self.assertEqual(ids,{r.fixture_id for r in self.evaluation.scored_rows})
        baseline=self.model.frequency_baseline
        for row in self.forecasts.rows:
            if row.decision=='FORECAST': self.assertEqual(row.baseline,baseline)

    def test_scoring_formulas(self):
        self.assertEqual(ce._scores((1.,0.,0.),0),(0.,-0.))
        b,l=ce._scores((1/3,1/3,1/3),0)
        self.assertAlmostEqual(b,2/3); self.assertAlmostEqual(l,math.log(3))
        b,l=ce._scores((.5,.3,.2),0)
        self.assertAlmostEqual(b,.38); self.assertAlmostEqual(l,math.log(2))
        for values,label in (((0.,1.,0.),0),((math.nan,0.,0.),1),((.5,.5,.5),0)):
            with self.assertRaises(ce.ChronologicalError): ce._scores(values,label)

    def test_convergence_and_score_equations(self):
        d=self.model.diagnostics
        self.assertLessEqual(d.gradient_inf_norm,1e-7)
        self.assertTrue(all(b<=a for a,b in zip(d.objective_trace,d.objective_trace[1:])))
        self.assertAlmostEqual(d.fitted_home_goals,575,places=6)
        self.assertAlmostEqual(d.fitted_away_goals,540,places=6)

    def test_tail_policy_and_explicit_normalization(self):
        for r in self.forecasts.rows:
            if r.decision!='FORECAST': continue
            mass=dict(r.mass)
            self.assertLessEqual(mass['omitted_mass_bound'],1e-10)
            self.assertAlmostEqual(sum(r.raw_probabilities),mass['retained_mass'],places=12)
            self.assertAlmostEqual(sum(r.probabilities),1,places=12)

    def test_mathematical_metrics_and_uncertainty_not_target_tuned(self):
        means=dict(self.evaluation.means)
        n=len(self.evaluation.scored_rows)
        for field in ('brier','log_loss','baseline_brier','baseline_log_loss'):
            self.assertAlmostEqual(means[field],math.fsum(getattr(r,field) for r in self.evaluation.scored_rows)/n)
        self.assertEqual(self.evaluation.date_clusters,102)
        self.assertEqual(self.evaluation.bootstrap_replicates,4000)
        for _,(low,high) in self.evaluation.paired_descriptive_95_intervals:
            self.assertLess(low,high)
        self.assertEqual(sum(b[2] for b in self.evaluation.calibration),3*n)

    def test_reproducibility_and_full_replay(self):
        self.assertEqual(self.fit(),self.model)
        self.assertTrue(ce.verify_evaluation(self.evaluation,self.model,self.forecasts,self.dataset,self.inputs,license_bytes=self.license))

    def test_tampered_model_even_resealed_rejected(self):
        for m in (replace(self.model,intercept=9),ce._seal(replace(self.model,intercept=9))):
            with self.assertRaises(ce.ChronologicalError):
                ce.forecast_holdout(m,self.dataset,self.inputs,license_bytes=self.license)

    def test_tampered_forecast_even_resealed_rejected(self):
        row=next(r for r in self.forecasts.rows if r.decision=='FORECAST')
        changed=replace(row,probabilities=(.9,.05,.05))
        f=ce._seal(replace(self.forecasts,rows=tuple(changed if r==row else r for r in self.forecasts.rows)))
        with self.assertRaises(ce.ChronologicalError): ce.evaluate_holdout(self.model,f,self.dataset,self.inputs,license_bytes=self.license)

    def test_resealed_scoring_tamper_rejected_by_replay(self):
        changed=ce._seal(replace(self.evaluation,scored=999))
        with self.assertRaises(ce.ChronologicalError):
            ce.verify_evaluation(changed,self.model,self.forecasts,self.dataset,self.inputs,license_bytes=self.license)

    def test_source_license_season_and_acquisition_tamper(self):
        for value in (b'',self.license+b'x'):
            with self.assertRaises(data.CompletedEplError): self.fit(license=value)
        for item in (replace(self.inputs[0],raw_bytes=self.inputs[0].raw_bytes+b'x'),
                     replace(self.inputs[0],source=replace(self.inputs[0].source,path='2026-27/1-premierleague.txt'))):
            with self.assertRaises(data.CompletedEplError): self.fit(values=(item,self.inputs[1]))

    def test_no_config_or_holdout_training_override(self):
        with self.assertRaises(TypeError): ce.fit_development(self.dataset,self.inputs,license_bytes=self.license,config=numeric.RealFitConfig(ridge=5))
        for value in (self.model,self.forecasts,self.evaluation):
            with self.assertRaises(FrozenInstanceError): value.sha256='forged'
            with self.assertRaises(ce.ChronologicalError): ce.artifact_json(ce._seal(replace(value,strict_point_in_time_eligible=True)))

    def test_original_synthetic_and_prospective_gates_reject_artifacts(self):
        for value in (self.model,self.forecasts,self.evaluation):
            raw=ce.artifact_json(value)
            self.assertFalse(parse_synthetic_json(raw).valid)
            with self.assertRaises(ExpectedGoalsError): fit_expected_goals(value,None)
            with self.assertRaises(EvidenceError): freeze_packet(raw)

    def test_no_io_or_protected_public_fit_call(self):
        with patch('socket.socket',side_effect=AssertionError),patch('builtins.open',side_effect=AssertionError), \
             patch.object(Path,'read_bytes',side_effect=AssertionError),patch.object(numeric,'fit_real_epl',side_effect=AssertionError):
            self.assertEqual(self.fit(),self.model)

    def test_numeric_failure_is_atomic_no_fallback(self):
        with patch.object(numeric,'_fit_rows',side_effect=numeric.RealTrainingError('NOT_CONVERGED','test')):
            with self.assertRaises(numeric.RealTrainingError): self.fit()


if __name__=='__main__': unittest.main()

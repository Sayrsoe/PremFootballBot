"""Protocol-only tests; no new training, prediction or scoring operations."""
import ast
from contextlib import ExitStack
from dataclasses import replace, FrozenInstanceError
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from premfootballbot import chronological_candidates as cp
from premfootballbot import chronological_epl as old
from premfootballbot import completed_epl as data
from premfootballbot.match_data import parse_synthetic_json
from premfootballbot.prospective_evidence import freeze_packet, EvidenceError
from tests.test_completed_epl import inputs,FIXTURE

DATES=(date(2024,12,26),date(2025,1,1),date(2025,3,8))


class ProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs=inputs(); cls.license=(FIXTURE/'LICENSE.md').read_bytes()
        cls.dataset=data.import_completed_epl(cls.inputs,license_bytes=cls.license)
        cls.protocol=cp.build_protocol(cls.dataset,cls.inputs,license_bytes=cls.license,target_dates=DATES)

    def build(self, dataset=None, values=None, license=None, dates=DATES, policy=cp.ProtocolPolicy()):
        return cp.build_protocol(self.dataset if dataset is None else dataset,self.inputs if values is None else values,
            license_bytes=self.license if license is None else license,target_dates=dates,policy=policy)

    def test_complete_source_identity_and_exposure(self):
        p=self.protocol
        self.assertEqual(p.dataset_sha256,self.dataset.sha256)
        self.assertEqual(tuple(s.path for s in p.sources),tuple(s.source.path for s in self.dataset.seasons))
        self.assertEqual(p.exposure,((2024,'DEVELOPMENT_ONLY'),(2025,'EXPOSED_HOLDOUT_NOT_CONFIRMATORY')))
        self.assertEqual(p.policy.selection_seasons,(2024,))

    def test_reuses_original_selector_exactly(self):
        original=old.development_folds
        with patch.object(old,'development_folds',wraps=original) as selector:
            p=self.build()
        selector.assert_called_once()
        expected=original(self.dataset,self.inputs,license_bytes=self.license,target_dates=DATES)
        self.assertEqual(tuple(tuple(r.fixture_id for r in f.training) for f in p.folds),tuple(f.training_ids for f in expected))
        self.assertEqual(tuple(tuple(t.fixture.fixture_id for t in f.targets) for f in p.folds),tuple(f.target_ids for f in expected))

    def test_temporal_partition_and_atomic_days(self):
        for f in self.protocol.folds:
            target={r.original.fixture_id for r in self.dataset.rows if r.original.season_start_year==2024 and r.original.match_date==f.target_date}
            self.assertEqual(target,{t.fixture.fixture_id for t in f.targets})
            self.assertTrue(all(r.match_date<=f.target_date-timedelta(days=2) for r in f.training))
            self.assertFalse(target & {r.fixture_id for r in f.training})
            self.assertEqual(len(f.training)+sum(n for _,n in f.exclusions),760)
            self.assertEqual(dict(f.exclusions)['EXPOSED_HOLDOUT_RESERVED'],380)

    def test_population_from_selected_history_only(self):
        for f in self.protocol.folds:
            self.assertEqual(f.training_population,tuple(sorted({t for r in f.training for t in (r.home_team_id,r.away_team_id)})))
            self.assertNotIn('sunderland',f.training_population)

    def test_january_boundary_is_calendar_not_match_count(self):
        p=self.build(dates=(date(2025,1,1),))
        self.assertEqual(p.folds[0].training_date_limit,date(2024,12,30))
        self.assertTrue(all(r.match_date<=date(2024,12,30) for r in p.folds[0].training))

    def test_future_results_or_rosters_do_not_change_history_population(self):
        # Private assembly oracle: poison unselected result values and future
        # team names, never pass this invalid dataset through public source gates.
        dates=(date(2024,12,26),)
        base=old._folds(self.dataset.rows,dates,2)
        original=cp._assemble(self.dataset,base,cp.ProtocolPolicy())
        rows=[]
        for row in self.dataset.rows:
            if row.original.match_date>dates[0]:
                row=replace(row,home_team_id='INVENTED_FUTURE_TEAM',
                            original=replace(row.original,home_goals_ft90=99,away_goals_ft90=98))
            rows.append(row)
        attacked=replace(self.dataset,rows=tuple(rows))
        self.assertEqual(cp._assemble(attacked,base,cp.ProtocolPolicy()),original)

    def test_min_history_is_explicit_not_hidden_training(self):
        p=self.build(dates=(date(2024,8,16),))
        f=p.folds[0]
        self.assertEqual(f.training,())
        self.assertEqual(f.history_status,'INSUFFICIENT_HISTORY')
        self.assertTrue(all(t.reason=='INSUFFICIENT_HISTORY' for t in f.targets))

    def test_real_archive_Dminus1_exclusion(self):
        f=self.build(dates=(date(2024,8,17),)).folds[0]
        self.assertEqual(f.training,())
        self.assertEqual(dict(f.exclusions)['EMBARGO'],1)  # Aug16 opener, not known by Aug15 proxy limit.
        self.assertTrue(all(t.fixture.match_date==date(2024,8,17) for t in f.targets))

    def test_labels_and_scores_absent(self):
        payload=json.loads(cp.protocol_json(self.protocol))
        def walk(value):
            if isinstance(value,dict):
                self.assertFalse({'home_goals','away_goals','home_goals_ft90','away_goals_ft90','actual','probabilities','coefficients','metrics'} & set(value))
                for v in value.values(): walk(v)
            elif isinstance(value,list):
                for v in value: walk(v)
        walk(payload)
        self.assertEqual(payload['execution_status'],'PROTOCOL_ONLY_NOT_EXECUTED')

    def test_no_historical_certification_at_any_level(self):
        p=self.protocol
        for item in (p,*p.folds,*(r for f in p.folds for r in (*f.training,*(a.fixture for a in f.targets)))):
            self.assertIsNone(item.kickoff_utc)
            self.assertIsNone(item.historical_available_at)
            self.assertFalse(item.strict_point_in_time_eligible)
        self.assertIn('NO PROSPECTIVE VALIDITY CLAIM',p.warnings)

    def test_immutable_and_canonical_replay(self):
        self.assertEqual(cp.protocol_json(self.protocol),cp.protocol_json(self.build(dates=tuple(reversed(DATES)))))
        self.assertTrue(cp.verify_protocol(self.protocol,self.dataset,self.inputs,license_bytes=self.license))
        with self.assertRaises(FrozenInstanceError): self.protocol.sha256='forged'

    def test_manifest_dict_order_and_source_order(self):
        self.assertEqual(self.protocol,self.build(values=tuple(reversed(self.inputs))))

    def test_policy_has_future_scoring_and_paired_accounting_only(self):
        p=self.protocol.policy
        self.assertIn('UNSCALED_MULTICLASS_BRIER',p.future_metrics)
        self.assertEqual(p.uncertainty_replicates,4000)
        self.assertEqual(p.paired_policy,'COMMON_FIXTURE_IDS_PLUS_ALL_MATCH_DENOMINATORS')
        self.assertIn('PRIOR_ONLY',p.coverage_segments)
        self.assertIn('SEPARATE_APPROVAL',p.future_scoring)

    def test_embargo_and_minimum_history_validation(self):
        for field,values in (('embargo_days',(0,1,True,2.5,367)),('minimum_history_matches',(0,True,381,'100'))):
            for value in values:
                with self.subTest(field=field,value=value),self.assertRaises(cp.ProtocolError): self.build(policy=replace(cp.ProtocolPolicy(),**{field:value}))
        self.assertEqual(self.build(policy=cp.ProtocolPolicy(embargo_days=3)).policy.embargo_days,3)

    def test_holdout_dates_and_duplicate_dates_forbidden(self):
        for dates in ((date(2025,8,15),),(date(2026,1,1),),(DATES[0],DATES[0]),(),[DATES[0]],(datetime(2025,1,1,tzinfo=timezone.utc),)):
            with self.subTest(dates=dates),self.assertRaises(ValueError): self.build(dates=dates)

    def test_exposed_set_cannot_be_laundered(self):
        for change in ({'selection_seasons':(2024,2025)},{'source_seasons':(2023,2024,2025)},
                       {'exposed_label':'UNTOUCHED_CONFIRMATORY'},{'candidate_selection':'HOLDOUT_SEARCH'},
                       {'benchmarks':('NEW_UNAPPROVED_MODEL',)},{'future_metrics':('ROI',)}):
            with self.assertRaises(cp.ProtocolError): self.build(policy=replace(cp.ProtocolPolicy(),**change))

    def test_forged_json_policy_or_protocol_not_trusted(self):
        for raw in (b'{"embargo_days":0,"embargo_days":2}',{},json.loads(cp.protocol_json(self.protocol))):
            with self.assertRaises(cp.ProtocolError): cp.protocol_json(raw)
            with self.assertRaises(cp.ProtocolError): self.build(policy=raw)

    def test_source_bytes_rights_revision_and_missing_license(self):
        with self.assertRaises(data.CompletedEplError): self.build(license=b'CC0')
        for field,value in (('repository_commit_sha','a'*40),('licence_id','UNKNOWN'),('path','2026-27/1-premierleague.txt')):
            item=replace(self.inputs[0],source=replace(self.inputs[0].source,**{field:value}))
            with self.assertRaises(data.CompletedEplError): self.build(values=(item,self.inputs[1]))
        with self.assertRaises(data.CompletedEplError): self.build(values=(replace(self.inputs[0],raw_bytes=self.inputs[0].raw_bytes+b'x'),self.inputs[1]))

    def test_spoofed_team_fixture_or_duplicate_source_rows_rejected(self):
        first=self.dataset.rows[0]
        for row in (replace(first,home_team_id='sunderland'),replace(first,original=replace(first.original,fixture_id='FORGED'))):
            attacked=data._seal(replace(self.dataset,rows=(row,)+self.dataset.rows[1:]))
            with self.assertRaises(data.CompletedEplError): self.build(dataset=attacked)
        attacked=data._seal(replace(self.dataset,rows=self.dataset.rows+(first,)))
        with self.assertRaises(data.CompletedEplError): self.build(dataset=attacked)

    def test_seal_and_resealed_training_reference_tamper(self):
        f=self.protocol.folds[0]
        row=replace(f.training[0],home_team_id='forged')
        changed=replace(f,training=(row,)+f.training[1:])
        with self.assertRaises(cp.ProtocolError): cp.protocol_json(replace(self.protocol,folds=(changed,)+self.protocol.folds[1:]))
        # Rebuild population too, defeating a superficial seal/population check.
        selected=changed.training
        population=tuple(sorted({t for r in selected for t in (r.home_team_id,r.away_team_id)}))
        changed=cp._seal(replace(changed,training_population=population))
        p=cp._seal(replace(self.protocol,folds=(changed,)+self.protocol.folds[1:]))
        with self.assertRaises(cp.ProtocolError): cp.verify_protocol(p,self.dataset,self.inputs,license_bytes=self.license)

    def test_resealed_target_in_training_and_partial_day(self):
        f=self.protocol.folds[0]
        changed=cp._seal(replace(f,training=f.training+(f.targets[0].fixture,)))
        with self.assertRaises(cp.ProtocolError): cp.protocol_json(cp._seal(replace(self.protocol,folds=(changed,)+self.protocol.folds[1:])))
        changed=cp._seal(replace(f,targets=f.targets[:1]))
        p=cp._seal(replace(self.protocol,folds=(changed,)+self.protocol.folds[1:]))
        with self.assertRaises(cp.ProtocolError): cp.verify_protocol(p,self.dataset,self.inputs,license_bytes=self.license)

    def test_resealed_governance_or_timing_mutation(self):
        for change in ({'exposure':((2025,'CONFIRMATORY'),)},{'warnings':()}, {'strict_point_in_time_eligible':True},
                       {'execution_status':'MODEL_FITTED'},{'kickoff_utc':'2025-01-01T15:00:00Z'}):
            with self.assertRaises(cp.ProtocolError): cp.protocol_json(cp._seal(replace(self.protocol,**change)))

    def test_resealed_exclusion_counts_need_source_replay(self):
        f=cp._seal(replace(self.protocol.folds[0],exclusions=()))
        p=cp._seal(replace(self.protocol,folds=(f,)+self.protocol.folds[1:]))
        with self.assertRaises(cp.ProtocolError): cp.verify_protocol(p,self.dataset,self.inputs,license_bytes=self.license)

    def test_nominal_round_trap_uses_actual_dates(self):
        lookup={r.original.fixture_id:r for r in self.dataset.rows}
        f=self.protocol.folds[-1]
        self.assertTrue(all(lookup[r.fixture_id].original.match_date<=f.training_date_limit for r in f.training))
        rounds=[lookup[r.fixture_id].nominal_round for r in f.training]
        self.assertNotEqual(rounds,sorted(rounds))

    def test_no_forbidden_execution_path_invoked(self):
        forbidden=('chronological_epl.fit_development','chronological_epl.forecast_holdout','chronological_epl.evaluate_holdout',
                   'chronological_epl._fit','chronological_epl._forecast','chronological_epl._evaluate','chronological_epl._bootstrap',
                   'real_epl_training._fit_rows','real_epl_training.fit_real_epl','expected_goals.fit_expected_goals',
                   'backtesting.score_1x2','result_evaluation.score_1x2','poisson.poisson_distribution')
        with ExitStack() as stack:
            for name in forbidden: stack.enter_context(patch('premfootballbot.'+name,side_effect=AssertionError(name)))
            stack.enter_context(patch('socket.socket',side_effect=AssertionError('network')))
            stack.enter_context(patch('builtins.open',side_effect=AssertionError('I/O')))
            stack.enter_context(patch.object(Path,'read_bytes',side_effect=AssertionError('disk')))
            self.assertEqual(self.build(),self.protocol)
            self.assertTrue(cp.verify_protocol(self.protocol,self.dataset,self.inputs,license_bytes=self.license))

    def test_no_label_clock_or_randomness_access_in_new_core(self):
        tree=ast.parse(Path(cp.__file__).read_text(encoding='utf8'))
        for n in ast.walk(tree):
            if isinstance(n,ast.Attribute):
                self.assertNotIn(n.attr,('home_goals_ft90','away_goals_ft90','now','utcnow','today','fit_development','_fit_rows','_scores'))
            if isinstance(n,ast.Import): self.assertNotIn('random',{i.name for i in n.names})

    def test_existing_synthetic_and_prospective_boundaries(self):
        raw=cp.protocol_json(self.protocol)
        self.assertFalse(parse_synthetic_json(raw).valid)
        with self.assertRaises(EvidenceError): freeze_packet(raw)


class TinyFoldOracleTests(unittest.TestCase):
    def test_manual_two_day_oracle_training_population_and_embargo(self):
        # Pure invented metadata, not accepted at source-backed public entrypoint.
        def row(identity,day,home,away):
            original=SimpleNamespace(fixture_id=identity,season_start_year=2024,match_date=date(2025,1,day),source_sha256='a'*64)
            return SimpleNamespace(original=original,home_team_id=home,away_team_id=away)
        rows=(row('early',1,'A','B'),row('Dminus1',2,'FUTURE_A','FUTURE_B'),
              row('target1',3,'A','C'),row('target2',3,'B','A'),row('future',4,'C','D'))
        actual=data.import_completed_epl(inputs(),license_bytes=(FIXTURE/'LICENSE.md').read_bytes())
        tiny=replace(actual,rows=rows)
        selected=old._folds(rows,(date(2025,1,3),),2)
        p=cp._assemble(tiny,selected,cp.ProtocolPolicy(minimum_history_matches=1))
        f=p.folds[0]
        self.assertEqual(tuple(r.fixture_id for r in f.training),('early',))
        self.assertEqual(tuple(t.fixture.fixture_id for t in f.targets),('target1','target2'))
        self.assertEqual(f.training_population,('A','B'))
        self.assertEqual(dict(f.exclusions),{'EMBARGO':1,'TARGET_DATE':2,'FUTURE_DEVELOPMENT':1})
        self.assertEqual(tuple(t.reason for t in f.targets),('UNSEEN_TEAM_ABSTAIN_CONTROL','HISTORY_ONLY_NO_EXECUTION'))


if __name__=='__main__': unittest.main()

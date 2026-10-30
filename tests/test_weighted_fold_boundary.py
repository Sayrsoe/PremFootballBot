"""Phase 4C2-B2A: read-only, source-backed chronological training boundary."""
import ast
from contextlib import ExitStack
from dataclasses import FrozenInstanceError, replace
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
import unittest

from premfootballbot import chronological_candidates as cp
from premfootballbot import completed_epl as data
from premfootballbot import weighted_fold_boundary as wb
from premfootballbot import weighted_poisson as wp
from premfootballbot import real_epl_training as old
from premfootballbot import chronological_epl as chron
from premfootballbot import retrospective_candidates as cold
from tests.test_completed_epl import inputs, FIXTURE

DATES = (date(2024, 8, 17), date(2024, 12, 26), date(2025, 1, 1), date(2025, 3, 8))


class SourceBackedBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = inputs()
        cls.license = (FIXTURE/'LICENSE.md').read_bytes()
        cls.dataset = data.import_completed_epl(cls.inputs, license_bytes=cls.license)
        cls.protocol = cp.build_protocol(cls.dataset, cls.inputs,
            license_bytes=cls.license, target_dates=DATES)
        cls.artifact = wb.build_training_boundary(cls.protocol, cls.dataset,
            cls.inputs, license_bytes=cls.license)

    def build(self, protocol=None, dataset=None, values=None, license=None):
        return wb.build_training_boundary(self.protocol if protocol is None else protocol,
            self.dataset if dataset is None else dataset,
            self.inputs if values is None else values,
            license_bytes=self.license if license is None else license)

    def verify(self, artifact=None, protocol=None, dataset=None, values=None, license=None):
        return wb.verify_training_boundary(self.artifact if artifact is None else artifact,
            self.protocol if protocol is None else protocol,
            self.dataset if dataset is None else dataset,
            self.inputs if values is None else values,
            license_bytes=self.license if license is None else license)

    def modified_fold(self, index=0, **changes):
        f = wb._seal(replace(self.artifact.folds[index], **changes))
        return wb._seal(replace(self.artifact,
            folds=self.artifact.folds[:index]+(f,)+self.artifact.folds[index+1:]))

    def test_public_builder_requires_source_replay_and_c1_audit(self):
        with patch.object(cp, 'verify_protocol', wraps=cp.verify_protocol) as verified, \
             patch.object(data, 'verify_completed_dataset', wraps=data.verify_completed_dataset) as sourced:
            self.assertEqual(self.build(), self.artifact)
        verified.assert_called_once()
        sourced.assert_called_once()
        self.assertTrue(self.verify())
        self.assertEqual(self.build(), self.build())

    def test_development_only_and_complete_date_group_boundaries(self):
        ids = set()
        for f, original in zip(self.artifact.folds, self.protocol.folds):
            self.assertEqual(f.target_date, original.target_date)
            self.assertEqual(f.protocol_fold_sha256, original.sha256)
            self.assertEqual(f.targets, original.targets)
            self.assertEqual(f.history_status, original.history_status)
            self.assertEqual(f.training_date_limit,
                             f.target_date-timedelta(days=self.artifact.policy.embargo_days))
            self.assertEqual(len(f.training), len(original.training))
            self.assertEqual(tuple(o.fixture for o in f.training), original.training)
            self.assertEqual(f.training_population, original.training_population)
            self.assertEqual({t.fixture.fixture_id for t in f.targets},
                             {r.original.fixture_id for r in self.dataset.rows
                              if r.original.season_start_year == 2024 and r.original.match_date == f.target_date})
            for t in f.targets:
                self.assertNotIn(t.fixture.fixture_id, ids)
                ids.add(t.fixture.fixture_id)
        self.assertEqual(self.artifact.target_count, len(ids))

    def test_explicit_ages_and_dminus2_not_dminus1(self):
        for f in self.artifact.folds:
            for o in f.training:
                self.assertEqual(o.age_days, (f.target_date-o.fixture.match_date).days)
                self.assertGreaterEqual(o.age_days, 2)
                self.assertLessEqual(o.fixture.match_date, f.training_date_limit)
                self.assertEqual(o.fixture.season_start_year, 2024)
        p = cp.build_protocol(self.dataset, self.inputs, license_bytes=self.license,
            target_dates=(date(2025, 1, 1),))
        f = self.build(protocol=p).folds[0]
        self.assertEqual(f.training_date_limit, date(2024, 12, 30))
        self.assertTrue(all(o.age_days >= 2 for o in f.training))
        self.assertTrue(any(o.age_days == 2 for o in f.training))

    def test_training_labels_are_exact_for_authorized_selected_ids_only(self):
        lookup = {r.original.fixture_id:r for r in self.dataset.rows}
        for f in self.artifact.folds:
            for obs in f.training:
                original = lookup[obs.fixture.fixture_id]
                self.assertEqual((obs.home_goals_ft90, obs.away_goals_ft90),
                                 (original.original.home_goals_ft90, original.original.away_goals_ft90))
                self.assertEqual((obs.fixture.home_team_id, obs.fixture.away_team_id),
                                 (original.home_team_id, original.away_team_id))
                self.assertEqual(obs.fixture.source_sha256, original.original.source_sha256)

    def test_under_100_history_is_not_fitted(self):
        self.assertEqual(self.artifact.folds[0].history_status, 'INSUFFICIENT_HISTORY')
        self.assertEqual(len(self.artifact.folds[0].training), 0)
        for f in self.artifact.folds:
            self.assertIs(f.real_fitting_authorized, False)
        self.assertIs(self.artifact.real_fitting_authorized, False)
        self.assertIs(self.artifact.scoring_authorized, False)
        self.assertIs(self.artifact.candidate_selection_authorized, False)

    def test_typed_and_immutable_manifest_not_a_toy_adapter(self):
        with self.assertRaises(FrozenInstanceError):
            self.artifact.folds[0].target_date = date.today()
        with self.assertRaises(FrozenInstanceError):
            self.artifact.real_fitting_authorized = True
        f = self.artifact.folds[2]
        self.assertTrue(f.training)
        self.assertEqual(type(f.training[0]), wb.TrainingObservation)
        self.assertNotIsInstance(f.training[0], wp.InventedMatch)
        self.assertNotIn(b'toy:', wb.boundary_json(self.artifact))
        self.assertIsNone(self.artifact.kickoff_utc)
        self.assertIsNone(self.artifact.historical_available_at)
        self.assertIs(self.artifact.strict_point_in_time_eligible, False)
        self.assertEqual(self.artifact.exposure, ((2024, 'DEVELOPMENT_ONLY'), (2025, cp.EXPOSED)))

    def test_private_assembly_ignores_target_future_embargo_holdout_goals(self):
        p = cp.build_protocol(self.dataset, self.inputs, license_bytes=self.license,
            target_dates=(date(2025, 1, 1),))
        training_ids = {r.fixture_id for r in p.folds[0].training}
        expected = wb._assemble(p, self.dataset.rows)
        poisoned = tuple(row if row.original.fixture_id in training_ids else replace(row,
            original=replace(row.original, home_goals_ft90='NOT_A_SCORE', away_goals_ft90=None))
            for row in self.dataset.rows)
        self.assertEqual(wb._assemble(p, poisoned), expected)
        with self.assertRaises(ValueError):
            self.build(protocol=p, dataset=data._seal(replace(self.dataset, rows=poisoned)))

    def test_private_assembly_ignores_excluded_roster_details(self):
        p = cp.build_protocol(self.dataset, self.inputs, license_bytes=self.license,
            target_dates=(date(2025, 1, 1),))
        ids = {r.fixture_id for r in p.folds[0].training}
        poisoned = tuple(row if row.original.fixture_id in ids else replace(row,
            home_team_id='UNTRUSTED_AFTER_CUTOFF', away_team_id='UNTRUSTED_2025') for row in self.dataset.rows)
        self.assertEqual(wb._assemble(p, poisoned), wb._assemble(p, self.dataset.rows))

    def test_training_label_mutation_changes_digest_and_is_rejected_publicly(self):
        f = self.protocol.folds[2]
        ref = f.training[0]
        changed = tuple(replace(r,original=replace(r.original,
            home_goals_ft90=(r.original.home_goals_ft90+1)%5))
            if r.original.fixture_id == ref.fixture_id else r for r in self.dataset.rows)
        p = cp._seal(replace(self.protocol, folds=(f,)))
        before = wb._assemble(p, self.dataset.rows)
        after = wb._assemble(p, changed)
        self.assertNotEqual(before.folds[0].training_rows_sha256,after.folds[0].training_rows_sha256)
        self.assertEqual(before.folds[0].training_ids_sha256, after.folds[0].training_ids_sha256)
        with self.assertRaises(ValueError):
            self.build(protocol=p, dataset=data._seal(replace(self.dataset, rows=changed)))

    def test_input_license_and_pinned_source_changes_rejected(self):
        with self.assertRaises(ValueError): self.build(license=b'wrong')
        raw = self.inputs[0]
        bad_input = replace(raw, raw_bytes=raw.raw_bytes + b'\n# tampered')
        with self.assertRaises(ValueError): self.build(values=(bad_input,)+self.inputs[1:])
        with self.assertRaises(ValueError): self.build(dataset=replace(self.dataset, sha256='0'*64))

    def test_policy_cannot_lower_100_history(self):
        p = cp.build_protocol(self.dataset,self.inputs,license_bytes=self.license,
            target_dates=(DATES[1],),policy=cp.ProtocolPolicy(minimum_history_matches=99))
        with self.assertRaises(wb.TrainingBoundaryError): self.build(protocol=p)
        p = cp.build_protocol(self.dataset,self.inputs,license_bytes=self.license,
            target_dates=(DATES[1],),policy=cp.ProtocolPolicy(embargo_days=3, minimum_history_matches=380))
        self.assertEqual(self.build(protocol=p).folds[0].history_status,'INSUFFICIENT_HISTORY')

    def test_denied_holdout_target_dates(self):
        with self.assertRaises(ValueError):
            cp.build_protocol(self.dataset,self.inputs,license_bytes=self.license,
                target_dates=(date(2025, 8, 15),))
        with self.assertRaises(ValueError):
            cp.build_protocol(self.dataset,self.inputs,license_bytes=self.license,
                target_dates=(date(2026, 5, 3),))

    def test_c1_resigned_identity_spoof_rejected(self):
        f=self.protocol.folds[2]
        fraud=replace(f.training[0],home_team_id='fake-team')
        forged=cp._seal(replace(f,training=(fraud,)+f.training[1:]))
        protocol=cp._seal(replace(self.protocol,folds=self.protocol.folds[:2]+(forged,)+self.protocol.folds[3:]))
        with self.assertRaises(ValueError):self.build(protocol=protocol)

    def test_resealed_age_spoof_fails_structural_validation(self):
        f=self.artifact.folds[2]
        tampered=replace(f.training[0], age_days=f.training[0].age_days+1)
        fake=self.modified_fold(index=2,training=(tampered,)+f.training[1:])
        with self.assertRaises(wb.TrainingBoundaryError):wb.boundary_json(fake)

    def test_resealed_train_goal_spoof_fails_hash_and_source_replay(self):
        f=self.artifact.folds[2]
        tampered=replace(f.training[0],home_goals_ft90=(f.training[0].home_goals_ft90+1)%5)
        fake=self.modified_fold(index=2,training=(tampered,)+f.training[1:])
        with self.assertRaises(wb.TrainingBoundaryError):wb.boundary_json(fake)
        rows=(tampered,)+f.training[1:]
        adjusted=wb._seal(replace(f,training=rows,training_rows_sha256=data.archive._hash(tuple(
            (r.fixture,r.home_goals_ft90,r.away_goals_ft90,r.age_days) for r in rows))))
        sealed=wb._seal(replace(self.artifact,folds=self.artifact.folds[:2]+(adjusted,)+self.artifact.folds[3:]))
        wb.boundary_json(sealed)  # Re-sealing is not source authorization.
        with self.assertRaises(wb.TrainingBoundaryError):self.verify(artifact=sealed)

    def test_resealed_target_elision_fails_source_backed_replay(self):
        f=self.artifact.folds[3]
        self.assertGreater(len(f.targets), 1)
        removed=f.targets[1:]
        altered=wb._seal(replace(f,targets=removed))
        fake=wb._seal(replace(self.artifact,
            folds=self.artifact.folds[:3]+(altered,)+self.artifact.folds[4:],
            target_count=self.artifact.target_count-1))
        wb.boundary_json(fake)
        with self.assertRaises(wb.TrainingBoundaryError):self.verify(artifact=fake)

    def test_bad_flags_and_missing_target_rejected(self):
        for field in ('real_fitting_authorized','scoring_authorized','candidate_selection_authorized',
                      'strict_point_in_time_eligible'):
            with self.subTest(field=field), self.assertRaises(wb.TrainingBoundaryError):
                wb.boundary_json(wb._seal(replace(self.artifact, **{field:True})))
        fake=self.modified_fold(index=2,targets=())
        with self.assertRaises(wb.TrainingBoundaryError):wb.boundary_json(fake)

    def test_invalid_type_and_timing_metadata_denied(self):
        with self.assertRaises(wb.TrainingBoundaryError):wb.boundary_json(replace(self.artifact,folds=list(self.artifact.folds)))
        with self.assertRaises(wb.TrainingBoundaryError):wb.boundary_json(wb._seal(replace(self.artifact,historical_available_at='invented')))
        with self.assertRaises(wb.TrainingBoundaryError):wb.boundary_json(wb._seal(replace(self.artifact,kickoff_utc='invented')))
        f=self.artifact.folds[2]
        o=replace(f.training[0],home_goals_ft90=True)
        fake=self.modified_fold(index=2,training=(o,)+f.training[1:])
        with self.assertRaises(wb.TrainingBoundaryError):wb.boundary_json(fake)

    def test_different_protocol_cannot_verify_existing_boundary(self):
        p=cp.build_protocol(self.dataset,self.inputs,license_bytes=self.license,target_dates=(DATES[1],))
        with self.assertRaises(wb.TrainingBoundaryError):self.verify(protocol=p)

    def test_complete_2024_date_count_and_label_free_targets(self):
        dates=tuple(sorted({r.original.match_date for r in self.dataset.rows if r.original.season_start_year==2024}))
        p=cp.build_protocol(self.dataset,self.inputs,license_bytes=self.license,target_dates=dates)
        a=self.build(protocol=p)
        self.assertEqual(len(a.folds),109)
        self.assertEqual(a.target_count,380)
        ids=[r.fixture.fixture_id for f in a.folds for r in f.training]
        self.assertEqual(len(ids),sum(len(f.training) for f in a.folds))
        self.assertTrue(all(t.fixture.season_start_year==2024 for f in a.folds for t in f.targets))
        self.assertTrue(all(not hasattr(t, 'home_goals_ft90') for f in a.folds for t in f.targets))
        self.assertTrue(wb.verify_training_boundary(a,p,self.dataset,self.inputs,license_bytes=self.license))

    def test_no_model_call_or_internal_io_even_on_public_build(self):
        with ExitStack() as stack:
            guards=[(wp,'fit_invented_matches'),(old,'_fit_rows'),(chron,'fit_development'),
                    (cold,'build_cold_start_artifact')]
            mocks=[stack.enter_context(patch.object(obj,key,side_effect=AssertionError('no fitting/other pipeline')))
                   for obj,key in guards]
            self.assertEqual(self.build(),self.artifact)
        for m in mocks:m.assert_not_called()

    def test_ast_no_toystream_fitter_clock_network_or_files(self):
        path=Path(wb.__file__)
        tree=ast.parse(path.read_text(encoding='utf8'),feature_version=(3,10))
        imports=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
        self.assertNotIn('weighted_poisson',imports)
        self.assertEqual({n.module for n in ast.walk(tree)
                          if isinstance(n,ast.ImportFrom) and n.level==0},
                         {'__future__','dataclasses','datetime'})
        code=path.read_text(encoding='utf8')
        for banned in ('fit_invented_matches(', 'InventedMatch(', 'open(', 'os.', 'requests.',
                       'urllib.', 'datetime.now(', 'date.today(', 'random.', 'sklearn.', 'numpy.'):
            self.assertNotIn(banned, code)


if __name__=='__main__':
    unittest.main()

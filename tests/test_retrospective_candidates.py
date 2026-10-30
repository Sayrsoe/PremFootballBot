"""C2-A: invented pure oracles versus the exact pinned public archive pathway."""
import ast
from collections import Counter
from contextlib import ExitStack
from dataclasses import FrozenInstanceError, replace
from datetime import date, timedelta
from fractions import Fraction
import json
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from premfootballbot import retrospective_candidates as cs
from premfootballbot import chronological_candidates as cp
from premfootballbot import completed_epl as data
from premfootballbot.match_data import parse_synthetic_json
from premfootballbot.prospective_evidence import EvidenceError, freeze_packet
from tests.test_completed_epl import inputs, FIXTURE

DATES = (date(2024, 8, 17), date(2024, 12, 26), date(2025, 1, 1), date(2025, 3, 8))


class PureOracleTests(unittest.TestCase):
    """Invented counts/rows ONLY, never asserted to be source-authorized folds."""
    def test_hand_calculated_no_smoothing_probabilities(self):
        category, reason, p = cs._decision((3, 1, 2), 6, ('A', 'B'), 'A', 'UNKNOWN')
        self.assertEqual((category, reason), ('PRIOR_ONLY', 'TEAM_STRENGTH_UNIDENTIFIED'))
        self.assertEqual(p, tuple(float(Fraction(n, 6)) for n in (3, 1, 2)))
        self.assertEqual(p, (0.5, 1/6, 1/3))
        self.assertTrue(all(math.isfinite(x) and 0 < x <= 1 for x in p))
        self.assertAlmostEqual(math.fsum(p), 1, places=15)

    def test_one_or_both_unseen_same_unconditional_prior(self):
        for h, a in (('A', 'X'), ('X', 'B'), ('X', 'Y')):
            self.assertEqual(cs._decision((1, 1, 1), 3, ('A', 'B'), h, a),
                ('PRIOR_ONLY', 'TEAM_STRENGTH_UNIDENTIFIED', (1/3, 1/3, 1/3)))

    def test_established_teams_not_fitted_or_evaluated(self):
        self.assertEqual(cs._decision((3, 1, 2), 6, ('A', 'B'), 'A', 'B'),
                         ('ESTABLISHED_HISTORY', 'ESTABLISHED_NOT_EVALUATED', ()))

    def test_minimum_history_boundary_and_precedence(self):
        for counts in ((0, 0, 0), (3, 1, 1), (5, 0, 0)):
            self.assertEqual(cs._decision(counts, 6, ('A', 'B'), 'A', 'X'),
                             ('ABSTAIN', 'INSUFFICIENT_HISTORY', ()))
        self.assertEqual(cs._decision((3, 1, 2), 6, ('A', 'B'), 'A', 'X')[0], 'PRIOR_ONLY')

    def test_zero_class_abstains_even_for_established(self):
        for counts in ((0, 2, 4), (2, 0, 4), (2, 4, 0)):
            for away in ('B', 'X'):
                self.assertEqual(cs._decision(counts, 6, ('A', 'B'), 'A', away),
                                 ('ABSTAIN', 'ZERO_TRAINING_CLASS', ()))

    def test_bad_counts_numeric_and_threshold_fail_closed(self):
        for counts in ((-1, 2, 3), (True, 1, 2), (1.0, 1, 2), (math.nan, 1, 2),
                       (math.inf, 1, 2), (380, 1, 1), (1, 2), [1, 2, 3]):
            with self.subTest(counts=counts), self.assertRaises(cs.ColdStartError):
                cs._decision(counts, 1, ('A', 'B'), 'A', 'X')
        for minimum in (0, True, 1.0, 381):
            with self.assertRaises(cs.ColdStartError): cs._decision((1, 1, 1), minimum, (), 'A', 'X')

    def test_bad_population_or_target_identity_fail_closed(self):
        for population, h, a in ((['A'], 'A', 'X'), (('B', 'A'), 'A', 'X'),
                                  (('A', 'A'), 'A', 'X'), (('A',), 'A', 'A'), ((), '', 'X')):
            with self.assertRaises(cs.ColdStartError): cs._decision((1, 1, 1), 1, population, h, a)

    @staticmethod
    def oracle():
        # Six invented historical FT90 results:3H,1D,2A. Public importer rejects.
        rows = []
        for i, (h, a) in enumerate(((2, 0), (1, 0), (3, 2), (1, 1), (0, 1), (1, 2)), 1):
            r = SimpleNamespace(fixture_id=f'invented-{i}', season_start_year=2024,
                match_date=date(2024, 8, i), source_sha256='a'*64, home_goals_ft90=h, away_goals_ft90=a)
            rows.append(SimpleNamespace(original=r, home_team_id='A', away_team_id='B'))
        refs = tuple(cp.FixtureReference(r.original.fixture_id, 2024, r.original.match_date,
                                        'A', 'B', 'a'*64) for r in rows)
        fold = SimpleNamespace(training=refs, training_date_limit=date(2024, 8, 6))
        return fold, tuple(rows)

    def test_rejoined_labels_match_manual_training_counts(self):
        fold, rows = self.oracle()
        counts, ids_hash, rows_hash = cs._training_summary(fold, rows)
        self.assertEqual(counts, (3, 1, 2))
        self.assertEqual(ids_hash, data.archive._hash(tuple(r.fixture_id for r in fold.training)))
        self.assertEqual(len(rows_hash), 64)
        self.assertEqual(cs._training_summary(fold, tuple(reversed(rows))), (counts, ids_hash, rows_hash))

    def test_training_join_rejects_missing_duplicate_wrong_source_season_team_date(self):
        fold, rows = self.oracle()
        for changed in (rows[:-1], rows+(rows[0],)):
            with self.assertRaises(cs.ColdStartError): cs._training_summary(fold, changed)
        for field, value in (('source_sha256', 'b'*64), ('season_start_year', 2025),
                             ('match_date', date(2024, 8, 7)), ('home_team_id', 'X')):
            ref = replace(fold.training[0], **{field: value})
            attacked = SimpleNamespace(training=(ref,)+fold.training[1:], training_date_limit=fold.training_date_limit)
            with self.assertRaises(cs.ColdStartError): cs._training_summary(attacked, rows)
        duplicate = SimpleNamespace(training=fold.training+(fold.training[0],), training_date_limit=fold.training_date_limit)
        with self.assertRaises(cs.ColdStartError): cs._training_summary(duplicate, rows)

    def test_selected_invalid_goal_does_not_return_partial_counts(self):
        fold, rows = self.oracle()
        for value in (None, True, -1, 1.0, math.inf, math.nan, 101):
            bad = SimpleNamespace(**{**vars(rows[-1].original), 'home_goals_ft90': value})
            attacked = rows[:-1]+(SimpleNamespace(original=bad, home_team_id='A', away_team_id='B'),)
            with self.assertRaises(cs.ColdStartError): cs._training_summary(fold, attacked)

    def test_training_cutoff_includes_Dminus2_excludes_Dminus1(self):
        fold, rows = self.oracle()
        # Explicit cutoff Aug6 for a notional Aug8 target. Aug6 is allowed.
        self.assertEqual(sum(cs._training_summary(fold, rows)[0]), 6)
        attacked = SimpleNamespace(training=fold.training, training_date_limit=date(2024, 8, 5))
        with self.assertRaises(cs.ColdStartError): cs._training_summary(attacked, rows)


class SourceBackedColdStartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = inputs()
        cls.license = (FIXTURE/'LICENSE.md').read_bytes()
        cls.dataset = data.import_completed_epl(cls.inputs, license_bytes=cls.license)
        cls.protocol = cp.build_protocol(cls.dataset, cls.inputs, license_bytes=cls.license, target_dates=DATES)
        cls.artifact = cs.build_cold_start_artifact(cls.protocol, cls.dataset, cls.inputs, license_bytes=cls.license)

    def build(self, protocol=None, dataset=None, values=None, license=None):
        return cs.build_cold_start_artifact(self.protocol if protocol is None else protocol,
            self.dataset if dataset is None else dataset, self.inputs if values is None else values,
            license_bytes=self.license if license is None else license)

    def verify(self, artifact):
        return cs.verify_cold_start_artifact(artifact, self.protocol, self.dataset, self.inputs, license_bytes=self.license)

    def changed_first_fold(self, **changes):
        fold = cs._seal(replace(self.artifact.folds[0], **changes))
        return cs._seal(replace(self.artifact, folds=(fold,)+self.artifact.folds[1:]))

    def test_public_calls_source_and_protocol_replay_before_assembly(self):
        with patch.object(data, 'verify_completed_dataset', wraps=data.verify_completed_dataset) as source, \
             patch.object(cp, 'verify_protocol', wraps=cp.verify_protocol) as protocol:
            self.assertEqual(self.build(), self.artifact)
        source.assert_called_once()
        protocol.assert_called_once()

    def test_training_only_counts_independent_comprehension(self):
        lookup = {r.original.fixture_id:r for r in self.dataset.rows}
        for cf, pf in zip(self.artifact.folds, self.protocol.folds):
            counted = Counter()
            for ref in pf.training:
                r = lookup[ref.fixture_id].original
                counted['H' if r.home_goals_ft90 > r.away_goals_ft90 else 'D' if r.home_goals_ft90 == r.away_goals_ft90 else 'A'] += 1
            self.assertEqual(cf.training_counts, tuple(counted[k] for k in ('H', 'D', 'A')))
            self.assertEqual(sum(cf.training_counts), len(pf.training))
            self.assertEqual(cf.training_ids, tuple(r.fixture_id for r in pf.training))
            self.assertEqual(cf.fold_sha256, pf.sha256)

    def test_target_label_embargo_future_and_holdout_roster_poison_invariance(self):
        # Private assembly isolates dependency proof, never authorizes tampered
        # source. Every excluded result is an invalid nonnumeric sentinel.
        protocol = cp.build_protocol(self.dataset, self.inputs, license_bytes=self.license, target_dates=(date(2025, 1, 5),))
        training = {r.fixture_id for r in protocol.folds[0].training}
        expected = cs._assemble(protocol, self.dataset.rows)
        changed = tuple(r if r.original.fixture_id in training else replace(r,
            home_team_id='INVENTED_FUTURE_ROSTER', away_team_id='INVENTED_OTHER_TEAM',
            original=replace(r.original, home_goals_ft90='POISON', away_goals_ft90=None)) for r in self.dataset.rows)
        self.assertEqual(cs._assemble(protocol, changed), expected)
        self.assertTrue(any(r.original.match_date == date(2025, 1, 4) for r in changed))
        attacked = data._seal(replace(self.dataset, rows=changed))
        with self.assertRaises(data.CompletedEplError): self.build(protocol=protocol, dataset=attacked)

    def test_same_day_labels_are_never_read_even_first_opener(self):
        p = cp.build_protocol(self.dataset, self.inputs, license_bytes=self.license, target_dates=(date(2024, 8, 16),))
        changed = tuple(replace(r, original=replace(r.original, home_goals_ft90=None, away_goals_ft90=None)) for r in self.dataset.rows)
        self.assertEqual(cs._assemble(p, changed), cs._assemble(p, self.dataset.rows))

    def test_calendar_boundaries_and_whole_target_dates(self):
        p = cp.build_protocol(self.dataset, self.inputs, license_bytes=self.license,
                              target_dates=(date(2025, 1, 1), date(2025, 2, 15)))
        a = self.build(protocol=p)
        self.assertEqual(a.folds[0].training_date_limit, date(2024, 12, 30))
        self.assertGreater((a.folds[1].target_date-date(2024, 8, 16)).days, 180)
        for fold in a.folds:
            expected = {r.original.fixture_id for r in self.dataset.rows
                        if r.original.season_start_year == 2024 and r.original.match_date == fold.target_date}
            self.assertEqual({f.fixture.fixture_id for f in fold.forecasts}, expected)
            self.assertTrue(all(r.match_date <= fold.training_date_limit for pf in p.folds
                                if pf.target_date == fold.target_date for r in pf.training))

    def test_all_development_dates_actual_coverage_without_manufactured_cold_start(self):
        dates = tuple(sorted({r.original.match_date for r in self.dataset.rows if r.original.season_start_year == 2024}))
        p = cp.build_protocol(self.dataset, self.inputs, license_bytes=self.license, target_dates=dates)
        a = self.build(protocol=p)
        forecasts = tuple(f for fold in a.folds for f in fold.forecasts)
        self.assertEqual(a.all_targets, 380)
        self.assertEqual(len({f.fixture.fixture_id for f in forecasts}), 380)
        self.assertEqual(dict(a.category_counts), {'ESTABLISHED_HISTORY':280, 'PRIOR_ONLY':0, 'ABSTAIN':100})
        self.assertTrue(all(not f.probabilities for f in forecasts))
        self.assertTrue(all(f.fixture.season_start_year == 2024 for f in forecasts))

    def test_explicit_unfitted_and_insufficient_categories(self):
        self.assertTrue(all(f.category == 'ABSTAIN' and f.reason == 'INSUFFICIENT_HISTORY'
                            for f in self.artifact.folds[0].forecasts))
        self.assertTrue(all(f.category == 'ESTABLISHED_HISTORY' and f.reason == 'ESTABLISHED_NOT_EVALUATED'
                            and not f.probabilities for fold in self.artifact.folds[1:] for f in fold.forecasts))

    def test_sealed_invented_unknown_team_artifact_math_and_public_rejection(self):
        # Deliberately forged target identity, ONLY a private assembly oracle.
        # Real eligible development folds have no unknown-team cases.
        fold = self.protocol.folds[1]
        target = replace(fold.targets[0].fixture, away_team_id='INVENTED_UNKNOWN_TEAM')
        audit = cp.TargetAudit(target, 'NO_PREDICTION', 'UNSEEN_TEAM_ABSTAIN_CONTROL')
        fold = cp._seal(replace(fold, targets=(audit,)+fold.targets[1:]))
        p = cp._seal(replace(self.protocol, folds=(fold,)))
        a = cs._assemble(p, self.dataset.rows)
        forecast = a.folds[0].forecasts[0]
        self.assertEqual(forecast.category, 'PRIOR_ONLY')
        self.assertEqual(forecast.reason, 'TEAM_STRENGTH_UNIDENTIFIED')
        self.assertEqual(forecast.probabilities, tuple(float(Fraction(n, forecast.training_matches))
                                                     for n in forecast.training_counts))
        self.assertEqual(dict(a.category_counts), {'ESTABLISHED_HISTORY':7, 'PRIOR_ONLY':1, 'ABSTAIN':0})
        self.assertEqual(a.all_targets, 8)
        cs.cold_start_json(a)
        forged = replace(forecast, probabilities=(0.5, 0.25, 0.25))
        group = cs._seal(replace(a.folds[0], forecasts=(forged,)+a.folds[0].forecasts[1:]))
        with self.assertRaises(cs.ColdStartError): cs.cold_start_json(cs._seal(replace(a, folds=(group,))))
        with self.assertRaises(cp.ProtocolError): self.build(protocol=p)
        with self.assertRaises(cs.ColdStartError): self.verify(a)

    def test_training_result_change_changes_private_prior_and_digest_not_ids(self):
        p = cp._seal(replace(self.protocol, folds=(self.protocol.folds[1],)))
        ref = p.folds[0].training[0]
        row = next(r for r in self.dataset.rows if r.original.fixture_id == ref.fixture_id)
        changed = replace(row, original=replace(row.original, home_goals_ft90=0, away_goals_ft90=0))
        rows = tuple(changed if r.original.fixture_id == ref.fixture_id else r for r in self.dataset.rows)
        before = cs._assemble(p, self.dataset.rows).folds[0]
        after = cs._assemble(p, rows).folds[0]
        self.assertNotEqual(before.training_counts, after.training_counts)
        self.assertNotEqual(before.training_rows_sha256, after.training_rows_sha256)
        self.assertEqual(before.training_ids_sha256, after.training_ids_sha256)

    def test_minimum_floor_cannot_be_weakened_to_create_real_prior_cases(self):
        for minimum in (1, 99):
            p = cp.build_protocol(self.dataset, self.inputs, license_bytes=self.license,
                target_dates=(DATES[1],), policy=cp.ProtocolPolicy(minimum_history_matches=minimum))
            with self.assertRaises(cs.ColdStartError): self.build(protocol=p)
        p = cp.build_protocol(self.dataset, self.inputs, license_bytes=self.license,
            target_dates=(DATES[1],), policy=cp.ProtocolPolicy(minimum_history_matches=380, embargo_days=3))
        self.assertEqual(dict(self.build(protocol=p).category_counts)['ESTABLISHED_HISTORY'], 0)

    def test_no_targets_labels_scores_or_fitted_parameters_in_artifact(self):
        payload = json.loads(cs.cold_start_json(self.artifact))
        forbidden = {'home_goals', 'away_goals', 'home_goals_ft90', 'away_goals_ft90', 'actual',
                     'outcome', 'brier', 'log_loss', 'metrics', 'coefficients', 'rates', 'model'}
        def walk(v):
            if isinstance(v, dict):
                self.assertFalse(forbidden & set(v))
                for child in v.values(): walk(child)
            elif isinstance(v, list):
                for child in v: walk(child)
        walk(payload)

    def test_restrictions_sources_and_exposure_at_every_level(self):
        a = self.artifact
        self.assertEqual(a.sources, self.protocol.sources)
        self.assertEqual(a.dataset_sha256, self.dataset.sha256)
        self.assertEqual(a.protocol_sha256, self.protocol.sha256)
        self.assertEqual(a.exposure, ((2024, 'DEVELOPMENT_ONLY'), (2025, cp.EXPOSED)))
        for item in (a, *a.folds, *(f for fold in a.folds for f in fold.forecasts)):
            self.assertEqual(item.status, cp.STATUS)
            self.assertIsNone(item.historical_available_at)
            self.assertIsNone(item.kickoff_utc)
            self.assertIs(item.strict_point_in_time_eligible, False)

    def test_deterministic_source_row_date_order_and_replay(self):
        p = cp.build_protocol(self.dataset, tuple(reversed(self.inputs)), license_bytes=self.license,
                              target_dates=tuple(reversed(DATES)))
        self.assertEqual(cs.cold_start_json(self.build(protocol=p, values=tuple(reversed(self.inputs)))), cs.cold_start_json(self.artifact))
        self.assertEqual(cs._assemble(p, tuple(reversed(self.dataset.rows))), self.artifact)
        self.assertTrue(self.verify(self.artifact))

    def test_frozen_nested_objects_and_untrusted_json_not_accepted(self):
        for obj, field in ((self.artifact, 'sha256'), (self.artifact.folds[0], 'sha256'),
                           (self.artifact.folds[0].forecasts[0], 'reason')):
            with self.assertRaises(FrozenInstanceError): setattr(obj, field, 'tamper')
        for raw in ({}, cs.cold_start_json(self.artifact), json.loads(cs.cold_start_json(self.artifact))):
            with self.assertRaises(cs.ColdStartError): cs.cold_start_json(raw)
            with self.assertRaises(cs.ColdStartError): self.build(protocol=raw)

    def test_license_and_source_credentials_tamper_rejected_before_label_join(self):
        with patch.object(cs, '_assemble', side_effect=AssertionError('assembly before source verification')):
            for license in (b'', b'CC0', self.license+b' '):
                with self.assertRaises(data.CompletedEplError): self.build(license=license)
            for field, value in (('repository_url', 'https://example.com'), ('repository_commit_sha', 'a'*40),
                                 ('path', '2023-24/1-premierleague.txt'), ('path', '2026-27/1-premierleague.txt'),
                                 ('licence_id', 'UNKNOWN'), ('expected_sha256', 'a'*64), ('expected_git_blob_sha', 'a'*40)):
                item = replace(self.inputs[0], source=replace(self.inputs[0].source, **{field:value}))
                with self.assertRaises(data.CompletedEplError): self.build(values=(item, self.inputs[1]))
            with self.assertRaises(data.CompletedEplError): self.build(values=(replace(self.inputs[0], raw_bytes=self.inputs[0].raw_bytes+b' '), self.inputs[1]))

    def test_resealed_archive_scores_aliases_season_and_duplicate_rejected(self):
        row = self.dataset.rows[0]
        attacks = (replace(row, home_team_id='burnley'), replace(row, original=replace(row.original, season_start_year=2025)),
                   replace(row, original=replace(row.original, home_goals_ft90=99)))
        for changed in attacks:
            dataset = data._seal(replace(self.dataset, rows=(changed,)+self.dataset.rows[1:]))
            with self.assertRaises(data.CompletedEplError): self.build(dataset=dataset)
        with self.assertRaises(data.CompletedEplError): self.build(dataset=data._seal(replace(self.dataset, rows=self.dataset.rows+(row,))))

    def test_protocol_partial_target_day_and_holdout_laundering_rejected(self):
        f = cp._seal(replace(self.protocol.folds[1], targets=self.protocol.folds[1].targets[:1]))
        p = cp._seal(replace(self.protocol, folds=(self.protocol.folds[0], f)+self.protocol.folds[2:]))
        with self.assertRaises(cp.ProtocolError): self.build(protocol=p)
        for policy in (replace(self.protocol.policy, selection_seasons=(2024, 2025)),
                       replace(self.protocol.policy, exposed_label='UNTOUCHED'), replace(self.protocol.policy, embargo_days=1)):
            with self.assertRaises(cp.ProtocolError): self.build(protocol=cp._seal(replace(self.protocol, policy=policy)))

    def test_unsealed_or_resealed_probability_category_and_count_tamper(self):
        f = self.artifact.folds[0].forecasts[0]
        for change in ({'probabilities':(1., 0., 0.)}, {'probabilities':(math.nan, 0., 0.)},
                       {'category':'PRIOR_ONLY'}, {'training_counts':(1, 1, 1)}, {'training_matches':False}):
            with self.assertRaises(ValueError):
                # Canonical no-NaN encoding may reject before a seal exists.
                changed = self.changed_first_fold(forecasts=(replace(f, **change),)+self.artifact.folds[0].forecasts[1:])
                self.verify(changed)
        with self.assertRaises(cs.ColdStartError): self.verify(replace(self.artifact, all_targets=999))

    def test_resealed_consistent_wrong_support_requires_source_replay(self):
        first = self.artifact.folds[0]
        forecasts = tuple(replace(f, training_rows_sha256='f'*64) for f in first.forecasts)
        changed = self.changed_first_fold(training_rows_sha256='f'*64, forecasts=forecasts)
        cs.cold_start_json(changed)  # A checksum is not source authorization.
        with self.assertRaises(cs.ColdStartError): self.verify(changed)

    def test_resealed_forged_target_identity_or_partial_group_rejected(self):
        fold = self.artifact.folds[1]
        f = fold.forecasts[0]
        changed = cs._seal(replace(fold, forecasts=(replace(f, fixture=replace(f.fixture, fixture_id='FORGED')),)+fold.forecasts[1:]))
        a = cs._seal(replace(self.artifact, folds=(self.artifact.folds[0], changed)+self.artifact.folds[2:]))
        cs.cold_start_json(a)
        with self.assertRaises(cs.ColdStartError): self.verify(a)
        # Reconcile aggregate counts too, so only source replay exposes omission.
        changed = cs._seal(replace(fold, forecasts=fold.forecasts[:1]))
        a = cs._seal(replace(self.artifact, folds=(self.artifact.folds[0], changed)+self.artifact.folds[2:],
            all_targets=self.artifact.all_targets-7, category_counts=tuple((k,n-7 if k=='ESTABLISHED_HISTORY' else n) for k,n in self.artifact.category_counts)))
        cs.cold_start_json(a)
        with self.assertRaises(cs.ColdStartError): self.verify(a)

    def test_resealed_duplicate_targets_and_counts_do_not_reconcile(self):
        first = self.artifact.folds[0]
        with self.assertRaises(cs.ColdStartError): cs.cold_start_json(self.changed_first_fold(forecasts=first.forecasts+(first.forecasts[0],)))
        with self.assertRaises(cs.ColdStartError): cs.cold_start_json(cs._seal(replace(self.artifact, all_targets=0)))

    def test_timing_and_disclaimer_laundering_rejected(self):
        for change in ({'warnings':()}, {'version':'NEW'}, {'exposure':((2025, 'CLEAN'),)},
                       {'strict_point_in_time_eligible':True}, {'kickoff_utc':'2025-01-01T15:00:00Z'},
                       {'historical_available_at':'2024-08-01'}):
            with self.assertRaises(cs.ColdStartError): self.verify(cs._seal(replace(self.artifact, **change)))

    def test_no_fitter_scorer_network_clock_or_file_access(self):
        forbidden = ('chronological_epl.fit_development', 'chronological_epl.forecast_holdout', 'chronological_epl.evaluate_holdout',
            'chronological_epl._fit', 'chronological_epl._forecast', 'chronological_epl._evaluate', 'chronological_epl._bootstrap',
            'real_epl_training._fit_rows', 'real_epl_training.fit_real_epl', 'expected_goals.fit_expected_goals',
            'backtesting.score_1x2', 'result_evaluation.score_1x2', 'poisson.poisson_distribution')
        with ExitStack() as stack:
            for name in forbidden: stack.enter_context(patch('premfootballbot.'+name, side_effect=AssertionError(name)))
            for name in ('socket.socket', 'urllib.request.urlopen', 'builtins.open', 'time.time'):
                stack.enter_context(patch(name, side_effect=AssertionError(name)))
            stack.enter_context(patch.object(Path, 'read_bytes', side_effect=AssertionError('disk')))
            stack.enter_context(patch.object(Path, 'write_bytes', side_effect=AssertionError('disk')))
            self.assertEqual(self.build(), self.artifact)
            self.assertTrue(self.verify(self.artifact))

    def test_core_imports_and_result_access_are_bounded(self):
        tree = ast.parse(Path(cs.__file__).read_text(encoding='utf8'))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = {a.name for a in node.names} if isinstance(node, ast.Import) else {node.module or ''}
                self.assertFalse(names & {'socket', 'urllib', 'os', 'sys', 'time', 'random', 'pathlib'})
            if isinstance(node, ast.Attribute):
                self.assertNotIn(node.attr, ('today', 'now', 'utcnow', '_fit_rows', '_fit', '_scores', '_bootstrap'))
        readers = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)
                   and any(isinstance(n, ast.Attribute) and n.attr in ('home_goals_ft90', 'away_goals_ft90') for n in ast.walk(node))}
        self.assertEqual(readers, {'_training_summary'})

    def test_synthetic_and_prospective_gates_reject_artifact(self):
        raw = cs.cold_start_json(self.artifact)
        self.assertFalse(parse_synthetic_json(raw).valid)
        with self.assertRaises(EvidenceError): freeze_packet(raw)


if __name__ == '__main__':
    unittest.main()

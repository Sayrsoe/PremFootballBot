"""Invented numerical oracles only. No EPL fixture ingestion/fitting/scoring."""
import ast
from contextlib import ExitStack
from dataclasses import FrozenInstanceError, replace
from datetime import date, timedelta
from fractions import Fraction
import json
import math
from pathlib import Path
import random
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from premfootballbot import weighted_poisson as wp
from premfootballbot import real_epl_training as old
from premfootballbot.match_data import parse_synthetic_json
from premfootballbot.prospective_evidence import freeze_packet, EvidenceError


def invented_rows(home=2, away=1):
    teams = ('toy:A', 'toy:B', 'toy:C')
    return tuple(wp.InventedMatch(f'toy:m{i}', h, a, home, away, 30*i)
                 for i, (h, a) in enumerate((h, a) for h in teams for a in teams if h != a))


def varied_rows():
    return tuple(replace(r, home_goals=(i*i+1)%5, away_goals=(i+2)%4)
                 for i, r in enumerate(invented_rows()))


def old_invented_adapter(rows):
    # Dedicated invented values, not a real archive or a bypass of its public gate.
    return tuple(SimpleNamespace(fixture_id=r.fixture_id, match_date=date(2000, 1, 1)-timedelta(days=r.age_days),
        home_team_raw=r.home, away_team_raw=r.away, home_goals_ft90=r.home_goals, away_goals_ft90=r.away_goals) for r in rows)


def synthetic_recovery_case():
    rng = random.Random(440201)
    teams = ('toy:A', 'toy:B', 'toy:C')
    attack, vulnerability = (-0.3, 0.0, 0.3), (0.2, 0.0, -0.2)
    mu, advantage = 0.1, 0.25
    def poisson(rate):
        bound, product, k = math.exp(-rate), 1.0, 0
        while product > bound:
            product *= rng.random()
            k += 1
        return k-1
    result = []
    for i in range(3):
        for j in range(3):
            if i == j: continue
            for k in range(400):
                result.append(wp.InventedMatch(f'toy:r{len(result)}', teams[i], teams[j],
                    poisson(math.exp(mu+advantage+attack[i]+vulnerability[j])),
                    poisson(math.exp(mu+attack[j]+vulnerability[i])), k%360))
    return tuple(result), (mu, advantage, *attack, *vulnerability)


class WeightTests(unittest.TestCase):
    def test_half_life_formula_exact_checkpoints(self):
        self.assertEqual(wp.decay_weights((0, 90, 180, 270), 90), (1.0, 0.5, 0.25, 0.125))
        for half in (90, 180, 365):
            self.assertEqual(wp.decay_weights((half, 2*half), half), (0.5, 0.25))
        self.assertEqual(wp.HALF_LIFE_CANDIDATES, (None, 90, 180, 365))

    def test_no_decay_and_monotonic_composition(self):
        self.assertEqual(wp.decay_weights((0, 1, 1000000), None), (1., 1., 1.))
        a, b, combined = wp.decay_weights((2, 70, 72), 180)
        self.assertAlmostEqual(combined, a*b, places=15)
        self.assertGreater(a, b)
        self.assertLess(wp.decay_weights((20,), 90)[0], wp.decay_weights((20,), 365)[0])

    def test_invalid_ages_rejected_also_no_decay(self):
        for age in (-1, True, 1.0, math.nan, math.inf, '1', 1000001):
            for half in (None, 90):
                with self.subTest(age=age,half=half), self.assertRaises(wp.WeightedPoissonError): wp.decay_weights((age,), half)
        for ages in ((), [0], (0,)*(wp.MAX_MATCHES+1)):
            with self.assertRaises(wp.WeightedPoissonError): wp.decay_weights(ages, 90)

    def test_invalid_half_life_including_infinity_rejected(self):
        for half in (True, 0, -1, math.inf, math.nan, '90', 1e10):
            with self.assertRaises(wp.WeightedPoissonError): wp.decay_weights((10,), half)
            with self.assertRaises(wp.WeightedPoissonError): wp.WeightedConfig(half_life_days=half)

    def test_decay_underflow_not_silently_dropped_or_clipped(self):
        for half in (0.001, 5e-324):
            with self.assertRaises(wp.WeightedPoissonError): wp.decay_weights((1000000,), half)

    def test_invalid_explicit_weights_rejected(self):
        for w in (True, 0, -0.5, 1.01, math.nan, math.inf, '1', None):
            with self.assertRaises(wp.WeightedPoissonError): wp.weight_summary((w,))
        for weights in ((), [1], (1,)*(wp.MAX_MATCHES+1)):
            with self.assertRaises(wp.WeightedPoissonError): wp.weight_summary(weights)

    def test_ess_hand_oracle_uniform_and_scale_invariance(self):
        s = wp.weight_summary((1., 0.5, 0.25))
        self.assertEqual(s.sum_weights, 1.75)
        self.assertAlmostEqual(s.effective_sample_size, float(Fraction(49, 21)), places=14)
        self.assertEqual(wp.weight_summary((1.,)*6).effective_sample_size, 6)
        self.assertAlmostEqual(wp.weight_summary((0.1, 0.05, 0.025)).effective_sample_size, s.effective_sample_size, places=14)
        self.assertEqual(wp.weight_summary((1e-250,)*3).effective_sample_size, 3)


class ObjectiveTests(unittest.TestCase):
    def setUp(self):
        self.rows = varied_rows()
        self.theta = (0.2, -0.1, 0.15, -0.25, 0.1, -0.1, 0.3, -0.2)
        self.weights = (1., 0.75, 0.5, 0.3, 0.125, 0.01)

    def evaluate(self, theta=None, weights=None, ridge=4.):
        return wp.evaluate_objective(self.rows, self.weights if weights is None else weights,
                                     self.theta if theta is None else theta, ridge=ridge)

    def test_uniform_objective_gradient_hessian_match_protected_kernel(self):
        teams, data = old._design(old_invented_adapter(self.rows))
        e = self.evaluate(weights=(1.,)*len(self.rows))
        gradient, hessian = old._derivatives(self.theta, data, 4.)
        self.assertEqual(teams, ('toy:A', 'toy:B', 'toy:C'))
        self.assertEqual(e.objective, old._objective(self.theta, data, 4.))
        self.assertEqual(e.gradient, tuple(gradient))
        self.assertEqual(e.hessian, tuple(tuple(r) for r in hessian))

    def test_uniform_equivalence_across_parameter_points_and_ridges(self):
        _, observations = old._design(old_invented_adapter(self.rows))
        rng = random.Random(405)
        for ridge in (0.01, 4., 100.):
            for _ in range(4):
                theta = tuple(rng.uniform(-1, 1) for _ in range(8))
                actual = self.evaluate(theta=theta, weights=(1.,)*6, ridge=ridge)
                gradient, hessian = old._derivatives(theta, observations, ridge)
                self.assertEqual(actual.objective, old._objective(theta, observations, ridge))
                self.assertEqual(actual.gradient, tuple(gradient))
                self.assertEqual(actual.hessian, tuple(tuple(row) for row in hessian))

    def test_independent_manual_full_weighted_nll_and_penalty(self):
        nll = 0.0
        teams = ('toy:A', 'toy:B', 'toy:C')
        for row, weight in zip(self.rows, self.weights):
            h, a = teams.index(row.home), teams.index(row.away)
            eta_h = self.theta[0]+self.theta[1]+self.theta[2+h]+self.theta[5+a]
            eta_a = self.theta[0]+self.theta[2+a]+self.theta[5+h]
            nll += weight*(math.exp(eta_h)-row.home_goals*eta_h+math.lgamma(row.home_goals+1)
                          +math.exp(eta_a)-row.away_goals*eta_a+math.lgamma(row.away_goals+1))
        e = self.evaluate()
        self.assertAlmostEqual(e.negative_log_likelihood, nll, places=13)
        self.assertAlmostEqual(e.penalty, 2*sum(t*t for t in self.theta[2:]), places=14)
        self.assertEqual(e.objective, e.negative_log_likelihood+e.penalty)

    def test_finite_difference_gradient_and_hessian_nonuniform_weights(self):
        for ridge in (0.01, 4., 30.):
            with self.subTest(ridge=ridge):
                e = self.evaluate(ridge=ridge)
                for i in range(len(self.theta)):
                    eps = 1e-5
                    plus, minus = list(self.theta), list(self.theta)
                    plus[i] += eps; minus[i] -= eps
                    p, m = self.evaluate(tuple(plus), ridge=ridge), self.evaluate(tuple(minus), ridge=ridge)
                    self.assertAlmostEqual((p.objective-m.objective)/(2*eps), e.gradient[i], delta=2e-8)
                    for j in range(len(self.theta)):
                        self.assertAlmostEqual((p.gradient[j]-m.gradient[j])/(2*eps), e.hessian[j][i], delta=2e-8)

    def test_hessian_from_objective_mixed_differences(self):
        # Independent second difference of the scalar objective, not gradient.
        e = self.evaluate()
        eps = 2e-4
        for i in range(8):
            for j in range(i+1):
                values = []
                for si, sj in ((1,1), (1,-1), (-1,1), (-1,-1)):
                    t = list(self.theta); t[i] += si*eps; t[j] += sj*eps
                    values.append(self.evaluate(tuple(t)).objective)
                actual = (values[0]-values[1]-values[2]+values[3])/(4*eps*eps)
                self.assertAlmostEqual(actual, e.hessian[i][j], delta=3e-7)

    def test_hessian_symmetry_positive_quadratic_forms(self):
        e = self.evaluate()
        for i in range(8):
            for j in range(8): self.assertEqual(e.hessian[i][j], e.hessian[j][i])
        rng = random.Random(88)
        for _ in range(20):
            v = [rng.uniform(-2,2) for _ in range(8)]
            oracle = 4*sum(x*x for x in v[2:])
            for active, goals, weight in wp._prepare(self.rows, self.weights)[2]:
                oracle += weight*math.exp(math.fsum(self.theta[k] for k in active))*sum(v[k] for k in active)**2
            quadratic = sum(v[i]*e.hessian[i][j]*v[j] for i in range(8) for j in range(8))
            self.assertGreater(quadratic, 0)
            self.assertAlmostEqual(quadratic, oracle, places=11)

    def test_weight_scale_scales_likelihood_not_ridge(self):
        a = self.evaluate()
        b = self.evaluate(weights=tuple(w/2 for w in self.weights))
        self.assertEqual(a.penalty, b.penalty)
        self.assertAlmostEqual(b.negative_log_likelihood, a.negative_log_likelihood/2, places=14)
        for i in range(8):
            penalty_gradient = 0 if i<2 else 4*self.theta[i]
            self.assertAlmostEqual(b.gradient[i]-penalty_gradient, (a.gradient[i]-penalty_gradient)/2, places=13)
            for j in range(8):
                penalty_hessian = 4 if i==j and i>=2 else 0
                self.assertAlmostEqual(b.hessian[i][j]-penalty_hessian, (a.hessian[i][j]-penalty_hessian)/2, places=13)

    def test_unpenalized_intercept_home_and_ridge_derivatives(self):
        a, b = self.evaluate(ridge=1.), self.evaluate(ridge=5.)
        self.assertEqual(a.gradient[:2], b.gradient[:2])
        for i in range(8):
            self.assertAlmostEqual(b.gradient[i]-a.gradient[i], 0 if i<2 else 4*self.theta[i], places=13)
            for j in range(8): self.assertAlmostEqual(b.hessian[i][j]-a.hessian[i][j], 4 if i==j and i>=2 else 0, places=13)

    def test_weight_alignment_survives_row_permutation(self):
        self.assertEqual(self.evaluate(), wp.evaluate_objective(tuple(reversed(self.rows)), tuple(reversed(self.weights)), self.theta))

    def test_weight_dimension_and_theta_types_bounds_fail(self):
        with self.assertRaises(wp.WeightedPoissonError): wp.evaluate_objective(self.rows, (1.,), self.theta)
        for theta in (self.theta[:-1], list(self.theta), (True,)+self.theta[1:], (math.nan,)+self.theta[1:],
                      (math.inf,)+self.theta[1:], (100.,)+self.theta[1:]):
            with self.assertRaises(wp.WeightedPoissonError): self.evaluate(theta=theta)
        for ridge in (0, -1, True, math.inf, math.nan, 10001):
            with self.assertRaises(wp.WeightedPoissonError): self.evaluate(ridge=ridge)

    def test_curvature_underflow_fails(self):
        with self.assertRaises(wp.WeightedPoissonError): self.evaluate(theta=(-99.,)*8, weights=(5e-324,)*6)


class FitTests(unittest.TestCase):
    def test_balanced_closed_form_uniform_and_decayed(self):
        # Each age block contains all6 pairs: equal weighted exposures.
        rows = tuple(replace(r, fixture_id=f'toy:b{k}_{i}', age_days=k*90)
                     for k in range(3) for i,r in enumerate(invented_rows()))
        for half in (None, 90, 180, 365):
            model = wp.fit_invented_matches(rows, wp.WeightedConfig(half_life_days=half))
            self.assertAlmostEqual(model.intercept, 0, places=12)
            self.assertAlmostEqual(model.home_advantage, math.log(2), places=12)
            self.assertTrue(all(abs(t.attack)<1e-12 and abs(t.defense_vulnerability)<1e-12 for t in model.teams))
            self.assertLessEqual(model.diagnostics.gradient_inf_norm, model.diagnostics.gradient_threshold)

    def test_uniform_fit_matches_existing_kernel_on_invented_rows_only(self):
        rows = varied_rows()
        mu,h,teams,diag = old._fit_rows(old_invented_adapter(rows), old.RealFitConfig())
        actual = wp.fit_invented_matches(rows)
        expected = (mu,h,*(t.attack for t in teams),*(t.defense_vulnerability for t in teams))
        got = (actual.intercept,actual.home_advantage,*(t.attack for t in actual.teams),*(t.defense_vulnerability for t in actual.teams))
        for a,b in zip(expected,got): self.assertAlmostEqual(a,b,places=12)
        self.assertAlmostEqual(actual.diagnostics.objective_trace[-1],diag.objective,places=12)

    def test_seeded_synthetic_nonzero_parameter_recovery(self):
        rows, expected = synthetic_recovery_case()
        model = wp.fit_invented_matches(rows, wp.WeightedConfig(half_life_days=180))
        got = (model.intercept,model.home_advantage,*(t.attack for t in model.teams),*(t.defense_vulnerability for t in model.teams))
        for a,b in zip(expected,got): self.assertAlmostEqual(a,b,delta=0.15)
        self.assertEqual(len(rows),2400)
        self.assertGreater(model.diagnostics.weights.effective_sample_size,2000)

    def test_convergence_monotonic_objective_and_weighted_score_equations(self):
        model = wp.fit_invented_matches(varied_rows(),wp.WeightedConfig(half_life_days=90))
        d = model.diagnostics
        self.assertGreater(d.iterations,0)
        self.assertTrue(all(b<a for a,b in zip(d.objective_trace,d.objective_trace[1:])))
        self.assertAlmostEqual(d.objective_trace[-1],d.negative_log_likelihood+d.penalty,places=13)
        self.assertLessEqual(d.gradient_inf_norm,d.gradient_threshold)
        self.assertAlmostEqual(d.weighted_fitted_home,d.weighted_observed_home,delta=2e-7)
        self.assertAlmostEqual(d.weighted_fitted_away,d.weighted_observed_away,delta=2e-7)
        self.assertGreater(d.minimum_relative_pivot,1e-12)
        self.assertAlmostEqual(sum(t.attack for t in model.teams),0,delta=2e-7)
        self.assertAlmostEqual(sum(t.defense_vulnerability for t in model.teams),0,delta=2e-7)

    def test_global_and_per_team_exposure_ess(self):
        rows = varied_rows();model = wp.fit_invented_matches(rows,wp.WeightedConfig(half_life_days=90))
        weights = wp.decay_weights(tuple(r.age_days for r in rows),90)
        self.assertEqual(model.diagnostics.weights,wp.weight_summary(weights))
        self.assertAlmostEqual(sum(t.exposure.sum_weights for t in model.teams),2*sum(weights),places=14)
        for t in model.teams:
            self.assertEqual(t.exposure,wp.weight_summary(tuple(w for r,w in zip(rows,weights) if t.team in (r.home,r.away))))

    def test_stronger_ridge_shrinks_effects_on_invented_case(self):
        weak = wp.fit_invented_matches(varied_rows(),wp.WeightedConfig(ridge=0.01))
        strong = wp.fit_invented_matches(varied_rows(),wp.WeightedConfig(ridge=1000))
        magnitude = lambda m:sum(t.attack*t.attack+t.defense_vulnerability*t.defense_vulnerability for t in m.teams)
        self.assertLess(magnitude(strong),magnitude(weak))

    def test_high_contrast_invented_counts_exercise_actual_backtracking(self):
        scores = ((100,0),(0,0),(0,0),(0,0),(0,0),(0,1))
        rows = tuple(replace(r, home_goals=h, away_goals=a, age_days=0)
                     for r,(h,a) in zip(invented_rows(),scores))
        model = wp.fit_invented_matches(rows,wp.WeightedConfig(ridge=0.01))
        self.assertGreater(model.diagnostics.backtracks,0)
        self.assertLessEqual(model.diagnostics.gradient_inf_norm,model.diagnostics.gradient_threshold)

    def test_small_but_conditioned_weight_mass_uses_stricter_gradient_threshold(self):
        rows = tuple(replace(r,age_days=30) for r in varied_rows())
        model = wp.fit_invented_matches(rows,wp.WeightedConfig(half_life_days=1))
        self.assertLess(model.diagnostics.gradient_threshold,1e-12)
        self.assertLessEqual(model.diagnostics.gradient_inf_norm,model.diagnostics.gradient_threshold)

    def test_negative_home_advantage_and_zero_goals_in_some_matches(self):
        model = wp.fit_invented_matches(invented_rows(home=1,away=2))
        self.assertAlmostEqual(model.home_advantage,-math.log(2),places=12)
        self.assertTrue(any(r.home_goals==0 or r.away_goals==0 for r in varied_rows()))
        self.assertIsInstance(wp.fit_invented_matches(varied_rows()),wp.WeightedFit)

    def test_degenerate_empty_all_zero_and_single_zero_venue_rejected(self):
        for rows in ((),invented_rows(0,0),invented_rows(0,1),invented_rows(1,0)):
            with self.assertRaises(wp.WeightedPoissonError): wp.fit_invented_matches(rows)

    def test_config_types_ranges_nonfinite_and_iteration_failure(self):
        for name,values in (('ridge',(True,0,-1,math.nan,math.inf,10001)),
                            ('gradient_tolerance',(True,0,1e-12,0.1,math.inf)),('max_iterations',(True,0,1.5,201))):
            for value in values:
                with self.assertRaises(wp.WeightedPoissonError): wp.WeightedConfig(**{name:value})
        with self.assertRaises(wp.WeightedPoissonError): wp.fit_invented_matches(varied_rows(),{})
        with self.assertRaises(wp.WeightedPoissonError) as caught:
            wp.fit_invented_matches(varied_rows(),wp.WeightedConfig(max_iterations=1))
        self.assertEqual(caught.exception.code,'NOT_CONVERGED')

    def test_invalid_rows_identity_scores_ages_and_no_archive_duck_typing(self):
        row = invented_rows()[0]
        for change in ({'home':row.away},{'home':'arsenal'},{'fixture_id':'x'}, {'record_kind':'REAL'},
                       {'home_goals':True},{'away_goals':math.nan},{'home_goals':101},{'home_goals':-1},{'age_days':-1}):
            with self.assertRaises(wp.WeightedPoissonError): wp.fit_invented_matches((replace(row,**change),))
        for rows in ([row],(SimpleNamespace(**vars(old_invented_adapter((row,))[0])),),(row,row),invented_rows()*(wp.MAX_MATCHES+1)):
            with self.assertRaises(wp.WeightedPoissonError): wp.fit_invented_matches(rows)

    def test_team_count_bound(self):
        rows = tuple(wp.InventedMatch(f'toy:m{i}',f'toy:T{i}',f'toy:T{i+1}',1,1,0) for i in range(21))
        with self.assertRaises(wp.WeightedPoissonError): wp.fit_invented_matches(rows)

    def test_ill_conditioned_tiny_mass_does_not_claim_gradient_convergence(self):
        rows = tuple(replace(r,age_days=600) for r in invented_rows())
        with self.assertRaises(wp.WeightedPoissonError) as caught:
            wp.fit_invented_matches(rows,wp.WeightedConfig(half_life_days=1))
        self.assertEqual(caught.exception.code,'ILL_CONDITIONED')

    def test_failed_newton_or_line_search_never_returns_partial_model(self):
        with patch.object(wp,'_newton_step',return_value=([0.]*8,0.1)):
            with self.assertRaises(wp.WeightedPoissonError) as c: wp.fit_invented_matches(varied_rows())
            self.assertEqual(c.exception.code,'NUMERIC_ERROR')
        original = wp._calculate
        first = original([0.]*8,wp._prepare(varied_rows(),(1.,)*6)[2],4.)
        # Finite derivatives but impossible Armijo decrease throughout50 trials.
        with patch.object(wp,'_calculate',return_value=first):
            with self.assertRaises(wp.WeightedPoissonError) as c: wp.fit_invented_matches(varied_rows())
            self.assertEqual(c.exception.code,'NOT_CONVERGED')

    def test_deterministic_permutation_serialization_and_exact_replay(self):
        rows = varied_rows();config = wp.WeightedConfig(half_life_days=180)
        model = wp.fit_invented_matches(rows,config)
        other = wp.fit_invented_matches(tuple(reversed(rows)),config)
        self.assertEqual(wp.weighted_fit_json(model),wp.weighted_fit_json(other))
        self.assertTrue(wp.verify_weighted_fit(model,rows))
        self.assertEqual(model,wp.fit_invented_matches(rows,wp.WeightedConfig(half_life_days=180.,ridge=4)))

    def test_frozen_artifact_and_tamper_replay(self):
        rows = varied_rows();model = wp.fit_invented_matches(rows)
        with self.assertRaises(FrozenInstanceError): model.intercept = 99
        with self.assertRaises(FrozenInstanceError): model.teams[0].attack = 99
        with self.assertRaises(wp.WeightedPoissonError): wp.weighted_fit_json(replace(model,intercept=model.intercept+0.1))
        for change in ({'intercept':model.intercept+0.1},{'input_sha256':'f'*64},
                       {'config':wp.WeightedConfig(half_life_days=90)}):
            with self.assertRaises(wp.WeightedPoissonError): wp.verify_weighted_fit(wp._seal(replace(model,**change)),rows)
        with self.assertRaises(wp.WeightedPoissonError): wp.verify_weighted_fit(model,(replace(rows[0],home_goals=2),)+rows[1:])

    def test_restrictions_and_untrusted_json(self):
        model = wp.fit_invented_matches(varied_rows())
        self.assertEqual(model.status,wp.STATUS)
        for field in ('real_data_authorized','prediction_api_available','strict_point_in_time_eligible'):
            self.assertIs(getattr(model,field),False)
            with self.assertRaises(wp.WeightedPoissonError): wp.weighted_fit_json(wp._seal(replace(model,**{field:True})))
        for raw in ({},wp.weighted_fit_json(model),json.loads(wp.weighted_fit_json(model))):
            with self.assertRaises(wp.WeightedPoissonError): wp.weighted_fit_json(raw)
        self.assertFalse(parse_synthetic_json(wp.weighted_fit_json(model)).valid)
        with self.assertRaises(EvidenceError): freeze_packet(wp.weighted_fit_json(model))

    def test_no_network_files_clock_real_training_scoring_or_existing_kernel_calls(self):
        rows = varied_rows()
        forbidden = ('real_epl_training._fit_rows','real_epl_training._objective','real_epl_training._derivatives',
            'real_epl_training._solve','real_epl_training.fit_real_epl','chronological_epl.fit_development',
            'chronological_epl.evaluate_holdout','chronological_epl.forecast_holdout','completed_epl.import_completed_epl',
            'retrospective_candidates.build_cold_start_artifact','expected_goals.fit_expected_goals','result_evaluation.score_1x2')
        with ExitStack() as stack:
            for name in forbidden: stack.enter_context(patch('premfootballbot.'+name,side_effect=AssertionError(name)))
            for name in ('socket.socket','urllib.request.urlopen','builtins.open','time.time'):
                stack.enter_context(patch(name,side_effect=AssertionError(name)))
            stack.enter_context(patch.object(Path,'read_bytes',side_effect=AssertionError('file read')))
            stack.enter_context(patch.object(Path,'write_bytes',side_effect=AssertionError('file write')))
            model = wp.fit_invented_matches(rows,wp.WeightedConfig(half_life_days=90))
            self.assertTrue(wp.verify_weighted_fit(model,rows))

    def test_core_has_no_project_import_adapter_rng_or_clock(self):
        tree = ast.parse(Path(wp.__file__).read_text(encoding='utf8'))
        allowed = {'__future__','dataclasses','hashlib','json','math','re'}
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom): self.assertIn(node.module,allowed)
            if isinstance(node,ast.Import): self.assertTrue({n.name for n in node.names} <= allowed)
            if isinstance(node,ast.Attribute): self.assertNotIn(node.attr,('now','today','utcnow','read_bytes','write_bytes'))


if __name__ == '__main__':
    unittest.main()

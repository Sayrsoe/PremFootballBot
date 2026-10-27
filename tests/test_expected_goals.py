"""Independent math, rank, optimizer and safety regressions for Phase2B."""
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from fractions import Fraction
import math
import unittest

from premfootballbot.expected_goals import (
    ModelConfig, ExpectedGoalsError, fit_rate_ratio, prediction_identifiability,
    _design, _rank_basis,
    fit_expected_goals, predict_expected_goals, ErrorCode, _problem, _evaluate,
    _cholesky, _solve, _exp,
)
from tests.expected_goals_cases import batch, payload, parse, team, target, CUTOFF, TOY_A, TOY_B, TOY_C

class CheckpointATests(unittest.TestCase):
    def test_toy_a_hand_worked_factors_and_rates(self):
        model=fit_rate_ratio(batch(),CUTOFF,config=ModelConfig(kappa=2))
        factors={r.team_id:r for r in model.factors}
        expected={"a":(8,2,1.5,.6),"b":(5,4,1.05,.9),"c":(1,8,.45,1.5)}
        for name,(scored,conceded,alpha,beta) in expected.items():
            row=factors[team(name)]
            self.assertEqual((row.scored,row.conceded),(scored,conceded))
            self.assertAlmostEqual(row.exposure_for,14/3,delta=1e-12)
            self.assertAlmostEqual(row.exposure_against,14/3,delta=1e-12)
            self.assertAlmostEqual(row.alpha,alpha,delta=1e-12)
            self.assertAlmostEqual(row.beta,beta,delta=1e-12)
        self.assertAlmostEqual(model.baseline_home*factors[team("a")].alpha*factors[team("c")].beta,3.375,delta=1e-12)
        self.assertAlmostEqual(model.baseline_away*factors[team("c")].alpha*factors[team("a")].beta,.225,delta=1e-12)
        self.assertAlmostEqual(model.baseline_home*factors[team("b")].alpha*factors[team("a")].beta,.945,delta=1e-12)
        self.assertAlmostEqual(model.baseline_away*factors[team("a")].alpha*factors[team("b")].beta,1.125,delta=1e-12)

    def test_toy_b_full_model_rank(self):
        model=fit_rate_ratio(batch(TOY_B),CUTOFF)
        self.assertEqual(model.training.rank.rank,6)
        self.assertTrue(model.training.rank.model_identified)

    def test_toy_c_model_unidentified_both_observed_contrasts_identified(self):
        model=fit_rate_ratio(batch(TOY_C),CUTOFF)
        self.assertEqual(model.training.rank.rank,3)
        self.assertFalse(model.training.rank.model_identified)
        for h,a in (("a","b"),("b","a")):
            result=prediction_identifiability(model,team(h),team(a))
            self.assertTrue(result.home_identified)
            self.assertTrue(result.away_identified)

    def test_corrected_matching_rank_and_each_reverse_rate(self):
        model=fit_rate_ratio(batch([("a","b",2,1),("c","d",1,1)]),CUTOFF)
        rank=model.training.rank
        self.assertEqual(rank.rank,4)
        for h,a,same in (("a","b",True),("b","a",False)):
            result=prediction_identifiability(model,team(h),team(a))
            self.assertEqual((result.home_identified,result.away_identified),(same,same))
            for vector in _design(model.training.teams,team(h),team(a)):
                self.assertEqual(len(_rank_basis([*rank.basis,vector])),4 if same else 5)
        cross=prediction_identifiability(model,team("a"),team("c"))
        self.assertTrue(cross.cross_component)
        self.assertFalse(cross.home_identified or cross.away_identified)

    def test_rank_basis_is_exact_rational(self):
        basis=_rank_basis([(1,2,3),(2,4,6),(1,0,1)])
        self.assertEqual(len(basis),2)
        self.assertTrue(all(isinstance(v,Fraction) for r in basis for v in r))

    def test_unused_registered_team_is_not_parameter(self):
        raw=payload()
        raw["teams"].append(dict(team_id=team("unused"),aliases=["Invented UNUSED"]))
        model=fit_rate_ratio(parse(raw),CUTOFF)
        self.assertEqual(model.training.teams,tuple(team(t) for t in "abc"))
        self.assertEqual(len(model.factors),3)

    def test_config_rejects_invalid_types_and_values(self):
        for field in ("tau","kappa","gradient_tolerance","decrement_tolerance"):
            for value in (0,-1,True,"4",math.nan,math.inf):
                with self.subTest(field=field,value=value),self.assertRaises(ExpectedGoalsError) as caught:
                    ModelConfig(**{field:value})
                self.assertEqual(caught.exception.code,"BAD_CONFIG")
        for field in ("g_max","n_min","max_iterations","max_teams"):
            for value in (0,True,1.5):
                with self.assertRaises(ExpectedGoalsError):
                    ModelConfig(**{field:value})

    def test_empty_zero_sides_and_excess_goals(self):
        for games,code in (([],"EMPTY_TRAINING"),([("a","b",0,1)],"DEGENERATE_ZERO_GOALS"),
                           ([("a","b",1,0)],"DEGENERATE_ZERO_GOALS"),
                           ([("a","b",0,0)],"DEGENERATE_ZERO_GOALS"),
                           ([("a","b",25,1)],"GOALS_OUT_OF_RANGE")):
            with self.assertRaises(ExpectedGoalsError) as caught:
                fit_rate_ratio(batch(games),CUTOFF)
            self.assertEqual(caught.exception.code,code)

    def test_frozen_config_and_comparison(self):
        config=ModelConfig()
        with self.assertRaises(FrozenInstanceError):
            config.tau=1
        model=fit_rate_ratio(batch(),CUTOFF)
        with self.assertRaises(FrozenInstanceError):
            model.baseline_home=2


class OptimizerTests(unittest.TestCase):
    def test_independent_decimal_ridge_reference(self):
        # 60-digit Decimal exp/ln + pivoted Gaussian elimination, separately
        # implemented in delivery/verify_decimal_reference.py (no g/H reuse).
        references=[(TOY_A,(-.27525654440600044,.587786664902119,
            .3247540196765101,.05807281915994435,-.38282683883645445,
            .2332339309168146,.04729186649401918,-.2805257974108338)),
            (TOY_C,(-.00618837530421019,.4054651081081644,
             .05568281225865333,-.05568281225865333,.05568281225865333,-.05568281225865333))]
        for games,values in references:
            model=fit_expected_goals(batch(games),CUTOFF)
            for actual,expected in zip(model.theta,values):
                self.assertAlmostEqual(actual,expected,delta=1e-9)

    def test_participating_team_limit_and_config_type(self):
        games=[("a","club"+str(i),1,1) for i in range(40)]
        with self.assertRaises(ExpectedGoalsError) as caught:
            fit_expected_goals(batch(games),CUTOFF)
        self.assertEqual(caught.exception.code,"BAD_CONFIG")
        with self.assertRaises(ExpectedGoalsError):
            fit_expected_goals(batch(),CUTOFF,config=None)

    def test_toy_b_small_tau_limit(self):
        from premfootballbot.expected_goals import fit_expected_goals, predict_expected_goals
        model=fit_expected_goals(batch(TOY_B),CUTOFF,config=ModelConfig(tau=1e-6))
        L=math.log(2)
        expected=(0,L,L/3,L/3,-2*L/3,L/3,-2*L/3,L/3)
        for actual,reference in zip(model.theta,expected):
            self.assertAlmostEqual(actual,reference,delta=1e-4)
        result=predict_expected_goals(model,**target())
        self.assertAlmostEqual(result.lambda_home,2,delta=1e-4)
        self.assertAlmostEqual(result.lambda_away,.5,delta=1e-4)

    def test_toy_c_ridge_fit_preserves_identification_distinction(self):
        model=fit_expected_goals(batch(TOY_C),CUTOFF)
        for home,away in (("a","b"),("b","a")):
            result=predict_expected_goals(model,**target(home,away))
            self.assertFalse(result.model_identified)
            self.assertTrue(result.contrasts.home_identified and result.contrasts.away_identified)
            self.assertFalse(result.prior_driven)

    def test_totals_gauges_and_both_convergence_criteria(self):
        for tau in (.25,1,4):
            model=fit_expected_goals(batch(),CUTOFF,config=ModelConfig(tau=tau))
            d=model.diagnostics
            self.assertAlmostEqual(d.fitted_home_total,9,delta=1e-8)
            self.assertAlmostEqual(d.fitted_away_total,5,delta=1e-8)
            self.assertAlmostEqual(d.attack_sum,0,delta=1e-8)
            self.assertAlmostEqual(d.defense_sum,0,delta=1e-8)
            self.assertLessEqual(d.gradient_inf,14e-8)
            self.assertLessEqual(d.newton_decrement_squared/2,14e-12)
            self.assertGreater(d.minimum_cholesky_pivot,0)
            self.assertTrue(all(math.isfinite(v) for v in model.theta))
            self.assertEqual(d.objective,d.objective_history[-1])

    def test_objective_contains_factorial_constants_and_exact_penalty(self):
        training=fit_rate_ratio(batch(),CUTOFF).training
        designs,goals=_problem(training)
        theta=(0.0,)*8
        result=_evaluate(theta,designs,goals,4)
        expected=12+sum(math.log(math.factorial(y)) for y in goals)
        self.assertAlmostEqual(result.nll,expected,delta=1e-13)
        values=(.2,-.4,.1,-.1,.2,.3,-.4,.5)
        result=_evaluate(values,designs,goals,4)
        self.assertAlmostEqual(result.objective-result.nll,2*sum(v*v for v in values[2:]),delta=2e-14)

    def test_independent_finite_difference_gradient_and_hessian(self):
        training=fit_rate_ratio(batch(),CUTOFF).training
        X,y=_problem(training)
        points=[(0.,)*8,(.2,-.4,.1,-.1,.2,.3,-.4,.5),(-1.,.8,-.2,.3,.1,-.3,.2,.1)]
        eps=1e-6
        for theta in points:
            value=_evaluate(theta,X,y,4)
            for i in range(8):
                plus=list(theta);plus[i]+=eps
                minus=list(theta);minus[i]-=eps
                vp,vm=_evaluate(plus,X,y,4),_evaluate(minus,X,y,4)
                derivative=(vp.objective-vm.objective)/(2*eps)
                self.assertAlmostEqual(derivative,value.gradient[i],delta=1e-6*max(1,abs(derivative)))
                for j in range(8):
                    second=(vp.gradient[j]-vm.gradient[j])/(2*eps)
                    self.assertAlmostEqual(second,value.hessian[j][i],delta=1e-6*max(1,abs(second)))

    def test_home_away_mirror_allows_negative_advantage(self):
        original=fit_expected_goals(batch(),CUTOFF)
        mirrored=fit_expected_goals(batch([(a,h,y,x) for h,a,x,y in TOY_A]),CUTOFF)
        self.assertLess(mirrored.home_advantage,0)
        self.assertAlmostEqual(mirrored.mu,original.mu+original.home_advantage,delta=1e-9)
        self.assertAlmostEqual(mirrored.home_advantage,-original.home_advantage,delta=1e-9)
        for p,q in zip(original.parameters,mirrored.parameters):
            self.assertAlmostEqual(p.attack,q.attack,delta=1e-9)
            self.assertAlmostEqual(p.defense,q.defense,delta=1e-9)

    def test_replicating_matches_equivalent_to_half_ridge(self):
        doubled=fit_expected_goals(batch(TOY_A*2),CUTOFF,config=ModelConfig(tau=4))
        half=fit_expected_goals(batch(),CUTOFF,config=ModelConfig(tau=2))
        for p,q in zip(doubled.theta,half.theta):
            self.assertAlmostEqual(p,q,delta=1e-9)

    def test_same_platform_permutations_bitwise_reproducible(self):
        import random
        raw=payload()
        expected=fit_expected_goals(parse(raw),CUTOFF)
        for seed in range(10):
            random.Random(seed).shuffle(raw["records"])
            raw["teams"].reverse()
            model=fit_expected_goals(parse(raw),CUTOFF)
            self.assertEqual(model,expected)

    def test_team_label_bijection(self):
        renamed={"a":"z","b":"x","c":"y"}
        original=fit_expected_goals(batch(),CUTOFF)
        other=fit_expected_goals(batch([(renamed[h],renamed[a],x,y) for h,a,x,y in TOY_A]),CUTOFF)
        mapped={p.team_id:p for p in other.parameters}
        for p in original.parameters:
            q=mapped[team(renamed[p.team_id.rsplit(":",1)[1]])]
            self.assertAlmostEqual(p.attack,q.attack,delta=1e-12)
            self.assertAlmostEqual(p.defense,q.defense,delta=1e-12)

    def test_never_scoring_team_has_finite_shrunk_attack(self):
        model=fit_expected_goals(batch([("a","b",0,1),("b","a",2,0)]),CUTOFF)
        self.assertLess(next(p.attack for p in model.parameters if p.team_id==team("a")),0)
        self.assertTrue(all(math.isfinite(v) for v in model.theta))

    def test_armijo_backtracking_and_monotone_objectives(self):
        games=[("a","b",0,1)]*20+[("c","d",20,1)]
        model=fit_expected_goals(batch(games),CUTOFF,config=ModelConfig(tau=.25))
        self.assertGreater(model.diagnostics.backtracks,0)
        trace=model.diagnostics.objective_history
        self.assertTrue(all(b<=a for a,b in zip(trace,trace[1:])))

    def test_iteration_limit_is_typed_failure(self):
        with self.assertRaises(ExpectedGoalsError) as caught:
            fit_expected_goals(batch(),CUTOFF,config=ModelConfig(max_iterations=1))
        self.assertEqual(caught.exception.code,"NOT_CONVERGED")

    def test_cholesky_known_solution_and_bad_pivots(self):
        lower,minimum,maximum=_cholesky(((4.,2.),(2.,3.)))
        answer=_solve(lower,(6.,5.))
        for actual in answer:
            self.assertAlmostEqual(actual,1,delta=1e-14)
        self.assertEqual((minimum,maximum),(2,4))
        for matrix in (((0.,0.),(0.,0.)),((1.,2.),(2.,1.)),((math.nan,),)):
            with self.assertRaises(ExpectedGoalsError) as caught:
                _cholesky(matrix)
            self.assertEqual(caught.exception.code,"HESSIAN_NOT_PD")

    def test_fitter_does_not_return_partial_after_factorization_failure(self):
        from unittest.mock import patch
        with patch("premfootballbot.expected_goals._cholesky",
                   side_effect=ExpectedGoalsError(ErrorCode.HESSIAN_NOT_PD,"injected failure")):
            with self.assertRaises(ExpectedGoalsError) as caught:
                fit_expected_goals(batch(),CUTOFF)
        self.assertEqual(caught.exception.code,"HESSIAN_NOT_PD")

    def test_fit_stage_exp_guards(self):
        for eta in (-1000,1000,math.nan,math.inf):
            with self.assertRaises(ExpectedGoalsError) as caught:
                _exp(eta)
            self.assertEqual(caught.exception.code,"RATE_OUT_OF_RANGE")
        training=fit_rate_ratio(batch(),CUTOFF).training
        X,y=_problem(training)
        for bad in (-1000.,1000.,math.nan):
            with self.assertRaises(ExpectedGoalsError):
                _evaluate((bad,0.,0.,0.,0.,0.,0.,0.),X,y,4)

    def test_curvature_is_not_uniformly_strong_in_mu(self):
        X,y=_problem(fit_rate_ratio(batch(),CUTOFF).training)
        first=_evaluate((0.,)*8,X,y,4).hessian[0][0]
        second=_evaluate((-30.,0.,0.,0.,0.,0.,0.,0.),X,y,4).hessian[0][0]
        self.assertLess(second,first*1e-12)

    def test_fitted_models_and_diagnostics_immutable(self):
        model=fit_expected_goals(batch(),CUTOFF)
        for obj,field in ((model,"mu"),(model.parameters[0],"attack"),(model.diagnostics,"iterations")):
            with self.assertRaises(FrozenInstanceError):
                setattr(obj,field,0)

class ForecastTests(unittest.TestCase):
    def test_arithmetic_overflow_and_opposed_infinities_are_typed(self):
        model=fit_expected_goals(batch(),CUTOFF)
        for mu,h in ((1e308,1e308),(math.inf,-math.inf)):
            with self.assertRaises(ExpectedGoalsError) as caught:
                predict_expected_goals(replace(model,mu=mu,home_advantage=h),**target())
            self.assertEqual(caught.exception.code,"RATE_OUT_OF_RANGE")

    def test_toy_a_rate_ratio_public_forecasts(self):
        model=fit_rate_ratio(batch(),CUTOFF,config=ModelConfig(kappa=2))
        for h,a,x,y in (("a","c",3.375,.225),("b","a",.945,1.125)):
            result=predict_expected_goals(model,**target(h,a))
            self.assertAlmostEqual(result.lambda_home,x,delta=1e-12)
            self.assertAlmostEqual(result.lambda_away,y,delta=1e-12)
            self.assertIn("APPROXIMATE_RATE_RATIO",result.warnings)

    def test_unknown_and_cross_component_default_refusals(self):
        model=fit_expected_goals(batch([("a","b",2,1),("c","d",1,1)]),CUTOFF)
        for h,a,code in (("a","new","NO_HISTORY"),("a","c","CROSS_COMPONENT"),
                          ("b","a","PREDICTION_NOT_IDENTIFIED")):
            with self.assertRaises(ExpectedGoalsError) as caught:
                predict_expected_goals(model,**target(h,a))
            self.assertEqual(caught.exception.code,code)

    def test_explicit_prior_forecasts_label_both_unidentified_rates(self):
        model=fit_expected_goals(batch([("a","b",2,1),("c","d",1,1)]),CUTOFF)
        for h,a in (("a","new"),("a","c"),("b","a")):
            result=predict_expected_goals(model,**target(h,a),allow_unidentified=True)
            self.assertTrue(result.prior_driven)
            self.assertFalse(result.contrasts.home_identified or result.contrasts.away_identified)
            self.assertEqual(result.method,"ridge_prior")

    def test_explicit_league_and_comparison_fallback(self):
        data=batch()
        model=fit_expected_goals(data,CUTOFF)
        ratio=fit_rate_ratio(data,CUTOFF,config=ModelConfig(kappa=2))
        league=predict_expected_goals(model,**target("a","new"),fallback="league")
        self.assertAlmostEqual(league.lambda_home,1.5)
        self.assertAlmostEqual(league.lambda_away,5/6)
        result=predict_expected_goals(model,**target("a","new"),fallback=ratio)
        self.assertEqual(result.method,"rate_ratio_fallback")
        self.assertTrue(result.prior_driven)
        self.assertAlmostEqual(result.lambda_home,2.25)
        self.assertAlmostEqual(result.lambda_away,.5)

    def test_fallback_from_different_history_rejected(self):
        model=fit_expected_goals(batch(),CUTOFF)
        other=fit_rate_ratio(batch(TOY_B),CUTOFF)
        with self.assertRaises(ExpectedGoalsError):
            predict_expected_goals(model,**target("a","new"),fallback=other)

    def test_rate_bounds_no_clamping_or_fallback_on_numeric_error(self):
        model=fit_expected_goals(batch(),CUTOFF)
        for value in (-1000,1000,math.inf,math.nan):
            with self.assertRaises(ExpectedGoalsError) as caught:
                predict_expected_goals(replace(model,mu=value),**target(),fallback="league")
            self.assertEqual(caught.exception.code,"RATE_OUT_OF_RANGE")
        with self.assertRaises(ExpectedGoalsError):
            _exp(math.log(100)+.01,prediction=True)
        self.assertGreater(_exp(-700,prediction=True),0)

    def test_plausibility_warning_and_unverified_metadata(self):
        model=fit_expected_goals(batch(),CUTOFF)
        high=replace(model,mu=math.log(9),home_advantage=0.,
                     parameters=tuple(replace(p,attack=0.,defense=0.) for p in model.parameters))
        result=predict_expected_goals(high,**target())
        self.assertIn("RATE_PLAUSIBILITY:home",result.warnings)
        self.assertIn("RATE_PLAUSIBILITY:away",result.warnings)
        self.assertIn("TARGET_METADATA_UNVERIFIED",result.warnings)

    def test_poisson_integration_retains_raw_mass(self):
        result=predict_expected_goals(fit_expected_goals(batch(),CUTOFF),**target())
        distribution=result.probabilities()
        self.assertGreater(result.lambda_home,0)
        self.assertLessEqual(result.lambda_home,100)
        self.assertLessEqual(distribution.mass.omitted_mass_bound,1e-10)
        x=distribution.one_x_two()
        self.assertAlmostEqual(x.home_win+x.draw+x.away_win,distribution.mass.retained_mass,delta=5e-12)
        self.assertIn("TARGET_METADATA_UNVERIFIED",result.warnings)

    def test_invalid_forecast_args(self):
        model=fit_expected_goals(batch(),CUTOFF)
        for update in (dict(home_team_id=team("c")),dict(home_team_id="real:team:a"),
                       dict(target_fixture_id="bad"),dict(allow_unidentified=1),dict(fallback="silent")):
            args=target();args.update(update)
            with self.assertRaises(ExpectedGoalsError):
                predict_expected_goals(model,**args)

if __name__=="__main__":
    unittest.main()

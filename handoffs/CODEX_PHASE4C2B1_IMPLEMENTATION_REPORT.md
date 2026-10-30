# Phase 4C2-B1 — isolated weighted Poisson numerical engine

## Scope and verified baseline

The owner authorized numerical implementation, invented/synthetic tests, complete
regressions, review and one draft PR with a GitHub-hosted final review ZIP. No new
prompt ZIP was needed. Fetched existing code/decisions/handoffs from GitHub main:
e055e4df76aad0d982e6524ff147fecf4b5e4024, tree
eeb52ee26a8e7c0bf3231fef0fba1051ee25e5e9. This exactly matched the requested base;
checkout was clean, zero open PRs. Branch: codex/phase4c2b1-weighted-poisson.

Read AGENTS, relevant README sections, numerical/chronological/protocol/cold-start
modules and tests, prior numerical/4B/4C1/4C2-A handoffs and restrictions. The old
objective penalizes team attacks and defensive vulnerabilities, not intercept or
home advantage. Preserve it, all existing training functions, authorization pins,
raw fixtures, source rights and synthetic/prospective/frozen evidence byte-for-byte.

New files: premfootballbot/weighted_poisson.py and tests/test_weighted_poisson.py;
README addition; this permanent report; final package only at
handoffs/reviews/PremFootballBot_Phase4C2B1_Final_Review.zip. No dependency added.
No actual EPL data was used by the new module/tests, no new real model fitted or
scored, no exposed holdout selection, B2 adapter, forecasts, paid services, live
APIs, credentials, deployment or merge. Required old regression tests retain
their previously authorized fixture fits/scoring; these are not new B1 studies.

## Research completed before coding

- [goalmodel at 84ecd6c2bbad3ccb967abf88ef49e5bcd074e545](https://github.com/opisthokonta/goalmodel/tree/84ecd6c2bbad3ccb967abf88ef49e5bcd074e545):
  DESCRIPTION v0.6.4 GPL-3, R/goalmodel_fit.R, R/goalmodel_misc.R,
  man/weights_dc.Rd, tests/testthat/test_1.R. Inspected weighted likelihood and
  exponential age weights. xi=ln(2)/half-life gives the requested equivalent
  formula. Rejected data-derived currentDate=max(dates), future dates silently
  zero-weighted, GPL source copying and R/dependency stack. R/weights.R was absent;
  resolved actual implementation via GitHub tree. Mathematical ideas only.
- [penaltyblog at 6870f0e762e9cba35fa722dc14a8daeaf8bc6134](https://github.com/martineastwood/penaltyblog/tree/6870f0e762e9cba35fa722dc14a8daeaf8bc6134):
  LICENCE MIT, penaltyblog/models/poisson.py, models/loss.pyx,
  models/gradients.pyx, test/test_poisson_weighted_gradient.py. Useful per-match
  weighting of both goal terms and uniform-weight invariance tests. Independently
  derived Hessian and stronger finite-difference tests. Rejected attack constraints,
  numeric defaults, external real-match test fixtures, Cython/OpenMP/NumPy/SciPy
  dependencies and prediction/grid interfaces. No third-party code copied/run.
- [skforecast at 3ecc0dc3d251c313b08ce26a572d17a2ace022c4](https://github.com/skforecast/skforecast/tree/3ecc0dc3d251c313b08ce26a572d17a2ace022c4):
  LICENSE BSD-3-Clause, skforecast/model_selection/_split.py and
  model_selection/tests/tests_split/test_timeseriesfold.py. Useful explicit
  type/gap/offset validation. Rejected row-count gaps, inferred cutoffs, refits,
  candidate search, pandas/NumPy and any real fold integration in B1.

All heads checked against GitHub before implementation. No external executable
code installed or run, no incompatible source copied. Code licenses do not grant
football-data rights. This task acquired no match data and changes no source gate.

## API and data boundary

Isolated module imports only stdlib dataclasses/hashlib/json/math/re. Public API:

    InventedMatch(fixture_id, home, away, home_goals, away_goals, age_days)
    WeightedConfig(half_life_days=None, ridge=4, max_iterations=100, gradient_tolerance=1e-7)
    decay_weights(ages_tuple, half_life_days) -> tuple[float, ...]
    weight_summary(weights_tuple) -> WeightSummary
    evaluate_objective(matches, weights, theta, *, ridge=4) -> ObjectiveEvaluation
    fit_invented_matches(matches, config=WeightedConfig()) -> WeightedFit
    weighted_fit_json(model) -> canonical bytes
    verify_weighted_fit(model, matches) -> True

Only exact InventedMatch tuples are accepted; no archive or synthetic pipeline
object is converted. IDs use a bounded toy: namespace, distinct teams, unique
fixtures; ages are explicit integer days0..1000000. No date/cutoff inference,
hidden clock, file loading, JSON loader, network, RNG or project training call.
The invented marker prevents accidental type confusion; it cannot authenticate
the truth/rights of arbitrary caller-supplied numbers. Deliberately relabeling
real matches is outside scope and is not authorized by this numerical API.

Matches1..10000, observed teams2..20, ordinary integer goals0..100. Numeric bools,
NaN/infinity, malformed types/containers/IDs, missing values and negative ages fail.
No-decay uses half_life_days=None, still checking every age. Other half-lives must
be finite positive <=1e9 days; None/90/180/365 are declared design candidates only.
No candidate is empirically selected. Decay/explicit weights must be finite in
(0,1]; underflow to zero fails, never clips/drops. Weight arrays align with input
matches and are sorted together by (-age, fixture_id); team blocks sort by ID.

## Objective, derivatives and equivalence

Parameter order: theta=(mu,h,attacks_sorted,defensive_vulnerabilities_sorted).
Positive vulnerability means weaker defense, matching the existing engine:

    eta_home = mu + h + attack_home + vulnerability_away
    eta_away = mu + attack_away + vulnerability_home
    w_i = 2 ** (-age_days_i / half_life_days), or 1 for no decay
    lambda = exp(eta)
    L = sum_i w_i * [lambda_home - y_home*eta_home + lgamma(y_home+1)
                    +lambda_away - y_away*eta_away + lgamma(y_away+1)]
        + ridge/2 * sum_j(team_parameter_j**2)

Weights are RAW, not normalized to mean/sum1; ridge is NOT weight-scaled.
Therefore uniformly reducing weights increases effective shrinkage. This is
explicit policy, not an invariant or a data-tuned choice. Both factorial terms
are included and weighted. The intercept/home coefficients are unpenalized.

For one goal observation with sparse design vector x and the match weight w:

    gradient += w * (lambda-y) * x
    Hessian += w * lambda * outer(x,x)
    gradient_team += ridge * theta_team
    Hessian_team_diagonal += ridge

With all w=1 these are exactly the existing unweighted objective/derivatives,
including constants and penalty. Tests compare exact float equality at13 invented
parameter/ridge points and fit agreement to12 decimal places on invented rows.
No existing numerical objective/solver is called by the new core.

The Hessian is positive definite in exact arithmetic: v'Hv is a sum of nonnegative
w*lambda*(x'v)^2 plus ridge*||v_team||^2. A zero sum forces team components zero;
any away observation then forces v_mu=0 and its home observation forces v_h=0.
Positive ridge/weights/rates thus give strict convexity, even with disconnected
team populations. Positive weighted home AND away goal totals exclude the
unpenalized zero-venue boundary; otherwise fail DEGENERATE_DATA. This is a
mathematical property, not a guarantee of convergence within a finite budget.

## Solver, stability and diagnostics

Deterministic Newton with independent textbook Cholesky and triangular solves,
Armijo coefficient1e-4, starting scale1 and up to50 halvings. Initialization uses
weighted venue means via differences of logs (no unstable intermediate ratio),
zero team effects. No clipping, jitter, hidden smoothing or approximate fallback.
Parameters must remain finite with absolute value<100. The sparse design has at
most4 active parameters, keeping exponent arguments bounded below overflow.
Nonpositive/nonfinite weighted curvature, nonfinite derivatives/direction,
non-descent, line-search or iteration exhaustion fail atomically with coded errors.

Positive ridge0.01..10000; max iterations1..200; gradient tolerance1e-10..1e-5.
Defaults match old engineering settings, not tuned on football data. At EVERY
iteration, including a putative converged solution, a Cholesky pivot must exceed
1e-12 times the maximum Hessian diagonal. The recorded minimum relative pivot is
a numerical guard/proxy, not a condition-number estimate. Very small weight mass
may fail ILL_CONDITIONED, rather than report success because its gradient shrank.
Stopping threshold=tolerance*min(1,sum_weights); this preserves old absolute
tolerance for mass>=1 and tightens it for small mass. Neither absolute thresholds
nor pivot guard certify accuracy outside the declared domain.

Global/per-team WeightSummary reports match count, raw weight mass, min/max and
Kish ESS=(sum w)^2/sum(w^2). ESS is computed after dividing weights by their maximum
to avoid square underflow; actual likelihood weights are NOT rescaled. ESS counts
matches, not the two goal observations. It describes concentration/exposure, not
independence, sufficient predictive information or inferential power.

Frozen diagnostics record iterations/backtracks, objective trace, full NLL/penalty,
gradient norm/threshold, minimum pivot, global weights, weighted observed/fitted
home/away totals; team estimates include individual exposure/ESS. WeightedFit
records canonical config, sorted input/weight fingerprint, coefficients, effects,
diagnostics and status INVENTED_NUMERICAL_TEST_ONLY_NOT_MODEL_AUTHORIZED, with
real_data_authorized=False, prediction_api_available=False and false strict
point-in-time eligibility. There is no rate/forecast/scoring API or model approval.

Canonical sorted-key/no-NaN JSON and SHA256 seals support deterministic exact
replay in the SAME Python/math runtime. Seals are consistency checks, not
signatures or model authorization. Serialization checks type/seal/flags only;
consumers must use verify_weighted_fit with original invented inputs to reject
re-sealed changes. No untrusted JSON deserializer exists. Cross-runtime byte
equivalence is not promised; no existing portable authorization pin is changed.

## Executable invented-data example

```python
from premfootballbot.weighted_poisson import (
    InventedMatch, WeightedConfig, fit_invented_matches,
    weighted_fit_json, verify_weighted_fit,
)
teams = ("toy:A", "toy:B", "toy:C")
matches = tuple(InventedMatch(f"toy:m{i}", h, a, 2, 1, 30*i)
                for i, (h,a) in enumerate((h,a) for h in teams for a in teams if h != a))
fit = fit_invented_matches(matches, WeightedConfig(half_life_days=180))
assert verify_weighted_fit(fit, matches)
canonical_bytes = weighted_fit_json(fit)
assert fit.real_data_authorized is False
```

No file writes inside the core. Caller handles persistence. These outputs cannot
be treated as an authorized real-EPL model or prospective evidence packet.

## Executed tests and numerical evidence

Windows11 CPython3.12.14. Baseline743 passed24.629s; new focused38 passed0.120s;
working full781 passed26.114s (743 unchanged+38 new). Commands:

    python -B -m unittest tests.test_weighted_poisson -v
    python -B -m unittest discover -s tests -v

Initial35 and expanded38 focused tests passed; no failing test run. Full verbose
baseline/working/committed-export logs and runtime details are in the final ZIP.
No Linux/3.13 or other runtime, remote CI, external linter/type checker claimed.
Exact-source Python3.10 grammar parsing is distinct from runtime verification.

Independent central-difference oracle at a nonuniform weighted invented point:
max gradient error1.2182e-10; Hessian from gradient error1.4579e-10 (step1e-5);
scalar-objective mixed-second-difference error6.7681e-8 (step2e-4). Uniform
objective/gradient/Hessian differences exactly0. Additional tests cover several
ridges/parameter points, Hessian symmetry and positive quadratic-form identity,
full constants, raw weight scaling versus unchanged penalty, and venue score
equations. Balanced invented data recover closed-form means; a seeded2400-match
three-team Poisson simulation recovers nonzero parameters with maximum absolute
error0.046253 (assertion bound0.15), ESS2065.19646. Seed440201 is test-only; core
has no RNG. These are numerical checks, not football accuracy or empirical tuning.

Tests also exercise actual backtracking on invented0/100-count contrast, negative
home advantage, zero goals in some matches, no-goal venue/empty failure, tiny but
conditioned weight mass, tiny ill-conditioned mass, decay/curvature underflow,
parameter/config/weight/age/type/identity bounds, iteration/direction/line-search
failure atomicity, deterministic row permutation, replay/re-sealed tampering,
frozen outputs and rejection by unchanged synthetic/prospective validators.
Denial mocks prevent old numerical/source/real-data/fitting/scoring, network,
file and clock calls in the new core. AST test permits only its stdlib imports.

## Review package, protected files and stop gate

Only the four implementation/documentation files above plus the final review ZIP
change from base. All80 protected baseline files (everything except README) must
remain byte-identical. Final package includes complete exact source, baseline,
binary patch, Git/SHA256 manifests, raw commit evidence, logs, mathematical audit,
invented example artifacts, changed-file inventory and portable review verifier.

Packaging uses two commits to avoid self-reference: implementation commit holds
the complete tested source; a delivery-only child adds the single ZIP. The ZIP
pins implementation/base commits and trees, contains every source file except
the ZIP itself, and documents reconstructing the delivery tree by adding its own
Git blob. Final delivery head/tree and ZIP checksum/download URL are reported in
the draft PR/owner response. No other delivery-commit changes are permitted.
Verify raw GitHub download bytes, CRC/member hashes and source/tree/replay before
cleanup. Only the final named ZIP remains in handoffs/reviews; no prompt, approval,
scratch/planning/packaging files are committed. The identified task temporary
workspace is removed after its required evidence is preserved in the final ZIP.

Limits: invented-only numerical verification, bounded dense solver, finite-budget
failures, runtime-specific exact replay, engineering tolerances and unvalidated
weight/ridge choices. No real-data integration, historical embargo enforcement,
half-life winner, uncertainty inference or predictive improvement established.
B2 must separately design authorized source/fold replay, leakage and exposure
controls before any new real-data use. Request independent mathematical/source/
provenance/isolation review and explicit owner approval before any merge. Keep
draft; stop here. No B2, predictions, deployment or merge.

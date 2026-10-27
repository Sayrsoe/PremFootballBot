# Phase 2B synthetic-only implementation report

## Baseline, authority and scope

Executed the owner's explicit Phase2B instruction and v1.3 package.
Read START_HERE.md, PROMPT_FOR_CODEX.md, acceptance, reviewed math and verdict,
PROJECT_CONTROL, DELIVERY_CHECKLIST, AGENTS.md, README, existing source APIs
and relevant tests. Consulted only Toy A/B/C and algorithm portions of the
optional extracted older report; reviewed corrections take priority.

Package SHA256:
1abf44b583f74dec37d5a540f5e6789d0b532c5e7d7d3d4c78045846a37369d6.
All 11 handoff manifest entries verified.
Live main matched b23e15fcd70fb28751df9ac1c1a6f89c7860986a.
Created codex/phase2b-synthetic-xg-estimator from that commit.
Before edits, Python 3.12.14 ran all 248 existing test methods successfully.

Only the expected-goals module, new synthetic fixture/tests/helper, README
and this report are changed. Earlier modules, __init__, AGENTS, tests, fixtures
and dependency/toolchain files remain untouched. Runtime is Python >=3.10
stdlib only; actual tests use 3.12.14, with 3.10 grammar checked at export.
No real match/provider data, network ingestion, API key, odds, tuning,
Phase3, frontend, market comparison or merge.

## Research and pre-code plan

Inspected on 2026-10-27:
- [penaltyblog](https://github.com/martineastwood/penaltyblog/tree/6870f0e762e9cba35fa722dc14a8daeaf8bc6134),
  pinned 6870f0e762e9cba35fa722dc14a8daeaf8bc6134,
  MIT [LICENCE](https://github.com/martineastwood/penaltyblog/blob/6870f0e762e9cba35fa722dc14a8daeaf8bc6134/LICENCE)
  and models/poisson.py. Useful separation of likelihood/gradient/prediction;
  rejected SciPy/NumPy/Cython dependency, constraint/gauge convention,
  nonnegative h bound, default normalization and feed/data ecosystem.
  Tests/test_poisson.py and tests directory were unavailable at this snapshot;
  no reference-test coverage is claimed.
- [mpmath](https://github.com/mpmath/mpmath/tree/8e67af565cd14a4a8728a7a0879347f6778399e4),
  pinned 8e67af565cd14a4a8728a7a0879347f6778399e4,
  BSD-3-Clause [LICENSE](https://github.com/mpmath/mpmath/blob/8e67af565cd14a4a8728a7a0879347f6778399e4/LICENSE).
  Inspected matrices/linalg.py cholesky/cholesky_solve and
  tests/test_linalg.py factorization/residual checks.
  Adopted mathematical factorization/solve/error-check concepts, implemented
  independently using math.fsum. No package dependency or copied code.
  GitHub code search confirmed the relevant implementations.

Code licences do not confer data rights. No external dataset was downloaded.
The pre-code design/checkpoint note is included in external delivery evidence.
Checkpoint A established historical selection/rank/comparison; checkpoint B
added the reviewed joint objective, optimizer and forecasts. No subagents used.

## Public contracts and integration

Direct import from premfootballbot.expected_goals; no root export changes.

ModelConfig defaults:
tau=4, kappa=4, g_max=20, n_min=6, max_iterations=100,
gradient_tolerance=1e-8, decrement_tolerance=1e-12, max_teams=40.
Finite positive real hyperparameters; bool/text rejected. Integer guards:
g_max 1..1000, n_min 1..10000, iterations 1..1000, participating teams 2..40.
Settings are synthetic engineering choices, not data-tuned EPL estimates.

- fit_expected_goals(batch: ImportResult, cutoff_utc: datetime, *,
  config: ModelConfig=ModelConfig()) -> FittedModel.
- fit_rate_ratio(batch, cutoff_utc, *, config=ModelConfig()) -> FittedRateRatio.
- prediction_identifiability(model, home_team_id, away_team_id)
  -> ContrastDiagnostics.
- predict_expected_goals(model, *, target_fixture_id, home_team_id,
  away_team_id, target_kickoff_utc, cutoff_utc, allow_unidentified=False,
  fallback=None) -> ExpectedGoalsForecast.
- ExpectedGoalsForecast.probabilities() -> existing PoissonDistribution.

Frozen configuration, parameters, training metadata, exact rank basis,
optimizer diagnostics, factors and forecast dataclasses contain only immutable
tuples/values. TrainingData retains canonical selected observations, participating
teams, appearances, fitting cutoff, batch/row SHA256, exclusion reason counts,
goal totals, component/rank flags and warnings. FittedModel has mu, h, team
attack/defense and theta view. OptimizerDiagnostics exposes objective, NLL,
gradient, decrement, accepted objective trace, backtracks, iterations, positive
Cholesky pivot range and post-fit totals/gauges. Forecast carries both rates,
per-rate contrast flags, full-model flag, method, prior_driven, target metadata,
hashes, cutoff and warnings. Local Laplace uncertainty diagnostics are omitted;
no calibrated uncertainty is inferred from curvature.

ExpectedGoalsError carries ErrorCode, including EMPTY_TRAINING,
DEGENERATE_ZERO_GOALS, BAD_CONFIG, GOALS_OUT_OF_RANGE, NOT_CONVERGED,
HESSIAN_NOT_PD, RATE_OUT_OF_RANGE, CUTOFF_AFTER_KICKOFF, CUTOFF_MISMATCH,
NO_HISTORY, CROSS_COMPONENT, PREDICTION_NOT_IDENTIFIED, TARGET_IN_TRAINING,
INPUT_INVALID and NUMERIC_ERROR. No partial fit is returned after failure.

README contains the complete executable input/API example. Running the committed
invented Toy A fixture at cutoff 2026-09-01 UTC, predicting A-home/C-away at
2026-09-02 UTC, returns approximately:
lambda_home=2.5038009008083715; lambda_away=0.4101151462906368.
Unchanged Phase1B returns H/D/A approximately
(0.8309347625227856,0.126027432538391,0.04303780488451258),
with retained mass 0.999999999945689 and explicit omitted mass.
These are synthetic mathematical outputs, not real-match forecasts.
Example batch hash bafa3938e9182391ad388f59ccea658fd02a5d229450943bdc096aa731227b25;
row hash 46b58552a14c2734d8624e69c9100013b201fe302000fb49ac1bbc8b7c3cbab2.

## Historical selection and exact identification

The fitter reconstructs the supplied ImportResult as version1 JSON and calls
the unchanged parse_synthetic_json(...).require_valid(), checks content hash,
then select_as_of(...,include_synthetic=True). Every selected row independently
reasserts synthetic, CLEARED, result/FINISHED/FT90, exact UTC kickoff, integer
nonnegative goals <=g_max, kickoff+90min<=available<cutoff. Unknown/coarse/
withdrawn/blocked revisions retain Phase2A exclusion/no-fallback semantics.
UTC offset must explicitly be zero. Retrieval time is never substituted.

Canonical row order is (kickoff,fixture_id,revision), teams lexicographic.
Unused registered teams are not parameters. Training-row hash excludes retrieval
stamps; batch hash separately includes the entire validated source context.
No joining of snapshots or real namespace is supported.
Target ID must not occur in training; prediction cutoff equals fit cutoff and
strictly precedes supplied exact kickoff. Historical results do not validate
target provenance, so every forecast emits TARGET_METADATA_UNVERIFIED.

Integer design coordinates are (mu,h,a_1..a_n,d_1..d_n).
A cached incremental Fraction echelon basis uses distinct exact design rows,
not graph heuristics. Full data identification requires rank=2n (two intrinsic
gauge freedoms). Both forecast design rows are individually reduced against
this basis; unknown teams fail identification. Components remain diagnostic.
Corrected matching counterexample rank=4; each already observed rate row keeps
rank4; each reverse orientation rate row increases rank to5.
Toy C rank3 is not full-model identified, yet both observed orientations'
scoring contrasts are identified. Ridge uniqueness is not data identification.

By default unsupported, cross-component and cold-start forecasts fail.
Explicit allow_unidentified=True permits prior-driven unsupported ridge
coefficients, using zero a/d for unknown teams. Explicit fallback='league'
uses empirical Hbar/Abar for both unsupported rates; a supplied FittedRateRatio
must match batch hash, row hash and cutoff. All such results label method and
prior_driven. Supported forecasts do not silently switch methods, and numeric
failure never triggers fallback. Direct comparison forecasts are labelled
APPROXIMATE_RATE_RATIO. Sparse appearance counts and [0.05,8] rate band warn.

## Objective, arithmetic and convergence

eta_H=mu+h+a_home-d_away; eta_A=mu+a_away-d_home.
NLL=sum(exp(eta)-goals*eta+lgamma(goals+1)).
J=NLL+(tau/2)*sum(a*a+d*d), uniform unweighted rows.
mu/h unpenalized; h may be negative. Analytic g/H follow the reviewed signs.
Sparse row contributions and fsum produce dense derivatives.

Initialize mu=log(Abar), h=log(Hbar)-log(Abar), effects zero.
Own deterministic dense Cholesky, triangular solves and Newton decrement;
Armijo c=1e-4, step halves down to2^-40, bounded iterations.
Both gradient infinity norm <=1e-8*max(1,total goals) and decrement²/2
<=1e-12*max(1,total goals) are required with default tolerances.
Post-fit attack/defense sums and fitted home/away totals must meet
1e-8*max(1,total goals). Finite checks guard every objective/solve/rate.
Cholesky pivots are numerical proxies, not condition numbers.

Fit exponent arithmetic is bounded to eta in [-700,700], rejecting overflow/
underflow risks rather than manufacturing zero rates. Invalid Armijo trials
backtrack; failure raises NOT_CONVERGED. Prediction requires finite >0 <=100,
no clipping. Both aggregate scoring sides must be positive.
Dense limit40 teams bounds parameter dimension82. Extremely small ridge may
still fail floating-point factorization; no guaranteed/global Newton
convergence or uniform strong-convexity assertion is made.

The Gamma-Poisson comparison uses observed Hbar/Abar, scored/conceded counts
and venue exposures; (S+kappa)/(E+kappa), (C+kappa)/(F+kappa).
It is an approximate exposure heuristic, not opponent-adjusted MLE or a ridge
parameter oracle.

## Actual checks and checkpoint outcomes

Python3.12.14 Windows, stdlib only. Commands:
python -B -m unittest discover -s tests -v
python -B -m unittest tests.test_expected_goals -v
python -B -m unittest tests.test_expected_goals tests.test_expected_goals_leakage -v

Baseline: 248 pass. Checkpoint A: 9 pass.
Initial checkpoint B: 55 new tests pass.
Review added three tests and extended adversarial coverage. One new overflow
regression initially exposed an untyped fsum OverflowError; fixed typed rate
arithmetic, preserving no-fallback behavior. Final reviewed full suite:
306 total / 306 pass / 0 failures / 0 errors:
248 unchanged +38 math/optimizer/forecast +20 leakage methods.
Final delivery evidence records reruns/export verification and exact commits.

Gates include hand-worked Toy A rate-ratio outputs within1e-12; Toy B small
tau1e-6 parameters/rates within1e-4; Toy C and corrected matching rank;
central finite-difference gradient/Hessian at3 fixed points with1e-6 relative/
absolute scale; independent Decimal ridge anchors within1e-9; totals/gauges;
mirror with negative h; duplication vs tau/2; lexical renaming; ten same-
platform permutations bitwise identical; never-scoring clubs; explicit
Armijo backtracking; typed nonconvergence, bad pivots, exp/overflow and
no-clipping errors; caps/config; frozen outputs; Poisson integration.

Twenty leakage methods cover strict availability equality, future records,
late corrections (without unjustified parameter-direction claims), withdrawals,
unknown higher revisions, coarse times, licence/status exclusions, retrieval
independence, matching cutoffs, target exclusion/provenance, forged batch/hash,
real namespace and independent selected-row assertions.

Independent 60-digit Decimal exp/ln + pivoted Gaussian elimination oracle
uses separately built dense equations and exact factorial constants; no
production derivative/rank/Cholesky helper. Maximum parameter discrepancies:
Toy A 4.22e-11, Toy B 5.33e-15, Toy C 1.82e-10. Script and full results included
in external evidence; A/C values are permanent regression anchors.
A fully invented 20-team/380-match engineering smoke fit had rank40,
3 iterations, gradient infinity norm about1.27e-10 and took about0.30s on
this host. This is neither recovery coverage nor forecast validation.

No configured linter, formatter, type checker or CI exists; none claimed.
Python3.10 runtime not available; grammar compatibility checked during export.
No real predictive skill, parameter-recovery rate or calibration measured.

## Changed paths and independent-review handoff

Seven scoped paths:
premfootballbot/expected_goals.py
tests/test_expected_goals.py
tests/test_expected_goals_leakage.py
tests/fixtures/phase2b_synthetic_v1.json
tests/expected_goals_cases.py
README.md
handoffs/CODEX_PHASE2B_IMPLEMENTATION_REPORT.md

The additional new test helper centralizes invented rows/targets used by both
new suites; no existing helpers or fixtures modified.
Scope limitations: declared synthetic timestamps/rights are not external facts;
target metadata is unverified; forecasts use provisional priors/settings;
no empirical uncertainty, provider compatibility or EPL accuracy was tested.
Fitted output objects should come from fitting functions, not untrusted manual
construction/serialization. Exact rank is data support, not estimation quality.
Keep local/source numerical constraints and explicit fallback labels.

Record exact head/tree/parent and publication outcome in external delivery.
Push only the new branch and open a draft PR, never merge. If Git credentials
block publication, provide exact committed source ZIP, diff/mail patch,
Git bundle, tree/SHA256 manifest and all evidence for independent review.

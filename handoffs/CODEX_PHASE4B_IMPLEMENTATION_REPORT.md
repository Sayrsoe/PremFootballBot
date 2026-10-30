# Phase4B fixed retrospective training/evaluation implementation

## Authority, baseline and scope

Executed the pasted owner request (the user instruction) and supporting Phase4B
ZIP requirements. Read AGENTS, README, completed/source importers, protected real
and synthetic estimators, backtesting, Poisson, evidence/result modules, relevant
tests and handoffs. Reviewed scratch scripts/results as references, not production
code or target metrics. Verified remote/local main57747fbd8cc0ec4de34557b4e433e38cdff2e9f3,
tree027671fef5a8cf768635c5bb2dc0b06a86250349. Clean starting checkout;
branch codex/phase4b-retrospective-training.653 baseline tests passed9.187s.
Budget฿0; no new dependencies, subagents or external executable code.

Scope: isolated stdlib training/evaluation on exact Phase4A2024–25/2025–26 bytes,
fixed ridge4.0, one2024 development fit and fixed2025 holdout. Integrity replay
recomputes the SAME2024 fit; never within-holdout retraining. No selectable
hyperparameter, fitting window, current-season source or tuning/search API.
All earlier Python modules, fixtures/tests, protected2023 model authorization,
synthetic gates, shadow flow and Trial1 are unchanged. No API, credential access,
odds, bets, publication of predictions, deployment, merge or new phase.

## Research before coding

- [goalmodel](https://github.com/opisthokonta/goalmodel/tree/84ecd6c2bbad3ccb967abf88ef49e5bcd074e545),
  version0.6.4, GPL3 DESCRIPTION. Inspected R/goalmodel_fit.R and
  tests/testthat/test_1.R: team attack/defense, home effect, convergence and
  name-identity checks. Adopted these mathematical/checking patterns. Rejected
  Dixon-Coles/covariate/other-distribution additions, automatic covariate defaults,
  R dependencies and copying GPL implementation. No external code copied/run.
- [skforecast](https://github.com/skforecast/skforecast/tree/3ecc0dc3d251c313b08ce26a572d17a2ace022c4),
  BSD3 LICENSE, model_selection/_split.py and tests/tests_split/test_timeseriesfold.py
  inspected at current main3ecc0dc3. Useful explicit train/test fold, gap,
  refit and input-bound contracts. Adopted immutable date-group folds; deliberately
  rejected row-count gaps, overlapping holdout folds, search, adjustable refit,
  pandas/NumPy dependencies. Our embargo is CALENDAR DAYS, never number of rows.
- [sportdb](https://github.com/sportdb/sport.db/tree/43ff505bf726db5f62890c0b8413eb30a12c88b3),
  CC0 LICENSE, match_reader.rb and test_match_reader_eng.rb re-inspected.
  Adopted explicit season/team identities and data-error boundaries; rejected
  guessed dates, permissive aliases, database ingestion and implicit writes.

Research snapshots were inspected through GitHub, not installed; current default
branches do not establish historical data availability. No external code licenses
are used to imply rights to football data. Existing source CC0 audit retained.
The pre-code design is supplied in review evidence.

## Model and source provenance

New premfootballbot/chronological_epl.py reuses only the existing PURE numerical
kernel real_epl_training._fit_rows and its immutable config/diagnostic types.
It never calls the public pinned2023 fitter or synthetic importer/fitter, never
constructs fake synthetic records and does not widen any earlier source gate.
KernelRow explicitly adapts CANONICAL team IDs into the kernel's historical
*_raw slot names; no raw source row is changed. Original normalized source rows
remain in the immutable Phase4A dataset. This private numeric dependency is
documented and protected by old numerical tests plus new boundary tests.

Every public fit/fold/forecast/evaluate boundary verifies completed dataset by
re-importing exact source bytes/manifests/license. Source dataset digest at the
recorded acquisition audit is59623d6ff79c1171b056a5da8960bb4cf7f2fb201c5ccc16223fd173b41f57f0.
OpenFootball England revision9ee7a0c351805c99cc334478a9bf04b7d0432fec:

|Season|Git blob|Raw SHA256|
|---|---|---|
|2024–25|ca0fe4923f0164d0f879f796ab0759253e13bc06|e39716b01af0c8654a9fae7b5555e6b02f506ea05239e0d0eef41936ba80e1e3|
|2025–26|918adf1c0af4f613c73530cb528ab0df72461cfb|38c1de56c9e9b6662c7efc1420b7e1fe00dddbb502fe72d8f759e773ba3c093b|

License CC0-1.0, blob670154e3538863b2d9891fd5483160fbdfc89164,
SHA25636ffd9dc085d529a7e60e1276d73ae5a030b020313e6c5408593a6ae2af39673.
No source/rights/pins changed and no new football source fetched. Supplied bytes
and license are rechecked, with inherited factual-accuracy/third-party-rights
limitations. Acquisition/source revision is never first-publication evidence.

## API, stages and leakage controls

    development_folds(dataset, inputs, *, license_bytes, target_dates, embargo_days=2)
    fit_development(dataset, inputs, *, license_bytes) -> DevelopmentModel
    forecast_holdout(model, dataset, inputs, *, license_bytes) -> HoldoutForecasts
    evaluate_holdout(model, snapshot, dataset, inputs, *, license_bytes) -> HoldoutEvaluation
    artifact_json(artifact) -> bytes
    verify_evaluation(evaluation, model, snapshot, dataset, inputs, *, license_bytes)

Date folds accept UNIQUE development match dates only, never datetimes/UTC or
holdout dates. A whole target date is one group. Training IDs are2024 rows with
date<=target minus2..366 calendar days. Same-day/D-1/future rows cannot enter.
This is a partition audit utility, not rolling model selection or holdout tuning.
The primary experiment uses full2024 training and later2025 holdout, with explicit
complete calendar-date groups in both artifacts and disjoint fixture IDs.

DevelopmentModel contains only3802024 KernelRows, training-only source identity,
row digest, fixed config, coefficients/team identities, convergence diagnostics,
training frequencies and date groups, runtime/version and seal. It has no2025
goals, fixture IDs or full-dataset hash dependency. Initialization, coefficient
fit, frequency counts and all priors use2024 only. Full source validation may
inspect holdout integrity, but no holdout labels enter any fitting calculation.

HoldoutForecasts contains380 identities/dates/canonical teams and date groups,
model/source digests, decisions, rates, raw/conditional probabilities, training
baseline and mass diagnostics. It contains NO holdout goals/outcomes/scores.
Forecast generation never reads holdout goals; unknown teams abstain with empty
probabilities and UNSEEN_PROMOTED_TEAM. No invented league-strength fallback.
Both stages are immutable/sealed. Forecasting verifies exact development-model
replay; scoring also verifies label-free snapshot replay before reading outcomes.
Replay remains byte-exact in the same runtime; re-sealed model/forecast/evaluation
tampering cannot bypass source-backed recomputation. Checksums are not signatures.

All artifacts carry RETROSPECTIVE_DATE_LEVEL_SIMULATION_NOT_EX_ANTE_VERIFIED,
kickoff_utc=None, historical_available_at=None and false strict eligibility.
No artifact is accepted by the prospective recorder or synthetic pipeline.

## Mathematics, numeric policy and uncertainty

log home rate=mu+h+attack_home+vulnerability_away;
log away rate=mu+attack_away+vulnerability_home. Positive vulnerability is weaker
defense. Minimize full independent-Poisson NLL plus4/2 times squared team effects;
mu/home advantage unpenalized. Existing deterministic Newton/Cholesky/backtracking
kernel is reused with100 iteration limit and1e-7 gradient tolerance. Fail atomically
on nonconvergence/nonfinite or implausible coefficients; no fallback or clipping.
Parameters must be finite with absolute value<20 and rates finite in(0,100].

Existing Poisson engine uses tail1e-10, maxcap512. Validate raw probabilities,
retained/omitted mass, bound and roundoff. Raw masses remain visible; conditional
division by their retained sum is explicit for proper scoring only. No original
Poisson behavior changes. Zero actual probability raises a declared infinite-
loss error rather than silently clipping. Unscaled Brier=sum(p-onehot)^2,
natural log loss=-ln(p_actual). Baseline is exact empirical2024 outcome counts
155home/93draw/132away, probabilities(155,93,132)/380. Both methods use EXACTLY
the same272 supported fixture IDs. Numeric failure halts, never silently drops a
difficult match. Means and denominators are reported separately from abstentions.

Fixed10-bin classwise descriptive calibration records count/mean probability/
observed fraction; not a calibration claim. Paired baseline-minus-model losses
are grouped by scored calendar date. Fixed4000 bootstrap resamples, seed4042026,
stdlib local Random, weighted by all matches in sampled dates, linear-interpolated
2.5/97.5 percentiles. No global RNG mutation. This posthoc descriptive interval
is not preregistered inference, independence proof or a tuning signal.

## Executed experiment and reference comparison

380 training;380 holdout;272 scored;108 abstained (71.578947% coverage). Counts
are derived from canonical team support, not hardcoded. Unknown clubs: Burnley,
Leeds, Sunderland.102 scored date clusters. No within-holdout retraining.

|Metric(lower better)|Poisson|Training-only frequencies|
|---|---:|---:|
|Mean unscaled Brier|0.6310161552923944|0.6526472625061104|
|Mean natural log loss|1.0502031344917846|1.0777063782527052|

Five Newton updates, no backtracks; gradient infinity norm2.0872192862952943e-14.
Full objective1101.1981576338846=NLL1096.7444458511445+penalty4.453711782740057.
Fitted goal totals575/540 equal observed training totals. Reference scratch model
used L-BFGS-B23 iterations with gradient about1.92e-5 and omitted factorial
constants from objective. The objective constants do not change coefficients;
different optimization precision explains tiny score differences (~6e-9 Brier,
~9e-9 log loss). No data/penalty adjustment or tuning was performed to match it.

Paired descriptive95% intervals: Brier advantage[-0.0051769781,0.0486708304],
log-loss advantage[-0.0094375810,0.0645445272]. Both cross zero. The scratch
bootstrap used NumPy RNG; ours uses stdlib Random with the same stated seed,
so resamples/percentiles need not match. Point estimates remain comparable;
neither interval establishes statistical superiority or prospective validity.

## Executable offline example

```python
from tests.test_completed_epl import inputs, FIXTURE
from premfootballbot.completed_epl import import_completed_epl
from premfootballbot.chronological_epl import (
    fit_development, forecast_holdout, evaluate_holdout, artifact_json, verify_evaluation,
)
sources = inputs()  # Exact existing checked-in manifests/CC0 fixture bytes.
license_bytes = (FIXTURE / "LICENSE.md").read_bytes()
dataset = import_completed_epl(sources, license_bytes=license_bytes)
model = fit_development(dataset, sources, license_bytes=license_bytes)
forecasts = forecast_holdout(model, dataset, sources, license_bytes=license_bytes)
evaluation = evaluate_holdout(model, forecasts, dataset, sources, license_bytes=license_bytes)
assert verify_evaluation(evaluation, model, forecasts, dataset, sources, license_bytes=license_bytes)
model_bytes, forecast_bytes, evaluation_bytes = map(artifact_json, (model, forecasts, evaluation))
```

This performs only the authorized retrospective experiment; no file writes in
core, public forecast or shadow model approval. Caller chooses artifact paths.

## Tests, changed files and independent-review gate

Baseline653 passed9.187s. Initial25 new targeted tests passed2.474s; added explicit
date-group coverage test. Final full suite679 tests (653 unchanged+26 new),
commands `python -B -m unittest tests.test_chronological_epl -v` and
`python -B -m unittest discover -s tests -v`. Exact counts/timings/logs, final
source export/replay, numeric outputs and protected-file verification in review ZIP.
No Linux/3.13 runtime, remote CI, external lint/type checker or3.10 runtime claimed.

New tests cover exact source/license, train/test IDs and dates, full date groups,
future/holdout score poisoning, kernel inputs, same-day embargo/holdout exclusion,
promotion counts, score math/zero policy, convergence/tails, matched baseline,
calibration/uncertainty accounting, deterministic full replay, re-sealed parameter/
forecast/score tampering, fixed config, existing authorization/isolation gates,
atomic numeric failure and no I/O/protected public fitting call.

Changed files: README.md; premfootballbot/chronological_epl.py;
tests/test_chronological_epl.py; this handoff. All earlier source, tests, fixtures
and authorized model fingerprints remain byte-identical to approved main.

No known local test failures. One retrospective holdout, selected coverage,
already researched holdout, assumed Poisson independence/constant strengths,
unknown historical availability and weak uncertainty remain material limits.
Not calibrated, profitable, current-season capable or ex-ante verified. Any future
tuning needs separate development/holdout governance and a fresh evaluation set.
Request independent source/leakage/math/replay review. Draft PR only; stop after
handoff. No merge/deployment/next milestone without separate owner authorization.

# Phase 3A implementation report

## What I read

Read START_HERE, complete PROMPT_FOR_CODEX, approved scope/acceptance,
SCORING_AND_LEAKAGE_SPEC, PROJECT_CONTROL, DELIVERY_CHECKLIST and all four
reference_planning_v1.0 documents. Their old planning-only status is superseded
by the owner's explicit instruction; technical and phase limits are preserved.
Inspected AGENTS.md, README, recent main history, existing match_data,
expected_goals, poisson, settlement APIs and related tests/fixtures.

Handoff SHA256:
7f3a878d2f95536ecceab1398b720456eba96ab7b5e15226763a81ffd311040c.
All11 handoff manifest entries verified.
Live main matched8d38b1f78074eb8951b44e8739211362a1205631,
tree1643931ed56978d72a7e26e2705f423931d7b78d.
Created codex/phase3a-synthetic-backtesting from that main; baseline306 tests
passed on Windows Python3.12.14 before edits. No reset, rebase or main changes.

Research inspected scikit-learn snapshot
[12e80081f5fd629fbac44223ba6ce7af8afae73a](https://github.com/scikit-learn/scikit-learn/tree/12e80081f5fd629fbac44223ba6ce7af8afae73a),
with BSD-3-Clause
[COPYING](https://github.com/scikit-learn/scikit-learn/blob/12e80081f5fd629fbac44223ba6ce7af8afae73a/COPYING).
Read model_selection/_split.py TimeSeriesSplit and
model_selection/tests/test_split.py chronological/gap toy tests;
metrics/_classification.py log_loss/Brier and
metrics/tests/test_classification.py symbolic-label, scaling, clipping and
invalid-input tests; calibration.py calibration_curve bin counts.
Adopted chronological replay, explicit class/score conventions and bin
count/mean/frequency concepts. Rejected index-only/equal-spacing assumptions
for result availability, probability clipping, inferred alphabetical order,
quantile/fitted bins and third-party dependencies. Our bins are explicitly
left-closed/right-open, except probability1 in the final bin.
No reference code/data copied or external package installed.
No provider source or football dataset was fetched; rights research remains
outside this task. A design checkpoint note preceded implementation and is
included with delivery evidence.

## What changed

One new standard-library module separates invented ex-ante targets, forecast
generation, later labels and evaluation. It reuses all earlier runtime APIs
unchanged, including historical selection and the two Phase2B fitters.
No current-clock calls, CLI/network provider behavior or spending.

Eight scoped paths:
- premfootballbot/backtesting.py
- tests/test_backtesting.py
- tests/test_backtesting_leakage.py
- tests/backtesting_cases.py
- tests/fixtures/phase3a_synthetic_v1.json
- tests/fixtures/phase3a_synthetic_targets_v1.json
- README.md
- handoffs/CODEX_PHASE3A_IMPLEMENTATION_REPORT.md

The optional separate target manifest file makes the forecast/label input
boundary explicit. Existing source, exports, tests, fixtures, AGENTS, dependency
and CI configuration are unchanged.

## API/data contracts

Direct import from premfootballbot.backtesting:
- parse_target_manifest(data: bytes) -> TargetManifest
- generate_forecasts(batch: ImportResult, manifest: TargetManifest, *,
  config: BacktestConfig=BacktestConfig()) -> ForecastSnapshot
- select_labels(batch: ImportResult, forecasts: ForecastSnapshot, *,
  evaluation_cutoff_utc: datetime) -> LabelSnapshot
- evaluate_forecasts(forecasts, labels) -> BacktestReport
- score_1x2(probabilities: ProbabilityMass, actual: str, *,
  tail_tolerance=1e-10) -> Scores
- snapshot_json(snapshot) -> bytes, verifying the stored canonical SHA256.

All public snapshot/config/result dataclasses are frozen with immutable tuples.
TargetManifest is strict version1 UTF8 JSON: namespace, is_synthetic=true,
team_ids and targets. TargetFixture has fixture_id, competition_code=EPL,
season_start_year, canonical home/away IDs, intended_kickoff_utc,
prediction_cutoff_utc and declared_at_utc. Require declaration<cutoff<kickoff.
Known RFC3339 offsets normalize UTC; no naive/date-only/unknown offset,
duplicate IDs/keys, extra outcome fields, unknown clubs or self-matches.
Caps:4MiB manifest,1..1000 targets; season1992..9998. Kickoff must leave a
representable90min interval. These are invented declarations, not authenticated
provider evidence. A postmatch-only result cannot substitute for this manifest.

BacktestConfig holds an unchanged frozen ModelConfig before replay;
default Poisson omitted-bound target1e-10 (only stricter values accepted),
inclusive max_goals512,5 calibration bins and min_evidence20.
No parameter/threshold selection uses evaluation outcomes.

MethodForecast stores method/version/status/reason, rates, raw H/D/A mass and
tail accounting, origin batch/selected-row hashes, historical ID/revision
references, exclusion counts, warnings and rank/optimizer diagnostics.
No target ground-truth score, class or difference appears in ForecastSnapshot.
Ridge/rate-ratio version is phase2b-v1; league version phase3a-league-v1.
ForecastSnapshot records immutable manifest/config/version/mass policy/banner.

EvaluationLabel is a DISTINCT type with eligible/excluded status, selected
revision, actual goals/class and availability only for eligible labels.
LabelSnapshot records frozen evaluation time, full evaluation-batch hash,
forecast linkage and explicit latest-observed/no-fallback policy.
BacktestReport contains per-fixture scoring attempts, full-universe coverage,
paired IDs/means, individual unpaired metrics, seasons and calibration.
Excluded labels have null ground truth; unavailable metrics are null, never
invented zero or nonfinite values.

BacktestError carries stable codes: input/manifest/identity/time/config,
SNAPSHOT_TAMPERED/INVALID, LEAKAGE_DETECTED, probability/mass/TAIL_GUARD,
ZERO_OBSERVED_MASS and label/evaluation-snapshot failures.
Expected Phase2B errors retain reason codes such as EMPTY_TRAINING,
DEGENERATE_ZERO_GOALS, NO_HISTORY, CROSS_COMPONENT,
PREDICTION_NOT_IDENTIFIED and NOT_CONVERGED as per-method abstentions.
Unknown programming errors are not silently converted into successful output.

README gives the executable example: parse the TWO invented JSON files,
generate forecasts, select labels at2027-08-01 UTC, evaluate, serialize.
The delivered reproduce_example.py uses those same public interfaces.
There are no edits/callsite changes inside earlier modules.

## Mathematical & temporal choices

### Historical replay and projection

Targets ordered by (cutoff,fixture ID), not random splits.
Revalidate the Phase2A batch and canonical content hash; call unchanged
select_as_of with strict availability<cutoff and synthetic selection.
Reject known target results before cutoff, doubtful target history, known
postponements, kickoff/identity mismatch or higher unknown revisions.
Never use a future final kickoff to populate pre-match metadata.
The independent manifest can supply synthetic fixture knowledge even without
a matching Phase2A fixture notice, but must have a pre-cutoff declaration.

For each selected historical fixture, construct a NEW valid Phase2A batch
with its complete revision prefix through the selected result and only
referenced teams/source documents. Do not renumber or overwrite revisions.
Withdrawn/quarantined/ineligible fixture groups are not revived. Reselect
through Phase2A and assert equivalence. Future target rows never reach a fitter.
Selected manifest fixtures must match identity and cannot have a result
available before their declared intended kickoff+90min; this conservatively
rejects forged early future-target results. An earlier-than-declared reschedule
can therefore require exclusion, rather than guessed historical knowledge.

Origin batch hash describes the projected input, not the full future archive.
Training hash uses canonical selected historical rows excluding retrieval
stamps. Omit NOT_YET_AVAILABLE counts from prediction serialization so adding
future rows does not leak via counts/digests. Other visible and conservative
uncertainty exclusions remain explicit. Historical source provenance is fixed;
source prose is provenance, not a modeled feature.

Call ridge and rate-ratio fitters independently, then existing prediction API
with no allow_unidentified/fallback argument. Verify their actual selected
rows, hashes, cutoff and config against independent selection; violations
raise hard LEAKAGE_DETECTED. The league benchmark independently invokes the
existing comparison preparation for validation/rank and uses ONLY prior
home/away totals divided by historical match count, never multipliers or
season totals. It enforces the same exact pair-support policy rather than
quietly assigning cold-start priors. Ordinary fit/support errors abstain.

### Later label policy

Evaluation cutoff is fixed, aware, normalized UTC and after every intended
kickoff in that snapshot. Stage2 calls select_as_of on the frozen evaluation
batch; strict equality at label availability remains excluded.
Join exact canonical fixture ID, competition/season/teams and intended kickoff.
Require FT90/CLEARED/exact kickoff, later availability after forecast and at
least intended kickoff+90min. Rescheduled final kickoff gives KICKOFF_CHANGED.
Unknown/retracted higher revision gives an exclusion, never an earlier label.
A later correction can change a later scoring snapshot only.
Evaluation never fits models or mutates forecasts.

Unknown-availability revisions are conservatively quarantined under existing
Phase2A semantics even when they cannot be placed at an origin. This can
reduce coverage; it is not evidence of genuine real historical availability.
Synthetic target declarations and hashes cannot authenticate real knowledge.

### Scoring, truncation and populations

ProbabilityMass contains raw H,D,A and retained/omitted/bound metadata.
No normalization, clipping or epsilon substitution. Require finite [0,1]
values, internally consistent masses within5e-12 floating roundoff,
omitted<=bound<=configured tiny tolerance. Insufficient caps abstain.
Unrepresentable numeric inputs fail with typed errors rather than overflow.

Primary log loss=-ln(p_actual).
Brier=sum three squared one-hot errors, range0..2, no division by3.
RPS uses A<D<H: two cumulative boundary errors, no division by2.
Handwritten p=(.6,.3,.1) oracles:
H log loss.5108256237659907, Brier.26, RPS.17;
D1.2039728043259361,.86,.37;
A2.302585092994046,1.26,1.17.
Zero observed mass is ZERO_OBSERVED_MASS and excluded from paired scores.
No NaN/Infinity is serialized.

These are controlled-approximation scores, not exact normalized probabilities.
A truncation-only log-loss error bound log1p(B/p_actual) is also reported.
A tiny absolute omitted bound need not imply small relative log-loss error.
The bound is not a formal floating-point interval certificate or empirical
forecast uncertainty. Brier/RPS also remain explicitly raw/approximate.
Optional exact-score and AH diagnostics are deferred to keep mandatory scope
focused; no bookmaker lines, prices or economic return calculations.

Headline comparisons use intersection of fully forecasted, eligible labeled,
successfully scored target IDs across ALL3 methods.
Report full manifest, per-method forecast/abstention counts/reasons,
predicted-but-missing-label counts, scoring errors and individual unpaired
metrics. Per-season comparisons and fixed uniform H/D/A reliability bins use
the identical paired population. Empty bins have null means/frequencies.
N<20 is INSUFFICIENT_EVIDENCE; larger bins remain DESCRIPTIVE_ONLY with no
uncertainty estimate. No winner, real calibration or profitability claim.

## Tests actually executed / result counts

Windows Python3.12.14, stdlib only:
- Baseline python -B -m unittest discover -s tests -v:306 passed.
- Checkpoint A scoring/manifest:18 passed.
- Checkpoint B integration/report:32 passed. An initial test-file import
  placement error was corrected before this pass.
- Checkpoint C new suites:55 passed, including23 leakage methods.
- Review added two numeric/datetime guard regressions; initially1 failure/
  1 error exposed missing typed input guards, then corrected.
- Reviewed full suite:363 passed,0 failures/errors:
  306 old methods untouched +34 scoring/manifest/report +23 leakage.

Final requested full command and separate targeted leakage run, source grammar/
stdlib checks, mutation sensitivity and isolated export evidence are recorded
with delivery artifacts. No configured linter/type checker/CI exists and no
CI/3.10 runtime success is claimed. Python3.10 grammar is checked at export.

Negative controls inject future target goals, future historical corrections,
new future fixtures/unused teams, a forged pre-cutoff target and another future
target, a deliberately leaky selector, a future-trained fitter and a
prior-driven substitute. Guards catch protocol violations; permissible later
data changes leave prior forecast objects/JSON digests IDENTICAL.
Tests also cover declared boundaries, paired-subset integrity under ridge-only
failure, class-specific handwritten scores, tail failure/no normalization,
zero/tiny probabilities, separate labels, later correction/withdrawal,
unknown revisions, doubtful/rescheduled kickoff, rights/identity, UTC offset/
permutation stability, finite serialization, tampered snapshots and no refitting
during scoring. All forecast JSON trees are checked for forbidden truth keys.

The independent invented fixture has13 targets/34 observation revisions:
home/draw/away ties, two synthetic seasons, cold/disconnected groups,
correction, withdrawal, uncertainty, reschedule, missing label and postponement.
Each method forecasts8, abstains5;7 labels eligible;3 predicted targets lack
an eligible scoring label; paired N=5 (four2026, one2027).
All summary/bin evidence is insufficient. Counts are engineering outputs,
not a measured success rate. Separate sample JSON artifacts are delivered.

## Performance/coverage caveats

Repeated per-origin local dense fits are deliberate and deterministic; no
large-scale throughput guarantee. Phase2B participating-team/numeric limits
still apply. Disconnected/cold-start and unknown chronology can shrink coverage.
Comparison means never substitute different method populations.
Identical bit patterns are tested on this platform only.
No real football data, paid service, tuning, source acquisition, Phase3B/3C/3D
or inference about actual EPL performance/financial edge was undertaken.
Budget remained ฿0; no external dependency installation or paid purchase.

## GitHub links and SHAs

Base8d38b1f78074eb8951b44e8739211362a1205631.
Feature branch codex/phase3a-synthetic-backtesting.
Final head/tree, draft PR state/link, exact diff and checksums are recorded in
the external delivery report after commit/publication, avoiding a self-referential
commit hash. Publish draft only; no ready/merge transition.

## Limitations/risks / HANDOFF_NEXT_AGENT

Synthetic declarations and licence/time metadata are assigned by test authors.
Origin projections preserve referenced historical source text/checksums; a
rewrite of historical provenance is a different input, not promised equivalent.
Unknown availability produces conservative abstentions, not reconstructed truth.
Digests detect changed content; they are not authenticated signatures. Public
output dataclasses are intended to originate from these APIs, not to establish
trust in arbitrary manually constructed/rehashed objects.
Proper-score truncation guarantees concern the declared mass bound, separately
from arithmetic error and real-model uncertainty. Optional exact-score/AH,
real providers, source rights, real publication history and actual forecast
quality remain untested and out of scope.

Exact next steps: GPT-6 independently review the draft PR, projection and
label/score separation, paired denominator and scoring oracles; reproduce
all tests/example and verify head/tree/changed paths. Owner must separately
authorize any merge. Do not mark ready, merge, buy services, acquire real data,
or start Phase3B/3C/3D from this handoff.

# PremFootballBot

This offline Python library provides exact Asian handicap settlement (Phase 1A)
and fixed-rate independent-Poisson probabilities (Phase 1B).
It accepts **full-time regulation goals including stoppage time**, excluding
extra time and penalties. All examples and tests use fabricated results.

## Quick start

Requires Python 3.10 or newer. Run from this checkout; there are no third-party
dependencies or installation steps.

```python
from fractions import Fraction
from premfootballbot import calculate_payout, parse_handicap, settle_handicap

# q=+1 means +0.25 goals for the selected home team.
result = settle_handicap(1, 1, side="home", handicap_q=parse_handicap("+0.25"))
assert result.outcome.value == "HW"
assert (result.win, result.refund, result.loss) == (
    Fraction(1, 2), Fraction(1, 2), Fraction(0)
)

payout = calculate_payout(result, decimal_odds="1.90", stake="100")
assert payout.net == Fraction(45)
assert payout.gross == Fraction(145)
assert payout.net_per_unit == Fraction(9, 20)

tiny = calculate_payout(result, decimal_odds="1.90", stake="0.01")
assert tiny.net == Fraction("0.0045")  # deliberately unrounded
```

## Interface and conventions

- `settle_handicap(home_goals, away_goals, side, handicap_q) -> Settlement`:
  goals are nonnegative integers; side is exactly `"home"` or `"away"`.
  Booleans are rejected as goals/quarter units.
- `handicap_q` is an integer from the **selected side's perspective**.
  Positive values help that team: +3 is +0.75, -3 is -0.75, +4 is +1.0.
  Odd q splits half the stake at q-1 and half at q+1; even q settles once.
- `parse_handicap(decimal_text) -> int` is optional. It accepts exact plain
  decimal strings, such as `"-0.75"`, `".25"` and `"+1.00"`; non-quarter
  values are rejected rather than rounded.
- `Settlement` is immutable, exposing `outcome` and exact `Fraction` values
  `win`, `refund`, `loss`, summing to one. `Outcome` enum values are
  `FW`, `HW`, `P`, `HL`, `FL`.
- `calculate_payout(settlement, *, decimal_odds, stake="1") -> Payout`:
  odds and stake are finite **decimal strings**, with odds >1 and stake >0.
  Floats, Decimal/Fraction objects, exponent notation, whitespace, separators,
  fraction text and trailing decimal points are rejected. Leading signs,
  leading zeroes and a leading decimal point are accepted.
- `Payout` is immutable. `odds`, `stake`, `net`, `gross`,
  `net_per_unit` and `gross_per_unit` are exact fractions. Net and gross
  refer to the supplied stake; the default is one.
- Invalid types raise `TypeError`; invalid values raise `ValueError`, with
  the offending field named. Calculations do not depend on Decimal precision.

Per-unit net/gross returns at decimal odds o:

| Outcome | Net | Gross |
| --- | --- | --- |
| FW | o-1 | o |
| HW | (o-1)/2 | (o+1)/2 |
| P | 0 | 1 |
| HL | -1/2 | 1/2 |
| FL | -1 | 0 |

Boundary examples: +0.75 with a one-goal defeat is HL; +1.0 with a one-goal
victory is FW; -0.75 with a one-goal victory is HW.

## Tests

```console
python -B -m unittest discover -s tests -v
```

The suite includes all 26 research golden cases, 30 independent DeepSeek
regression cases, both-side boundary corrections, input rejection, exact money
examples and exhaustive small-domain invariants. The original reusable cases
are in `tests/golden_cases.py`; the reviewed CSV is preserved in
`tests/fixtures/deepseek_30_regression_fixtures.csv`. Each DeepSeek row has its
own named unittest in `tests/test_deepseek_regressions.py`.

For another application, place this checkout on its Python import path and
import the public `premfootballbot` API. No package installer or framework is
needed for the current scope.

## Scope and handoff

Administrative voids/abandonments and currency rounding policies are outside
this library. Phase 1A contains no external data, odds feeds, prediction models,
database, frontend or betting recommendations.

See [the implementation handoff](handoffs/CODEX_PHASE1A_IMPLEMENTATION_REPORT.md)
for decisions, source references, executed checks and integration notes.

## Phase 1B: hypothetical Poisson probabilities

Supply expected-goal rates yourself; this baseline does not estimate team
strength or claim real-match accuracy. The independence assumption and any
supplied rates require later empirical evaluation.

```python
from premfootballbot import poisson_distribution

# Hypothetical rates, not an EPL forecast.
model = poisson_distribution(1.4, 1.1)
match = model.one_x_two()
home_plus_quarter = model.asian_handicap("home", handicap_q=1)

print(model.home_cap, model.away_cap)  # 14, 13 (inclusive)
print(match.home_win, match.draw, match.away_win)
# Approximately 0.438042706888, 0.266344854275, 0.295612438789
print(home_plus_quarter.fw, home_plus_quarter.hw, home_plus_quarter.push,
      home_plus_quarter.hl, home_plus_quarter.fl)
# Approximately 0.438042706888, 0.266344854275, 0, 0, 0.295612438789
print(model.mass.retained_mass)       # Approximately 0.999999999952226
print(model.mass.omitted_mass)        # Approximately 4.77739868416e-11
print(model.mass.omitted_mass_bound)  # Approximately 4.77969999977e-11
print(model.score_probability(1, 1))  # Approximately 0.126410897881
assert model.score_probability(100, 100) is None

# Reuse the same cached distribution for another selected-side line.
away_minus_half = model.asian_handicap("away", handicap_q=-2)
```

- `poisson_distribution(lambda_home, lambda_away, *, tolerance=1e-10,
  max_goals=512)` chooses separate caps using positive upper-tail bounds.
  Joint rates must be finite `numbers.Real` values in [0, 100]; bool, text
  and Decimal inputs are rejected. Zero is exact. Tolerance must be finite
  and strictly between 0 and 1; the inclusive integer cap must be in [0, 512].
  `GoalCapError` means the target cannot be established within that cap.
- `truncated_poisson_distribution(lambda_home, lambda_away, *,
  home_cap, away_cap)` uses explicit caps with no tolerance promise.
  For example, caps (0, 0) at rates (1.4, 1.1) retain only
  `exp(-2.5)`, approximately 0.082085, exposing substantial omitted mass.
- `poisson_pmf(goals, rate)` is a scalar log-space PMF; goals are
  nonnegative integers, excluding bool. It supports the rate-800 mode stress
  check. Very large scalar arguments remain limited by floating-point
  arithmetic and are not a general arbitrary-precision calculation.
- Frozen `PoissonDistribution` holds tuple marginals and a cached
  `difference_pmf` ordered from `-away_cap` through `home_cap`.
  Each cell is the raw product of its marginal masses. Above-cap score
  queries return `None`: those scores belong to omitted mass.
- `one_x_two()` returns frozen H/D/A fields; `asian_handicap(side, q)`
  returns frozen `fw, hw, push, hl, fl` fields. They share `mass` metadata.
  Handicap signs, validation and classifications come from Phase 1A.
  Outcome fields are probabilities of events, not fractional stake returns.
- No cell or outcome probability is renormalized. Outcome totals equal
  retained mass within floating-point roundoff.
  `MassSummary` reports `retained_mass`, `omitted_mass`,
  `omitted_mass_bound` and `mass_roundoff`.
  Omitted mass is calculated from positive tail terms: mathematically 1-M,
  but it remains positive when M rounds to 1.0. The geometric upper bound
  includes a floating-point margin; it is not an interval-arithmetic proof.
  `mass_roundoff` exposes the raw difference sum minus the retained CDF
  product, rather than correcting probabilities.

The joint rate limit and maximum caps bound work to at most 513 squared
products; scalar rate 800 is tested separately. The default target controls
truncation, not parameter uncertainty or prediction accuracy.

The Phase 1A/1B suite has 180 tests: the unchanged 68 Phase 1A tests,
24 independent 1X2 rows, 49 independent AH rows, and 39 numerical/integration
tests. The new fixture CSV bytes are preserved under `tests/fixtures/`.
Both adaptive and supplied fixed-cap results are checked against every row
at absolute tolerance 1e-9.

See [the Phase 1B implementation report](handoffs/CODEX_PHASE1B_IMPLEMENTATION_REPORT.md)
for research, licensing, numerical design, executed checks and limitations.

## Phase 2A-Offline: synthetic observation records

The `premfootballbot.match_data` module is an offline, version-1 synthetic
JSON importer. It validates records and preserves observation histories.
It does not obtain EPL data or fit a model. Its API is separate from the
existing settlement and probability functions.

```python
from datetime import datetime, timezone
from pathlib import Path
from premfootballbot.match_data import (
    parse_synthetic_json, select_as_of, summarize_coverage, snapshot_manifest,
)

data = Path("tests/fixtures/phase2a_synthetic_v1.json").read_bytes()
batch = parse_synthetic_json(data).require_valid()
old = select_as_of(batch, datetime(2026, 8, 2, tzinfo=timezone.utc))
corrected = select_as_of(batch, datetime(2026, 8, 4, tzinfo=timezone.utc))
assert [(r.revision, r.home_goals_90) for r in old.observations] == [(1, 0)]
assert [(r.revision, r.home_goals_90) for r in corrected.observations] == [(2, 1)]

print(batch.content_sha256)
# 81fc7eb53c76c3693c77ba533b6c55c4a036c724a8f3f25c60e878ce28bfa2aa
print(summarize_coverage(batch, expected_matches={2026: 380})[0].fixture_count)
# 4; the expected count is explicitly hypothetical, not a source inventory.
manifest = snapshot_manifest(batch)
assert not select_as_of(
    batch, datetime(2027, 1, 1, tzinfo=timezone.utc), include_synthetic=False
).observations
```

Input must be UTF8 bytes with exactly these envelope fields:
`schema_version=1`, `namespace`, `teams`, `source_documents`, `records`.
The committed [synthetic JSON example](tests/fixtures/phase2a_synthetic_v1.json)
is the complete executable schema example. Team IDs/aliases are explicit;
each source document embeds invented text, its verified SHA256, a terms ID,
a licence state and `is_synthetic=true`. Every observation must match its
registered provenance. Only `synthetic:<slug>` namespaces are supported.
Unknown fields and duplicate JSON keys fail; no fuzzy identity matching.

- `parse_synthetic_json(data: bytes) -> ImportResult` returns frozen tuples
  of observations, teams, documents and structured issues. Any error rejects
  the entire batch. Inspect `errors`/`warnings` or call `require_valid()`
  to raise `MatchDataError`. Input is bounded to 4 MiB and 10,000 records.
- Revisions start at zero and are consecutive, with explicit
  `supersedes_revision` links and stable fixture/source/team/season identity.
  Known availability must increase strictly. Identical duplicates collapse;
  only retrieval stamps may differ, retaining the earliest. Content conflicts
  fail. A replay with different identity needs a new fixture.
- `select_as_of(batch, cutoff_utc, *, include_synthetic=True)` returns only
  eligible FT90 results with availability **strictly before** the aware
  cutoff. It chooses the latest observed revision before applying status,
  precision and licence gates. An observed withdrawal cannot resurrect an
  older score. A higher revision with unknown availability quarantines the
  older result; a known later successor can resolve that uncertainty.
- Exact timestamps require explicit offsets and normalize to UTC. Date-only
  or unknown kickoffs stay coarse; null availability stays unknown.
  Retrieval time never substitutes for publication. Kickoff+90 minutes is
  only a result-availability lower bound. Fixture announcements may occur
  after kickoff. Only FINISHED result/FT90 records carry integer goals;
  awarded, abandoned and unplayed observations have null scores/basis.
- `canonical_content(batch)` returns sorted normalized UTF8 bytes for
  SHA256 hashing, excluding retrieval timestamps. It is a hash representation,
  not an input document. `snapshot_manifest(batch)` keeps retrieval stamps
  and verified source-document digests separately. No clock is consulted.
- `summarize_coverage(batch, *, expected_matches=None)` counts distinct
  latest-present fixtures separately from revisions and reports statuses,
  missing availability, coarse kickoffs and separate fixture/result
  completeness against optional explicit expectations. It is not a historical
  training selection and does not assume every season has 380 matches.

The Phase 1A/1B/2A suite has 248 tests: the unchanged 180 Phase 1A/1B tests plus 53
validation/determinism tests and 15 independent leakage scenario tests.
Run `python -B -m unittest discover -s tests -v`.

This importer cannot verify a fabricated label's real-world truth or establish
provider rights. It verifies the declared embedded document's checksum, not
that every observation is independently supported by that text. Histories
are immutable within a parsed batch; compare hashes/manifests to audit changes
between snapshots. Real data, provider adapters, training, odds and subsequent
phases require separate scope and review.

See [the Phase 2A implementation report](handoffs/CODEX_PHASE2A_IMPLEMENTATION_REPORT.md)
for the exact contract decisions, research, executed checks and limitations.

## Phase 2B: synthetic-only expected-goals estimation

`premfootballbot.expected_goals` fits a small ridge-penalized independent
Poisson model from the synthetic observations validated by Phase 2A. It also
provides an explicitly approximate Gamma-Poisson rate-ratio comparison.
These are engineering examples, not evidence of real EPL forecast skill.

```python
from datetime import datetime, timezone
from pathlib import Path
from premfootballbot.match_data import parse_synthetic_json
from premfootballbot.expected_goals import fit_expected_goals, predict_expected_goals

batch = parse_synthetic_json(
    Path("tests/fixtures/phase2b_synthetic_v1.json").read_bytes()
).require_valid()
cutoff = datetime(2026, 9, 1, tzinfo=timezone.utc)
model = fit_expected_goals(batch, cutoff)
forecast = predict_expected_goals(
    model,
    target_fixture_id="synthetic:phase2b:fixture:example",
    home_team_id="synthetic:phase2b:team:a",
    away_team_id="synthetic:phase2b:team:c",
    target_kickoff_utc=datetime(2026, 9, 2, tzinfo=timezone.utc),
    cutoff_utc=cutoff,
)
print(forecast.lambda_home, forecast.lambda_away)
# Approximately 2.5038009008083715, 0.4101151462906368
probabilities = forecast.probabilities()  # unchanged Phase 1B engine
print(probabilities.one_x_two())
assert "TARGET_METADATA_UNVERIFIED" in forecast.warnings
```

- Direct import preserves existing package exports. `fit_expected_goals(batch,
  cutoff_utc, *, config=ModelConfig())` and `fit_rate_ratio(...)` revalidate one
  synthetic batch through Phase 2A, select strictly available results, and
  retain selected rows, hashes, exclusions, team counts and exact rank.
- The main model uses `eta_H=mu+h+a_home-d_away` and
  `eta_A=mu+a_away-d_home`, with unpenalized mu/h and positive attack/defense
  ridge. Higher defense reduces opponents' rates; home advantage can be
  negative. The objective includes the Poisson factorial constants.
- `ModelConfig` defaults: tau=4, kappa=4, g_max=20, n_min=6, at most
  100 Newton iterations, gradient tolerance 1e-8 and decrement tolerance
  1e-12, both scaled by total goals. These are provisional synthetic settings.
  Config/type, empty selection, zero-goal aggregate sides and oversized scores
  raise `ExpectedGoalsError` with a machine-readable `code`.
- Identifiability uses exact rational rank of the full integer design.
  The two prediction rate rows are each checked against its cached row span.
  Graph components alone cannot establish identification: even reversing a
  previously observed pairing can be unsupported.
- Unsupported/unknown/cross-component predictions fail by default.
  `allow_unidentified=True` explicitly permits prior-driven ridge values
  (zero unknown-team attack/defense). Alternatively `fallback="league"`
  uses the empirical home/away averages for both rates, or supply a
  `FittedRateRatio` from the same batch/rows/cutoff. These forecasts are
  labelled by method and `prior_driven`; there is no automatic fallback after
  an optimization or rate error. The comparison does not adjust for opponents.
- Fitting and prediction cutoffs must be exact aware UTC values, with the
  prediction cutoff equal to the fit cutoff and strictly before target kickoff.
  Target fixture IDs must be absent from training. Target identity/kickoff are
  caller-supplied: historical result selection cannot authenticate them.
- Returned rates must be finite, strictly positive and <=100, without clipping.
  Rates outside the provisional [0.05,8] band emit warnings.
  Fitting also rejects log rates outside [-700,700] for arithmetic safety.
  Dense fitting is limited to 40 participating teams (82 parameters);
  unused registered teams do not become parameters.
- Frozen diagnostics expose NLL/objective, gradient norm, Newton decrement,
  iterations, backtracks, objective trace, Cholesky pivots and post-fit
  goal-total/gauge checks. Pivots are numerical proxies, not a condition
  number or forecast confidence interval. No empirical uncertainty or
  guaranteed global Newton convergence is claimed.

The Phase 1A/1B/2A/2B suite has 306 tests, including all unchanged 248 earlier tests,
38 new math/optimizer/forecast tests and 20 new leakage tests. Run
`python -B -m unittest discover -s tests -v`. Independent hand-worked and
60-digit Decimal references, derivative checks and exact-rank counterexamples
are described in [the Phase 2B report](handoffs/CODEX_PHASE2B_IMPLEMENTATION_REPORT.md).

No real data, provider integration, odds, tuning, Phase 3 or merge is included.

## Phase 3A: synthetic walk-forward evaluation

**SYNTHETIC DEMONSTRATION ONLY — NO REAL EPL ACCURACY OR BETTING PROFIT CLAIMS.**

The new `premfootballbot.backtesting` module separates predeclared targets,
forecast generation, later label selection and scoring. It does not fetch
football data or run paid services. The observation and target JSON files below
are independently invented test inputs.

```python
from datetime import datetime, timezone
from pathlib import Path
from premfootballbot.match_data import parse_synthetic_json
from premfootballbot.backtesting import (
    parse_target_manifest, generate_forecasts, select_labels,
    evaluate_forecasts, snapshot_json,
)

fixtures = Path("tests/fixtures")
batch = parse_synthetic_json(
    (fixtures / "phase3a_synthetic_v1.json").read_bytes()
).require_valid()
manifest = parse_target_manifest(
    (fixtures / "phase3a_synthetic_targets_v1.json").read_bytes()
)
forecasts = generate_forecasts(batch, manifest)  # no target ground truth
labels = select_labels(
    batch, forecasts,
    evaluation_cutoff_utc=datetime(2027, 8, 1, tzinfo=timezone.utc),
)
report = evaluate_forecasts(forecasts, labels)  # never refits
print(report.banner)
print(report.manifest_n, len(report.paired_ids))  # 13 targets, paired N=5
canonical_report = snapshot_json(report)  # finite sorted JSON with verified SHA256
```

- `parse_target_manifest(bytes) -> TargetManifest` accepts a strict version1
  synthetic namespace/team registry and targets with canonical IDs,
  competition, season, intended kickoff, prediction cutoff and declaration
  timestamp. Require `declared_at < cutoff < kickoff`; known offsets normalize
  to UTC. Unknown fields (including scores), duplicate IDs, date-only/naive
  times, self-matches and unknown teams are rejected.
- `generate_forecasts(batch, manifest, *, config=BacktestConfig())` orders
  origins by cutoff and fixture ID. It selects history using the unchanged
  Phase 2A API, then gives each fitter a valid batch containing only complete
  historical revision prefixes. No current target result enters a fit.
  Forecast batch hashes describe these origin projections, not future labels.
- Three fixed methods: existing ridge Poisson, existing approximate rate-ratio,
  and a league benchmark using prior home/away averages. All enforce the same
  exact pair-support policy. Cold starts, disconnected/unidentified pairs,
  empty/degenerate histories and numerical failures produce reason-coded
  abstentions. No fallback or `allow_unidentified=True` is enabled.
- `select_labels(batch, forecasts, *, evaluation_cutoff_utc)` is a separate
  frozen later snapshot. It joins exact fixture IDs, requires matching
  identity/season/kickoff and eligible later FT90 availability, and preserves
  strict revision/no-fallback rules. Rescheduled final kickoffs are excluded
  rather than retrofitted into forecasts.
- `evaluate_forecasts(forecasts, labels)` reports full-universe coverage,
  abstentions, label exclusions and scoring errors. Comparative means,
  per-season results and calibration use the same explicit intersection
  of scored targets across all three methods. Individual unpaired counts and
  means remain separately labelled. Fixed uniform bins include empty bins;
  N<20 is marked `INSUFFICIENT_EVIDENCE`, with no uncertainty estimate.
- Primary score is natural-log loss; Brier sums all three squared errors
  (range0..2), and RPS uses ordered A<D<H and two cumulative boundaries,
  without dividing by2. `score_1x2(ProbabilityMass, "H"|"D"|"A")` has
  independent handwritten test oracles. Zero observed mass raises a typed
  error; no clipping.
- Raw Poisson masses are never renormalized. The omitted bound must meet
  default1e-10 (or a stricter configured target); insufficient caps abstain.
  Scores are labelled controlled approximations. Each score also records a
  truncation-only log-loss bound `log1p(B/p_observed)`: a small absolute tail
  does not guarantee a small relative log-loss error. Floating-point error
  is separate from this bound.
- Snapshots/config/results are frozen and hashed; forecast snapshots contain
  no label, actual class, final goals or goal difference. Digests detect
  content changes, not authenticated source truth. Synthetic declarations
  and unknown-revision quarantines are not evidence of real historical
  publication times.

The fixture demonstrates13 targets,8 forecasts and5 abstentions per method,
7 eligible labels,3 unavailable/ineligible labels among each method's forecasts,
and paired N=5 across2026/2027 synthetic seasons. No method winner is claimed.

Run `python -m unittest discover -s tests -v`.
The complete suite has363 tests:306 earlier tests unchanged,
34 new scoring/manifest/report tests and23 new leakage tests.
See [the Phase 3A implementation report](handoffs/CODEX_PHASE3A_IMPLEMENTATION_REPORT.md)
for research, signatures, policies, exact evidence and review guidance.
Optional exact-score and AH diagnostics are deferred. Budget: ฿0; no real
data, paid services, Phase3B/3C/3D or merge.


## Phase 3B Scope A: isolated OpenFootball archive exploration

**EXPLORATORY ONLY / NO POINT-IN-TIME CERTIFICATION.** The independent
`premfootballbot.openfootball_exploratory` module parses caller-supplied pinned
OpenFootball England CC0 archive bytes. It preserves real archive labels and
cannot feed the existing synthetic-only training or backtesting APIs.

The supported inspected profiles are `2023-24/1-premierleague.txt` and
`2025-26/1-premierleague.txt`, with explicit raw team-label lists. Other seasons,
competitions, unknown teams and unsupported layouts need separate review.
No downloader, scraper, network call, credentials or new dependencies are added.

```python
from datetime import date, datetime, timezone
from pathlib import Path
from premfootballbot.openfootball_exploratory import (
    OpenFootballSource, parse_openfootball_epl,
    summarize_exploratory_coverage, select_exploratory_prior_dates,
    exploratory_json,
)

# Caller has already obtained and independently verified this exact pinned file.
# The supplied retrieval time must be your actual recorded acquisition time.
raw = Path("/your/local/archive/2023-24/1-premierleague.txt").read_bytes()
recorded_retrieval_utc = ...  # replace with your recorded aware datetime
source = OpenFootballSource(
    repository_url="https://github.com/openfootball/england",
    repository_commit_sha="9ee7a0c351805c99cc334478a9bf04b7d0432fec",
    path="2023-24/1-premierleague.txt",
    expected_git_blob_sha="23cdd8a340b72f6f30c514fbf609d5cf252723aa",
    expected_sha256="0bfb4a7fffe0b1bf7318955686eafeb28fc9676346ae433259e7409d69551450",
    licence_id="CC0-1.0",
    licence_evidence_url="https://github.com/openfootball/england/blob/9ee7a0c351805c99cc334478a9bf04b7d0432fec/LICENSE.md",
    licence_blob_sha="670154e3538863b2d9891fd5483160fbdfc89164",
    retrieved_at_utc=recorded_retrieval_utc,
)
archive = parse_openfootball_epl(raw, source=source)
coverage = summarize_exploratory_coverage(archive)
print(coverage.banner, coverage.accepted_rows, coverage.quarantined_rows)
# Pinned sample audit: 380 accepted, 0 quarantined; this is parsing coverage.
candidates = select_exploratory_prior_dates(archive, date(2023, 9, 1))
print(candidates.policy)  # hypothetical retrospective candidates only
report_bytes = exploratory_json(coverage)
```

`OpenFootballError.code` distinguishes atomic integrity/provenance/encoding
failures from line-level quarantine. Each accepted row retains raw text,
calendar-date header, exact source line/locator, file SHA256 and Git blob SHA.
Duplicate, changed-date or conflicting home-away pair rows are excluded without
choosing a winner; unknown/status/invalid-date rows retain reasons and counts.
UTF8 BOM and CRLF are supported without altering the raw-byte checksum.

Calendar years use the explicit July–June season window, with weekday validation.
Printed `HH:MM` remains untrusted text: `kickoff_utc=None`, timezone `UNKNOWN`,
`historical_available_at=None`. Retrieval describes acquisition of a final
archive; it never substitutes for historical result publication.

The optional helper applies a calendar embargo of at least two days and excludes
an optional adapter target identity. It does not fit, forecast or certify prior
knowledge. Its digest covers only selected semantic rows and stable source
identity, so purely future nonconflicting changes leave earlier candidates
unchanged. A correction/conflict to an earlier fixture can invalidate it.
Full import/audit hashes include source pins and locators and change accordingly.
Checksums verify caller assertions; offline parsing cannot authenticate a remote
commit tree, data truth or every third-party right. No real-data model training,
performance measurement, AH odds, win rate, ROI or paid-data access is included.

Run `python -m unittest discover -s tests -v` (418 tests), and
`python -m unittest tests.test_openfootball_exploratory_leakage -v` (18 tests).
See [the Scope A implementation report](handoffs/CODEX_PHASE3B_SCOPEA_IMPLEMENTATION_REPORT.md)
for source audits, licensing, API contracts, tests and limitations.

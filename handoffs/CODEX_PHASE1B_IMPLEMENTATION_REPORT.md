# Phase 1B implementation report

## Repository and scope

Reviewed AGENTS.md, README, settlement.py, existing tests and handoffs.
Fetched current GitHub main and confirmed Phase 1A squash merge
ae5f0bff33e745daeb9f6aa7f78b4c5fdf59381b before creating
codex/phase1b-poisson-baseline from that exact commit.
The original settlement module, exact payouts, 26 golden cases, 30 Phase 1A
fixtures and all 68 existing tests are unchanged. Existing exports remain.

Input handoff: PremFootballBot_Phase1B_Codex_Handoff_v1.0.zip,
SHA256 9a0f093ed73003d6c83ba4271f7f746f9265b404e07dff52b71af8307d7a5c0f.
Read START_HERE.md, CODEX_PHASE1B_TASK.md, the complete DeepSeek research
and both CSVs. No real data, fitting, odds/EV, Dixon-Coles, frontend or Phase 2.

## Research and plan

Studied these source snapshots and licenses before implementation:

- [penaltyblog](https://github.com/martineastwood/penaltyblog/tree/6870f0e762e9cba35fa722dc14a8daeaf8bc6134):
  MIT [LICENCE](https://github.com/martineastwood/penaltyblog/blob/6870f0e762e9cba35fa722dc14a8daeaf8bc6134/LICENCE).
  Inspected models/football_probability_grid.py and models/utils.pxd.
  Useful patterns: separate score marginals, grid aggregation and log PMFs.
  Rejected its default grid normalization and stake-fraction W/P/L public
  semantics: this task needs raw mass and five outcome event probabilities.
  Avoided its compiled/scientific dependencies.
- [SciPy](https://github.com/scipy/scipy/tree/f5d04b01ed54ee27861e2aa2ed9c0e5484a79551):
  BSD-3-Clause [license](https://github.com/scipy/scipy/blob/f5d04b01ed54ee27861e2aa2ed9c0e5484a79551/LICENSE.txt).
  Inspected scipy/stats/_discrete_distns.py, poisson_gen, and
  [official Poisson documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.poisson.html).
  Adopted the mathematical log-PMF approach and separate survival-tail
  accounting; implemented with stdlib math, without SciPy or copied code.
  Python's [math documentation](https://docs.python.org/3.10/library/math.html)
  informed lgamma/fsum use.

Both permissive reference licenses were inspected; no reference implementation
code was transplanted and no new dependency or provider data was added.
Snapshots pin research provenance rather than asserting future freshness.

Plan followed: independently verify fixtures; implement stable marginal/tail
accounting and cached differences; aggregate via Phase 1A; add permanent
regressions/invariants; run complete tests; document and export/publish.

## Architecture and API

New premfootballbot/poisson.py uses math, numbers.Real and frozen dataclasses
with tuple fields. Exported via premfootballbot/__init__.py:

- poisson_pmf(goals, rate) -> float
- poisson_distribution(lambda_home, lambda_away, *, tolerance=1e-10,
  max_goals=512) -> PoissonDistribution
- truncated_poisson_distribution(lambda_home, lambda_away, *, home_cap,
  away_cap) -> PoissonDistribution
- PoissonDistribution: rates, marginal tuples, cached difference_pmf, mass,
  home_cap/away_cap properties; score_probability(h,a), one_x_two(),
  asian_handicap(side, handicap_q).
- MassSummary(retained_mass, omitted_mass, omitted_mass_bound, mass_roundoff),
  OneXTwoProbabilities(home_win, draw, away_win, mass),
  AsianHandicapProbabilities(side, handicap_q, fw, hw, push, hl, fl, mass).
- GoalCapError and DEFAULT_TOLERANCE, MAX_GOAL_CAP, MAX_DISTRIBUTION_RATE.

Rates accept finite nonnegative numbers.Real, excluding bool; Fraction works,
Decimal/text do not implicitly coerce. Joint rates are explicitly bounded to
100; inclusive cap integers to 512. Scalar mode-at-800 evaluation is supported.
Invalid types raise TypeError, invalid values ValueError; insufficient cap or
unrepresentable tail target raises GoalCapError. Numerical inconsistency
beyond the explicit roundoff budget raises ArithmeticError.

For each nonzero difference mass, asian_handicap calls the unchanged
settle_handicap with surrogate scores (max(d,0), max(-d,0)).
No second settlement policy exists. Multiple lines reuse one cached
difference tuple. Exact score masses are products of exposed marginals;
above-cap queries return None, not a claim of true probability zero.

## Equations and numerical limits

For lambda > 0, log p(k) = -lambda + k log(lambda) - lgamma(k+1).
Zero lambda is handled exactly. Difference masses sum raw p_home(i)*p_away(j)
over i-j=d with math.fsum, avoiding an eagerly allocated square matrix.

For inclusive cap N beyond the mode, the decreasing upper tail is bounded by
p(N+1)/(1-lambda/(N+2)). The bound is evaluated in log space, padded for
floating-point roundoff and rounded toward infinity with nextafter.
Separate caps each meet epsilon/2, so the combined bound
B_h+B_a-B_h*B_a meets epsilon. Impossible/subnormal targets fail explicitly.

Tail mass is summed from positive decreasing terms with a geometric remainder
stopping test, rather than inferred from a CDF rounded to one.
For caps below the mode, direct lower-tail PMF summation preserves tiny CDFs.
Retained mass M=C_h*C_a; omitted mass T_h+T_a-T_h*T_a equals 1-M
mathematically, but floating-point subtraction can lose a tiny tail.
This is intentional and documented. No silent normalization or probability
correction is performed. mass_roundoff exposes sum(raw differences)-M;
an absolute discrepancy exceeding 5e-12 raises ArithmeticError.
Bounds have floating-point safeguards, not formal interval certification.
Targets far below machine epsilon control truncation only, not total
floating-point error.

Joint limits bound work to at most 513**2 products. Scalar PMF800 is separate:
large full score distributions are deliberately unsupported.
Independence, hand-supplied rates and truncation are modeling limitations.
No prediction accuracy, calibration, profitability or real-match validity
was evaluated or claimed.

## Independent fixtures and source inconsistency

Before production comparison, recalculated all 24 1X2 and 49 AH rows using
70-digit Decimal.exp and recurrence from p(0), direct joint accumulation,
and independent integer-leg AH classification, with no production imports.
All rows agree within 1e-9; largest absolute discrepancy was approximately
5.28414e-10 from the rounded research values.
The independent mode reference p_800(800) is
0.01410327042158371942767780436510208908413816637463801723411840288289981.

The research half-line threshold table says GD >= -h+1, which is incorrect
for noninteger h. The integer win threshold is floor(-h)+1 (GD > -h).
The CSV values passed recalculation; settlement.py remains authoritative.

Original CSV bytes are preserved, including Unicode minus in AH q;
only parsing normalizes that character.
SHA256:
- deepseek_24_1x2_fixtures.csv:
  5f1c411e713a999d89de6cd8baab381e680cf2958eadfb2233924dad7bbdda72
- deepseek_49_ah_fixtures.csv:
  465f8c1a0c8ac9e0d22dad3773bfcb01c731c68ba4a713c10cd10891ea0d3a4d

## Actual verification

Runtime: Python 3.12.14 on Windows; no third-party packages.
Before changes, python -X utf8 -B -m unittest discover -v passed all 68
Phase 1A methods. After implementation, the same command passed 180 methods
(68 original, 73 independently named fixture methods, 39 numerical/integration
methods), with zero failures/errors. Each of the 73 fixture methods checks
both adaptive and supplied fixed caps, absolute tolerance 1e-9.

New coverage includes exact zeros, type/value rejection, finite/nonfinite
rates, PMF800 against the independent decimal reference, separate caps,
tight/insufficient cap handling, tiny positive tails even when M rounds 1,
raw fixed-cap missing mass, immutability, exact scores, q-sign and negative
modulo sparsity, classifier reuse, same cached distribution across lines,
home/away mirrors, opposite-side complementarity, monotonicity, and
independent small-matrix vs difference/AH aggregation.

README's hypothetical (1.4,1.1) example was executed:
caps (14,13), H/D/A approximately
(0.43804270688840347, 0.26634485427468785, 0.29561243878913485);
home+0.25 gives FW=H, HW=D, P=HL=0, FL=A.
M approximately 0.999999999952226, omitted 4.777398684163419e-11,
bound 4.77969999976989e-11, roundoff 2.220446049250313e-16.

No repository lint/type-check/CI configuration or Python 3.10 runtime is
present; no such checks are claimed. Code uses Python 3.10-compatible syntax
and stdlib APIs. This is numerical verification, not empirical forecasting
evaluation. Delivery evidence records final rerun and export verification.

## Changed files and delivery

Only eight Phase 1B files:
README.md; premfootballbot/__init__.py; premfootballbot/poisson.py;
tests/test_poisson.py; tests/test_poisson_fixtures.py;
tests/fixtures/deepseek_24_1x2_fixtures.csv;
tests/fixtures/deepseek_49_ah_fixtures.csv;
handoffs/CODEX_PHASE1B_IMPLEMENTATION_REPORT.md.

Commit on the feature branch; attempt a normal push and draft PR targeting
main. If Git authentication fails, deliver exact committed source ZIP,
format-patch against pinned main, SHA256 manifest and logs for GPT-6 review.
The external delivery report records actual commit and publication outcome.
Do not merge or start a subsequent phase without owner authorization.

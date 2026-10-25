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

The complete suite now has 180 tests: the unchanged 68 Phase 1A tests,
24 independent 1X2 rows, 49 independent AH rows, and 39 numerical/integration
tests. The new fixture CSV bytes are preserved under `tests/fixtures/`.
Both adaptive and supplied fixed-cap results are checked against every row
at absolute tolerance 1e-9.

See [the Phase 1B implementation report](handoffs/CODEX_PHASE1B_IMPLEMENTATION_REPORT.md)
for research, licensing, numerical design, executed checks and limitations.

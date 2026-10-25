# PremFootballBot

Phase 1A is an offline Python library for exact Asian handicap settlement.
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

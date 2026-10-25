# CODEX_PHASE1A_IMPLEMENTATION_REPORT

- Date: 2026-10-24 (Asia/Bangkok)
- Scope: approved Phase 1A exact Asian handicap settlement library and tests
- Local branch: codex/phase1a-ah-settlement
- Base: ea9dbac2ed4f2d0db91b694c364b45d03665fe6c
- Repository: https://github.com/Sayrsoe/PremFootballBot

## Initial implementation result (historical)

Implemented a pure, standard-library Python settlement library with typed immutable results, strict inputs, signed integer quarter handicaps, exact Fraction payouts and fabricated tests. All 38 unittest test methods pass, including the 26 named golden cases exercised as subtests.

At the initial delivery, changes were local, uncommitted and not pushed. The approved review follow-up adds 30 independent regression cases and publishes the Phase 1A feature branch for PR review; see [the follow-up report](CODEX_PHASE1A_REVIEW_FOLLOWUP_REPORT.md). No merge into main, deployment or Phase 1B work is authorized.

## Repository review and authorization

Inspected the requested PremFootballBot-Connected checkout rather than the unrelated old empty folder. It was clean on main tracking origin/main, with origin https://github.com/Sayrsoe/PremFootballBot.git and the base commit above. Its only tracked files were AGENTS.md and the minimal README.md. No tests, package manager, linter, type checker, runtime dependencies or CI existed.

Read root AGENTS.md and applicable ancestor locations. Followed its research-first, minimal-dependency and honest-check requirements. Preserved AGENTS.md and all existing Git history. Created a new feature branch from the inspected main only after confirming the working tree was clean.

The current user instruction authorizes CODEX_IMPLEMENTATION_TASK.md. The matching approved handoff ZIP and VERIFIED_GOLDEN_CASES.md were read. The latter reports an independent 26-case mathematical check; that supplied claim is distinguished from the actual implementation tests run here. DeepSeek's independent-review task was not run, and no review result is presumed.

## Research, references and licensing

Reviewed CODEX_P1_RESEARCH_v1.1 materials and the prior exact golden table. Rechecked penaltyblog master: still 6870f0e762e9cba35fa722dc14a8daeaf8bc6134, the researched ref. Its license text was re-read and remains MIT at that snapshot.

Useful references, checked/reviewed 2026-10-24:
- [penaltyblog selected-side quarter handling](https://github.com/martineastwood/penaltyblog/blob/6870f0e762e9cba35fa722dc14a8daeaf8bc6134/penaltyblog/models/football_probability_grid.py#L252-L310).
- [Its AH tests](https://github.com/martineastwood/penaltyblog/blob/6870f0e762e9cba35fa722dc14a8daeaf8bc6134/test/test_football_probability_grid.py#L367-L478).
- [Its MIT license](https://github.com/martineastwood/penaltyblog/blob/6870f0e762e9cba35fa722dc14a8daeaf8bc6134/LICENCE).
- [Betfair's split-stake explanation](https://support.betfair.com/app/answers/detail/a_id/6418) and [Smarkets' independent explanation](https://help.smarkets.com/hc/en-gb/articles/115001324169-What-is-Asian-Handicap-betting), reviewed through the existing same-day research.

Adopted concepts: selected-side sign convention, equal quarter splits, separation of outcome from odds-dependent returns, independent fixed oracles and metamorphic invariants.

Rejected: using three averaged stake fractions as full-bet event probabilities; approximate float comparisons for quarter validation; broad scraper/model dependencies; copying the unlicensed comparison project's source; importing Poisson/DC features into this scope.

No third-party source was copied, cloned, vendored or installed. This is an independent implementation of the approved mathematical contract. No new project code license was chosen; a release/license decision remains with the owner. Software reference licenses do not grant rights to third-party football data.

## Changed files

| File | Purpose |
| --- | --- |
| .gitignore | Ignore Python caches and a local virtual environment |
| README.md | Source-checkout quick-start, API/conventions, exact return table and test command |
| premfootballbot/__init__.py | Public imports and export list |
| premfootballbot/settlement.py | Pure settlement, parsing, exact payouts and typed results |
| tests/__init__.py | Local test package |
| tests/golden_cases.py | Reusable G01–G26 fabricated oracles, derived before implementation |
| tests/test_settlement.py | Golden, boundary, validation, precision and invariant tests |
| handoffs/CODEX_PHASE1A_IMPLEMENTATION_REPORT.md | This implementation handoff |

No dependency manifest/build system was introduced: importing from the checkout and running unittest need no installation. Python 3.10+ is the documented syntax baseline; execution was verified on the bundled Python 3.12.14 only.

## Public API

Import these names from premfootballbot:

- Side = Literal["home", "away"].
- Outcome: FULL_WIN="FW", HALF_WIN="HW", PUSH="P", HALF_LOSS="HL", FULL_LOSS="FL".
- Settlement(outcome: Outcome): frozen result with outcome and exact Fraction attributes win, refund and loss. Fractions are derived from the enum, not caller-supplied.
- Payout: frozen returned record with odds, stake, net and gross as Fractions; net_per_unit and gross_per_unit are Fraction properties.
- parse_handicap(decimal_text: str) -> int.
- settle_handicap(home_goals: int, away_goals: int, side: Side, handicap_q: int) -> Settlement.
- calculate_payout(settlement: Settlement, *, decimal_odds: str, stake: str="1") -> Payout.

Outcome classification has no odds input. Payout amounts net/gross refer to the supplied stake. The default is one stake unit; explicit unit-return properties are available for scaled results.

### Exact example

```python
from fractions import Fraction
from premfootballbot import calculate_payout, parse_handicap, settle_handicap

settlement = settle_handicap(
    1, 1, side="home", handicap_q=parse_handicap("+0.25")
)
assert settlement.outcome.value == "HW"
assert settlement.win == Fraction(1, 2)
assert settlement.refund == Fraction(1, 2)
assert settlement.loss == 0

payout = calculate_payout(settlement, decimal_odds="1.90", stake="100")
assert payout.net == 45
assert payout.gross == 145
assert payout.net_per_unit == Fraction(9, 20)

tiny = calculate_payout(settlement, decimal_odds="1.90", stake="0.01")
assert tiny.net == Fraction("0.0045")
```

### Conservative input policy

Goals and handicap_q must be integers with bool rejected. Goals cannot be negative. Side values are case-sensitive and exactly home/away.

The optional handicap parser, odds and stake accept plain finite decimal strings only. Leading signs/zeroes and a leading decimal point are allowed. Floats, Decimal/Fraction objects, numeric coercion, whitespace, separators, exponent notation, rational text and trailing decimal points are rejected. Handicaps must be exact multiples of 0.25; odds must exceed 1; stake must exceed zero.

TypeError identifies invalid input types; ValueError identifies invalid values. Messages name the relevant field. Fractions are calculated from strings without Decimal arithmetic, so a changed Decimal precision cannot round a near-quarter into acceptance or alter a payout.

No minimum/maximum wager, currency precision, display formatting or rounding policy was invented. Administrative void rules are not modeled.

## Calculations

For even q, one full stake is classified by sign(4*d+q). For odd q, equal halves use q-1 and q+1; d is selected goals minus opponent goals. Integer half-stake counts map to FW/HW/P/HL/FL, then to exact fractions.

For winning/refunded/lost stake fractions w/r/l and decimal odds o:
- net per unit = w*(o-1)-l;
- gross per unit = w*o+r;
- w+r+l=1; net=gross-1.

The mathematical core performs no network/file access, model fitting or live integration.

## Executed validation

Working directory: the connected checkout, on the feature branch.

Actual interpreter:
C:\Users\arkr1\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe

Actual test invocation in PowerShell:

```powershell
& 'C:\Users\arkr1\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -B -m unittest discover -s tests -v
git diff --check
git diff --exit-code -- AGENTS.md
```

Portable equivalent for an available Python 3.10+ interpreter:

```console
python -B -m unittest discover -s tests -v
```

Results:
- Unit tests: **38 methods passed, OK**; all **26 G01–G26 golden subcases** matched category, win/refund/loss fractions, exact unit net and gross.
- Both-side explicit corrections passed: +0.75 losing by one = HL; +1.0 winning by one = FW; -0.75 winning by one = HW; -1.25 winning by one = HL.
- 100 stake at odds 1.90 passed for all categories: net +90/+45/0/-50/-100.
- 0.01 half-win at 1.90 passed with exact unrounded net 0.0045.
- Exhaustive small-domain tests include 1,800 settlements (goals 0–5, q -12–12, both sides) at three odds, label switching, opposite-side/line symmetry, monotonicity, equal-goal translation and quarter-component payout equivalence. Tests also cover parser/type/value failures, very large integers, immutability and low Decimal precision.
- README quick-start code was executed as written: **passed**.
- A separate provenance check parsed the original research Markdown table: **all 26 reusable records matched it exactly**.
- Whitespace verification over all seven source/test/README/ignore files passed. git diff --check passed after correction.
- AGENTS.md diff check passed; guidance was unchanged.
- No linter/type-check configuration existed, so none was installed or claimed as run.

The first unit run already passed all 38 tests, but git diff --check then flagged an extra blank line at README EOF. Final newline formatting was corrected in authored files; the suite and whitespace check were rerun successfully. Git also emits its existing LF/CRLF conversion warning; no Git line-ending configuration was changed.

## Integration instructions

Run imports/examples/tests from the repository root, or add the checkout to a consuming application's import path. Use the public imports above. Pass only completed regulation-time goals; the caller owns period selection and administrative result policy.

Normalize external handicap text once through parse_handicap; never confuse home-line signs with selected-side signs. Keep source validity, odds availability and cancellation handling outside the pure functions.

Serialize exact Fraction outputs as numerator/denominator pairs if another system needs them. Any future conversion to display decimals or currency rounding should be an explicit consumer policy, not an implicit float conversion inside this library.

The initial delivery had no PR or remote feature branch. The subsequent approved review follow-up commits and publishes these files together with the independent regression tests. Its final ZIP handoff records the resulting commit and PR URL for coordinator review.

## Limitations and next steps

No real data, bookmaker integrations, predictions, Poisson/DC, backtest, frontend, database, training, scraping, betting recommendation or deployment was added. Fixed fabricated tests establish settlement behavior, not predictive accuracy.

Only Python 3.12.14 was exercised; no multi-version CI, packaging/install workflow or static type-checker was configured. Arbitrary numeric input/resource caps remain a future interface-hardening decision; normal Python integer/string conversion limits apply. Direct construction of Payout is a passive record; use calculate_payout for validated computation.

A new DeepSeek review was not supplied or executed. Return this handoff and the implementation snapshot for coordinator review, reconcile any independent challenge cases, then obtain separate approval before merging main or expanding scope. Review can lead to fixes within this approved settlement scope.

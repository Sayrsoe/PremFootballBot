# Phase 1A review follow-up

- Date: 2026-10-24 (Asia/Bangkok)
- Branch: codex/phase1a-ah-settlement
- Scope: regression coverage and publication of the approved settlement implementation

## Changes

Preserved the 26 original golden cases and all production settlement code.
Added tests/fixtures/deepseek_30_regression_fixtures.csv exactly as supplied in
PremFootballBot_Phase1A_Review_Handoff_v1.1.zip. Added
tests/test_deepseek_regressions.py, exposing DS01-DS30 as 30 individually
discoverable unittest methods. Expected outcome and exact Fraction net/unit
come directly from the CSV, never from the implementation.

Fixture schema and the complete unique DS01-DS30 identifier set are checked
during discovery, preventing an empty or truncated fixture from passing.
Each case checks category, exact net/unit and gross/unit.

Updated README test documentation and marked the original implementation
handoff's publication state as historical. No unrelated files, dependencies,
settlement conventions or Phase 1B features were changed.

## Sources and independent comparison

Read START_HERE.md, CODEX_FOLLOWUP_TASK.md and REVIEW_FINDINGS.md from the review
ZIP, plus the original DeepSeek mathematical report available locally.
All 30 CSV rows match its source table exactly. No fixture was rejected.

CSV SHA-256:
267804a79360d8ab180b1dd9b78bac17039cb802e6c4a87807a9fa3f39bb9484

Review ZIP SHA-256:
A80B4BB330A008361698209ADC2BFE9DCB947B68F93011C508770575E136AAC3

No new broad GitHub research was needed: this is a bounded test/publication
follow-up using the already approved contract. Existing research references
and license notes remain in CODEX_PHASE1A_IMPLEMENTATION_REPORT.md. The supplied
fixtures are fabricated user-provided review data; no third-party implementation
was copied and no new source/data license was selected.

## Validation

Executed on Python 3.12.14:

    python -X utf8 -B -m unittest discover -s tests -v
    git diff --check
    git diff --exit-code -- AGENTS.md

Result: 68 test methods passed, including all 30 DeepSeek cases individually
and the unchanged 26 original golden subcases. No failed test, rejected
fixture or production defect was found. Exact 100-unit and tiny-stake returns,
input validation and exhaustive small-domain invariants continue to pass.

A final staged diff/whitespace check and exact file-scope review precede the
commit. The final external ZIP includes captured test output and publication
verification with the actual commit SHA and PR URL, obtained after this report
is committed.

## Contract and limits

The library remains standard-library-only and pure. Full-time regulation goals,
selected-side signed integer quarters, equal half-stake splitting, exact
Fraction returns and strict decimal-string inputs are unchanged. No currency
rounding, administrative void rules, real data, feeds, models or deployment.

One Python version was tested; no CI/multi-version matrix or linter was added.
The original DeepSeek report's broader bookmaker/convention suggestions are
not adopted as verified provider rules. No merge is authorized. The coordinator
and owner should review the PR before any merge or Phase 1B decision.

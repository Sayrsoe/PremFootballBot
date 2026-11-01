# Phase C1-C1 — invented-only provider contract/quarantine laboratory

**Owner approval:** Explicit approval in conversation dated 2026-11-01, limited to synthetic-only offline contracts, rights/provenance quarantine, fixture crosswalk, market-schema experiments, adversarial tests and a draft PR. **No merge authorization.** No extra instructions.

## Base and research decision

GitHub base `main`: `6da28b6c892394ebe4bb99e36bbeda83fefd2a9b`; source tree `6ff3cd38fe2c002979c0cb1cc2c6d28c23a9c851`, previously verified after merge of PR #20. Live refs must be reverified at PR creation/review time.

The C1-B research synthesis and independent architecture report were reviewed. The smallest architecture-preserving choice is to model completely invented provider input **outside** `provider_normalization_lab.py`, `odds_observations.py` and the C0 recorder. The design reuses the internal concept of pure functions, strict string-decimal values, domain-separated canonical SHA-256 and explicit structured denials; no outside provider data or third-party code was copied. No external packages were added.

## New files and their boundaries

- `premfootballbot/provider_contracts.py`: immutable invented envelopes; `toy:`/`https://example.invalid` gates; strictly bounded duplicate-key rejecting JSON; rejects all JSON numeric tokens and nonfinite constants in the string-only toy format; decoder/encoder nesting failures become coded denials; exact fractions/prices and integer quarter-goal units independent of ambient Decimal settings; SHA-256 source-byte binding.
- `premfootballbot/provider_quarantine.py`: immutable toy-only rights decisions with status UNKNOWN/BLOCKED/CLEARED and purpose-limited **simulated** permissions, predecessor digests, external-head replay, review/effective/expiry ordering, revocation and wrong-purpose denials. No real rights determination occurs, and a self-resealed whole chain is not independently authenticated without an external pinned head.
- `premfootballbot/fixture_crosswalk.py`: independently reviewed toy team mappings and exact fixture identity/kickoff/revision checks; no fuzzy or results-assisted matching, no automatic reschedule promotion; denied missing, reversed, noninjective or forged identity records.
- `premfootballbot/provider_schema_lab.py`: pinned toy market profile, complete 1X2 or selected-side signed-quarter AH, exact prices, one bookmaker/period/snapshot, rights and source digest checks, explicitly separated `source_observed_at_utc` and `snapshot_reviewed_at_utc`; preserves bookmaker/publication/archival timestamps as *claims*, not independent observations. Emits only `SIMULATED_ONLY_NOT_C0_OR_MODEL`. No C0 bridge, no market polling, no model use.
- `tests/test_provider_c1c1.py`: fully invented adversarial unit tests covering source rights and lineage, identity, AH signs/quarter arithmetic, cross-context precision, malformed deep JSON, timestamp gates, and protected module isolation.
- This implementation report: scope, evidence and limitations.

**Existing tracked files intentionally untouched:** C1-A module and tests, C0 recorder, odds/prospective/result modules, weighted Poisson/B2A/real-data modules, historical fixtures, holdout files, CI and governance. These protections must be verified by comparing full Git trees against the base before any merge.

## Local validation and limits

Development runtime: Python 3.13.5, a local **older B1 snapshot** augmented with current C1-A module/test copies. This is not the current complete GitHub `main` working tree.

- Focused: `python -B -m unittest tests.test_provider_c1c1 -v`: **86/86 passed** after the final hardened version.
- Targeted compatibility: `python -B -m unittest tests.test_provider_c1c1 tests.test_provider_normalization_lab tests.test_prospective_evidence tests.test_odds_evaluation tests.test_real_epl_isolation -q`: **244/244 passed**.
- `python -m compileall -q` over the five new Python files: **passed**.
- Full `unittest discover -s tests -v` on that older local snapshot exceeded its allotted run duration; **no full-local-suite success is claimed**. Only exact-head GitHub Actions Python 3.10/3.12 logs may establish the current complete repo result. CI **PENDING** until post-PR verification.

## Remaining limitations and independent-review challenge

All C1-C1 records are fabricated. Even a simulated `CLEARED` status and an apparently consistent timestamp remain operator inputs, not rights clearance, true bookmaker publication time, original source authenticity, genuine prospective collection or real account entitlements. The toy crosswalk assumes manually reviewed mapping; the output is ineligible for C0 and any historical/prospective model. A future bridge requires separate approval and a full provenance/rights model. No real data, credentials, provider endpoint, network, paid service, prediction, training, scoring, deployment or merge was used.

Review adversarially: forged/mismatched dataclass seals, decoding/encoding recursion, long strings, numeric types, Decimal context, artificially altered rights chain or revocation, missing/duplicate identity mapping, reversed HOME/AWAY, mismatched kickoff, mixed bookmakers, suspended markets, postcutoff acquisition and source observation versus snapshot review. Repeat exact protected-file Git blob identity, static imports and CI log checks. If anything fails, REQUEST CHANGES; do not waive findings merely because CI passes.

**Merge state: NOT MERGED.** Require independent acceptance of exact base/head/tree and separate owner squash-merge approval.

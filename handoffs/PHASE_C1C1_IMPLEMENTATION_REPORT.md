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

- Focused: `python -B -m unittest tests.test_provider_c1c1 -v`: **89/89 passed** after the final hardened version.
- Targeted compatibility: `python -B -m unittest tests.test_provider_c1c1 tests.test_provider_normalization_lab tests.test_prospective_evidence tests.test_odds_evaluation tests.test_real_epl_isolation -q`: **247/247 passed**.
- `python -m compileall -q` over the five new Python files: **passed**.
- Full `unittest discover -s tests -v` on that older local snapshot exceeded its allotted run duration; **no full-local-suite success is claimed**. Only exact-head GitHub Actions Python 3.10/3.12 logs may establish the current complete repo result. CI **PENDING** until post-PR verification.

## Pre-review adversarial follow-up (same approved scope)

Before independent review, a direct attempt to pass a dataclass with a forged `canonical_fixture_id="real:..."` through the new market laboratory exposed an unchecked in-memory fixture object boundary. The output was labeled synthetic but contained a non-toy canonical ID. `provider_schema_lab.normalize_invented_market` now replays the complete `fixture_crosswalk.make_fixture_revision` validation before reading payloads. Three permanent regressions cover forged canonical fixture ID, forged team identity and malformed source SHA. The final local test counts above include these corrections. The earlier draft-PR CI head is superseded by the repair head; fresh CI on the **updated exact tree** is required.

## Remaining limitations and independent-review challenge

All C1-C1 records are fabricated. Even a simulated `CLEARED` status and an apparently consistent timestamp remain operator inputs, not rights clearance, true bookmaker publication time, original source authenticity, genuine prospective collection or real account entitlements. The toy crosswalk assumes manually reviewed mapping; the output is ineligible for C0 and any historical/prospective model. A future bridge requires separate approval and a full provenance/rights model. No real data, credentials, provider endpoint, network, paid service, prediction, training, scoring, deployment or merge was used.

Review adversarially: forged/mismatched dataclass seals, decoding/encoding recursion, long strings, numeric types, Decimal context, artificially altered rights chain or revocation, missing/duplicate identity mapping, reversed HOME/AWAY, mismatched kickoff, mixed bookmakers, suspended markets, postcutoff acquisition and source observation versus snapshot review. Repeat exact protected-file Git blob identity, static imports and CI log checks. If anything fails, REQUEST CHANGES; do not waive findings merely because CI passes.

**Merge state: NOT MERGED.** Require independent acceptance of exact base/head/tree and separate owner squash-merge approval.

## Independent Codex audit P2 remediation — 2026-11-02

**Prior draft head:** `48a9533d1176109cb84f898413da4442c30cc153` at tree `fe9aaf11200ec0a739a20f132cd782ce6a34cd90`. The independent auditor returned **REQUEST CHANGES** with F1–F4; the earlier green 980/980 CI belongs only to that former head. Remediation is confined to C1-C1's own invented-only source/contracts/crosswalk/schema/test and this report. `main` and all 100 baseline file blobs remain out of scope.

- **F1 simulated rights at usage:** verify the **same externally pinned** purpose-specific rights chain at acquisition, capture and final snapshot review. Revocation, expiry and intervening temporary BLOCKED states now deny `MARKET_QUALIFICATION`. This does not grant genuine rights or authorize any downstream model/C0 use.
- **F2 reviewed fixture identity:** the market entry now requires a separately pinned `ReviewedFixtureBinding` containing both invented provider fixture revisions, full HOME/AWAY identities, reviewed explicit crosswalks, schedule revision, source digests and reviewer. Creation calls `match_fixture_revisions`; verification replays the complete source and team crosswalks, validates the expected external digest, and compares the supplied fixture against the pinned primary revision. The envelope binds the approval digest, and normalized invented output retains its digest and both team IDs. Simply hashing replacement `toy:` metadata inside normalization is insufficient. **Trust limit:** the pinned hash must actually be retained outside the untrusted request; a fabricated, entirely re-sealed toy world with a substituted external pin remains a caller-assurance limitation, not real identity certification.
- **F3 explicit freshness:** policy `C1C1_TOY_REVIEW_900_SECONDS_V1` requires source observation and any present provider-update claim to be no older than 900 seconds at the snapshot review. Synthetic bound only, **not empirically validated** for real EPL providers. Historical creation/bookmaker publication claims are not independently proved by this policy.
- **F4 forged `raw_length`:** validate exact ASCII positive decimal text, prohibit leading zeros and bound its digit count to `len(str(MAX_BYTES))` **before** conversion to an integer. Oversized numeric strings (including 5,000 digits) produce `FORGED_ENVELOPE`, not bare `ValueError`.

Fourteen added permanent test methods cover revocations/expiry at different stages, valid-toy identity/orientation substitution, pinned binding tampering and crosswalk replay, exact 900/901-second freshness boundaries, and long/invalid length lexemes. The focused test count is now **103**, subject to fresh independent CI on the exact new head. Do not claim previous-head GitHub CI as validation of the changes.

**Local testing reality:** The repair workspace contains exact C1-C1 Git source from the initial handoff, and the read-only C1-A normalizer from the earlier audited handoff; it does not contain the full protected C0/evidence/odds modules. Running the 103 focused tests with *test-only in-memory stand-ins* for the two missing protected imports passed 103/103 on local CPython 3.13. This validates the C1-C1 pure functions and confirms no calls to these stubs, but is **not** an exact current-repository full-suite result or proof of real protected integrations. The unchanged C1-C1 unit test which patches the actual protected modules must run against full GitHub CI as the decisive check.

**New head/tree and Python 3.10/3.12 CI:** must be recorded after GitHub publication and actual log inspection. The draft PR stays **unmerged**. Obtain a new read-only independent audit and separate exact-head owner approval before any squash merge. No provider network, credentials, genuine data, fitting, predictions, spending or deployment were used.

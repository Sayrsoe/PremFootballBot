# Phase 4C2-B2A — source-backed read-only development training boundary

## Authority and scope

The owner approved **B2A implementation and a draft PR only** after the proposed task allocation on 2026-10-31. This is a boundary-validation milestone, not approval to train or evaluate a weighted model on historical EPL outcomes. No real-data model fitting, outcome scoring, candidate selection, market bets, deployment, paid services or merge is authorized.

Starting repository: `Sayrsoe/PremFootballBot`, `main` at
`bf79766ea8f356a7b68864c772b2314f8dc102c1`, tree
`bc962b2e7ec89aa6cafb02ac6e111a6c872b36ca`. The owner-approved PR #16 weighted numerical engine, PR #15 CI, and PR #17 engineering workflow remain intact.

## Repository and external reference review

Inspected the actual C1 `chronological_candidates.py` source-backed protocol, C2-A `retrospective_candidates.py` training-only support join, completed OpenFootball pinned EPL source and C2-B1 `weighted_poisson.py` invented-only interface, relevant tests and the approved prior handoffs. Also checked pinned GitHub references for [skforecast chronological model selection](https://github.com/skforecast/skforecast/tree/3ecc0dc3d251c313b08ce26a572d17a2ace022c/skforecast/model_selection) (BSD-3-Clause) and [penaltyblog model implementations](https://github.com/martineastwood/penaltyblog/tree/6870f0e762e9cba35fa722dc14a8daeaf8bc6134/penaltyblog/models) (MIT). Adopted only the design principles of explicit temporal boundaries, training-versus-target separation and no unapproved refitting; **no third-party code copied or dependencies added**. Neither a code license nor an archive checksum establishes football-data correctness or historic publication timing.

## New API and data contract

One new module: `premfootballbot/weighted_fold_boundary.py`:

- `build_training_boundary(protocol, dataset, inputs, *, license_bytes) -> TrainingBoundary` verifies the exact raw source/LICENSE through C1 replay **before** joining selected training outcomes.
- `boundary_json(boundary) -> bytes` validates typed immutable structure and sealed identities, but is **not** a source-authentication shortcut.
- `verify_training_boundary(boundary, protocol, dataset, inputs, *, license_bytes) -> bool` repeats source-backed construction and canonical-byte comparison, rejecting even internally re-sealed source forgeries.
- Private `_assemble` and `_observation` are pure test oracles, **not** public source-authorizing entry points.
- Each `TrainingObservation` contains the C1 canonical source-backed fixture reference, authenticated FT90 **training** goals, and explicit `age_days = (target_date - training_match_date).days`. Target entries retain only C1 `TargetAudit` fixture identities/category/reason, never target result labels or model probabilities.
- Every fold records the selected training population, cutoff, history status and separate training-ID/training-label digests. Artifacts contain source/dataset/protocol identifiers, 2024 development / 2025 exposed boundary, label-free target count, retrospective timing disclaimers, and permanently-false `real_fitting_authorized`, `scoring_authorized` and `candidate_selection_authorized` flags.

The public path accepts exactly the existing pinned OpenFootball two-season source identity; 2024–25 development dates only, ≥100 selected training matches for sufficient-history status, ≥2 calendar-day embargo. Future/embargo/target/2025–26 result labels and rosters do not contribute to constructed training observations. Unknown or corrupt input fails closed; missing history remains explicitly insufficient rather than creating a fit.

**Crucial numerical security boundary:** This does **not** transform historical rows into B1's `toy:` `InventedMatch` objects. The B1 fitter and all existing real, synthetic, prospective, shadow, odds and historical scoring APIs remain unchanged. Exposing a typed, retrospective training manifest is not authorization for an external caller to train a model.

## Verification performed and limitations

- New focused tests: **22/22 passed**, local CPython **3.13.5**, command `python -B -m unittest tests.test_weighted_fold_boundary -v`.
- Full suite **by independent test module**: **803/803 passed, zero failed across 24 modules**, each run as `python -B -m unittest tests.test_<module> -v`; 4 concurrent workers, with isolated interpreters. Includes old B1, C1, C2-A and all existing tests. This is NOT a claim that the combined single-interpreter full-suite command passed.
- Single-process `python -B -m unittest discover -s tests -v` did not finish within the local execution limit. Reported as a **timeout / no final result**, not a pass or a model failure. GitHub Actions Python 3.10 and 3.12 results must be checked separately on the PR's exact head.
- Module Python 3.10 grammar parse succeeded; grammar compatibility is not a separate Python 3.10 runtime test.
- Source-backed replay; 109 complete 2024-development target date groups and exactly 380 label-free targets; exact cutoff/age oracle; D−2 included and D−1 excluded; 100-history minimum; source/license tampering; fake C1 identity; forged re-sealed observations and target omission; altered excluded/future/holdout labels and rosters; no fitting invocation; immutable/sealed artifacts; false timing/authorization flags.
- Existing code, fixture bytes, model authorizations and pinned source manifests are unchanged; README update, new module, dedicated tests and this report are the only intended files.

**Interpretation:** this is retrospective date-level reconstruction using a permitted CC0 source snapshot. It is NOT evidence that the match results were published before each historical cutoff. SHA digests are local consistency checks, not signatures or proof of historical availability. The existing 2025–26 exposed holdout remains unsuitable for candidate selection. No forecast, accuracy, calibration, ROI or profitability is claimed.

## Independent review and next owner gate

Check the exact PR/head/tree and diff against the baseline; ensure no outside modules or raw evidence were changed. Verify both GitHub CI jobs and if they fail, report honestly and obtain approval for any code fix. Reperform source/age/target-label isolation checks and inspect that no public real-data numeric fitter or `toy:` relabeling path was added. The review materials are this report, tests and PR diff, all on GitHub; no ZIP required.

**Keep PR as draft. No merge without separate exact-head owner authorization.** Phase 4C2-B2B real-data fitting, scoring, parameter selection, prospective feed integration and deployment remain outside authorization.

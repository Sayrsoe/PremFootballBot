# Phase4C1 chronological protocol/fold audit implementation

## Authority and verified starting point

Read START_HERE, OWNER_APPROVAL, PROJECT_CONTROL, PROMPT_FOR_CODEX and all
accompanying requirements, current AGENTS/README, Phase4A/4B handoffs, completed
source parser, chronology, protected model/synthetic/backtest/evidence modules
and relevant tests. Input manifest9 entries verified. Owner authorizes only
offline non-training protocol/fold auditing and draft PR; earlier planning-only
wording does not require a second approval for this scope.

Remote/local main973434cf4f5551bbb53caa9f2712e0ae7366c2fc,
tree69ee9e7a5ec82d1a36f3f5562926c2c32bacaba2 matched before edits. Branch
codex/phase4c1-chronological-protocol. Baseline679 tests passed11.083s on
Windows CPython3.12.14. Budget฿0; no new dependency, subagent, source or provider.

**NO NEW MODEL FITTING OR OUTCOME SCORING. NO PROSPECTIVE VALIDITY CLAIM.**
No trainer, optimizer, forecast, scorer, bootstrap or random generator is called
by the new code or targeted tests. The required unchanged full suite includes
old training/scoring fixture regressions; running those is not a new experiment
or permission to alter their pathways. No model/parameter search, live API,
credentials, odds, current-season import, public predictions, merge or deployment.

## Research completed before implementation

- [skforecast](https://github.com/skforecast/skforecast/tree/3ecc0dc3d251c313b08ce26a572d17a2ace022c4),
  current main3ecc0dc3d251c313b08ce26a572d17a2ace022c4, BSD3 LICENSE,
  model_selection/_split.py and tests/tests_split/test_timeseriesfold.py
  inspected again. Adopted explicit split/gap validation, immutable audit intent
  and offset-bound tests. Rejected row-count gaps, automatic refits, search,
  overlapping selections and pandas/NumPy/runtime dependencies. Our gap is whole
  calendar days, not sample count.
- [goalmodel](https://github.com/opisthokonta/goalmodel/tree/84ecd6c2bbad3ccb967abf88ef49e5bcd074e545),
  current master84ecd6c2bbad3ccb967abf88ef49e5bcd074e545, DESCRIPTIONv0.6.4
  GPL3, R/goalmodel_predict.R and tests/testthat/test_1.R inspected. Useful
  team-name/identity parity, duplicate/nonfinite checks and explicit model/data
  separation. No numerical model, automatic covariate default, ratings or GPL
  source copied; no R dependencies/external executable code installed or run.

Repo revisions matched the earlier inspected research snapshots. Freshness of a
Git repository is not historical publication evidence. External research only
informs independently implemented validation patterns; no new licensing exposure
from copied code or dependencies. Pre-code design note is in review evidence.

## Minimal architecture and contracts

New premfootballbot/chronological_candidates.py only. Public API:

    ProtocolPolicy(...)
    build_protocol(dataset, inputs, *, license_bytes, target_dates, policy=ProtocolPolicy())
    protocol_json(protocol) -> canonical UTF8 bytes
    verify_protocol(protocol, dataset, inputs, *, license_bytes) -> True

build_protocol WRAPS the approved chronological_epl.development_folds without
changing its code. That function first source-replays the completed dataset and
license, then selects2024 date groups with calendar embargo. No numeric route
is used. Typed policy accepts only embargo2..366 days and minimum history1..380;
all other governance fields have fixed approved values. Default minimum100 is a
predeclared engineering protocol threshold, not learned/tuned or a claim of
sufficient statistical power. No model candidates or parameter grid are executed.

Policy fixes source seasons(2024,2025), selection season(2024), exposed(2025),
DEVELOPMENT_ONLY_NO_HOLDOUT_SELECTION and EXPOSED_HOLDOUT_NOT_CONFIRMATORY.
Benchmarks ABSTAIN_CONTROL/TRAINING_CLASS_FREQUENCY/FIXED_RIDGE4_REFERENCE are
names for future comparison, not newly fitted models. Prior-only behavior is
reserved, not implemented. Paired common-fixture evaluation plus all-target
denominators, established/prior/abstained/failure segments, unscaled Brier,
natural log loss, classwise calibration, later label join and paired descriptive
date-cluster uncertainty seed4042026/replications4000 are typed placeholders.
No scoring/bootstrap/randomness occurs; executing future work needs approval.

CandidateProtocol preserves version, exact dataset/source identities (including
acquisition/license evidence), alias/profile fingerprints, policy, frozen folds,
explicit exposure, warnings, execution_status=PROTOCOL_ONLY_NOT_EXECUTED and seal.
Each sealed FoldDefinition records target/maximum training date, embargo, training
FixtureReferences, TargetAudit references, training-only team population,
minimum-history status and exclusion reason counts. FixtureReference records
ID/season/date/canonical teams/source hash only: NO GOAL LABELS or metrics.
All nested containers returned are immutable tuples/frozen dataclasses.

Targets are every source fixture on a chosen development date, never a selected
subset. Target date tuple must be explicit, unique, nonempty and<=380; not UTC
datetimes, strings or2025-season holdout dates. Training is exactly the existing
selector's2024 IDs with date<=target-embargo. All target/D-1/future and holdout
rows are excluded regardless of input order or nominal matchweek. Source-aware
parsing/replay detects duplicate/spoofed fixtures, aliases and raw-byte changes.

Training team population is computed ONLY from eligible training references.
No future roster, target roster, goal labels, class frequencies, feature values,
priors or normalizers enter it. Target identity is used only to flag missing
history, not add a training team. With insufficient history or unseen team the
control audit says NO_PREDICTION and stable reason; otherwise ESTABLISHED_HISTORY
with HISTORY_ONLY_NO_EXECUTION. No prediction or fallback prior is produced.

Exclusion reason inventory: TARGET_DATE, EMBARGO, FUTURE_DEVELOPMENT and
EXPOSED_HOLDOUT_RESERVED. Training count+all exclusions equals760 for each
verified-source fold. Source validation necessarily parses all approved facts
for integrity; this is not access to labels for candidate selection or scoring.
No holdout fixture is a selection target. Attempts to relabel it untouched or
add it to selection, metrics/benchmark changes or an executable phase are rejected.

Every relevant output keeps status
RETROSPECTIVE_DATE_LEVEL_SIMULATION_NOT_EX_ANTE_VERIFIED,
historical_available_at=None, kickoff_utc=None, strict_point_in_time_eligible=False.
No date is converted to kickoff or result publication UTC. Archive acquisition,
checksum and a2-day proxy do not certify availability or correction timing.
2025–26 is explicitly exposed after prior Phase4B; no new confirmatory claim.

## Integrity and threat boundary

Canonical JSON uses existing sorted-key/no-NaN encoder and SHA256. Fold and
protocol seals cover policy, references and audit fields. Serialization checks
typed shape, immutable containers, temporal/disclaimer rules, source-hash shape,
unique dates/IDs, target/train disjointness, nested seals, date limits and
history-only population/categories. No untrusted JSON loader is exposed: dicts,
bytes, duplicate-key JSON or deserialized payloads are not trusted typed objects.
ProtocolError has code PROTOCOL_INVALID; source/selector exceptions preserve
their existing failure types/reasons. Output reason strings are machine-readable.

Checksums are not signatures and do not prevent malicious re-sealing. Consumers
must call verify_protocol with original bytes/license: it rebuilds the protocol
through source-backed selector replay and compares exact canonical bytes. This
rejects re-sealed team/ID/partial-date/exclusion/governance alterations. Changing
an allowed embargo/min-history policy intentionally defines a NEW protocol hash;
it is not an authorization to execute or optimize that protocol.
No hidden wall clock, file/network access, global mutation, RNG, goals/metrics
or numeric fitting dependency is invoked by the new core.

## Source and license audit

Existing pinned OpenFootball commit9ee7a0c351805c99cc334478a9bf04b7d0432fec;
2024-25 blobca0fe4923f0164d0f879f796ab0759253e13bc06,
SHA256e39716b01af0c8654a9fae7b5555e6b02f506ea05239e0d0eef41936ba80e1e3;
2025-26 blob918adf1c0af4f613c73530cb528ab0df72461cfb,
SHA25638c1de56c9e9b6662c7efc1420b7e1fe00dddbb502fe72d8f759e773ba3c093b.
CC0-1.0 license blob670154e3538863b2d9891fd5483160fbdfc89164,
SHA25636ffd9dc085d529a7e60e1276d73ae5a030b020313e6c5408593a6ae2af39673.
Two380-result profiles remain unchanged; no2023 normalization or2026 source.
CC0 statement is not factual-accuracy/third-party-rights certification. No source
retrieval or acquisition timestamp was invented or backdated in this phase.

## Executable offline example (NO FITTING/SCORING)

```python
from datetime import date
from tests.test_completed_epl import inputs, FIXTURE
from premfootballbot.completed_epl import import_completed_epl
from premfootballbot.chronological_candidates import build_protocol, protocol_json, verify_protocol

sources = inputs()
license_bytes = (FIXTURE / "LICENSE.md").read_bytes()
dataset = import_completed_epl(sources, license_bytes=license_bytes)
protocol = build_protocol(dataset, sources, license_bytes=license_bytes,
    target_dates=(date(2024, 12, 26), date(2025, 1, 1), date(2025, 3, 8)))
assert verify_protocol(protocol, dataset, sources, license_bytes=license_bytes)
canonical_bytes = protocol_json(protocol)
```

At default policy/recorded source identity, protocol digest
2a2fd9e127e7aa44780e33ed1e5ee598f3562d21f6fdf14834e08b6cafa4220a.
Example counts: Dec26 training169/targets8; Jan1 training188/targets1;
Mar8 training271/targets6. Every fold excludes380 exposed holdout fixtures.
These are dataset/protocol counts, not outcomes, predictions or model metrics.

## Tests, protected files and independent-review gate

Baseline679 passed11.083s. Initial25 new tests passed2.429s; added year-boundary,
future-score/roster poison and real D-1 checks. Final suite707 tests (679 existing
+28 new), commands `python -B -m unittest tests.test_chronological_candidates -v`
and `python -B -m unittest discover -s tests -v`. Final committed-export actual
counts/timings and logs are in review ZIP. Existing regressions are unchanged.
No Linux/3.13 runtime, remote CI, new model experiment or linter/type checker
execution claimed.3.10 grammar and exact-source/protected-file checks supplied.

Manual invented5-row oracle reasons through D-2 inclusion, D-1 exclusion, whole
same-day grouping, future exclusion and unseen-team control without any labels.
Public full-archive tests exercise replay, policy/governance, source/license/
revision tampering, duplicate dates/IDs, team spoofing, resealed manifests,
serialization, input ordering, rescheduled rounds, no outcomes/metrics and
same/future-day population invariance. Call-denial mocks cover all numeric,
forecast/scoring/bootstrap/network/I/O routes; new-core AST rejects label/time/RNG
access. Old model-authorization, synthetic and prospective tests still pass.

Changed files: README.md; premfootballbot/chronological_candidates.py;
tests/test_chronological_candidates.py; this handoff. No prior source/test/fixture,
model authorization or Trial1 changed. Exact head/tree/base, full manifest,
patch reconstruction, protocol output and source-only ZIP are delivered outside
the commit. Review package includes START_HERE.md and a complete review report.

No known local implementation failure. Remaining limits: archive facts are not
historical availability, policy choices are not validated models, data are only
two approved seasons, and exposed2025–26 cannot become fresh confirmatory data.
Please independently review source, exclusions, population isolation, typed
governance and replay before separate owner merge approval. Keep draft; no4C2/4C3.
**NO NEW MODEL FITTING OR OUTCOME SCORING. NO PROSPECTIVE VALIDITY CLAIM.**

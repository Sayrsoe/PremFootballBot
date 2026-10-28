# Phase 3B Scope A implementation handoff — 2026-10-28

EXPLORATORY ONLY / NO POINT-IN-TIME CERTIFICATION.

## Scope and repository inspection

Implemented a pure offline OpenFootball EPL archive adapter, separate from every
synthetic ingestion, estimation and backtesting path. No real model was fitted,
evaluated or forecast; no odds, provider/API calls, credentials, dependencies,
payments or Phase 3C/3D work. Budget used: ฿0. Publication is a draft feature PR
only; merge and any subsequent integration require separate owner approval.

All execution-package instructions and both reference-verification documents
were read. The old research-only approval status is superseded only within the
owner's expressly approved Scope A. Main was fetched and matched
`272ad0463b077f15b3476b8b4330a743ed3d4bcc`, tree
`b75d3bda7b478730139280aa1b8e98906a0458c7`. Reviewed AGENTS.md, README,
source/test structure, all relevant prior APIs, dependency conventions and recent
commits. Branch: `codex/phase3b-scopea-openfootball-exploratory`, created from
that main. Protected source, exports, existing tests/fixtures, CI/config and
AGENTS.md are unchanged. No configured lint/type-check tool or CI was found.

## Research and design checkpoint, completed before implementation

- [OpenFootball England](https://github.com/openfootball/england/tree/9ee7a0c351805c99cc334478a9bf04b7d0432fec)
  at `9ee7a0c351805c99cc334478a9bf04b7d0432fec`: inspected both authorized
  season files and [CC0 LICENSE.md](https://github.com/openfootball/england/blob/9ee7a0c351805c99cc334478a9bf04b7d0432fec/LICENSE.md),
  independently checked exact Git blob hashes on supplied base64-decoded bytes.
  CC0 applies to this source, not unapproved providers; the license includes
  accuracy/third-party-rights disclaimers. No data is redistributed in bulk.
- [Yetric football-txt-parser](https://github.com/yetric/football-txt-parser/tree/69a85c64af37ea1f29107a629774c725b37fd5ed)
  at `69a85c64af37ea1f29107a629774c725b37fd5ed` (July 2026): read README,
  [MIT LICENSE](https://github.com/yetric/football-txt-parser/blob/69a85c64af37ea1f29107a629774c725b37fd5ed/LICENSE),
  package.json, [src/parser.ts](https://github.com/yetric/football-txt-parser/blob/69a85c64af37ea1f29107a629774c725b37fd5ed/src/parser.ts)
  and [test/parser.test.ts](https://github.com/yetric/football-txt-parser/blob/69a85c64af37ea1f29107a629774c725b37fd5ed/test/parser.test.ts).
  Repository search found relevant maintained parsing work; issue search returned
  no issues. Adopted header/match separation and invented layout/rollover tests.
  Rejected default noon, unconditional UTC `Z`, fuzzy aliases, silent skips,
  broad cup grammars and computed standings. No code copied, installed or run;
  MIT patterns inform an independent stdlib implementation, without dependencies.

The separate pre-code DESIGN_BEFORE_IMPLEMENTATION.md is in the review evidence
bundle. Planned signatures were retained; added `target_fixture_id` for explicit
self-exclusion and a sealed JSON serializer. Profiles are deliberately restricted
to the two inspected seasons rather than guessing team rosters for other years.
The pinned 2023 file is score-centered; v-separated support is an additional
tested grammar, not a claim that the pinned sample contains v rows.

## API and data contract

Direct imports only from `premfootballbot.openfootball_exploratory`:

```python
parse_openfootball_epl(raw_bytes: bytes, *, source: OpenFootballSource) -> ExploratoryImport
summarize_exploratory_coverage(imported: ExploratoryImport) -> ExploratoryCoverage
select_exploratory_prior_dates(imported: ExploratoryImport, target_date: date, *,
    embargo_calendar_days: int = 2, target_fixture_id: str | None = None) -> ExploratoryDateCandidates
exploratory_json(value) -> bytes
```

Frozen dataclasses: OpenFootballSource, ExploratoryMatch, QuarantinedRow,
ExploratoryImport, ExploratoryCoverage, ExploratoryCandidate,
ExploratoryDateCandidates. Source requires canonical repository, immutable full
lowercase commit/blob/SHA256, exact supported path, CC0 ID, checked license blob,
canonical evidence URL at the same commit and caller-recorded aware retrieval.
Retrieval normalizes to UTC solely as an acquisition event.

Atomic `OpenFootballError.code` values: SOURCE_TYPE, REPOSITORY, SOURCE_HASH,
SOURCE_PATH, LICENCE, RETRIEVAL, INPUT_TYPE, INPUT_SIZE, SHA256_MISMATCH,
GIT_BLOB_MISMATCH, ENCODING, TEXT_CONTROL, TEXT_BOUNDS, DOCUMENT_TITLE,
SECTION_HEADER; consumer boundaries also use SNAPSHOT_TAMPERED, TARGET_DATE,
TARGET_ID and EMBARGO. Nothing is partially returned on document failure.

Line-level reasons: MISSING_DATE, AMBIGUOUS_DATE, INVALID_DATE, SEASON_DATE,
WEEKDAY_MISMATCH, UNRECOGNIZED_DATE_CONTEXT, NOT_FINISHED_FT90,
UNRECOGNIZED_ROW, TEAM_IDENTITY, INVALID_CLOCK, HALFTIME_EXCEEDS_FT90,
UNVERIFIED_ANNOTATION and REPEATED_PAIR_IDENTITY. Header issues are separately
counted; accepted+quarantined exactly equals the match-like scan denominator.

Source bounds: 1 byte..4MiB, <=20,000 lines, <=2,048 characters per line.
Strict UTF8, optional initial BOM, LF/CRLF, no embedded BOM/control separators;
hashes always use exact original bytes. One exact matching season title is
mandatory. EPL team/match counts20/380 are diagnostic expectations only.

The parser has two anchored grammars: optional HH:MM + home + FT score + optional
HT + away; optional HH:MM + home v away + FT score + optional HT. FT90 integer
goals0..99; HT never replaces FT and cannot exceed either FT side. Explicit raw
team labels come from the inspected20-team season profiles; no automatic alias
normalization. Indented scorer-parenthesis blocks are ignored as annotations;
status/unknown annotation text conservatively invalidates the preceding result.
Postponed, awarded, abandoned, cancelled, suspended, extra-time and penalty
variants are not accepted as FT90.

Headers use abbreviated month + day, optional weekday and year. Years derive
from a fixed July–June season window: July..December=start year,
January..June=following year. Explicit year and weekday must agree. This yields
one date without a row-order-dependent rollover heuristic. Unsupported/invalid
headers reset date context; round headers also reset it. Unknown formats are
quarantined, never assigned the last valid date by accident.

Internal fixture identity hashes season plus ordered raw home/away labels, with
no claim of official match IDs. Raw line/header references and immutable-commit
locators retain audit traceability. All repeated ordered pairs, even identical
copies or changed-date/status/malformed counterparts with recognizable teams,
invalidate their parsed results. Reverse home/away is a separate identity.
Without official IDs, a completely changed team label cannot establish a
historical revision chain; no original archive state is reconstructed.

## Temporal separation and reproducibility

All real outputs carry NON_SYNTHETIC_REAL_ARCHIVE,
EXPLORATORY_DATE_LEVEL_RECONSTRUCTION and EXPLORATORY_ONLY. Strict eligibility
is false/count0. Every row's `kickoff_utc` and `historical_available_at` is None,
and clock timezone is UNKNOWN. Printed clocks are text only. Source timestamps,
Git history and final scores do not prove historical publication or ex-ante
fixture declarations. No synthetic conversion/export interface is provided.

Candidate selection requires a calendar date (not datetime/unknown), whole-day
embargo2..36600, excludes explicit target ID, and keeps only dates<=D-embargo.
This is a HYPOTHETICAL retrospective convention, not evidence that the rows were
known before a match. It neither trains nor evaluates anything.

Canonical candidate rows omit mutable file SHA/blob/commit/retrieval/line
positions; their digest covers selected facts, stable repository/path/license,
target date/ID, embargo and normalizer version. Therefore nonconflicting future
append/poison, retrieval changes and row reordering preserve earlier candidate
bytes. Changed earlier facts or newly observed duplicates/corrections can
invalidate them and legitimately change this digest. Cross-season files cannot
be concatenated/imported as one profile. Full source/import/coverage hashes
include complete provenance and audit locators, and change with raw bytes.

SHA256 snapshots detect accidental content changes, not malicious re-signing.
The offline parser validates pins against caller assertions; it cannot
authenticate their remote commit-tree membership or the truth of a result.
For the two audits below this membership/blob evidence was independently read
through GitHub. Callers must do that verification for any other snapshot.
`NORMALIZER_SHA256` is a grammar/profile/policy fingerprint, not the whole Python
file hash. Exact implementation file hashes are in the delivery manifest.

## Independent pinned sample audits (no real model calls)

Acquisition context recorded2026-10-28T09:58:02Z; explicitly not match availability.
Only the two approved source samples and license were inspected; full datasets
are excluded from Git and the review bundle. SOURCE_AUDIT.json in that bundle
keeps coverage, quarantine arrays and three representative source-line checks.

| Profile | Git blob | Raw SHA256 | score-pattern rows | accepted/quarantined | printed/missing clocks |
|---|---|---|---:|---:|---:|
|2023-24|23cdd8a340b72f6f30c514fbf609d5cf252723aa|0bfb4a7fffe0b1bf7318955686eafeb28fc9676346ae433259e7409d69551450|380|380/0|235/145|
|2025-26|918adf1c0af4f613c73530cb528ab0df72461cfb|38c1de56c9e9b6662c7efc1420b7e1fe00dddbb502fe72d8f759e773ba3c093b|380|380/0|380/0|

Both use upstream commit9ee7a0c351805c99cc334478a9bf04b7d0432fec, CC0 license
blob670154e3538863b2d9891fd5483160fbdfc89164. Scan totals: 2023=638 lines,
258 ignored+380 match-like; 2025=1099 lines,719 ignored+380 match-like. No
header issues or quarantine reasons in either specific pinned sample. Strict
point-in-time eligible count0 for both; coverage is not a factual accuracy audit.

Independent score-row pattern counts agreed with380, and source lines were
spot-checked separately: 2023 L11 Burnley0-3 Manchester City onAug11,
L317 Crystal Palace3-1 Brentford onDec30, L634 Crystal Palace5-0 Aston Villa
onMay19; 2025 L10 Liverpool4-2 Bournemouth onAug15, L556 Brighton2-0 Burnley
onJan3, L1094 West Ham3-0 Leeds onMay24. Raw labels retain their source suffixes.
The check does not independently adjudicate the official truth of those scores.

Semantic source digests (canonical accepted facts, excluding provenance changes):
- 2023: ac1a691aa44cfb154d6c396934932c96c3eba2d87b1b104a28c7364cdbbb9700
- 2025: 3a2e917b6668a0180853597ed68cf658fc260c8f39b645b1ce5e8b66045ce7fa

## Actual executed tests and review evidence

Environment: Windows, Python3.12.14. PYTHONDONTWRITEBYTECODE=1 for unittest runs.
- Baseline, before edits: `python -m unittest discover -s tests -v`:363 passed,
  1.751s, zero failures/errors.
- New tests initially53 passed. Added two conservative date/annotation guards;
  the new standalone award test exposed bracketed-note classification. Corrected
  it in the new module. The intermediate55-test run had1 failure; this is resolved.
- Final complete suite: `python -m unittest discover -s tests -v`:418 passed,
  1.916s, zero failures/errors:363 unchanged+37 new parser/rights/report cases
  +18 temporal/boundary cases. Full verbose evidence is delivered.
- Targeted `python -m unittest tests.test_openfootball_exploratory_leakage -v`:
  18 passed in0.028s, zero failures/errors.
- `git diff --check`:passed. Scope checked against the exact baseline; only
  allowed paths changed, no dependency/config/source dataset added.
- All24 Python files parsed with Python3.10 grammar via ast.parse; Python3.10
  runtime was NOT run. No lint/type-check/remote CI execution is claimed.

Tests cover both layouts, HT/FT/zero/bounds, raw labels and clocks, missing clock,
rollover/weekday/unknown date resets, rounds1/38, annotations, team spoofing,
duplicate/corrected/rescheduled/status fixtures, BOM/CRLF/UTF8/control/bounds,
source path/repo/commit/hash/license/retrieval failures, complete denominators,
immutable snapshots, tampering and deterministic semantic/JSON outputs.

Adversarial tests cover D-2 candidate-only, D-1/D/D+1 exclusion, invalid embargo,
unknown target/date underflow, target self-exclusion, future-score poison/append,
other-season rows, reordering, late retrieval, correction conflicts, synthetic
source/target gates, fitter/backtester rejection of real dataclasses before any
fit, pure-import/call boundaries, and frozen source fingerprints of all six
protected Python modules. Test snippets are explicitly INVENTED; team labels
come from profiles, invented scores are not presented as historical fixtures.

## Exact changed files and continuation contract

1. README.md — offline example, source/data boundaries and limitations.
2. premfootballbot/openfootball_exploratory.py — isolated new parser and reports.
3. tests/test_openfootball_exploratory.py — invented parser/provenance cases.
4. tests/test_openfootball_exploratory_leakage.py — temporal/boundary regressions.
5. handoffs/CODEX_PHASE3B_SCOPEA_IMPLEMENTATION_REPORT.md — this handoff.

There are no application call sites; only tests and the explicit README offline
example import the new API. The exact published head/tree/base, changed-file
hashes and PR draft/unmerged evidence are in the separate delivery manifest
(self-referential commit hashes cannot be embedded in their own commit).

Next agent: independently review the draft at its exact head/tree, rerun the
418 tests, inspect rights and timestamp assumptions, verify protected paths
unchanged and candidate digest sensitivity. Keep data types separate and never
relabel real archives synthetic. No merge/ready transition is authorized.
Additional seasons, provider access, real-data model integration, strict
historical certification and all Phase3C/3D work need separate owner approval.
No unresolved implementation test failures; the source authenticity and
historical-timestamp limitations above remain explicitly unsupported.

Request independent GPT-6 review before the owner separately approves any merge.

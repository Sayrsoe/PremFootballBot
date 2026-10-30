# Phase4A offline completed EPL importer — implementation handoff

## Authority and baseline

Read START_HERE, OWNER_APPROVAL, PROMPT_FOR_CODEX and all accompanying package
requirements, current AGENTS, README, parser/model/synthetic/shadow/odds/result
source and relevant tests/handoffs. Verified input manifest. Owner's explicit
implementation approval supersedes only the package's older research gate.
Starting remote/local maincfb75ca037c1876f6d5abb29d54a4320fb987dbc,
tree990d581a1d361b78eaba830d38483862e7573472. Clean checkout; branch
codex/phase4a-offline-completed-epl created from approved main. Baseline620 tests
passed in10.886s on Windows CPython3.12.14. Budget฿0; no new dependencies or agents.

Only offline completed2024–25/2025–26 real results staging is implemented.
No new fitting, model evaluation, backtest, calibration, odds import, prediction,
API/live integration, scraping, paid service, credential, automation, deployment,
public trial or merge. Existing full-suite model-fixture regressions were run as
required; no new model fit/training experiment or parameter change was performed.
Trial1 and all earlier source/tests remain unchanged.

## Comparable GitHub projects inspected before code

- [Yetric football-txt-parser](https://github.com/yetric/football-txt-parser/tree/69a85c64af37ea1f29107a629774c725b37fd5ed),
  current main69a85c64af37ea1f29107a629774c725b37fd5ed; MIT LICENSE,
  src/parser.ts and test/parser.test.ts inspected. Useful separation of date,
  score and fixture identity plus format fixture tests. Rejected default noon/
  UTC timestamps, permissive competition grammars, standings and penalty/ET
  handling. No TypeScript/package dependency or source copied/executed.
- [sportdb/sport.db](https://github.com/sportdb/sport.db/tree/43ff505bf726db5f62890c0b8413eb30a12c88b3),
  current master43ff505bf726db5f62890c0b8413eb30a12c88b3; CC0 LICENSE.md,
  sportdb-readers/lib/sportdb/readers/match_reader.rb and
  sportdb-readers/test/test_match_reader_eng.rb inspected. Useful league/season
  context, explicit team lookup, separate error inventory and historical EPL
  alias test cases. Rejected guessed season dates, automatic global aliases,
  database mutation, console I/O and its broader importer stack. Source notes
  identify stage/round identity concerns; we retain season+ordered canonical pair
  identity and use round only as a coverage annotation. No dependency or code copy.

Both are relevant football-results importers, not sources of certified match
availability. Checked upstream implementations/tests/license status rather than
assuming source-repo freshness proves historical first publication. Adopted
patterns were independently implemented. No external executable code was run.

## Independently checked source and rights audit

OpenFootball England immutable revision9ee7a0c351805c99cc334478a9bf04b7d0432fec,
commit date2026-10-15T14:42:31Z. Both season files and full LICENSE.md fetched
using connector base64 at this ref; exact bytes decoded and Git blob/SHA256
computed independently. Existing 2023–24 pins/model semantics are untouched.

| Source path | Git blob | Actual raw SHA256 |
|---|---|---|
|2024-25/1-premierleague.txt|ca0fe4923f0164d0f879f796ab0759253e13bc06|e39716b01af0c8654a9fae7b5555e6b02f506ea05239e0d0eef41936ba80e1e3|
|2025-26/1-premierleague.txt|918adf1c0af4f613c73530cb528ab0df72461cfb|38c1de56c9e9b6662c7efc1420b7e1fe00dddbb502fe72d8f759e773ba3c093b|
|LICENSE.md|670154e3538863b2d9891fd5483160fbdfc89164|36ffd9dc085d529a7e60e1276d73ae5a030b020313e6c5408593a6ae2af39673|

CC0-1.0 statement reproduced with exact fixture bytes. Its third-party-rights,
accuracy and warranty disclaimers remain applicable. This is the inspected
provider license, not independent adjudication of match facts or rights to other
providers. No restricted football-data.co.uk CSV, football-data.org API, current
season source, personal image or odds data was acquired/imported.

SOURCES.json records acquisition audit2026-10-30T12:15:01Z; it is not match
availability or first-publication. Input acquisition must be aware and no earlier
than the pinned revision. Caller assertions and hashes still do not authenticate
remote truth. No clock is read or historical publication fabricated. Nested
.gitattributes preserves exact raw CRLF data/license bytes in checkouts/archives.

## Architecture and deliberate compatibility refinement

New isolated premfootballbot/completed_epl.py. The original parser's implementation
and NORMALIZER_SHA256 are part of protected source tests and approved model
semantics. Rather than altering that contract, reuse the unchanged parser for
2025–26 and its existing date/score/row helpers for a narrow new2024–25 reader.
This meets the requested reuse while leaving every older behavior/fingerprint
intact. Private helper dependency is documented and protected by old+new tests.
No string rewrites pretending2024 data are2023, no source hash substitution,
no mutable global profile injection and no widening of the trainer's acceptance.

Public API:

    SeasonInput(raw_bytes: bytes, source: OpenFootballSource)
    import_completed_epl(inputs: tuple[SeasonInput,...], *, license_bytes)
    completed_json(dataset) -> bytes
    verify_completed_dataset(dataset, inputs, *, license_bytes) -> True

Returns frozen ExploratoryMultiSeasonDataset containing760 CompletedMatch rows,
two SeasonCoverage records, explicit reviewed alias tables/version and profile/
parser/license fingerprints. Each CompletedMatch preserves the full original
ExploratoryMatch with raw names/row/header, inferred date/precision, printed
clock, HT or None, scores, source locator/line/hash and unknown UTC/availability;
adds internal canonical club keys and nominal round. Canonical IDs are local
reviewed labels, not claimed official IDs. The two20-team rosters overlap in17
clubs; Ipswich/Leicester/Southampton differ from Burnley/Leeds/Sunderland.

Exactly two approved sources are required, sorted by year independent of input
order; no2023/2026 profile, partial current season or duplicate season. Inputs
must match all fixed repo/revision/path/blob/SHA256/license evidence and bytes.
Source limit4MiB, license20KiB, inherited line/text bounds. Typed manifests avoid
an untrusted JSON-deserialization surface; source fixtures' JSON manifests are
checked static caller inputs. No arbitrary JSON dataset loader is provided.

2024 uses strict v-layout with optional printed clock/HT;2025 uses the old
centered-score/scorer grammar. Date context is nearest valid explicit header;
July–June year inference and weekday checks are reused. Unknown rows, invalid
dates, scoreless fixtures, ambiguous aliases, invalid clocks/HT/status or round
headers raise CompletedEplError with code and immutable exact line/reason/raw
issues. No partially accepted completed dataset is returned.2025 quarantine and
header issues are converted to the same atomic rejection. No silent repairs.

Each season requires380 scored results, exactly20 canonical clubs,19 home+19
away appearances, one of each380 directed pairs and38 nominal rounds with10
results each. Duplicate pairs report affected source lines; missing coverage
reports exact pair deficit and counts as a line0 diagnostic. Round numbering
never determines chronology: rows are sorted by season/date/canonical home/away.
Actual rescheduled fixtures cause nonmonotone round order in the sorted2024 set.

Canonical JSON uses sorted keys/no NaN; immutable nested tuples/dataclasses.
Full SHA256 seal detects accidental changes; source-backed replay detects even
re-sealed altered canonical rows/metadata. Root and all original-row temporal
restrictions are enforced during serialization. Checksums are not signatures.
No dict ordering, wall clock or floating optimizer affects dataset bytes.

Every output stays NON_SYNTHETIC_REAL_ARCHIVE,
EXPLORATORY_DATE_LEVEL_RECONSTRUCTION, EXPLORATORY_ONLY with
strict_point_in_time_eligible=False, historical_available_at=None, kickoff_utc=None
and UNKNOWN clock timezone. Complete results are not prospective-backtest proof.

## Coverage and sample cases

| Season | Results/clubs | Dates | Home/away goals | Missing HT | Missing printed clocks |
|---|---|---|---|---|---|
|2024–25|380/20|2024-08-16..2025-05-25|575/540|16|164|
|2025–26|380/20|2025-08-15..2026-05-24|580/465|0|0|

Zero accepted-output quarantine/header issues; completeness computed from parsed
fixtures rather than #Matches380 comments. Header counts never authorize rows.
Accepted2024 L11: Manchester United FC v Fulham FC1-0(0-0), inferred2024-08-16;
accepted2025 L10: Liverpool4-2(1-0)Bournemouth, inferred2025-08-15. These are
archive facts, not independently certified official results. An invented
Arsenall alias, missing date, scoreless future fixture or awarded row is rejected
with its line; duplicate/missing schedules cannot be represented as complete.

## Executable offline API example

```python
import json
from datetime import datetime
from pathlib import Path
from premfootballbot.openfootball_exploratory import OpenFootballSource
from premfootballbot.completed_epl import SeasonInput, import_completed_epl, completed_json, verify_completed_dataset

folder = Path("tests/fixtures/completed_epl")
manifests = json.loads((folder / "SOURCES.json").read_text(encoding="utf8"))
inputs = tuple(SeasonInput((folder / (m["path"][:7] + ".txt")).read_bytes(),
    OpenFootballSource(**{**m, "retrieved_at_utc": datetime.fromisoformat(m["retrieved_at_utc"])}))
    for m in manifests)
license_bytes = (folder / "LICENSE.md").read_bytes()
dataset = import_completed_epl(inputs, license_bytes=license_bytes)
assert len(dataset.rows) == 760
assert verify_completed_dataset(dataset, inputs, license_bytes=license_bytes)
canonical_bytes = completed_json(dataset)
```

At recorded provenance dataset digest59623d6ff79c1171b056a5da8960bb4cf7f2fb201c5ccc16223fd173b41f57f0.
Changing acquisition audit legitimately changes the digest, never availability.

## Actual tests and review gate

Baseline620 passed10.886s. Initial targeted32 passed0.649s. Final suite653 tests passed11.448s
(620 existing+33 new) executed with `python -B -m unittest discover -s tests -v`;
exact timings/full verbose output and committed-export rerun are in review ZIP.
Targeted command: `python -B -m unittest tests.test_completed_epl -v`.
Cases cover both exact blobs/full rosters, dates/rescheduling/rollover, optional
HT, raw locators, aliases/promotions/collisions, missing/duplicate fixtures,
future scoreless/current season, unsupported rights/identities/acquisition,
repeated import/input ordering, nested immutability/tamper/re-seal replay,
no I/O/fitter calls and rejection at synthetic/backtest/prospective boundaries.
Existing original-parser/model authorization regression tests remain unchanged.
No Linux/3.13 runtime, remote CI or external linter/type checker claimed here.
Python3.10 grammar and protected-source/export/patch checks recorded in evidence.

Changed files: README.md, premfootballbot/completed_epl.py,
tests/test_completed_epl.py, tests/fixtures/completed_epl/{.gitattributes,
2024-25.txt,2025-26.txt,LICENSE.md,SOURCES.json,README.md}, and this handoff.
Exact head/tree/base, file hashes, test logs, source audit and source ZIP are
delivered separately to avoid self-referential hashes inside the commit.

No known source ambiguity or unresolved test failure in authorized pinned files.
Only exact inspected sources are admitted; new revisions require independent
review and explicit pin updates. Source factual accuracy, third-party rights and
first-publication remain limitations. No training/calibration/predictive-validity
claim or new phase. Keep draft and request independent source/math/identity/
temporal-isolation review before separate explicit owner merge approval.

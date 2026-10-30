# Phase 4C2-A: isolated offline prior-only cold-start fallback

## Authority, baseline and inspection

Owner request authorizes 4C2-A implementation/tests and one draft PR only. Read
START_HERE, OWNER_APPROVAL, complete PROMPT_FOR_CODEX and every accompanying
requirement/background document. Verified all 16 package manifest entries.
Archived research-only/future 4C2-B notes are context, not extra authorization.

Fetched main 466c81bdb4841d426e0c9603b221dd6778e6e0de and tree
a05def4c72741e100cc7df450e89e5507ccab8c0 matched exactly before edits. Clean
checkout, zero open PRs; new branch codex/phase4c2a-prior-only. Read AGENTS/README,
4A/4B/4C1 reports, completed archive/parser, chronology/protocol, protected real
fitter and Poisson code, source/chronology/synthetic/prospective/odds/isolation
tests. No older implementation rebuilt. Pre-code research/design checkpoint and
package audit are supplied outside the commit in review evidence.

Budget ฿0; stdlib only, no new dependencies, providers or delegated work. Protected
modules, fixture bytes, aliases, authorization pins and frozen evidence are
unchanged. Only README, new retrospective_candidates.py, its dedicated tests and
this report change. Exact base/head/tree, source/changed-file hashes, patch,
test logs and remote draft metadata are in the independent-review ZIP.

## Research before implementation

Pinned current GitHub revisions, pertinent implementation/tests and license:

- [goalmodel](https://github.com/opisthokonta/goalmodel/tree/84ecd6c2bbad3ccb967abf88ef49e5bcd074e545):
  DESCRIPTION v0.6.4 GPL-3, R/goalmodel_predict.R, tests/testthat/test_1.R.
  Useful explicit support/identity and fit-versus-predict separation. Rejected
  automatic covariate/rating defaults, GPL source copying and R dependencies.
- [penaltyblog](https://github.com/martineastwood/penaltyblog/tree/6870f0e762e9cba35fa722dc14a8daeaf8bc6134):
  LICENCE MIT, penaltyblog/models/poisson.py, test/test_model_poisson.py.
  Useful unknown-team/unfitted error tests and probability interface boundaries.
  Rejected optimizer, coefficient bounds, grid normalization and NumPy/Cython/
  SciPy stack. tests/ was absent; actual singular test/ path verified via tree.
- [skforecast](https://github.com/skforecast/skforecast/tree/3ecc0dc3d251c313b08ce26a572d17a2ace022c4):
  LICENSE BSD-3-Clause, skforecast/model_selection/_split.py and
  model_selection/tests/tests_split/test_timeseriesfold.py. Useful explicit
  gap/type/offset validation. Rejected row-count gaps, automatic refits/search,
  overlapping/partial target blocks and pandas/NumPy dependencies.
- [sport.db](https://github.com/sportdb/sport.db/tree/43ff505bf726db5f62890c0b8413eb30a12c88b3):
  LICENSE.md CC0, sportdb-readers/lib/sportdb/readers/match_reader.rb and
  sportdb-readers/test/test_match_reader_eng.rb. Useful season and ambiguous
  identity examples; rejected guessed season start/time, automatic mappings and
  database/file writes. Existing audited season-specific aliases are reused.

No third-party source copied or executed; no dependency installation. These code
licenses do not grant third-party football-data rights. Research freshness does
not establish source accuracy or historical first-publication times.

## Minimal contracts and mathematics

Public APIs in premfootballbot.retrospective_candidates:

    build_cold_start_artifact(protocol, dataset, inputs, *, license_bytes)
    cold_start_json(artifact) -> canonical UTF8 bytes
    verify_cold_start_artifact(artifact, protocol, dataset, inputs, *, license_bytes) -> True

The builder requires typed CandidateProtocol and original SeasonInput/source/
license bytes. verify_protocol rebuilds C1 via development_folds, which invokes
verify_completed_dataset before selection. Thus exact source/license replay AND
complete protocol replay precede assembly. No hash-only authorization shortcut.
Original source/protocol errors propagate; new validation raises ColdStartError
(code COLD_START_INVALID). Fatal errors return no partial artifact.

Preserve C1 policy governance, selection(2024), exposed(2025), full date blocks,
embargo 2..366 calendar days. C2-A additionally requires minimum history 100..380:
the default 100 cannot be lowered to manufacture unseen-team examples. A larger
predeclared threshold or embargo defines another protocol, not permission to
search settings. No new policy chosen using outcomes or exposed holdout.

_training_summary rejoins ONLY fold.training IDs to authenticated dataset rows.
Checks duplicate/missing IDs, season 2024, date<=D-embargo, ordered canonical team
pair and source SHA. FT90-only semantics come from the unchanged approved
parser/replay. Selected goal counts must be ordinary nonnegative bounded ints;
bool/float/missing/nonfinite values fail. Count H if home>away, D if equal, A
otherwise. n=nH+nD+nA must equal exact training length. Hash ordered support IDs
and (identity reference, training home goals, training away goals) separately.
Results outside the selected training IDs are never read by assembly; whole
source parsing still reads them solely for required archive-integrity replay.

Decision precedence is fixed:

1. n<minimum: ABSTAIN / INSUFFICIENT_HISTORY, empty probabilities.
2. Any H/D/A count zero: ABSTAIN / ZERO_TRAINING_CLASS, empty probabilities,
   including otherwise established targets. No smoothing, clipping or tuning.
3. Both target teams in training-only population: ESTABLISHED_HISTORY /
   ESTABLISHED_NOT_EVALUATED, empty probabilities. No fitter called.
4. Otherwise PRIOR_ONLY / TEAM_STRENGTH_UNIDENTIFIED. Probabilities in H/D/A order
   are exactly count/n as Python floats, finite, positive, <=1, sum within 1e-15
   of 1 using fsum. Integer counts/denominator are authoritative rational values.
   No team-specific multiplier, promotion/rating inference or fitted parameters.

No target result join, scoring/Brier/log loss, paired evaluation, bootstrap,
model selection, optimization or new Poisson computation occurs. The prior is
unconditional league frequency, not inferred unknown-team strength or calibration.

## Immutable artifacts, integrity and threat model

ColdStartForecast contains label-free FixtureReference (ID/date/canonical pair/
source SHA), fold/protocol/source fingerprints, decision/reason/probabilities,
training counts/denominator and ID/row digests. ColdStartFold groups every target
on one date, records cutoff, selected training IDs/population/counts/support
digests and nested forecasts, with its own SHA256. ColdStartArtifact preserves
the C1 policy, protocol/dataset/source manifests, alias/profile identity, source
fingerprint, grouped folds, all-target/category counts, exposure and fixed warnings.
All nested containers are tuples/frozen dataclasses; no target goals or metrics.

Canonical JSON uses the existing sorted-key/UTF8/no-NaN encoder. Serialization
checks typed immutable structure, seals, restrictions, cutoff, training support,
category/probability math, disjoint unique targets and exact denominator ledger.
It validates consistency, NOT authenticity: checksums are not signatures.
Consumers MUST source-replay verify_cold_start_artifact before relying on it.
That rebuilds through the original public source/C1 verification and compares
exact canonical bytes, rejecting re-sealed identity, support, omitted-target,
counts, provenance, policy or probability spoofs. No untrusted JSON loader exists.
Private helpers are explicitly untrusted test oracles, never public source gates.

Every artifact/fold/forecast has exact status
RETROSPECTIVE_DATE_LEVEL_SIMULATION_NOT_EX_ANTE_VERIFIED,
historical_available_at=None, kickoff_utc=None, strict_point_in_time_eligible=False;
fixture references retain the same unknown-time flags. Embargo is a date-level
proxy, not evidence that results were published then. 2025–26 remains explicitly
EXPOSED_HOLDOUT_NOT_CONFIRMATORY, excluded from new targets and selection. New
artifacts are rejected by existing synthetic and prospective packet validators.
No clock, runtime file/network access, trusted-time inference or publication API.

## Actual empirical feasibility, not performance

Default-policy audit of all 109 2024–25 calendar-date groups accounts for 380 unique
targets: **280 ESTABLISHED_HISTORY but unfitted, 0 PRIOR_ONLY, 100 ABSTAIN**, all 100
for insufficient history. First sufficient date 2024-11-09. Every eligible target
club has already appeared in selected training history; no real cold-start
forecast was manufactured. No holdout targets or scores, no new Phase 4B 272/108 comparison.
Counts are descriptive engineering feasibility, not forecast accuracy or success.

Complete artifact seal:
da1719a356ab7129f0499d85012bf54c91e51ca8c74ad521dec51b1fa20b9c0c
Protocol seal:
e13ae3b612c5c0134aaa3bfa6e2c63dec058b6b063a0cebdc7f7a952acdd3490
Dataset seal:
59623d6ff79c1171b056a5da8960bb4cf7f2fb201c5ccc16223fd173b41f57f0
Source fingerprint:
edb2a0b423e62d77b97cd104bd8c720f10b3a7580fc0d54cfd52bf006df9a4be

## Source and licensing audit

Existing pinned OpenFootball England commit 9ee7a0c351805c99cc334478a9bf04b7d0432fec:

- 2024-25/1-premierleague.txt: blob ca0fe4923f0164d0f879f796ab0759253e13bc06;
  SHA256 e39716b01af0c8654a9fae7b5555e6b02f506ea05239e0d0eef41936ba80e1e3.
- 2025-26/1-premierleague.txt: blob 918adf1c0af4f613c73530cb528ab0df72461cfb;
  SHA256 38c1de56c9e9b6662c7efc1420b7e1fe00dddbb502fe72d8f759e773ba3c093b.
- CC0-1.0 LICENSE.md: blob 670154e3538863b2d9891fd5483160fbdfc89164;
  SHA256 36ffd9dc085d529a7e60e1276d73ae5a030b020313e6c5408593a6ae2af39673.

Existing manifest acquisition 2026-10-30T12:15:01Z is acquisition only, not match
publication. 380 results per season; exact canonical aliases/profile unchanged.
CC0 is a source rights statement, not factual correctness/third-party-rights
certification. No new source acquired; no 2023 identity bridge, 2026–27 data, lower
league/team-strength proxy, paid API, scraping, odds integration or credentials.

## Executable offline example (no fitting/scoring)

```python
from tests.test_completed_epl import inputs, FIXTURE
from premfootballbot.completed_epl import import_completed_epl
from premfootballbot.chronological_candidates import build_protocol
from premfootballbot.retrospective_candidates import (
    build_cold_start_artifact, cold_start_json, verify_cold_start_artifact,
)

sources = inputs()  # Caller reads exact existing checked-in bytes/manifests.
license_bytes = (FIXTURE / "LICENSE.md").read_bytes()
dataset = import_completed_epl(sources, license_bytes=license_bytes)
dates = tuple(sorted({r.original.match_date for r in dataset.rows
                      if r.original.season_start_year == 2024}))
protocol = build_protocol(dataset, sources, license_bytes=license_bytes, target_dates=dates)
artifact = build_cold_start_artifact(protocol, dataset, sources, license_bytes=license_bytes)
assert verify_cold_start_artifact(artifact, protocol, dataset, sources, license_bytes=license_bytes)
assert dict(artifact.category_counts) == {"ESTABLISHED_HISTORY":280, "PRIOR_ONLY":0, "ABSTAIN":100}
canonical_bytes = cold_start_json(artifact)  # Caller may save; core never writes.
```

## Tests and independent review gate

Baseline command python -B -m unittest discover -s tests -v: 707 passed in 15.843s on
Windows11 CPython 3.12.14. Implementation full 743 passed in 24.265s (707 older + 36 new).
Focused command python -B -m unittest tests.test_retrospective_candidates -v.
Final committed-export counts/timings/logs, example replay, AST 3.10 grammar check,
protected-file and complete Git blob/SHA manifests/patch reconstruction are
supplied in the review ZIP. No Linux/3.13/3.10 runtime, remote CI, external linter
or type checker run claimed. Required older tests include prior fixture fitting
and scoring regressions; these are not new 4C2-A model/evaluation experiments.

Tests cover exact counts/rational probabilities, no smoothing, one/both unknown,
established-unfitted, insufficient/zero-class precedence, bad numeric/identity
inputs, missing/duplicate/source/season/date joins, calendar embargo and boundary
dates, complete real development coverage and honest zero-prior count, private
target/D-1/future/holdout label/roster poisoning versus public tamper rejection,
source/license/profile/alias replay, canonical order, immutable artifacts,
untrusted JSON, sealed invented unknown-team artifact rejected publicly, re-sealed
probabilities/support/identity/partial-group/ledger/governance changes, and failure
atomicity. Denial mocks forbid fitters/scorers/Poisson/network/files/time; AST
restricts result access to the training join and rejects clock/RNG imports.

Initial focused 34-test run had two test-oracle setup errors: an assumed Dec31 source
fixture did not exist (changed to actual Jan4 D-1), and no-NaN encoder rejected
tampering before sealing (test now asserts that early rejection). Both corrected;
no production relaxation. Expanded 36-test suite and full regressions pass. No unresolved
local test failures. Exact-source final logs document what actually ran.

Limits: only pinned retrospective archives; no verified historical availability,
no empirical real unseen-team activation at approved history gate, no performance
evaluation, no calibration or team-specific unknown strength. Real cold-start
utility remains unmeasured. Do not interpret prior-only potential coverage as
accuracy, ROI, profitability or betting value. Independent source/math/leakage/
replay review is required before separate owner merge approval. Keep draft and
STOP here: no 4C2-B, fit/tuning, holdout selection, public forecast, deployment
or merge without new explicit authorization.

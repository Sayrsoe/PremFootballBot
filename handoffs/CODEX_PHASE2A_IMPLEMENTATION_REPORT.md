# Phase 2A-Offline implementation report

## Baseline and scope

User confirmed the Phase2A execution package in this chat. Read AGENTS.md,
README, current settlement/Poisson source and test structure, START_HERE.md,
CODEX_PHASE2A_EXECUTION_ORDER.md, MATCH_DATA_CONTRACT_REVIEWED.md,
SOURCE_DECISION.md and the complete independent DeepSeek source review.

Fetched latest GitHub main ee63be671575e67f769409aed19d7b239b0865a1
and verified the Phase 1B merge. Created
codex/phase2a-offline-match-ingestion from that main without reusing/resetting
an earlier branch. All 180 existing tests passed before changes.
The existing __init__.py, settlement.py, poisson.py and every existing test/
fixture remain unchanged. No dependency/toolchain changes.

Package SHA256:
c7852a004a2151bacbc84003d7c03dab356e2e4e0019a028695d0c6de7482d36.

Only synthetic JSON import/validation, revisions, as-of outcome selection,
provenance gates, stable hashes/manifests and coverage are implemented.
No provider data was acquired; no downloader, scraper, credentials, real
provider adapter, odds, training, estimates or later phase was implemented.

## Research and decisions made before coding

Inspected maintained
[sports-betting](https://github.com/georgedouzas/sports-betting/tree/eb4cedf376663fac68f508e50b83fd832e74dfd4),
pinned main eb4cedf376663fac68f508e50b83fd832e74dfd4
(last commit 2026-07-28, inspected 2026-10-26).
Read its [MIT LICENSE](https://github.com/georgedouzas/sports-betting/blob/eb4cedf376663fac68f508e50b83fd832e74dfd4/LICENSE),
[leakage tests](https://github.com/georgedouzas/sports-betting/blob/eb4cedf376663fac68f508e50b83fd832e74dfd4/tests/dataloaders/test_leakage.py)
and the relevant identity-validation/horizon gating in
[src/sportsbet/dataloaders/_base.py](https://github.com/georgedouzas/sports-betting/blob/eb4cedf376663fac68f508e50b83fd832e74dfd4/src/sportsbet/dataloaders/_base.py).
GitHub code search confirmed the current mask implementation.
Useful concepts: reject unavailable future information, preserve identity,
separate loading/validation/selection, test missing observations explicitly.
Rejected its betting/odds pipeline, scraper integration, pandas/sklearn/
cloudpickle dependencies and present-clock upcoming-fixture behavior.
No code or dataset was copied. MIT applies to reference code, not its feeds.

The supplied research is supporting evidence rather than provider permission.
No provider-rights or catalogue-completeness claims were independently cleared
in this milestone. In particular its provisional universal fixture
available<=kickoff rule is superseded by the reviewed contract: postponement
notices after kickoff are valid. The provider decision remains synthetic GO,
real-source integration deferred.

Before production coding, wrote design decisions and executable invented
input/acceptance tests. Decisions: one strict JSON version, frozen stdlib
dataclasses/tuples, atomic error results, explicit registries, consecutive
histories, strict-before cutoff, conservative unknown-revision quarantine,
stable content excluding retrieval timestamps. The external delivery includes
the pre-code design note.

## Input contract and public API

Module: premfootballbot.match_data, imported directly; Phase1A/1B exports
remain byte-for-byte unchanged. Python 3.10+ syntax/stdlib only.

Envelope has exactly schema_version (integer 1), namespace, teams,
source_documents, records. UTF8 bytes only, at most 4 MiB/10,000 records.
Unknown fields, duplicate JSON keys, invalid Unicode/nonfinite/typed values
and invalid containers fail closed. Version repeats on each observation.
One strict schema; no CSV/provider-specific mapping layer.

Namespace is synthetic:<slug>. Internal IDs use
<namespace>:team:<slug>, :fixture:<slug>, :source:<slug>, :record:<slug>,
:document:<slug> and :terms:<slug>. No real namespace or is_synthetic=false
is accepted. Team registries declare exact aliases; unknown/ambiguous aliases
and identical home/away IDs fail. Optional raw names are retained for audit.

SourceDocument fields: source_id, source_document_id, content_utf8,
source_checksum_sha256, source_terms_id, licence_status, is_synthetic.
Checksum must match embedded UTF8 text. All observation provenance fields
must match a registered document. CLEARED/UNKNOWN/BLOCKED are allowed for
auditing, but only CLEARED enters eligible outcomes. These declarations do
not themselves establish real data rights or prove a label is truly synthetic.

Observation fields follow the reviewed contract: schema/competition/season;
fixture/revision/supersedes; type/status; canonical teams and optional raw names;
kickoff precision/date/time; FT90 scores/basis; observation availability and
snapshot retrieval; full source/checksum/terms/licence/synthetic provenance.
Only optional supersedes_revision, match_date and raw names may be omitted;
normalization makes them explicit null. Season is start year 1992..9998,
not inferred from kickoff (unusual schedules can cross calendar boundaries).

Public functions:

- parse_synthetic_json(data: bytes) -> ImportResult.
  ImportResult has observations/teams/documents tuples, issues, duplicate
  count, namespace and content_sha256. errors/warnings/valid are inspectable.
  require_valid() raises MatchDataError carrying structured Issue values.
  Any error returns zero observations and no content hash: no partial import.
- canonical_content(batch: ImportResult) -> bytes.
  Deterministic normalized content for hashing, not a re-import document.
- snapshot_manifest(batch: ImportResult) -> SnapshotManifest.
  Stable content hash plus per-revision retrieval stamps and source digests.
- select_as_of(batch, cutoff_utc: datetime, *,
  include_synthetic: bool=True) -> AsOfSelection.
  Frozen observations and explicit per-revision exclusions.
- summarize_coverage(batch, *, expected_matches: Mapping[int,int]|None=None)
  -> tuple[SeasonCoverage,...].
  Latest-present fixture/status counts, revision count, eligible FT90 count,
  missing/coarse metadata, explicit optional denominators, separate fixture
  and result completeness. No universal 380-match assumption.

Consumers should use parser-produced batches, not fabricate output
dataclasses to bypass validation. These are local Python APIs, not an
untrusted code-execution/security boundary.

## Revision and availability semantics

A full fixture history starts at revision zero and increments consecutively.
Each successor supersedes the preceding revision. Fixture/source-record,
teams, competition and season remain stable. Postponement/rescheduling may
change kickoff within that identity; replays/new opponents need new fixture
IDs. Known availability strictly increases, even across unknown-time entries.
Conflicting duplicate (source_id,source_record_id,revision) rejects the batch.
Identical content duplicates ignore only retrieval stamps, keep their earliest
stamp, and emit a count warning.

Exact timestamps use explicit RFC3339-style offset with seconds and optional
1..6 fractional digits; normalize to UTC. Naive, unknown -00:00 offset,
excess fractional precision and overflow are rejected. No local timezone
is inferred. date_only requires date/null kickoff; unknown has neither.
An optional date accompanying exact kickoff must equal its UTC date.
Unknown availability remains null, never inferred from retrieval or kickoff.
Retrieval must not precede known observation availability.
For exact FINISHED FT90, availability >= kickoff+90min is a necessary lower
bound only, not evidence of actual publication.

Selection uses available_at < cutoff, including exact-boundary exclusion.
It first identifies latest observed revision, then applies licence, status,
FT90 and precision gates. No fallback to an old score after an observed
withdrawal, coarse correction or blocked revision. Future known revisions
cannot leak backward. A higher revision with unknown availability quarantines
an older result because its historical validity cannot be established.
A later known successor can resolve earlier unknown availability.
include_synthetic=False returns no rows from this synthetic-only importer.
This conservative policy favors exclusion over inventing historical times.

Canonical SHA256 includes normalized teams, documents and all revision
content, excluding only retrieved_at_utc. Registry/alias/record ordering is
deterministic; mutable retrieval stamps remain in the separate manifest.
Repeated imports and identical copies are idempotent. There is no clock call,
database or persistent mutation: immutable histories are within a parsed batch.
Cross-snapshot append-only enforcement requires comparing stored manifests/
prior histories; callers must not reinterpret a new hash as proof of no edits.

## Executed example and test evidence

Complete input example: tests/fixtures/phase2a_synthetic_v1.json.
Its teams, matches, source text and availability times are invented.
It includes three versions of fixture a, a post-kickoff postponement and later
reschedule for b, a date-only result with unknown availability for c, and an
unscored awarded observation for d.

README's example was executed:
parse_synthetic_json(Path(...).read_bytes()).require_valid();
select_as_of(..., 2026-08-02T00:00Z) returns fixture a revision 1, score 0-0;
2026-08-04T00:00Z returns revision 2, score 1-0.
Content SHA256:
81fc7eb53c76c3693c77ba533b6c55c4a036c724a8f3f25c60e878ce28bfa2aa.
Coverage: 4 distinct fixtures / 7 observations; 1 eligible current result,
1 unknown availability, 1 coarse kickoff; partial against hypothetical 380.

Windows Python 3.12.14, no third-party dependencies.
Commands actually run:

- python -X utf8 -B -m unittest discover -s tests -v
  Before implementation: 180/180 pass.
- python -X utf8 -B -m unittest tests.test_match_data
  tests.test_match_data_leakage -v
  Initial targeted pass: 60/60.
- Full initial suite: 240/240 pass.
- Two added diagnostic-order regression tests initially failed; source order
  affected conflicting-duplicate paths and first invalid registry diagnostic.
  Fixed stable validation order without accepting any conflicting record.
- Full reviewed suite: 248/248 pass, zero failures/errors:
  180 unchanged methods + 53 validation/determinism + 15 independent leakage.

Leakage expected histories are hand-written separately from production
eligibility helpers. The independent test module covers the strict publication
boundary; 823 cutoffs sampled every seven minutes across four synthetic days;
late corrections; observed withdrawal/blocked/coarse revisions without fallback;
unknown higher revisions and known successors; null availability; all statuses;
licence states; namespace isolation; aware/offset-equivalent cutoffs and
postponements. No real training or forecasting evaluation was performed.

Other tests cover invalid/bool/null scores, aliases/IDs/season/league/schema,
JSON/Unicode/resource errors, document checksums/provenance, DST offset
normalization, overflow, duplicate conflicts, full revision chains,
immutability, deterministic diagnostics, order permutations, stable hashes,
retrieval manifests, explicit partial coverage and repeated imports.

No configured formatter/linter/type checker or CI exists; no such checks are
claimed. Python 3.10 runtime is unavailable: grammar compatibility and isolated
export checks are recorded in the external delivery evidence. Final logs,
commit/tree hashes and publication outcome accompany delivery.

## Changed paths, limitations and integration

Seven paths only:
README.md; premfootballbot/match_data.py; tests/match_data_cases.py;
tests/test_match_data.py; tests/test_match_data_leakage.py;
tests/fixtures/phase2a_synthetic_v1.json;
handoffs/CODEX_PHASE2A_IMPLEMENTATION_REPORT.md.

The source-document checksum validates embedded text, not semantic entailment
of every normalized observation; the input author supplies both. Synthetic
labels cannot establish real-world truth. This importer accepts a complete
single-source history per fixture and fails on gaps/multi-source reconciliation;
it is not a provider contract or general event store.
Coverage is latest-present metadata, not historical model eligibility.
The 90min threshold is not an actual whistle/publication time.
No DST timezone database/inference, empirical data completeness, real-provider
quirks, real historical availability, legal clearance or predictive skill
was tested.

For future separately authorized work, pass only explicit cutoff-selected
outcomes to model code, retain source histories/manifests, require affirmative
provider permissions and timestamp provenance, and independently review any
adapter/reconciliation change. No Phase2B/3 work is included or authorized here.
Publish only this feature branch as a draft PR; never merge in this task.
If Git credentials fail, export exact committed source, patch, Git-tree/SHA256
manifest and review evidence for independent publication.

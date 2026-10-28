# Prospective EPL Evidence Recorder — Implementation & Independent Review Handoff

Status: **DRAFT PR ONLY; NO MERGE.** This milestone is offline evidence infrastructure, not real-data forecasting, backtesting, or independent source-publication proof.

## Repository / baseline
- Target `Sayrsoe/PremFootballBot`, **not** `Sayrsoe/BlockBid` (the latter was a conflicting link in the request).
- Required reviewed `main` baseline: `d591912b4aaac26eef60a4b50b62b3e3a81cc84f`, verified before feature work. Its source tree is `9e081554e50a371375ffbab783a7e42a4b2ca7ea`.
- No existing production modules, `AGENTS.md`, CI, dependency files or test fixtures intentionally modified. The root README receives an additive section only.
- Only permitted changed paths: `premfootballbot/prospective_evidence.py`, `tests/test_prospective_evidence.py`, `README.md`, `handoffs/CODEX_PROSPECTIVE_EVIDENCE_REPORT.md`.

## External GitHub research before implementation
1. `in-toto/attestation` specification: https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md — subject identifiers and cryptographic digest binding make provenance claims auditable. Adopt **explicit digest, subject/fixture binding, version and clear assertions**, not the full in-toto schema or its dependencies.
2. `sigstore/sigstore-python` repository: https://github.com/sigstore/sigstore-python — production attestation/signed artifact verification uses a much larger verification and trust stack. Do **not** add cryptographic signatures, network verification or third-party packages to this minimal offline module; a local hash is not an authenticated timestamp.
3. GitHub REST issue comments docs: https://docs.github.com/en/rest/issues/comments — comment IDs, URLs, server timestamps and body are possible later audit fields; copied metadata is untrusted. No automatic publication.
No external source code was copied.

## API contracts (stdlib only)
- `freeze_packet(packet: Mapping[str,Any] | str | bytes) -> FrozenEvidence`: validates an exact `v1` EPL pre-match schema and returns frozen canonical UTF-8 bytes, SHA-256 commitment and identifying summary. Raises `EvidenceError` on invalid data; no I/O/network/clocks.
- `manual_comment_template(frozen: FrozenEvidence) -> str`: generates **unposted** literal commitment including protocol, fixture ID, kickoff, cutoff, digest and unverified-evidence banner.
- `manual_external_audit_worksheet(frozen) -> str`: generates an operator checklist for a future independent manual verifier.
- `assess_untrusted_comment_metadata(frozen, metadata, *, fixture_status="UNKNOWN") -> CommentAssessment`: validates a **claim** about a GitHub comment; returns `REJECTED` or `PLAUSIBLE_CLAIM_UNVERIFIED`, never `EXTERNALLY_CHECKED`. The caller's `fixture_status` assertion also cannot upgrade trust.
- `FrozenEvidence` and `CommentAssessment` are immutable frozen dataclasses. No authenticated GitHub use or source fetching, no automatic posting.

## Integrity / policy
Canonical JSON: lexicographically sorted object keys; compact UTF-8 encoding, UTC timestamps normalized to six fractional digits, exact decimals normalized from text, unique source records sorted by `source_id`; root canonical size <=65,536 bytes; domain-separated digest `SHA256(b"PremFootballBot prospective evidence v1\\0" + canonical_bytes)` (the byte prefix ends in an actual NUL). Unknown rights remain UNKNOWN, blocked remain BLOCKED. Source `acquired_at` is only a caller claim. Embedded source `source_available_at` or `verified_by_external_observer_at` remains a *claim*, not a verified first-publication fact.

Rejects: duplicate JSON fields/source IDs; invalid Unicode/UTC/zone, teams equal, source-after-cutoff, acquisition/capture ordering violations, wrong protocol/league, malformed digest, post-match fields, oversized payload, unsafe URLs and secrets in common query parameters, float/boolean/nonfinite/negative/wrong-total forecasts, edited/late/mismatching comments, rescheduled/canceled fixture status asserted for claim review. It never imports the existing synthetic training or OpenFootball modules.

## Verification performed and limitations
- Pre-change GitHub connector reported exact expected `main` SHA. Read repo `AGENTS.md`, README, package API, relevant test conventions, tree listing; searched comparable GitHub code first.
- `python -B -m unittest discover -s tests -p 'test_prospective_evidence.py' -v`: **32/32 passing** locally (Python 3.13.5). Test fixtures are conspicuously fabricated and contain no predictions.
- `python -m py_compile` on module: passed.
- Full legacy suite **not run** in this local execution environment because `git clone` could not resolve github.com and the source checkout was not available. Baseline 418/418 refers to PRIOR independent merged-main review, not a new execution. Run full suite in Codex/CI or in a real checkout before marking PR ready; no full-suite success claim is made here.
- `git diff --check` and protected-file blob verification should be completed against the actual feature branch after publication; compare against original tree from main, and have independent reviewer verify these exactly.

## Remaining limitations / explicit future gates
- This is evidence infrastructure, **not** a trustworthy timestamp authority. User-supplied local clocks may be backdated; even a real GitHub timestamp shows only that the digest text was published, not the integrity or availability of underlying sources.
- Comments can be edited/deleted and screenshots or copied API metadata are insufficient for independently certified status. Strict externally checked labels not emitted.
- Cancelled/rescheduled fixture checks need separately verified live fixture metadata, prohibited from this module. Stale source recency/content rights require independent research; semantic truth of supplied source and fixture IDs is not verified.
- No real EPL models, provider integrations, datasets, odds, automatic publishing, returns/ROI, Phase 3C/3D or synthetic-policy changes.
- User must independently review and approve any merge. Do not mark the PR ready without the independent review specified in the handoff ZIP.
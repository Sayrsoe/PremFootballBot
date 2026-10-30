# Phase 3D-A implementation and independent-review handoff

## Authority and baseline

Owner approved an offline prospective shadow adapter, preserving all existing
synthetic, real-data and retrospective restrictions. Read AGENTS.md, README,
Poisson, prospective recorder, real training source, prior handoff and relevant
tests. Fetched main and verified commit9ff278f726bf8e3c5f72476867b4f4ecaaa66045,
tree cff6bf1969ffbd7b242883ddc57c51705b71877e. Baseline507 tests passed in2.714s
on CPython3.12.14/Windows. Branch codex/phase3da-offline-shadow-pilot.
Budget฿0; no new dependencies or subagents.

Scope is code and invented-fixture testing, not an operational pilot run.
No real independently verified future kickoff was supplied or invented. No
real forecast, historical ex-ante reinterpretation, accuracy, ROI, betting value,
paid provider, scraping, credentials, gambling, deployment, automation or merge.
Publication here means only the expressly authorized draft engineering PR.

## Research before implementation

- [Penaltyblog](https://github.com/martineastwood/penaltyblog/blob/6870f0e762e9cba35fa722dc14a8daeaf8bc6134/penaltyblog/models/football_probability_grid.py),
  MIT LICENCE inspected at6870f0e762e9cba35fa722dc14a8daeaf8bc6134. Shared
  grid/mass aggregation is useful; normalizing a truncated grid is conditional
  probability. Rejected silent soft failure on mass errors, automatic normalization
  without an audit, and its NumPy/SciPy ecosystem. Inspected open issue listing
  (no relevant numerical issue there); no external tests run.
- [python-tuf](https://github.com/theupdateframework/python-tuf/tree/2c771a035620b29c6e5f90030f501ae92d64cf83),
  current develop2c771a035620b29c6e5f90030f501ae92d64cf83. Inspected full Apache2
  LICENSE, tuf/ngclient/_internal/trusted_metadata_set.py and
  tests/test_trusted_metadata_set.py. Adopted the architecture of a separately
  provisioned trust root, strict ordering and expiry. This adapter does NOT
  implement TUF signatures/thresholds/rollback protection or claim equivalent
  security. No upstream code copied, installed or executed. Licenses apply to
  reference code, not unrelated football data. Existing stdlib implementation
  and dependency conventions are retained.

The pre-code design checkpoint is included in review evidence. Independent
hash-pinned review is deliberately an external owner-controlled trust boundary;
untrusted fixture data cannot grant itself verified status.

## Contract and offline owner workflow

Direct module import: premfootballbot.shadow_pilot. No root exports changed.

    forecast_shadow(model, raw_bytes, *, license_bytes, snapshot_bytes,
        review_bytes, approved_review_sha256=(), team_mapping, cutoff_utc,
        model_acquired_at_utc, operator) -> ShadowDecision

ShadowDecision is frozen: status, reason, report_bytes, report_sha256, packet.
The latter is the existing FrozenEvidence or None. All report content is plain
canonical UTF8 JSON; all returned nested state is immutable bytes/dataclasses.

Snapshot JSON is a manually checked transcription with exactly:

    fixture_id, league, home, away, kickoff_utc, status

league must be EPL; status SCHEDULED. Identifiers/ASCII labels and strict UTC-Z
timestamps reuse recorder validation. Home and away must differ. No score,
result, postmatch or extra fields; duplicates, floats, invalid UTF8 or >64KiB
JSON are rejected by the recorder's existing strict parsing helpers.

Review JSON has exactly:

    fixture (same object as snapshot), snapshot_sha256, source_url,
    license_status, license_reference, acquired_at_utc, reviewed_at_utc,
    valid_until_utc, reviewer

The snapshot SHA256 covers exact bytes. license_status must be CLEARED with an
HTTPS permission/license reference; source URL must be credential-free HTTPS.
reviewer is an independent operator ID, distinct case-insensitively from capture
operator. A signature-free claim is not automatically trusted: exact review
bytes must match an independently supplied approved_review_sha256 tuple. No
trust registry or real fixture is bundled in source. The only computed test
pins are explicitly INVENTED unit-test roots.

Owner operating sequence:
1. Obtain permitted fixture evidence manually. Independently verify league,
   identity, SCHEDULED status and precise UTC kickoff; preserve source and rights.
2. An independent person checks the snapshot and writes the review envelope,
   including real acquisition/review times and conservative expiration.
3. Owner provisions that envelope digest out of band, with independent review
   records, into the trusted tuple. Never self-pin arbitrary received data.
4. Supply explicit bijective future-name -> exact2023 raw-label mapping. Unknown
   or promoted teams abstain; no fuzzy alias or league-mean fallback.
5. Supply externally checked capture/cutoff time and model acquisition. Inspect
   the returned audit/packet. Any later manual evidence publication needs its
   own authorized action; this module cannot post or certify publication.

Temporal gates: acquisition<=review<=cutoff<expiry<=kickoff, cutoff<kickoff,
review age<=24h. Source retrieval<=model acquisition<=cutoff; latest training
calendar date strictly before both model acquisition and cutoff date. Therefore
historical training fixtures cannot be recast as pre-match observations.
Cutoff also represents local capture time; it is caller supplied, not trusted
time. All source_available_at fields remain None. Registry correctness, identity,
rights assertions, actual UTC truth, trusted time, revocation and latest fixture
changes must be checked externally. No hash or reviewer string authenticates
a person or proves that the source was truthful/first published then. Assurance
is always LOCAL_ONLY with external_audit_required true, never certification.

## Preserved model and numerical behavior

Every fit is replay-verified against exact pinned2023 archive/license bytes
through the unchanged real trainer. Only default config and reviewed artifact
e8a2ec2bfc109b28de8b9bbfa2c9727eb275ad493a99b482f064b064b542825a
are accepted. Different runtime artifact, re-sealed tampering, provenance changes
or tuning abstain. The original artifact retains RETROSPECTIVE_DESCRIPTIVE_ONLY,
false historical eligibility and no prediction API. This separate adapter uses
its parameters experimentally for a future shadow fixture; it does not change
the fit's status or imply historical/live validity. Report warns of stale2023–24
strengths. Runtime-specific pinning is intentional fail-closed behavior.

Rates reuse mu+h+attack_home+vulnerability_away and
mu+attack_away+vulnerability_home, exponentiated without clipping. Finite positive
rates<=100 feed unchanged poisson_distribution with tolerance1e-10/max_goals512.
Existing 1X2 aggregation is reused. Check finite bounded outcome masses,
0<=omitted<=tail_bound<=1e-10, positive retained mass, roundoff<=5e-12,
raw outcome sum matching retained mass and retained+omitted matching1.
Any failure abstains; no numerical/model fallback or AH market output.

The old recorder requires exact decimal probabilities totaling1. Explicitly
condition each raw1X2 mass on their retained sum; quantize to15 decimal places
using largest remainder (home/draw/away tie order). Local Decimal precision60
isolates this from caller context. Each quantization error is <=1e-15; truncation
conditioning is bounded by omitted mass plus recorded floating roundoff. Raw
outcomes, retained/omitted/bound/roundoff, rates, caps, emitted probabilities and
maximum adjustment remain visible in audit. Earlier Poisson APIs never normalize.

Audit binds snapshot/review hashes, model content/semantic hashes, configuration,
mapping, status/reason and numerical policy. Its SHA256 becomes a recorder input;
model bytes are a separate input. Recorder config digest binds exact model,
canonical mapping, version and tail policy. Existing freeze_packet performs the
final schema/temporal/exact-total checks. Publication remains separate.

On invalid fixture evidence, return ABSTAIN without packet. On downstream team,
model or numerical failure after valid evidence, return ABSTAIN plus a
NO_FORECAST packet with no probabilities/model. Reason and report are bound
into that packet. Recorder rejection itself abstains without a packet. No
abstention is a predictive performance sample. Reasons include UNAPPROVED_REVIEW,
SNAPSHOT_MISMATCH, FIXTURE_MISMATCH, UNSUPPORTED_FIXTURE, EVIDENCE_TIMING,
STALE_REVIEW, INDEPENDENT_REVIEW_REQUIRED, RIGHTS_NOT_CLEARED, MODEL_ACQUISITION,
UNAPPROVED_MODEL_ARTIFACT/CONFIG, HISTORICAL_TARGET, TEAM_MAPPING,
UNSUPPORTED_TEAM, NUMERICAL_RATE/MASS, RECORDER_REJECTED and typed invalid-input
class. Unexpected parser/model ValueError-family failures fail closed.

## Actual tests and evidence

Python3.12.14/Windows, stdlib unittest, -B:
- Baseline full suite507 passed in2.714s.
- Initial41-case development began with37 targeted cases, all passed in2.276s.
- Full final suite548 passed in5.243s:507 unchanged plus41 new test methods.
- Commands: python -B -m unittest tests.test_shadow_pilot -v;
  python -B -m unittest discover -s tests -v.
- Exact source export rerun, baseline evidence, protected-file comparison,
  patch reconstruction, grammar and Git integrity details are recorded in the
  portable review package with actual logs. No external lint/type-check tool,
  remote CI or Python3.10 runtime result is claimed.

Tests use the licensed existing real model fixture plus INVENTED future fixtures,
source URLs, permissions, reviewers and approval pins. Cases cover numerical
equations/tails/rounding, deterministic replay, recorder exact totals/commitments,
no trust pin, proof/snapshot tampering, uncertain UTC, postponement, wrong league,
late/stale/expired sources, independent-review requirement, unsafe rights/URLs,
strict JSON, unsupported teams/mappings, acquisition chronology, re-sealed model
tamper, unapproved provenance/tuning, numerical failures, low Decimal precision,
no I/O, no premature computation and unchanged synthetic rejection gates.

## Changed files, review request and limits

README.md; premfootballbot/shadow_pilot.py; tests/test_shadow_pilot.py;
handoffs/CODEX_PHASE3DA_IMPLEMENTATION_REPORT.md. All other tracked files,
including every earlier module/test/fixture, remain byte-identical to main.

Please obtain independent review of exact head/tree, proof/registry separation,
mathematics and conditional-mass contract, historical isolation and abstention
packets before separate owner merge approval. Keep draft; do not merge.
No actual source-verification ceremony, public prospective commitment or real
fixture forecast was performed. Unknown external trust and model staleness are
operational limits, not test failures. This code does not establish prediction
accuracy, profitability, calibrated uncertainty or betting value.

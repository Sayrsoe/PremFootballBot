# Phase 4C2-C0 — offline pre-match abstention/odds evidence recorder

## Authorized scope and starting point

Owner approved on 2026-10-31: implement an **offline-first pre-match fixture/evidence recorder** with source/provenance and odds validation, feature branch, tests and **draft PR only**. No real EPL fitting, current-season automated ingestion, wagering, deployment, paid providers or merge. No additional owner comments.

Repository: `Sayrsoe/PremFootballBot`. Starting `main` commit `a10fab4077ad8d27a62bddfdaa24352ad0a7f0dc`, tree `63f6e4e4618f05e51e9e61765810076e54230518`, after the authorized PR #18 merge. The existing read-only historical fold boundary is **not** imported or bypassed.

**Execution attribution:** code and tests for this proposal were authored/tested in a local Python workspace and prepared for GitHub through ChatGPT's available tools. A standalone Codex task instruction was also prepared for independent review/handoff. No Codex-run session or Codex-generated test result is claimed.

## Research / implementation decision

Inspected the actual `AGENTS.md`, `docs/ENGINEERING_WORKFLOW.md`, `.github/workflows/quality.yml`, `prospective_evidence.py`, `odds_observations.py`, `result_evaluation.py`, `shadow_pilot.py`, B1/B2A code, the existing synthetic source tests and frozen model authorization. This implementation **reuses** the already validated `freeze_packet`, `freeze_odds`, and `checked` contracts instead of adding a second forecast schema. Existing prior snapshot and result protections remain unchanged.

External reference research: [in-toto/in-toto](https://github.com/in-toto/in-toto) and [in-toto/attestation](https://github.com/in-toto/attestation) demonstrate what stronger signed, externally verifiable provenance would require; [unpingable/receipt_kernel](https://github.com/unpingable/receipt_kernel) illustrates append-only hash-chain and explicit invariants. We intentionally did **not** import their libraries, copy source, or claim local SHA-256 seals are signatures, independently trusted timestamps or security against whole-chain re-sealing. Zero dependencies/budget remain unchanged.

## Bounded C0 contract

Only new module: `premfootballbot/prematch_recorder.py`. It **does not forecast**. It consumes existing validated **NO_FORECAST** `FrozenEvidence` packets, optional **CLEARED** `FrozenRecord` odds objects, an abstention reason from an explicit allowlist, and *caller-claimed* 40-hex Git commit/tree identifiers. It refuses real model output, real-data fitting, score/settlement payloads, post-cutoff inputs and late/uncleared/mismatched odds. Source references are cross-checked against the evidence packet's recorded digest, URL, rights and acquisition time. BLOCKED inputs fail; UNKNOWN inputs remain explicit reference-only abstentions and cannot support attached odds.

`capture_abstention(...) -> CaptureRecord` and `checked_capture(record)` create/replay canonical bytes and a domain-separated SHA-256. `append_capture`, `verify_ledger`, `ledger_json`, `load_ledger` enforce ordered full-content hash chains, typed immutable rows, canonical JSON and optional external pinned-head verification. Re-sealing a whole chain is possible unless the earlier head was preserved externally; no attestation guarantee is implied. Each fixture/UTC kickoff/cutoff/Git-commit combination is unique. A rescheduled kickoff requires a new entry; fixture status cannot be independently verified by the recorder.

`python -m premfootballbot.prematch_recorder` provides **manual local-file** `record` and `verify` commands. `record` takes a pre-existing validated packet JSON and optional manually captured odds JSON files, reads an optional previous ledger and its externally pinned head, and creates a **new** ledger file with exclusive `O_EXCL` creation (never overwrite). It rejects output inside the repository, does not contact any feed, and does not write any fixture/quote/user secret into the public repository. User must supply the exact Git identity and store the output privately outside the checkout. No automatic clock, public API, networking, provider integration, workflow/schedule or background capture.

## Usage — synthetic example, no authentic EPL evidence

The fixture packet must follow `premfootballbot.prospective_evidence.freeze_packet`'s exact existing schema. Build it manually (or from authorized records) in an external/private path, for example `/private/fixture-packet.json`. For optional odds, the exact schema is `premfootballbot.odds_observations.freeze_odds`.

```bash
python -m premfootballbot.prematch_recorder record \
  --packet /private/fixture-packet.json \
  --out /private/ledger-v1.json \
  --reason NO_AUTHORIZED_MODEL \
  --repo-commit <40-hex-Git-commit> \
  --repo-tree <40-hex-Git-tree>

python -m premfootballbot.prematch_recorder verify \
  --ledger /private/ledger-v1.json --expected-head <64-hex-pinned-record-SHA256>
```

For the next capture, use `--previous /private/ledger-v1.json --expected-head <pinned-previous-head> --out /private/ledger-v2.json` (a new file). Never post captured private provider data or API secrets to public GitHub. The SHA and claimed timestamps must be externally checked; recording them is **not** such a check.

## Explicit assurance and stop gates

- Existing `weighted_poisson.py` accepts invented numerical data only; it is not used here. No B2A historical training object is cast to `toy:`. There is **no real EPL model fitting, prediction, calibration, scoring, benchmark, odds EV or trade execution**.
- Current-season fixture retrieval and odds provider access are NOT implemented. Captures use supplied immutable fixture identities/timestamps, not live or guaranteed-valid schedules.
- `source_rights` records **claims**, never legal clearance certification. Odds must have rights marked CLEARED and match a uniquely referenced packet input with identical recorded hash/URL; original source rights and retention still require an independent human check.
- All capture evidence is `LOCAL_ONLY_EXTERNAL_AUDIT_REQUIRED`; no independent timestamp source, signatures or persistence guarantee is asserted. The caller must store immutable ledger versions and preserve a separately pinned digest. The CLI only creates new files; manual deletion of old files or re-sealing a whole chain remains possible.
- Fixed future cutoff policy (such as two hours before kickoff) and automated snapshot scheduling are separate future decisions, not silently inferred or implemented.

## Verification evidence and known limitations

Local Python executed against the previously reviewed B1 source package and current unchanged core provenance/odds modules (the locally available source package **does not include the newly merged B2A module**, which is not imported by this task):

- `python -B -m unittest tests.test_prematch_recorder -q`: **33 passed**, zero failures (invented-only fixtures/quotes).
- Existing test modules: 23 of 24 completed individually and passed in a bounded parallel attempt; one long module did not finish before the execution limit. **No complete local full-suite pass is claimed.**
- The initial combined single-interpreter full suite exceeded the local process limit without a conclusive summary. **Not a pass**.
- GitHub Actions Python 3.10 and 3.12 on the **exact draft PR head** must be independently verified before an owner merge decision. Baseline main (post PR #18) previously passed **803 tests**; expected total after 33 new tests is **836**, subject to actual CI confirmation.
- Repo fixture bytes, existing modules, CI, source rights/pins, model flags, previous handoffs and historical holdout are unchanged.

## Independent-review handoff and owner gate

Review the four-file GitHub diff (`premfootballbot/prematch_recorder.py`, `tests/test_prematch_recorder.py`, `README.md`, this report), blob/commit/tree SHA, full GitHub CI, denial tests (forecast bypass, postcutoff/mismatched/uncleared odds, source spoof, tampering, duplicate fixtures, external head mismatch, no overwrite, no output under repo), and confirmation of zero model/real-data coupling. Only a separately approved exact-head review can authorize a merge. **Draft PR only. Do not begin a genuine model prediction or automated provider ingestion.**

## Independent Codex audit follow-up — 2026-10-31

An independent audit of initial head `d391c9b0c9ba83592dfd1ea8a73ccf2f446044a1` identified two P2 acceptance gaps despite the initial 836-test green CI:
1. An optional odds `independent_observed_at_utc` could occur after the packet's own capture but before its cutoff.
2. A conflicting price could reuse the same snapshot/bookmaker/market/selection/line with a different `captured_at_utc`.

Narrow repair: enforce that independent observation is no later than **both** packet capture and cutoff; remove capture time from the duplicate-selection key; require consistent capture-time and source metadata across selections in one snapshot/bookmaker; permit a genuinely distinct snapshot ID. The existing `checked_capture` and `checked_capture_payload` paths replay these validations. Three adversarial invented-data regressions cover both original probes, resealed-payload replay, cross-selection snapshot consistency and distinct-snapshot allowance.

The initial clean full-suite result was **not** sufficient to establish the fixed behavior. Rerun focused tests and GitHub Python 3.10/3.12 complete offline suites on the new exact head; do not claim success until the actual results are verified. No real EPL dataset, source gate, predictions, scoring, model, credentials, live feed, deployment or merge is authorized. Keep draft and separately request owner exact-head merge approval after independent re-review.

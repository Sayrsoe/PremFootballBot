# PR9 portable semantic model authorization follow-up

Reviewed base91b04725a30a6d4c3ab6855a3a46f7eac80f3b4c,
tree208584ae38c9d9cc3639d9d4e5055d9c96e1e688. GitHub PR9 confirmed draft
at that head. Read AGENTS, README, shadow adapter, real trainer/replay, existing
tests and Phase3D-A handoff. Existing Windows CPython3.12.14 suite:548 passed
in5.340s. Owner-supplied independent Linux CPython3.13.5 QA reported7 failures
and3 errors, all resolved by substituting the Linux model hash in memory.
That Linux result is supplied evidence, not an execution performed here.

## Finding and minimal solution

The old approved hash covered runtime label, optimizer trace/diagnostics and
floating-point parameters as exact JSON bytes. It therefore mixed artifact
integrity with semantic approval. Even changing only the runtime label after
legitimate recomputation invalidated authorization.

Three checks now apply in sequence, with no change to the real trainer:
1. Existing retrospective_json seal validation and verify_retrospective_fit
   recompute from the pinned raw source/license and require byte-for-byte equality
   in the executing runtime. No tolerance or excluded field is introduced here.
2. Exact default configuration and a FIXED approved semantic metadata SHA256.
   Projection retains all model fields except sha256, runtime, diagnostics,
   intercept, home_advantage, and the two floating effects per team. It retains
   the entire source import (including retrieval, source hash, raw rows, parser
   fingerprint, dates/locators and its seal), configuration, team names/order/
   counts, training counts, exclusions, license hash, warnings, version and
   restriction labels. Metadata digest is
   ec38297fd59fd07c2a17e8731c24d4afd01ea6c0b723910ff1de22b4e9f62b6e.
3. All42 parameters must be finite, have the exact approved shape/order, and be
   within1e-10 absolute error (no relative tolerance) of committed reviewed
   reference coefficients. The reference and metadata pin were extracted from
   the previously reviewed e8a2ec2bfc109b28de8b9bbfa2c9727eb275ad493a99b482f064b064b542825a
   artifact after independently verifying its seal. Neither reference is derived
   at runtime from incoming models or a newly generated allowlist.

1e-10 is a conservative numerical portability envelope, not a performance
tolerance. A home log-rate uses4 coefficients, so reference drift is bounded by
4e-10 in log-rate; away uses3. Unknown larger drift abstains and needs review.
No rounding buckets, NaN equality, relaxed provenance, wildcard hashes or
automatic hash approval. A parameter changed by even one ULP in an otherwise
valid submitted artifact still fails exact replay. Runtime/diagnostic fields
excluded from semantic approval remain fully protected by seal and replay.

This supports equivalent models fitted locally on different runtimes. It does
NOT import foreign-runtime artifact bytes through a relaxed verifier: they must
still exactly replay locally or abstain. This preserves the established replay
contract and fails closed on unsupported runtime/numerical differences.

Adapter version is phase3da-shadow-v2; report binds semantic-replay-v1 and fixed
semantic reference, while retaining exact submitted artifact/byte hashes. All
kickoff, rights, trust-root, chronology, mapping, tail-mass, recorder, abstention,
synthetic and retrospective restrictions remain. No genuine prediction published.

## Comparable implementation research

- NumPy main numpy/testing/_private/utils.py assert_allclose and LICENSE.txt
  (BSD-3-Clause), fetched for this task: explicit atol/rtol and strict shape
  comparison. Adopted bounded coefficient comparison; deliberately rejected
  default NaN equality and shape broadcasting. No package added/copied/run.
  https://github.com/numpy/numpy/blob/main/numpy/testing/_private/utils.py
- ONNX atba32230d7a3dafcfe6cee014c6974716da143f9c,
  onnx/backend/test/runner/__init__.py and Apache2 LICENSE: backend comparison
  separates exact output structure/type checks from numerical tolerances.
  Adopted that separation, retaining exact artifact replay as an additional
  security boundary. No ONNX dependency or external test execution.
  https://github.com/onnx/onnx/blob/ba32230d7a3dafcfe6cee014c6974716da143f9c/onnx/backend/test/runner/__init__.py

## Actual tests and limitations

`python -B -m unittest discover -s tests -v`:563 passed in8.432s on Windows
CPython3.12.14. 548 existing tests unchanged plus15 new tests. New tests cover
simulated CPython3.13.5 metadata, deterministic one-ULP libm/diagnostic changes
with exact local replay, drift beyond approval tolerance despite successful
replay, all42 reference coefficients, tiny parameter tampering, runtime relabel,
diagnostic tampering, source identity/license/retrieval changes, recomputed
configuration changes, nonfinite values, metadata/order and report binding.

Simulation patches only the trainer's runtime dependency or deterministic numeric
kernel during BOTH fit and replay. The real verifier is never mocked, disabled or
replaced. Leaving the simulated environment rejects those foreign bytes. These
are explicit compatibility simulations, not Linux executions. WSL reports it is
not installed; Docker/another Linux runtime was not available. Independent Linux
CPython3.13.5 rerun remains requested, including any drift outside1e-10.

Exact export rerun, full logs, protected-file hashes, patch reconstruction and
reviewed semantic reference are in the review ZIP. Actual export timing/counts
are recorded there. No Python3.10 runtime, remote CI or external lint/type check
is claimed. Budget฿0. No dependency, provider, publication or phase expansion.

Files in this follow-up: premfootballbot/shadow_pilot.py, new
tests/test_shadow_model_authorization.py, README.md, this handoff, and a notice
in CODEX_PHASE3DA_IMPLEMENTATION_REPORT.md superseding its old runtime pin.
The original Phase3D-A safeguards and tests remain intact. Request independent
review of the fixed projection/reference and runtime tests before owner merge
approval. PR9 stays draft; do not merge.

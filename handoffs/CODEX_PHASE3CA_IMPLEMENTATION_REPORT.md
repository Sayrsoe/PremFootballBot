# Phase 3C-A engineering handoff

## Authority, repository and scope

Executed the owner's pasted Phase 3C-A requirements, supplied in place of the
unavailable ZIP. Verified local and GitHub main commit
47d18a101107d4c8ea16e7bbcece654e7d8239cd, tree
f03d1bebe4a78e0e1f2ea7a2d8ca356db7895214 before coding. Read AGENTS.md,
README, relevant modules/tests, earlier implementation handoffs and recent
history. Baseline: 450 tests passed in 1.767s, Python 3.12.14 on Windows.
Branch: codex/phase3ca-offline-real-epl-fitting. No subagents used.

Budget: ฿0. Only one isolated module, two test files, one fixture directory,
README and this handoff are changed. All prior Python sources, exports, tests,
fixtures, synthetic protections, AGENTS and dependency configuration are unchanged.
This scope authorizes retrospective real-results fitting only. No deployment,
paid API, scraping, credentials, genuine prematch forecasts, prospective pilot,
automation or merge. Draft PR publication is the owner's explicit instruction;
the implemented library performs no publication or I/O.

## Research before implementation

- [Penaltyblog](https://github.com/martineastwood/penaltyblog/tree/6870f0e762e9cba35fa722dc14a8daeaf8bc6134),
  current master 6870f0e762e9cba35fa722dc14a8daeaf8bc6134, inspected
  penaltyblog/models/poisson.py and LICENCE (MIT), repository freshness and open
  issue listing. Adopted team attack/defense and home-effect log-link structure,
  separate objective/derivatives. Rejected its SciPy/NumPy/Cython dependency stack,
  nonnegative home constraint, forecast methods and normalized probability grids.
  No claim of having run its tests; the prior research recorded unavailable
  football tests at this snapshot. The open issues inspected added no relevant
  numerical guidance.
- [Statsmodels](https://github.com/statsmodels/statsmodels/tree/309691a4d15954c57542e8aacf1891f243dfcabb),
  main 309691a4d15954c57542e8aacf1891f243dfcabb (2026-10-29), inspected
  LICENSE.txt (BSD-3-Clause), genmod/families/family.py Poisson likelihood/deviance
  and genmod/tests/test_glm.py score/Hessian and cross-model assertions.
  Adopted full Poisson likelihood including factorial terms and independent
  numerical derivative checks. No Statsmodels dependency or test execution.
- OpenFootball exact source and full CC0 license inspected again using GitHub's
  connector, with immutable ref and base64 bytes. Code licenses do not grant
  dataset rights. No external executable code was downloaded/run/copied; the
  implementation is independent stdlib mathematics. No new package or security
  exposure from dependencies. The pre-code design note is in delivery evidence.

## Source and rights audit

Repository: https://github.com/openfootball/england
Commit: 9ee7a0c351805c99cc334478a9bf04b7d0432fec
Path: 2023-24/1-premierleague.txt
Git blob: 23cdd8a340b72f6f30c514fbf609d5cf252723aa
Raw SHA256: 0bfb4a7fffe0b1bf7318955686eafeb28fc9676346ae433259e7409d69551450
License: CC0-1.0; LICENSE.md blob 670154e3538863b2d9891fd5483160fbdfc89164
License SHA256: 36ffd9dc085d529a7e60e1276d73ae5a030b020313e6c5408593a6ae2af39673
Accepted-facts SHA256: ac1a691aa44cfb154d6c396934932c96c3eba2d87b1b104a28c7364cdbbb9700

The exact archive and license are deliberately redistributed as authorized CC0
offline regression fixtures, unlike the earlier parser-only package which
excluded bulk results. Their Git blob identities and SHA256 values were checked.
The license retains its accuracy/third-party-rights disclaimers; this audit
establishes the inspected source's stated license, not independently adjudicated
football facts or rights to other data. Nested .gitattributes preserves upstream
CRLF bytes in Git checkouts. SOURCE.json acquisition audit is 2026-10-29;
retrieval is never historical availability.

638 source lines, 380 accepted matches, 20 raw team labels, zero quarantines and
header issues; 235 printed clocks, 145 absent. Each ordered home/away pair occurs
once, each team has 19 home and 19 away matches. Goals: 684 home, 562 away.
Source lines 11, 317 and 634 have independent regression spot checks against
the earlier audit. No timezone or availability is inferred. Printed clocks,
original labels, raw rows, dates and immutable locators remain in the artifact.
2025-26 grammar/data are explicitly unauthorized here.

## API, mathematics and failures

Direct imports from premfootballbot.real_epl_training only:

    fit_real_epl(raw_bytes, *, source, license_bytes, config=RealFitConfig())
    retrospective_json(model) -> bytes
    verify_retrospective_fit(model, raw_bytes, *, license_bytes) -> True

No target, cutoff, forecast, scoring/evaluation or synthetic conversion API.
Input source must match all hard-coded approved pins, repo/path and CC0 evidence.
Exact license bytes are mandatory. The unchanged adapter reparses exact raw
bytes at every fit. Caller-created normalized rows/imports are not accepted.
Incomplete/quarantined/contradictory training coverage fails atomically; missing
scores are never imputed. No automatic source discovery or new season inclusion.

For home i and away j:

    log(lambda_home) = mu + h + attack_i + vulnerability_j
    log(lambda_away) = mu + attack_j + vulnerability_i
    objective = sum(lambda - goals*log(lambda) + lgamma(goals+1))
                + ridge/2 * sum(attack^2 + vulnerability^2)

Positive vulnerability means easier to score against. mu/h are unpenalized;
positive ridge selects the otherwise redundant team gauges (their sums are zero
at convergence). The penalized objective is strictly convex with both venue
observations and finite positive goal totals. Ridge-driven identifiability is
not empirical proof of a useful team-strength model. No low-score correction,
recency weighting, uncertainty estimate or correlated-goal model is claimed.

Sorted teams and date/fixture ordering, league-means initialization, analytic
gradient/Hessian, independent textbook Cholesky solve and Armijo backtracking.
No randomness; extreme trial rates are rejected rather than clipped. Gradient
infinity norm controls convergence, with bounded iterations/backtracking and
atomic failure. Config: ridge 0.01..10000 (default4), iterations1..200(default100),
gradient tolerance1e-10..1e-5(default1e-7). Bool/nonfinite/text values are rejected.
Both venue totals must be positive; degenerate training has no fallback model.

RealTrainingError.code: INPUT_TYPE, BAD_CONFIG, UNAPPROVED_SOURCE, LICENCE,
TRAINING_COVERAGE, TRAINING_METADATA, DEGENERATE_TRAINING, NUMERIC_ERROR,
NOT_CONVERGED, ARTIFACT_TAMPERED, REPLAY_MISMATCH; adapter document/provenance
failures retain their code with SOURCE_ prefix. No partial artifact on failure.

Frozen artifacts contain full source import, configuration, 20 team effects,
380/760 counts, zero-exclusion reasons, runtime/version, source/license/parser
fingerprints, objective trace, gradient norm, totals, penalty, NLL and explicitly
in-sample deviance. Every artifact is RETROSPECTIVE_DESCRIPTIVE_ONLY with false
strict-point-in-time eligibility, unknown availability and no prediction API.
Canonical JSON/SHA256 include all substantive fields and supplied provenance.
Integer/float equivalent config values canonicalize; repeated fits have identical
bytes in the same runtime. Different retrieval metadata changes the artifact
digest but not fitted parameters. Exact replay is intentionally runtime-specific.
Checksums are not signatures; re-sealed parameter/count/row tampering is detected
by recomputing from pinned source. No untrusted JSON deserialization API exists.

## Executed validation and descriptive result

Python 3.12.14, Windows, no third-party dependencies:

- Before coding: `python -B -m unittest discover -s tests -v`: 450 passed, 1.767s.
- First numerical/source test run: `python -B -m unittest tests.test_real_epl_training -v`:
  40 passed, 0.545s. No failed intermediate implementation tests.
- Complete suite: `python -B -m unittest discover -s tests -v`:
  507 passed, 2.545s; 450 unchanged +40 fitting/source/numerical +17 isolation.
- Final source/export integrity checks, Python3.10 grammar inspection and exact
  exported-source rerun are recorded with their actual output in delivery evidence.
  No Python3.10 runtime, external lint/type-check tool or remote CI run is claimed.

Tests cover exact fixture/license blobs, coverage/locators/clocks, deterministic
replay and re-sealed tampering, deleted/changed/reordered/appended/oversized or
malformed input, self-pinning attacks, unapproved seasons/metadata/licenses,
unknown retrieval, invalid configs and convergence failure. Numerical checks use
independent closed-form balanced examples, 50-digit Decimal likelihood, central
finite differences for every gradient/Hessian entry, score equations, shrinkage,
negative home effect, zero-goal venue failures, Cholesky known solutions and row
order invariance. Toy rows remain private numerical tests, never authorized real
training inputs. Tests also enforce unchanged synthetic fit/import/backtest gates,
prospective packet rejection, no clock/network/file calls and protected hashes.

Default pinned full-season fit: 5 Newton updates, no backtracks,
objective1140.7203211251276 = NLL1135.67954203597 + penalty5.040779089157788,
gradient infinity norm7.638334409421077e-14, in-sample deviance749.8711874562165.
Fitted home/away totals684/562 match intercept score equations. These are
descriptive optimizer checks only, not held-out accuracy or historical predictions.
Artifact e8a2ec2bfc109b28de8b9bbfa2c9727eb275ad493a99b482f064b064b542825a
under the recorded fixture provenance and CPython3.12.14 runtime.

## Changed files and integration gate

1. README.md
2. premfootballbot/real_epl_training.py
3. tests/test_real_epl_training.py
4. tests/test_real_epl_isolation.py
5. tests/fixtures/openfootball_2023_24/.gitattributes
6. tests/fixtures/openfootball_2023_24/1-premierleague.txt
7. tests/fixtures/openfootball_2023_24/LICENSE.md
8. tests/fixtures/openfootball_2023_24/SOURCE.json
9. tests/fixtures/openfootball_2023_24/README.md
10. handoffs/CODEX_PHASE3CA_IMPLEMENTATION_REPORT.md

No application integration call sites. An independent reviewer should validate
exact commit/tree/source manifest, rerun all tests and the README example, inspect
pins/rights, math, fixture byte preservation and real/synthetic separation. The
review ZIP includes exact Git source, patch, per-file integrity manifest, actual
test logs, model JSON, source audit and this handoff. Exact self-referential
commit/tree/PR identities are recorded outside the committed report.

No unresolved test failures. Material limitations remain: one retrospective
season, assumed independent constant-strength Poisson process, chosen ridge,
unknown historical availability/timezones, runtime-specific floating arithmetic,
and no predictive validity evidence. Keep draft until independent review and
separate owner merge approval. Prospective pilot, real prematch inference,
automation and deployment remain outside this PR.

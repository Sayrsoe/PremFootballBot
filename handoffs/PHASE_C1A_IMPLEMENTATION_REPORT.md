# PremFootballBot Phase C1-A — synthetic-only provider normalization implementation

## Authorization, roles and scope

Owner explicitly authorized **Phase C1-A synthetic-only provider normalization implementation** and tests, feature branch, and draft PR. No further comments. No live provider access, actual EPL fixtures/odds, real-data fitting, model predictions, deployment, paid services or merges. Starting verified `main`: `8db1884ee2046fc53c4e20409dfa82c5b7014bff`, tree `ba91006cbb20cbae54779687ca2e42c611ee16ea`. PR #19 already merged; no open PRs at kickoff. The previous C1 desk research/independent helper report is **not** interpreted as rights clearance, provider access, or fit authorization.

**Role attribution:** ChatGPT authored and locally executed the bounded patch and tests through available local/GitHub tools. The environment did **not** expose a Codex execution tool, and no separate Codex session or separate independent audit is claimed. The owner may delegate the final independent review to Codex using this PR and exact head/tree.

## Read-only review / research judgement

Read live GitHub `AGENTS.md`, `docs/ENGINEERING_WORKFLOW.md`, `docs/AGENT_HANDOFF_STANDARD.md`, `PROJECT_STATUS.md` (historical-only), tests and existing odds/prospective/C0 implementations. C1 research evaluated OddsPapi and football-data.org but did not certify them. We adopt internal strict team/fixture identity, explicit UTC, exact prices and snapshot/cutoff boundaries. A provider-specific third-party code comparison is not useful for a module explicitly forbidden to support real provider schemas, so no external library or provider SDK was copied or installed. This design deliberately rejects any purported real outcome-to-side mapping.

## Implementation

- `premfootballbot/provider_normalization_lab.py`: pure stdlib frozen invented fixture/market normalization, explicit allowlisted `toy:` identities, `example.invalid` sources, exact caller-supplied alias/outcome mappings, strict status/UTC/price/quarter-line/side validation, consistent timestamp roles and staleness denial, canonical hashing and stable `NormalizationError.code` failures; no IO/clock/network.
- `tests/test_provider_normalization_lab.py`: entirely fabricated fixtures and bookmaker markets; 44 focused tests plus subcases covering every core denial path, including +0.25/-0.25/+0.75/-0.75 and flipped HOME/AWAY mapping. No real provider or 2025–26 holdout data touched.
- `README.md`: additive C1-A reference and explicit limitations.
- This permanent report.

### Scope and known limitations

1. This is **not** a general data ingestion interface: it **requires** literal `toy:` IDs and `example.invalid` sources. It is not wired into C0, result scoring, Poisson fitting or prospective forecasting. No training or market performance claims.
2. Fixture aliases and the outcome mapping are supplied **explicitly** by the caller; correctness cannot be independently validated against a bookmaker. The model does not silently infer home from a vendor outcome `1`, or guess AH sign convention. Future approval must establish these mappings with first-hand evidence.
3. The enforced 900-second maximum age is a **synthetic test policy**, not research validation that a bookmaker's market was available at that time. Self-reported timestamps and `source_content_sha256` labels are not signed evidence; retained source bytes are not used or fetched by C1-A.
4. Rights remain `UNKNOWN` even if inputs try to assert `CLEARED`; `BLOCKED` is rejected outright. This lab cannot certify vendor legal rights.
5. No unique real provider ID crosswalk, no post-match status/result support, no rolling historical odds or in-memory real feed fixtures; these remain future, separately approvable gates.

## Actual local test evidence

- Python 3.13 local isolated C1-A: `python -B -m unittest tests.test_provider_normalization_lab -q` → **44 tests passed**.
- Python 3.13 local C1-A + older B1 baseline modules: `python -B -m unittest tests.test_provider_normalization_lab tests.test_prospective_evidence tests.test_odds_evaluation -q` → **133 tests passed**.
- Full local run over the **older B1 baseline snapshot** exceeded the execution timeout with no result. It is **not** a green full suite and does **not** represent the merged C0/B2A baseline.
- GitHub Actions Python 3.10/3.12 full suite against the **new PR head/tree**: **must be independently checked**; only actual CI logs qualify. Expected count is pre-PR 839 + 44 = 883, not a result claim.

## Reproducible PR handoff

Draft PR only, no merge. Reviewer: verify this precise base/head/tree, only the above four-file diff, previous protected module blob identity, focused and full CI logs, strict synthetic ID/source gates, no provider integration, denial tests for mapping, quote precision, cutoff, rights and result leakage. Independently review all new source and tests. Any actual fixture/odds connector, market quote sampling, training, scoring, retrospective-to-prospective promotion, and deployment require new approval. User must approve the exact reviewed head before any squash merge. GitHub branch ruleset is not yet active; manually enforced review gate remains necessary.

## Independent Codex audit follow-up — 2026-11-01

The independent Codex audit of original PR #20 head `b580fc485cc00497d0b69969113ebcc8256711b1` returned **REQUEST CHANGES** for two P2 failures despite successful original CI (883/883 on both versions):

1. Decimal arithmetic (`normalize()`/multiplication/abs) depended on ambient thread-local precision and Inexact traps, changing invented price `1.01` to `1` and handicap `-19.75` to `-20` (`-79` to `-80` quarter units).
2. Rehashed forged fixture JSON containing `NaN`/`Infinity`/`-Infinity` surfaced a plain `ValueError` rather than the documented coded `NormalizationError`.

Remediation stays inside the existing C1-A synthetic-only scope. The price/handicap boundary and quarter-unit conversion use exact context-independent `Fraction(Decimal)` arithmetic, with decimal text formatted directly instead of calling context-dependent `normalize()`. Fixture replay rejects nonfinite JSON constants at parse time and converts them to the stable `FORGED_FIXTURE` denial. Four permanent regression methods cover low-precision/alternate rounding/Inexact traps, signed `±19.75` AH lines, exact gross price boundaries and three forged nonfinite constants. Source/map/clock/rights semantics and existing protected files are unchanged.

**Review gate:** run focused tests, complete GitHub Actions Python 3.10/3.12 suites and independent adversarial audit on the new exact head. The original 883-test CI evidence is not evidence for the patched head. Draft PR only; owner must separately authorize an exact reviewed head for squash merge. No provider access, model fitting, scoring or deployment.

### Remediation local validation (not an exact-repository full-suite claim)

- `python -B -m unittest tests.test_provider_normalization_lab -v` in the isolated synthetic C1-A patch workspace: **48/48 passed** (the prior 44 plus four new adversarial test methods).
- `python -B -m unittest tests.test_provider_normalization_lab tests.test_prospective_evidence tests.test_odds_evaluation -q` on a previously available **older B1-only local baseline snapshot** with the patched C1-A module/tests added: **137/137 passed**. This is **not** the complete merged C0/B2A repository; only exact-head GitHub Actions can verify full regression.
- Original-head reproduction before repair showed `1.01` becoming `1`, `-19.75/+19.75` becoming `-80/+80` quarter units, an `Inexact` exception under precision-one trap, and a bare `ValueError` for forged nonfinite fixture JSON.
- No genuine EPL fixture, rights-cleared provider input, market quote, historical replay, trained model, forecast or score was introduced or tested by these fixes.

## Second independent re-review remediation — 2026-11-01

Codex's read-only re-review of PR #20 repair head `fd396ec141800970ae685ea826674dc9a47e38a6` confirmed the original two P2 fixes and identified one remaining **P2 structured-denial defect**: a rehashed fixture with a legal JSON number token such as `1e999` or `-1e999` in `assurance` was parsed by Python's default float decoder into an infinity. The subsequent `allow_nan=False` serializer raised a bare `ValueError` outside the fixture parser's coded `FORGED_FIXTURE` boundary. This was not a rights/model bypass, but violated the stable `NormalizationError.code` contract.

**Scoped correction:** Frozen fixture schema fields are strings exclusively. The fixture replay decoder now supplies `parse_int` and `parse_float` rejecting **all** JSON numeric tokens, in addition to the existing `parse_constant` rejection of `NaN`/`Infinity` extensions. The existing bounded parser catch converts them to `NormalizationError(code="FORGED_FIXTURE")` before canonicalization. No ambient floating-point conversion occurs during frozen-fixture JSON replay; valid existing string-only canonical bytes are unchanged. A permanent adversarial regression covers rehashed `1e999`, `-1e999`, underflow `1e-999`, integer `42`, and ordinary fractional `0.5` with exact denial code assertions.

Previous successful CI of 887 tests belongs **only to the previous head**. Verify the new repair head's exact source/tree and complete GitHub Python 3.10/3.12 CI logs before review. No provider access, auth-rights upgrade, fitting, forecast, deployment, scope expansion or merge is authorized. Keep PR draft and request a new independent re-review plus owner's separate exact-head merge approval.

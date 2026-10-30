# GitHub branch ruleset setup — owner/admin guide

This is **instructions only**; no branch protection or ruleset was created by this documentation change. A GitHub API query returned an empty repository ruleset list on 2026-10-31; reading branch protection was forbidden to the connected integration, so other protection could not be verified. Recheck the settings in GitHub before asserting protection is active.

## Prerequisites
1. Independently review and separately authorize/merge [PR #15](https://github.com/Sayrsoe/PremFootballBot/pull/15). It adds `.github/workflows/quality.yml` and the test matrix.
2. Separately review and authorize/merge this follow-up **after** updating its stacked PR base to `main`. Do not use a docs PR as merge approval.
3. Open the repository as an authorized admin in [GitHub](https://github.com/Sayrsoe/PremFootballBot/settings/rules). Ruleset options and enforcement for **public versus private** repositories and account plans may differ. Do not purchase or upgrade a plan without new approval.

## Recommended manual steps
1. Navigate to **Repository → Settings → Rules → Rulesets → New branch ruleset** (labels may vary).
2. Choose a descriptive name such as `main-approval-and-quality`; target **branch `main` only**. Start with `Evaluate` if offered, then switch to `Active` after verifying behavior. `Evaluate` does **not** block merges.
3. Require pull requests before merging, and block deletion/force pushes on `main` if available. Minimize bypass actors; inspect any inherited permissions/bypass lists. Ideally prevent direct pushes to `main`.
4. Require status checks **only after** the checks appear in a completed PR run from trusted GitHub Actions. For PR #15, the jobs are:
   - `Unit tests (Python 3.10)`
   - `Unit tests (Python 3.12)`
   The workflow display name is `Python quality gates`, **not itself a job**. Pick the actual check names shown in GitHub's UI; if GitHub prefixes names, use the exact displayed contexts.
5. Consider requiring conversation resolution. If requiring an approval review, understand that single-maintainer repositories may not allow self-approval. Choose only a feasible policy; **ChatGPT review + owner's explicit exact-head approval** is the project process regardless of GitHub's reviewer enforcement.
6. Restrict merges/allowed methods if your plan supports it. Prefer squash merges after independent review and explicit owner approval; **do not enable auto-merge**. A ruleset cannot verify that a ChatGPT conversation approved the exact SHA.
7. Save the ruleset. Verify it is **Active** and targets `main`. Confirm status checks are tied to their intended GitHub Actions workflow if that control is offered.

## Test enforcement safely (no deliberate production disruption)
- Verify a new harmless **draft PR** triggers both checks and displays completed statuses.
- Inspect whether GitHub blocks direct pushes, missing checks and unapproved merges as configured. Do not try to bypass actual protection or modify main to test.
- Verify no unexpected rules block authorized maintenance or require an impossible self-review.
- Record date, admin verification method, exact rule name, status and check contexts in a separately approved project-status PR. Do **not** store secrets, tokens or screenshots containing sensitive data.

## What this does and does not guarantee
| Enforcement | GitHub ruleset | Project review procedure |
| --- | --- | --- |
| Tests checked on PR | Possible after checks exist and rule is active | Verify exact-run SHA and job conclusions |
| Prevent direct push or force push | Possible if active and permissioned | Respect owner-controlled main |
| Require human GitHub approval | Plan/team/reviewer dependent | Owner must explicitly authorize the exact PR/head in conversation |
| Prevent fraudulent live-odds/forecast claims | **No** | Independent data-rights, timing, leakage and evidence review |
| Know when a forecast is valid | **No** | Genuine pre-match snapshots, forward validation and calibration |

## Troubleshooting and fallback
- **Settings unavailable / 403:** connected-app API access is not equivalent to admin UI rights. Use repository admin interface, or report `UNVERIFIED / NOT ENFORCED`. Do not call it protected.
- **No status checks to select:** wait until workflow runs on a PR at the correct head; choose actual job names, not guessed contexts.
- **No rulesets permitted on plan:** use workflow CI plus explicit owner/ChatGPT review as a *process*, document that main is not technically protected, and do not pay to upgrade without approval.
- **CI skipped/pending/unavailable:** stop; never claim a passing required check or merge readiness.
- **Status shows success but approval missing:** still **do not merge**.

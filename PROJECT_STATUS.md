# PremFootballBot — project control and status

> **Snapshot:** 2026-10-31. This is a manually maintained, evidence-linked status note, **not** a live dashboard. Verify GitHub PRs, CI and branch SHAs before acting. This file never grants implementation, merge, live-data or fitting authorization.

## Mission and hard boundaries
- EPL-first, Asian Handicap-first, free/permissioned data only; budget THB 0.
- Preserve point-in-time provenance, prospective versus retrospective separation, synthetic safeguards, data rights and exposed-holdout boundaries.
- No unapproved model fitting/tuning, new data ingestion, production/live predictions, purchases/wagers, paid services, deployment or merge.
- A demonstration win, good-looking EV or successful CI job is not proof of forecasting edge. No real-world profitability claim.

## Verified repository checkpoint (as of snapshot)
| Track | Evidence-backed state | Caveat |
| --- | --- | --- |
| Released `main` | Through Phase 4C2-A; [PR #14](https://github.com/Sayrsoe/PremFootballBot/pull/14) merged into main at `e055e4df76aad0d982e6524ff147fecf4b5e4024` | Recheck main SHA before new implementation. |
| Last documented full suite on main | 743 passing tests reported for Phase 4C2-A; see [README](README.md) and [Phase 4C2-A handoff](handoffs/CODEX_PHASE4C2A_IMPLEMENTATION_REPORT.md) | This is historical reported evidence, not a test run performed by this status document. |
| Engineering workflow foundation | [PR #15](https://github.com/Sayrsoe/PremFootballBot/pull/15), draft/open at `3c0b90b1deecd7d6cdaedc1a78577dbc65dcd08f` when checked | PR #15 is NOT on main as of snapshot. |
| PR #15 checks | GitHub Actions run [#41113508841](https://github.com/Sayrsoe/PremFootballBot/actions/runs/41113508841) completed successfully on Python 3.10 and 3.12 | Recheck when PR head changes. Successful unit tests do not establish prediction validity. |
| This documentation follow-up | Separately approved workflow-only change, stacked on PR #15 | Must be reviewed/merged only with new exact-head approval, after handling dependency on #15. |
| Real forward-looking EPL/AH validation | Not established; shadow/provenance/evaluation modules exist | No verified pre-match shadow decision, feed availability/rights, live accuracy, ROI or CLV is claimed. |

## Current milestone and owner gate
**Milestone:** make ChatGPT–Codex–GitHub collaboration durable and low-friction without changing football models.

**Approved scope for this follow-up:** project-status document; standard task allocation and Codex completion-report format; GitHub ruleset setup instructions; links in existing workflow documentation. **No model/data/CI logic change.**

**PR dependency:**
1. Independently review [PR #15](https://github.com/Sayrsoe/PremFootballBot/pull/15) and its exact head/CI, then obtain separate owner authorization to merge it. Do not treat this status as approval.
2. Review the follow-up draft PR against the PR #15 feature branch; verify only intended documentation changes.
3. After #15 is separately approved and merged, retarget the follow-up PR to `main` (and reconcile if needed). Recheck changed-file inventory, head/tree and CI, then seek its **own** exact-head merge approval.
4. Only after merging accepted workflow changes should an authorized maintainer enable and **verify** branch rules; [setup guide](docs/GITHUB_RULESET_SETUP.md).
5. Choose a **new** scope and get owner approval before any Phase 4C2-B, genuine pre-match ingestion, odds collection, fitting or model work.

## Next task allocation (no execution authority implied)
| Role | Next contribution | Required evidence |
| --- | --- | --- |
| Owner | Approve exact-head PR reviews and decide whether to enable settings | Explicit approval recorded in chat/PR, never inferred from CI. |
| ChatGPT | Check status/refs, plan approved work, independently review patches and tests | PR link, base/head/tree, scope comparison, concise risk and action report. |
| Codex | Implement only separately approved changes in its own branch; draft PR | Source/patch audit, actual commands/results, full [handoff](docs/AGENT_HANDOFF_STANDARD.md). |
| Research helper (optional) | Targeted source licensing/availability or independent reference checks | Links, publication/verification timestamps, terms, uncertainties; no implementation. |
| GitHub | Source of truth for commits, PR discussion, checks and rulesets | Current refs and settings, not this static snapshot. |

## Update discipline
- Update this snapshot **only** in an approved workflow/documentation PR after a material milestone/merge; record the evidence links and exact observed date.
- Do not mutate a reviewed PR head after owner approval without re-review.
- Keep **confirmed**, **reported**, **pending**, **unverified** and **blocked** labels distinct.
- Never update historical statuses as if verified today, and never assume this file refreshes itself.
- For current work, first inspect [AGENTS.md](AGENTS.md), [engineering workflow](docs/ENGINEERING_WORKFLOW.md), [handoff standard](docs/AGENT_HANDOFF_STANDARD.md) and current GitHub PRs.

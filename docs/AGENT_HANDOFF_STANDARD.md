# Agent allocation and Codex completion standard

This is a **reusable process template**, not blanket permission to implement. The owner approves the task and scope **before** a concrete Codex task is issued. For ordinary tasks, one detailed chat prompt is enough; ZIP packages are optional. GitHub holds durable artifacts and review history.

## Step A — ChatGPT's proposed task allocation (before implementation)
Copy and adapt the following, then request owner approval:

| Field | Required value |
| --- | --- |
| Milestone and outcome | One measurable result; why it is needed. |
| GitHub starting point | Repository, target branch, exact starting SHA, relevant prior PRs and dependencies. |
| Scope | Files/modules/behaviors allowed; explicit exclusions and protected artifacts. |
| Owner authorization | Research only, docs only, implementation/tests, or fitting; distinguish each permission. |
| ChatGPT | Scope/architecture, research synthesis, review criteria and independent review. |
| Codex | Specific bounded modifications, tests, evidence and **draft PR** only. |
| Research helper (if useful) | Specific external evidence question; provider rights and links; no code edits. |
| Acceptance criteria | Verifiable tests, fixtures, protected-file diff, documentation and failure/abstention behavior. |
| Stop conditions | Missing permission/source rights, changed baseline, unapproved live/paid activity, evidence integrity failures. |
| Owner's comments | Free-text feedback incorporated into approved scope before prompts/code. |

**Owner choices:** `APPROVE <scope>`, `REVISE <comments>`, or `RESEARCH ONLY`. No silence, successful test or previous merge is an approval. If the approved scope changes materially, return for authorization.

## Step B — Detailed Codex execution prompt contract
Only after explicit scope approval, provide a copyable prompt that:
1. Names the exact repo, starting point and one authorized milestone, including permitted files and forbidden changes.
2. Directs Codex to read `AGENTS.md`, `docs/ENGINEERING_WORKFLOW.md`, this standard, current status and relevant handoffs; verify live refs before editing.
3. Requires scoped repository inspection and appropriate external technical research/licensing checks (or a reason no outside research is needed).
4. Specifies concrete acceptance tests and independent oracles when relevant, strict provenance/cutoff/holdout controls and explicit abstentions.
5. Requires a distinct feature branch, isolated changes and a **draft PR**, with no merge/deployment/paid APIs/live bets.
6. Requires actual reproducible test commands and outputs, base/head/tree SHAs, precise changed files, CI job status, risks, remaining work and links.
7. Requires Codex to stop and report if assumptions, permissions, frozen baselines or required evidence are missing. It must not invent approvals, tests, fixture metadata or market odds.

## Step C — Codex completion report (paste into draft PR body or checked-in handoff)

### 1. Scope and approval
- Approved milestone, approving instruction, date and explicit exclusions:
- Starting branch/SHA and dependency PRs:
- Scope deviations: NONE, or blocked/reapproval required:

### 2. Research and decision record
- Repository files/previous implementations inspected:
- External references/licenses or why none are necessary:
- Decision rationale, alternatives rejected and identified data/usage rights:

### 3. Change inventory
- Feature branch and draft PR:
- Added/changed/removed files with purpose:
- Invariants, protected baseline/fixtures and unchanged logic:
- Dependencies/services/secrets introduced: NONE, or explicit approved list:

### 4. Verification — distinguish claims
- Local runtime and commands **actually run**, pass/fail/skips, exact totals:
- CI workflow run URL(s), job conclusions and SHA, or **PENDING/UNAVAILABLE**:
- Independent mathematical/security/leakage/source integrity verification:
- Checks **NOT** run and why:
- If tests were reported by an earlier PR, cite them as **prior reported evidence**, not this PR's own execution.

### 5. Data/model-specific assurance (if relevant)
- Data origins, permitted licenses, raw hashes and exact acquisition/publication timestamps:
- Forecast cutoff, training/target isolation, unknown kickoff/availability policy:
- Exposed holdout use and abstentions:
- Evidence level: SYNTHETIC, RETROSPECTIVE DESCRIPTIVE, SHADOW LOCAL-ONLY, or prospectively verified (only with support).
- NO prediction/ROI edge claim unless genuinely demonstrated.

### 6. Integrity and reviewer handoff
- Base commit SHA:
- Head commit SHA:
- Head source tree SHA:
- File diff/inventory and replay instructions:
- Risks and unresolved blockers:
- Proposed next separately approvable task:
- **Merge state: NOT MERGED; waiting for exact-head independent review and owner approval.**

## Step D — ChatGPT's independent reviewer response
Report (a) exact live base/head/tree, (b) diff and protected-file impact, (c) CI versus locally observed test evidence, (d) permission/data/temporal risks, (e) outcome `APPROVE FOR OWNER DECISION` / `REQUEST CHANGES` / `BLOCKED`, and (f) one clear owner decision. Reviewer approval is **not** merge authorization.

## Maintain continuity without extra owner work
- Keep key decisions, repo refs, final reports and PRs in GitHub; status snapshot is manually updated.
- Do not require the owner to shuttle ZIPs, replay commands or copy agent output when GitHub access can provide source and evidence.
- Update `PROJECT_STATUS.md` in an approved PR when the milestone changes; never rewrite historical hashes/claims or silently perform unrelated work.

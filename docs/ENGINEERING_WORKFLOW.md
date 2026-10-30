# PremFootballBot engineering workflow (permanent)

## Responsibilities
- **Owner:** supplies goals, authorizes the specific implementation scope, accepts or rejects reviewed PRs, and explicitly authorizes each merge or deployment.
- **ChatGPT:** research/architecture, detailed copyable task prompts directly in chat, risk/acceptance criteria, independent PR source/integrity review. No mandatory ZIP.
- **Codex:** inspect repository and comparable GitHub implementations when useful; implement only the approved scope on a feature branch, run checks, provide readable results and a **draft PR**.
- **GitHub:** persistent source of truth for code, tests, decisions, audit reports and CI status. Extra GitHub handoff files or binary ZIPs only when necessary.

## Default project cycle
1. User and ChatGPT define scope, non-goals and acceptance conditions; clarify whether an approval covers research only, implementation/tests, or fitting.
2. ChatGPT produces a **detailed task-specific prompt in chat**. Codex reads `AGENTS.md`, this document, relevant files and prior reports. Research similar GitHub projects before substantive changes, noting useful patterns and licenses.
3. Codex makes a feature branch, minimal implementation, appropriate focused tests, and the full offline suite. Do not alter protected files or data source pins without explicit authorization.
4. Codex creates a draft PR with the PR template completed. Provide reproducible commands, test counts, changed files, base/head/tree SHAs, known limitations and risk/temporal-provenance status. Keep review materials readable on GitHub; do not require a ZIP.
5. GitHub Actions runs Python 3.10 and 3.12 unittest matrices on PR and main. A reported green CI check does not itself prove mathematical correctness, data validity or predictive quality.
6. ChatGPT independently checks exact approved base/head/tree, changed-file inventory, source integrity, scope, tests and leakage boundaries. If independent tests cannot be executed, say so; distinguish local/CI/replay evidence.
7. Owner explicitly approves the exact reviewed PR/head for merge. Revalidate the live branch and tree immediately before merge. Squash-merge only the authorized PR. Separately verify new main commit/tree and PR state. No auto-merge or implied permission for the next phase.

## Security and data governance
- Keep Actions unprivileged (`contents: read`), avoid `pull_request_target` and PR-origin secrets, never execute unknown remote install scripts or grant AI tools unrestricted credentials.
- Pin data provenance/identities; clearly distinguish retrospective archives from proven pre-kickoff availability. Protect exposed evaluation sets from hyperparameter selection. Keep fixture coverage and abstentions explicit.
- Preserve synthetic/prospective safeguards, fixed evidence, licensing records, and existing model authorization restrictions.
- No paid APIs, wagers, live predictions, fitting, tuning, or deployment without separate owner approval.
- If CI fails or cannot start, report its state; do not claim a passing check. An owner may authorize a narrowly scoped follow-up fix.
- GitHub Actions may require repository Actions permissions and usage quota. Branch protection / required checks are a separate repository setting that may require owner admin privileges. Do not claim rules are enforced until verified.

## Efficiency
- Do not mandate ZIPs or create temporary task files in GitHub for ordinary tasks. Use long, directly copyable prompts in chat.
- Selectively delegate independent research/review; avoid multiple AIs doing identical work.
- Permanent documents: `AGENTS.md`, this workflow, final implementation reports and PRs. Delete only *task-created* scratch work; never delete previously approved evidence or source.
- Check available tools before promising in-chat actions. Never silently broaden scope or merge without explicit approval.

## PR acceptance checklist
- Scope match and clean diff; no secrets/unexpected dependencies.
- CI and focused tests, plus independent math/security/leakage checks as relevant.
- Provenance/cutoff/holdout correctly labelled; no claim of new validity from retrospective data.
- Exact head/tree reverified against the independent-review decision.
- Owner's explicit merge authorization recorded.

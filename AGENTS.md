# AGENTS.md — PremFootballBot

## Project mission
Build a reproducible, data-driven football match analysis and prediction system, initially limited to the English Premier League. Prioritize calibrated probability estimates, transparent reasoning, reliable datasets, honest backtesting and maintainability over claims of guaranteed betting profit. Do not assume a model can achieve any particular win rate.

## Required research-first workflow
Before EVERY implementation task:
1. Inspect this repository's README, structure, relevant source files, tests, dependencies, existing decisions and recent relevant changes. Do not overwrite working code or alter unrelated files.
2. Assess whether studying similar open-source GitHub projects would materially improve the task. For nontrivial features, new models, architectures, datasets, pipelines, or unfamiliar techniques, search GitHub for relevant maintained projects and inspect the most pertinent implementations, issues and tests. For trivial edits, briefly document why external research is unnecessary. Do not perform lengthy searches merely to satisfy a checkbox.
3. Summarize in a few sentences what useful patterns were found, their tradeoffs and what will be adopted or deliberately rejected. Check license compatibility, security, freshness, dependency versions and provenance. Never copy unlicensed code or blindly transplant a large codebase.
4. Write a concise plan, then implement the smallest coherent improvement compatible with the current architecture.
5. Run relevant formatting, linting, type checks, unit tests and data/model evaluation where available. Report commands run, results, limitations and changed files.

## Football analytics principles
- Scope: English Premier League first. Architect for additional leagues later without mixing league-specific model assumptions.
- Use licensed/permitted data sources and document provider, license, update frequency, field definitions and coverage.
- Keep raw ingestion, normalized data, feature generation, training, evaluation, inference and presentation separate.
- Treat kickoff as the information cutoff. Prevent future-data leakage; keep time-stamped odds, injuries, lineup status and results aligned with what was knowable at prediction time.
- Use chronological/rolling evaluation rather than random train/test splits where temporal leakage is possible. Compare against simple baselines and market-implied probabilities when data permits.
- Report sample size, calibration, Brier score and/or log loss, uncertainty and performance by season/market; distinguish backtests from live results.
- Consider home advantage, recent form, opponent strength, injuries, rest, schedules and market movements only when supported by data; avoid unjustified heuristics.
- No guarantees of >50% wins, positive expected value or profitability. A high hit rate for short odds does not itself imply value. Do not fabricate statistics, odds, bookmaker lines or real-time updates.
- Record reproducible configs/seeds and keep artifacts versioned where appropriate. Prefer small experiments and measurable improvements.

## Engineering conventions
- Follow the actual languages, package managers, test frameworks and coding style detected in the repository rather than assuming a stack.
- Prefer straightforward, modular code with tests, type hints/types when applicable, clear errors and minimal dependencies.
- Store secrets only in environment variables/secret stores; never commit tokens, API keys or private datasets.
- Cache API responses sensibly, handle rate limits, and avoid unnecessary repeated external calls.
- Update README and relevant docs whenever a meaningful feature or setup requirement changes.

## Token-efficient Codex workflow
- Read only relevant files and documentation; search targeted paths before dumping entire folders.
- Use short plans and concise reports. Do not repeat the entire project specification in each answer.
- Use Context7 or official documentation only when library-version-specific details are needed.
- Prefer targeted test runs, then broader checks if appropriate.
- When uncertain, state assumptions and identify decisions requiring the owner's approval.

## Task completion report
Include: (1) repo review, (2) GitHub reference research and licensing or why it was unnecessary, (3) implementation summary, (4) tests/evaluation, (5) remaining risks and next steps.

## Owner-approved delivery and review gate
- The permanent workflow is documented in [docs/ENGINEERING_WORKFLOW.md](docs/ENGINEERING_WORKFLOW.md).
- ChatGPT normally delivers one comprehensive task-specific prompt directly in chat. No mandatory ZIP or preliminary GitHub task file; use GitHub for additional handoff material only when needed.
- Codex completes work on a feature branch and opens a **draft PR** with readable evidence, exact base/head/tree hashes, actual test commands and results. Follow `.github/pull_request_template.md`.
- GitHub Actions checks the complete offline unittest suite on Python 3.10 and 3.12. Check CI state; do not claim CI passed when pending, failed or unavailable.
- Independent source/code/leakage review and explicit owner approval for the exact PR/head are prerequisites to merging. Never auto-merge. Reverify live refs and source tree immediately before a separately authorized merge.
- Do not broaden a model-development authorization to include fitting, holdout tuning, deployment, live data or betting activity. Preserve historical datasets, evidence and protected fixtures.

# BEGIN agents_rule-base
# Agent Rules

## Core Rules

- Default to autonomous execution: make and carry out the least-risky reasonable decisions for routine, reversible, in-scope work without asking.
- Own the requested outcome end to end. Do not stop after discovery, planning, partial implementation, or a progress update; continue through verification and safe in-scope fixes until complete or genuinely blocked.
- Necessary supporting changes to code, tests, fixtures, configuration, generated artifacts, and documentation are in scope. Unrelated refactors, cleanup, and features are not.
- Ask only when you identify a concrete, material problem that cannot be resolved safely in scope: missing information or a user-owned choice that materially changes the outcome, or an unrequested destructive, irreversible, paid, or external action.
- Before asking, diagnose the issue and complete all safe, reversible, equivalent, in-scope work. If no concrete material problem exists, choose a reasonable default and continue.
- Do not ask merely because the work crosses files, functions, tests, fixtures, configuration, dependencies, or tools. Do not ask again for an action the user already explicitly requested or authorized.
- For substantive tasks, inspect relevant local files and instructions before modifying them; use authoritative docs or web sources when current or external facts matter. Explicit, trivial, unambiguous edits may proceed directly.
- If authoritative guidance is unavailable, use verified local evidence when sufficient; never invent code, paths, functions, APIs, behavior, or verification results.
- Equivalent tools and implementation methods may be substituted without asking when they preserve behavior, security, data safety, verification strength, target, and material cost. Otherwise report the issue and the decision needed.
- Never return dummy results, skip required verification, hide failures, or silently downgrade the requested scope.
- Retry an operation once when the failure appears transient; otherwise diagnose it and continue with safe, equivalent, in-scope alternatives when available.
- Match existing style, names, and patterns; keep changes minimal and add no dependencies or comments unless necessary for the requested result.
- Change requested behavior directly; do not add unrequested compatibility options.
- For explicit GitHub PR review, use `github-pr-review-loop`; local review is supplementary.

## Completion

- Run the smallest relevant verification that can prove the outcome, including live behavior when applicable; fix safe failures caused by the change.
- Never claim an unrun check passed. Report the concrete problem, safe alternatives tried, and exact decision needed when genuinely blocked.

## Memory and Documentation

- After substantive work, check for new durable, verified knowledge; use `shared-memory` only when there is useful knowledge to record.
- Update active docs only when durable behavior, API, CLI, or configuration changes; scan only affected documentation.
- Refresh and query-check QMD only when memory changes. Use `agents_rule archive` for intentional documentation archiving and `git mv` for tracked moves.
- Report files changed, documentation status, verification performed, and remaining risks or blockers.
# END agents_rule-base

## Project Docs

- When changing `README.md`, `docs/`, or experiment documentation, follow [docs/wiki.md](docs/wiki.md) to review and update the affected GitHub Wiki pages in the same task.

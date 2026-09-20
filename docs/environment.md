# Actual environment

Verified 2026-09-20; public rewrite pilot rechecked 2026-09-21 on Linux x86_64.

| Component | Observed version / location |
| --- | --- |
| Python | 3.14.6, `/opt/miniconda/bin/python3` |
| Z3 | 4.15.4, `~/.local/opt/z3-4.15.4/bin/z3` |
| YoWASP package | `yowasp-yosys==0.69.0.0.post1233`, project `.tools/yosys-venv` |
| Yosys | 0.69, git `9f75ca1f9` |
| Runtime pins | yowasp-runtime 1.96; wasmtime 47.0.1; click 8.5.0; platformdirs 4.11.11 |
| Local project | `~/AIsimpV/rtl-relate` |
| Task worktree | `~/.agent-worktrees/AIsimpV/rewrite-pilot-20260921` |

Z3 executable SHA-256: `b6ae8336dd1be42b8c2a1641cb263f92fbe48aa8367524a227a8b29f3091eb9e`.

Yosys WASM SHA-256: `77fe957bef892d75f74a0ce2165d7b328b6cda462a0e0051509df0c5a55ece49`.

The actual installed launcher hash, WASM hash, version, command, script, source, JSON netlist and BTOR2 hashes are also recorded per frontend invocation. `environment.json` at the experiment root records platform, Python, solver identity, code hash, and Git base/head. A worktree source hash identifies an uncommitted run; a bootstrap Git SHA alone is not presented as the implementation revision.

No sudo, system package installation, Python Z3 package, or NeuroAbs dependency was needed. `scripts/bootstrap_yosys.sh` uses uv to reproduce the isolated frontend. The public-task source revisions and contract hashes are frozen in `fixtures/public/sources.json`; each task has a direct concrete proof using the same property harness and preprocessing.

Independence smoke was executed with PYTHONPATH cleared and Python isolated mode; adding only this project directory to sys.path still imported the package and accepted P1. Full commands and test results are recorded in `SPRINT_REPORT.md`.

The September 21 public matrix uses the bundled `yowasp-yosys-smtbmc` and Z3 for base plus k-induction; SymbiYosys was not used. LLM pilots use Codex CLI 0.154.0 with the existing `gpt-5.6-sol` / `high` setting. Exact per-run tool identities and costs remain in the report evidence. No new system package was required.

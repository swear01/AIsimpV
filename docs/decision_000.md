# Decision 000: independent feasibility slice

2026-09-20. Build a new local project and one Yosys→BTOR2 adapter. NeuroAbs is an external future baseline, not imported or changed. No baseline snapshot has been acquired, and no old LLM calls were rerun.

The checker uses the Python standard library and an existing Z3 CLI. YoWASP Yosys is isolated and pinned under the project `.tools/` directory. There is one RTL semantic export path; SMT-LIB is the solver encoding, not a second RTL parser. State IDs and clock identity come from validated export metadata. Human-authored templates bind to that manifest and are then checked; names alone do not establish correspondence.

The Wednesday slice is P1 and P5, including correct, too-coarse, and bug variants. FIFO, credit, FSM re-encoding, LLM discovery, summary reuse, general relations, and a may–must scheduler are not implemented. The first follow-up should be P2 with a positive nontrivial inductive invariant, because current accepted P1/P5 certificates use J=true.

Two issues found during development became regressions:

1. A failed solver version probe escaped result classification. The gate now returns and saves ERROR for both version and query process failures.
2. Dropping the clock name during export allowed an abstraction on `other_clk` to pass a `clk` contract. Each model now retains validated clock metadata, and both sides must match the frozen contract. Real RTL regression reproduced the old acceptance and confirmed rejection after the fix.

No GitHub repository or remote publishing is needed for this local experiment. Bootstrap base is local commit `8253476`; implementation uses branch `feat/wednesday-feasibility` in a worktree under `~/.agent-worktrees/`.

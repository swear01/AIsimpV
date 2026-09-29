# Candidate 02 changes

This candidate was assembled by the current Codex assistant from the pinned upstream source. It is not an independent clean-session API sample. The substantive step is enabling upstream `RISCV_FORMAL_BLACKBOX_REGS`, which replaces every nonzero register read with `$anyseq` while retaining x0=0. That branch already exists in PicoRV32; this candidate does not demonstrate that an LLM invented the abstraction. The original CPU control, instruction execution, M units, compressed handling, memory path, counters, and RVFI assignments are otherwise unchanged. The unused AXI/Wishbone adapter modules are removed from the file.

This drops the 32×32 exact register file from the relevant synthesized model. It allows arbitrary nonzero operands, unlike the earlier ADD-only zero-operand candidate. It also loses read-after-write consistency and can create register histories that the original CPU cannot. The design can still choose the original read values each cycle in principle, but that behavioral relationship has not been established with a checker.

Text size is 3,049 → 2,516 lines (17.5%). In the upstream RVFI/ALTOPS structural synthesis configuration, generic cells are 12,412 → 7,221 (41.8%). The latter is a size measure, not a solver-speed or assertion-coverage result. See [structural_size.md](../structural_size.md).

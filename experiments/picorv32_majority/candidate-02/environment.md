# Environment and interface differences

The pinned `wrapper.sv`, `checks.cfg`, reset connection, memory inputs, and parameter values are unchanged. The candidate changes internal register-read semantics: x0 remains zero; each nonzero source read may take an arbitrary 32-bit value at that read. Writes still appear in the CPU/RVFI logic but no longer constrain future register reads. This is intended as an abstract verification model, not a synthesizable drop-in CPU implementation.

The candidate uses PicoRV32's existing `$anyseq` branch and therefore relies on the toolchain's nondeterministic-value semantics. Size-only Yosys synthesis was run. No Formal, BMC, simulation, equivalence, or behavior check has been run.

# Environment and interface differences

The upstream `wrapper.sv`, `checks.cfg`, reset connection, and unconstrained `mem_ready`/`mem_rdata` inputs are unchanged as reference files. No new input assumption is introduced.

Inside the candidate, `ENABLE_FAST_MUL=1` and `ENABLE_DIV=1` from the wrapper are ignored: `WITH_PCPI` is fixed to zero, so M instructions no longer use multiply/divide engines. External PCPI support is also absent; the target wrapper leaves `ENABLE_PCPI=0`. This is a genuine reduction of original legal behavior, not a claim of over-approximation.

The unchanged non-M RTL suggests unchanged cycle timing for those paths, but that has not been checked. No Formal, compilation, simulation, or proof has been run on this candidate.

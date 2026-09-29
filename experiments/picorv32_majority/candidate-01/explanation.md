# Candidate 01 changes

This candidate was edited by the current Codex assistant after two separate API generations failed to return usable RTL. It is **not** an independent clean-session sample. DeepSeek Flash returned HTTP 403 after gateway retries. Muse Spark 1.3 Contributor returned HTTP 200 but spent all 16,384 completion tokens on reasoning, ending with no content. The failed raw requests/responses remain in local ignored `results/picorv32_majority/`.

The candidate keeps the original `picorv32` module, register file, fetch, decode, non-M ALU, branch, load/store, compressed-instruction handling, counters, and RVFI assignment paths. The internal PCPI multiply/divide engines become constant inactive wires, and `WITH_PCPI` becomes false. Eight M-instruction task intentions are explicitly sacrificed. The wrapper still passes its original M-enabled parameters, so this candidate intentionally ignores those parameters. Legal M execution from the original wrapper is not represented.

The other large source deletion removes `picorv32_pcpi_mul`, `picorv32_pcpi_fast_mul`, `picorv32_pcpi_div`, AXI/Wishbone adapters, and related helper modules. Those adapter modules are not instantiated by the frozen upstream wrapper. Most of the 946-line text reduction is this file trimming; the actual active hardware reduction is the removed multiply/divide datapath. No solver-size or performance improvement has been measured.

The original and candidate have 3,049 and 2,103 lines. The unchanged parts of the core are still complex. This is a deliberately limited majority-behavior candidate; it does not demonstrate that an LLM found a novel state abstraction.

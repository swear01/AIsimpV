# RTL abstraction: public benchmark shortlist

Date: 2026-09-21. This is a source survey and frontend smoke report, not a completed abstraction experiment. No checker code, contracts, or dependencies were changed.

## Recommended first experiments

1. **ZipCPU skidbuffer**, registered output, DW=8 first and DW=32 next. Public ready/valid implementation with upstream formal properties. Exercise removal of internal payload state while preserving output hold and relevant data relationships. Default DW=8 source exports through the current frontend unchanged, with FORMAL undefined. Certificate and property checking have not been run.
2. **AVR pipeline**, original 32-bit instance. Three 32-bit datapath registers plus two 32-bit historical-value registers used by the property: 96 design bits + 64 monitor bits. Exercise arithmetic relations across pipeline stages. Original embedded assertion currently blocks export; its exact meaning must be carried into a frozen external contract before integration.
3. **ZipCPU sfifo**, proposed depth 4 × width 8, then original default depth 16 × width 8. Exercise pointers/memory to occupancy and a data abstraction. The default source declares 144 design state bits. It requires additional memory and initialization support, so it is a follow-up rather than a ready-to-run case.

Widening the skidbuffer tests encoding/certificate cost; its simple hold property is likely easy even without abstraction. A verification speedup claim needs measured direct-proof difficulty and total candidate costs, including failed candidates. The current complete-state enumerator is a small-case fallback, not a competitive direct baseline for these larger designs.

## Sources and exact revisions

AVR revision: `9a76dc632066c4416cebccda3a4974a4f8adede8`.

- [Dataset description](https://github.com/aman-goel/avr/blob/9a76dc632066c4416cebccda3a4974a4f8adede8/tests/README.md): 535 invariant-checking tasks, including 141 open-source tasks. Check actual files before claiming an RTL source exists; industrial tasks inspected in the tree were distributed as BTOR2.
- [32-bit pipeline](https://github.com/aman-goel/avr/blob/9a76dc632066c4416cebccda3a4974a4f8adede8/tests/opensource/pipeline/pipeline.v): original property is `dataOut == tmp_stageTwo + tmp_stageOne || dataOut == 0`, using fixed-width 32-bit addition. Synchronous reset only clears `dataOut`; do not invent a whole-design reset.
- [16-entry buffer allocator](https://github.com/aman-goel/avr/blob/9a76dc632066c4416cebccda3a4974a4f8adede8/tests/opensource/vis_arrays_bufferAlloc/bufferAlloc.v): alternate future case, 16 busy bits, 5-bit count, 6 latched control/address bits; property `count <= 16`. A busy-set/count relation is a candidate invariant, not a proven certificate.
- [Arbiter to avoid as a nontrivial positive example](https://github.com/aman-goel/avr/blob/9a76dc632066c4416cebccda3a4974a4f8adede8/tests/opensource/h_Arbiter/main.v): client `rand_choice` is constant zero and requests start at zero. Source activity must be checked rather than inferred from the benchmark name.

ZipCPU/wb2axip revision: `2e8d3bc2d26ddc33d1881022a2a2b9d3f0c16b9b`.

- [skidbuffer RTL and properties](https://github.com/ZipCPU/wb2axip/blob/2e8d3bc2d26ddc33d1881022a2a2b9d3f0c16b9b/rtl/skidbuffer.v), [SBY configuration](https://github.com/ZipCPU/wb2axip/blob/2e8d3bc2d26ddc33d1881022a2a2b9d3f0c16b9b/bench/formal/skidbuffer.sby). File declares Apache-2.0. With registered output, 18 bits at DW=8 were measured; 66 bits at DW=32 and 130 at DW=64 are source-based calculations, not measurements. Original FORMAL harness includes reset and upstream hold assumptions.
- [sfifo RTL and properties](https://github.com/ZipCPU/wb2axip/blob/2e8d3bc2d26ddc33d1881022a2a2b9d3f0c16b9b/rtl/sfifo.v), [SBY configuration](https://github.com/ZipCPU/wb2axip/blob/2e8d3bc2d26ddc33d1881022a2a2b9d3f0c16b9b/bench/formal/sfifo.sby). File declares public domain. Memory initialization is unspecified and must remain symbolic. Properties include occupancy/flag relationships and data ordering with a formal monitor.

Retain upstream file headers and provenance when importing; repository-level licensing does not replace third-party file notices.

## Executed frontend smoke checks

All runs used unchanged upstream source and the existing `export_rtl`, with the correct actual clock port. No assertion/property proof was performed.

| Source | Result | What it establishes |
| --- | --- | --- |
| skidbuffer default, FORMAL undefined | EXPORTED; 18 state bits | Datapath/control frontend supports this configuration. `i_reset` is exported as a public input; this does not import the upstream reset/assumption contract. |
| AVR pipeline | UNSUPPORTED: Yosys `write_btor` rejects `$check` | Embedded assertion handling is missing. |
| AVR bufferAlloc | UNSUPPORTED: Yosys `write_btor` rejects `$check` | Assertion handling blocks first; memory handling remains an additional gap. |
| sfifo default, FORMAL undefined | UNSUPPORTED: `$memwr_v2` | Current frontend does not support memory writes. |
| ZipCPU wbarbiter default, FORMAL undefined | EXPORTED; 2 state bits | RTL line count and wide combinational buses do not establish a large sequential problem. Not selected. |

Source survey and smoke logs are retained locally but are not bundled in this repository. The exact upstream revisions and observed outcomes are recorded above; integration issues must reproduce and retain their own exports. The existing P1/P5 demo remains reproducible from this public checkout.

## Standard benchmark pool for later comparison

[HWMCC 2024](https://hwmcc.github.io/2024/) provides single-safety-property competition tasks and published result tables. Its word-level tracks include 319 bit-vector tasks and 321 bit-vector/array tasks. The [v4 dataset](https://zenodo.org/records/14775242) includes BTOR2/AIGER archives, raw results, logs, and bit-level certificates.

This is useful for a standardized later comparison. The distributed transition-system formats alone are insufficient evidence of an RTL-rewriting experiment; retain/find original RTL for tasks used to evaluate LLM RTL changes. No large HWMCC archive was downloaded or run in this survey.

## Integration acceptance criteria

Freeze source revision, parameters, original property, initial/reset behavior, environment, and observations before authoring an abstraction. Preserve the original task semantics, or explicitly label a derivative task and apply the same contract to both the direct baseline and the abstraction method. Do not remove assumptions or add zero initialization to make import succeed.

For each selected pair, record direct proof, certificate checking, abstract property proof, and any concrete replay; include all conversion and failed-attempt costs. Initial external cases establish transfer beyond authored fixtures; acceleration remains a separate experimental question.

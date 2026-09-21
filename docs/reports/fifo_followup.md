# Optional finite FIFO assessment

The 4×8 FIFO assessment is complete; integration remains **UNSUPPORTED**.
Yosys expanded the finite memory into registers without fixing its 32 initial
bits. The production frontend rejects generated undefined-value branches and
anonymous BTOR inputs. Equivalence, certificate checking, and property checking
remain **NOT_RUN**. This is separate from the four-task Wednesday matrix.

## Fixed input and semantics

- [Verbatim sfifo.v](../../fixtures/public/sfifo/sfifo.v) comes from
  [ZipCPU revision 2e8d3bc](https://github.com/ZipCPU/wb2axip/blob/2e8d3bc2d26ddc33d1881022a2a2b9d3f0c16b9b/rtl/sfifo.v).
  The source header dedicates the design to the public domain and is retained.
- SHA-256: `76a653781f1ecca1c1da92c4e5105ecd5d0f832b13cbfd31300ec88d9947e0c1`.
- Parameters: `BW=8, LGFLEN=2, OPT_ASYNC_READ=1,
  OPT_WRITE_ON_FULL=0, OPT_READ_ON_EMPTY=0`; `FORMAL` is undefined.
- Source and parameter provenance is in
  [provenance.json](../../fixtures/public/sfifo/provenance.json).
- One positive-edge `i_clk`; synchronous `i_reset` remains a public input.
  Controls start at `wr_addr=rd_addr=o_fill=0`, `r_empty=1`.
  Four 8-bit memory words have arbitrary initial values and hold until written.
- Reset does **not** guard the memory write at source lines 126–128: a reset edge
  can still write when `w_wr` is true. `o_data` reads memory even when empty.
  No memory initialization, reset guard, or observation mask was added.

## Observed result

The assessment ran on implementation base `9dd8e24` with Yosys 0.69,
git `9f75ca1f9`, using the existing pinned YoWASP installation.

| Stage | Result and retained evidence |
| --- | --- |
| Existing frontend, original parameterized RTL | `UNSUPPORTED`: `$memwr_v2` cell. |
| `memory_collect; memory_map; pmuxtree; opt_clean -purge` | Yosys exits 0; no memory cells remain. `collected.json/il` and `expanded.json/il/v` retained. |
| Initialization and clock audit | 42 register bits: 32 memory bits without init constraints; 10 explicitly initialized control bits, all on positive `i_clk`. Every net alias is inspected for hidden memory init constraints. |
| BTOR initialization audit | Four named BV8 memory states have no `init` record; control states total 10 bits and have `init` records. |
| Production netlist validation | `UNSUPPORTED`: `undefined/high-impedance RTL bit`. Two mux A branches contain X values, mapped to source write lines 127–128. |
| Production BTOR parsing | `UNSUPPORTED`: `BTOR2 line 40 input 3: state/input requires an unambiguous name`. Generated don't-care inputs are anonymous. |

The missing-init restriction is a further known boundary in `parse_btor2`, but
this run stopped at the anonymous input first. Neither X branch was replaced
with zero nor promoted into an assumed environment constraint.

These structural checks establish the reported register/initialization shape.
They do **not** establish normalization equivalence. In particular, no proof
that generated don't-care choices are unobservable has been run.

## Attempts and costs

All four engineering runs are retained, including the initial assessment-script
error. Their raw summaries, full commands, logs, hashes, and matching driver
snapshots are under `results/fifo-followup/`.

| Run | Result | Wall seconds |
| --- | --- | ---: |
| `20260921-01` | `ERROR`: audit expected `r_empty`, whose alias was removed by `opt_clean -purge` | 0.503926 |
| `20260921-02` | `UNSUPPORTED`; audit verifies the original direct `r_empty`/`o_empty` bit alias | 0.599247 |
| `20260921-03` | `UNSUPPORTED`; shared bounded process runner and failure-status handling added | 1.024313 |
| `20260921-final` | `UNSUPPORTED`; final driver and parameter/init audits | 0.603022 |

Total measured engineering-run wall time: **2.730508 seconds**, excluding human
preparation and separate verification. These are script-development attempts,
not additional RTL benchmark tasks or property proofs. Exact driver SHA-256,
costs, and raw-summary hashes are in [fifo-followup.json](data/fifo-followup.json).
A separate missing-executable fault check returned `ERROR`/exit 1 in 0.012550 s.

## Reproduction and next boundary

From the repository root, choose a new output directory:

```sh
python3 scripts/assess_fifo.py --out results/fifo-followup/new-run --yosys .tools/yosys-venv/bin/yowasp-yosys
python3 -m unittest discover -s tests -p test_fifo_frontend.py -v
```

The assessment independently attempts expansion even if original export fails.
Expected semantic `UNSUPPORTED` exits 0; process/error/timeout failure exits 1.
Existing output directories are refused. Four stdlib tests check hidden
initialization aliases, wrong control init/clock, required stage failures,
malformed tool output, and missing or malformed provenance. After an output
directory is created, input and parsing failures retain an `ERROR` summary with
diagnostics; a pre-existing output directory is never overwritten. The last two
tests were added during PR review; the four archived research runs above retain
their original driver snapshots and costs. No production frontend, IR, checker,
or matrix was modified.

The next bounded step is to justify any elimination of disabled-write X branches
and permit arbitrary initial values for the explicitly identified finite state
words. That work needs its own initialization/transition equivalence evidence;
this assessment does not introduce a symbolic-memory implementation.

A future control-only task can observe `o_fill/o_full/o_empty` and use candidate
`h.fill=o_fill`, with `J` relating fill to the modular pointer difference and
empty/full flags. If `o_data` remains observed, the abstract data state must
start arbitrarily and match concrete read values through its mapping/witness.
Discarding memory and freely choosing data cannot establish FIFO ordering;
ordering requires its own frozen property and sufficient data relationships.

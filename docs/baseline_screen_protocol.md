# Native RTL baseline screening

Exploratory screening registered before solver measurements, based on merged `da06227`.
The purpose is to find unchanged public RTL/property tasks with approximately
10-second direct proof cost on the current host (initial target band 5–30 s).

- First six tasks are pinned in `fixtures/public/baseline_candidates.json`, from AVR
  revision `9a76dc632066c4416cebccda3a4974a4f8adede8`; use each original README top file.
- Preserve original RTL bytes, assertions, assumptions, reset and initial-state
  semantics. No hand-written replacement property or forced-zero initialization.
- Use existing pinned YoWASP Yosys and Z3. Normal `prep -flatten`, `chformal -lower`,
  `dffunmap`, `opt_clean`, `write_smt2`; base plus k-induction, depth 20, shared
  45-second budget per task. This native-assertion path deliberately accepts a
  larger input scope than the current certificate frontend. A direct proof is
  not evidence that a certificate or an abstraction already works.
- Run tools serially. Record raw sources, command lines, model/driver/tool hashes,
  logs, solver transcripts, state/cell counts, load, proof and solver time.
  Source download/tool identity are outside per-task proof time but inside suite time.
- SAFE requires both base and induction. Base-only success is BOUNDED; timeout
  is UNKNOWN; reachable assertion failure is CEX, not a successful safety proof.
  Record all outcomes, including import errors and surprising/vacuous cases.
- The first screen is selection data, not a speedup experiment. Qualify promising
  SAFE cases with three fresh-process repeats; report every value/range.
  Changes to task selection or depth are follow-up exploratory runs, named and
  recorded separately. Do not manufacture a ten-second task by adding delay,
  disabling normal optimization or silently changing its property.
- If the first six do not yield candidates, inspect up to eight additional tasks.
  Initial and expanded screening solver budgets total at most 900 seconds;
  confirmation at most 600 seconds. No LLM calls or system package installation.

No claim of acceleration is possible in this screening: no abstract candidate
is being timed. Original Wednesday and fixed-pair timing evidence remain unchanged.

## FIFO follow-up protocol amendment (before execution)

The initial eleven tasks yielded no 5–30 s SAFE candidate. Four were SAFE under
one second; two timed out; four were BOUNDED; one had a native CEX. Huffman
decoder was additionally excluded because its output range makes the original
property combinationally true. No measured result has been replaced.

Use the remaining three task slots for the pinned ZipCPU sfifo full upstream
FORMAL properties: 16×8 synchronous read (`prf`), 16×8 asynchronous read (`prf_a`),
and the supported BW=32 synchronous parameter variant. Preserve all original
assertions, initial state and any assumptions; define SFIFO as upstream does.
Use **depth 4**, as specified by upstream sfifo.sby, rather than making B0 spend
extra time at depth 20. Keep the same Z3 engine and shared 45 s cap. This is a
separate run; its code/config hashes and costs are retained. These native proofs
do not remove the known symbolic-memory/initialization limitations of the
certificate frontend.

FIFO first preparation attempts returned ERROR before any solver call: current
Yosys requires `async2sync` before lowering edge-triggered `$check` assertions.
Add this normal single-clock formal preparation pass (as in SBY); preserve the
three failed attempts and their original driver snapshot. Regressions now use
edge-triggered assertions and require correct SAFE/CEX/no-assert classifications.
Rerun FIFO in a new directory with unchanged source, parameters and depth.

## Supported FIFO capacity sweep (before execution)

The fourteen initial/expanded tasks yielded no 5–30 s SAFE task. The three FIFO
configurations all proved the full upstream 28 assertions at depth 4 in about
1.8 s. Extend the exploratory task count by three supported parameter variants:
synchronous-read BW=32, LGFLEN=5/6/8 (32/64/256 entries), unchanged original
RTL/properties and depth 4. This measures natural storage-capacity scaling, not
added unrolling depth or a weakened property. Same 45 s per-task cap; cumulative
screening solver budget remains <=900 s. Keep all previous results. If a variant
is in the target band, confirm it with three fresh-process repetitions.

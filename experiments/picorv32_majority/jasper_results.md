# PicoRV32 86-task JasperGold assertion check

This follow-up checks the 86 generated assertion tasks in the pinned riscv-formal `checks.cfg` against the original PicoRV32 and candidate 05. The generated cover task and three hand-written `.sby` tasks are outside the 86-task denominator. This is a **bounded assertion comparison**, not an equivalence or behavior-inclusion certificate.

## Method

- JasperGold 2025.03 FCS reads the SystemVerilog checker, wrapper, and RTL directly. Yosys and Boolector are not part of this run. On the local Ubuntu 26.04 host, `-allow_unsupported_OS` is needed to start this Jasper release.
- For each generated `.sby`, `run_jasper.py` extracts its `defines.sv`, checker source, and pinned include files. Original and candidate use the same checker, defines, wrapper, clock, and reset. The pinned `rvformal_rand_const_reg` declarations require a fixed but arbitrary value over the trace; Jasper's native `assume -constant` supplies that meaning. Without it, the six cross-instruction baseline tasks falsely show counterexamples. Each run elaborates `rvfi_testbench`, sets `clock clock` and `reset reset`, then uses Jasper's `set_max_trace_length` and `set_prove_target_bound` at that task's `RISCV_FORMAL_CHECK_CYCLE` (15, 20, 25, or 30).
- `prove -all` gets 60 seconds of proof time and at most four Jasper jobs per run; four tasks run concurrently. A further 120-second process watchdog catches startup or shutdown hangs. An assertion task is `pass` only when every assertion is proven or user-bounded-proven, `fail` when any assertion has a counterexample, and otherwise `incomplete`, `timeout`, or `error`. Cover reachability is reported separately; a pass can be vacuous.
- The pinned wrapper leaves memory response nets undriven; Jasper treats them as free signals and warns about them. Jasper also warns that an original-core multiplication operator is automatically black-boxed. These warnings limit interpretation of a pass, particularly for M tasks; the original/candidate comparison is within the same Jasper setup.

## Results

| Task group | Original bounded pass | Candidate 05 bounded pass | Candidate 05 counterexample |
| --- | ---: | ---: | ---: |
| RV32I | 37/37 | 37/37 | 0 |
| M | 8/8 | 0/8 | 8 |
| C | 25/25 | 25/25 | 0 |
| Register / PC / order | 6/6 | 6/6 | 0 |
| CSR | 10/10 | 4/10 | 6 |
| **Total** | **86/86** | **72/86** | **14** |

There were no timeouts, incomplete tasks, or tool errors in the final selected results. Candidate 05 reaches **72/86 = 83.7% bounded assertion-task passes**, above the 69-task numerical target. This is evidence for those checkers only at their configured cycles; it is **not** an 83.7% behavior-inclusion result or an abstraction certificate. The 86 task names are correlated, and a bounded pass does not prove later cycles.

All 62 passing non-M instruction tasks have the check-cycle `cover(check && spec_valid && !trap)` covered. The four passing CSR tasks and six passing register/PC/order tasks also have covered assertion preconditions. For the eight removed M tasks, the original nontrapping check-cycle cover is covered, while candidate 05's is bounded-unreachable. Each M candidate task has an assertion counterexample. The six additional CSR counterexamples are `csrc_inc_{mcycle,minstret}_ch0`, `csrc_upcnt_{mcycle,minstret}_ch0`, and `csrw_{mcycle,minstret}_ch0`; all six original tasks pass. Earlier selective checks associate the CSR difference with removing the PCPI waiting/timeout path along with M; this full-suite run alone does not isolate the cause.

The first bulk run checked all 86 tasks for both designs. Ten tasks used `rvformal_rand_const_reg`; they were rerun for both designs after restoring constant-over-trace semantics with `assume -constant`. [The tracked JSON](jasper_results.json) selects those 20 corrected reports and the other 152 bulk reports. Raw `console.txt` and Jasper project directories remain under Git-ignored `results/picorv32_majority/jasper-{bounded-all,const-corrected}-20260930/`; each JSON log path is relative to `results/picorv32_majority/`.

## Reproduce

In the repository root, point `CHECKS` at the `cores/picorv32/checks` directory generated from pinned riscv-formal `c992aa61fdfe0846c5ed90324c596202a1c69b76`:

```sh
source /apps/eda/cadence/jasper.sh 2025.03
CHECKS=/path/to/pinned-riscv-formal/cores/picorv32/checks
python3 experiments/picorv32_majority/run_jasper.py \
  --checks "$CHECKS" --output "$PWD/results/picorv32_majority/jasper-bounded-all" \
  --design both --jobs 4 --timeout 60
```

The output directory contains `summary.json` and, for each design/task, `run.tcl`, `console.txt`, and the Jasper project. It is Git-ignored. The task-by-task machine-readable results from this run are tracked in [jasper_results.json](jasper_results.json).

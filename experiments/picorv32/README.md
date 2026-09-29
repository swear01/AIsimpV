# PicoRV32 ADD formal rewrite pilot

This case gives the model the complete 3,049-line `picorv32.v` from [YosysHQ/picorv32](https://github.com/YosysHQ/picorv32/tree/ef203c2b0a3fb793280f5114941416c425c5b461) and targets `insn_add_ch0` from [riscv-formal](https://github.com/YosysHQ/riscv-formal/tree/c992aa61fdfe0846c5ed90324c596202a1c69b76). The original `checks.cfg` selects `rvfi_insn_check` with the upstream `rvfi_insn_add` instruction model. All source files in `upstream/` other than the portable SBY file are byte-for-byte copies of those revisions; hashes are in `source.sha256.json`.

`upstream/insn_add_ch0.sby` is derived from the upstream `genchecks.py` output. Its checker, defines, depth 21, check cycle 20, reset cycle 1, and wrapper parameters are unchanged. The absolute source paths were made relative and the engine changed from Boolector to locally available Z3. The generated upstream task also sets `expect pass,fail`, so inspect the task's actual status; the command exit code alone does not establish that the property passed.

The upstream `rvfi_macros.vh` is about 780 KB. It remains byte-for-byte in the case and is used by the frontend/SBY, but is excluded from the model's prompt in the focused run. Candidate 01 is a retained earlier run that did include this entire macro; its exact input file list is in `candidate-01/task_input.json`. The two runs must not be pooled as same-prompt repetitions.

From the repository root, elaborate the original with its original checker:

```sh
python3 scripts/check_picorv32.py --out results/picorv32/original-frontend
```

With SymbiYosys and Z3 installed, run the portable original BMC task:

```sh
cd experiments/picorv32/upstream
sby -f insn_add_ch0.sby
```

Generate and inspect one candidate using the existing runner:

```sh
python3 scripts/freestyle_pilot.py rewrite --case experiments/picorv32 --out results/picorv32/rewrite-01 --provider deepseek
python3 scripts/check_picorv32.py --candidate results/picorv32/rewrite-01/candidate --out results/picorv32/frontend-01
python3 scripts/freestyle_pilot.py analyze --case experiments/picorv32 --candidate results/picorv32/rewrite-01/candidate --out results/picorv32/analysis-01 --provider deepseek
```

The frontend check compiles the candidate against the **original** property. It is not an abstraction soundness or equivalence check. An alternate property proposed in `property_proposal.md` is recorded for review and never silently replaces the upstream checker. Candidate generation and analysis have no tools and are separate API requests. The complete API requests and solver logs are kept outside Git in `results/` and `artifacts/`.

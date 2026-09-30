# environment.md

## Harness and property: unchanged

The following are unchanged:
- `wrapper.sv`, instantiating `picorv32` with `COMPRESSED_ISA=1`, `ENABLE_FAST_MUL=1`, `ENABLE_DIV=1`, `BARREL_SHIFTER=1`
- `rvfi_testbench.sv`, where reset is asserted only in the initial cycle
- `insn_add_ch0.sby`: depth 21, skip 20, check cycle 20, reset cycles 1, same defines
- `mem_ready` / `mem_rdata` remain free `rvformal_rand_reg` inputs
- The core's `FORMAL` restrict properties are kept: at most 4-cycle memory stall, and `resetn` is low only in the initial state

## Changed model-level conditions

These live inside the replacement `picorv32.v`, not as new assumes.

1. **Instruction subset.** Only LUI, AUIPC, RV32I OP-IMM and RV32I OP (funct7 `0000000` / `0100000`) execute. Every other fetched word, including all RVC, loads, stores, branches, JAL, JALR, FENCE, SYSTEM, M-extension, custom and illegal encodings, retires once with `rvfi_trap=1` and halts the core. This is effectively the same as restricting the environment to subset programs up to the first non-subset instruction.
2. **Ignored parameters.** `COMPRESSED_ISA`, `ENABLE_FAST_MUL`, `ENABLE_DIV` and `BARREL_SHIFTER` from the wrapper are accepted but ignored: there is no RVC and no PCPI, and shifts are single-cycle. `ENABLE_COUNTERS*`, `ENABLE_IRQ*`, `ENABLE_TRACE`, `TWO_*`, `LATCHED_MEM_RDATA`, `ENABLE_REGS_16_31` and `ENABLE_REGS_DUALPORT` are also ignored.
3. **Required parameter values.** `STACKADDR` must be the default `32'hffffffff`, because x2 initialisation is not modelled. `PROGADDR_RESET` must be word-aligned; a misaligned reset PC traps without an RVFI record.
4. **No data memory traffic.** The core never issues data reads or writes. `mem_instr` is 1 for every request and `mem_la_write` is 0.
5. **Register contents at reset.** Registers stay unconstrained at reset, as upstream with `REGS_INIT_ZERO=0`.

## Not changed

- `RISCV_FORMAL` is still required and honoured.
- `rvfi_valid` is driven for every retirement.
- RVFI operand and result fields carry the actual register-file and ALU values.
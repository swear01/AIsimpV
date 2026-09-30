# explanation.md

**Status: partial model and hypothesis only.** Nothing was compiled, simulated, BMC'd or equivalence-checked.

## Main source changes

The body of module `picorv32` was replaced by a small multi-cycle core with four states (fetch, iwait, exec, trap). It has:
- **Decode:** a direct 32-bit decoder over `insn_q`.
- **Register file:** a 32x32 register file, uninitialised unless `REGS_INIT_ZERO`, as upstream. Reads are guarded for x0; writes happen at retirement when rd != 0.
- **ALU:** one ALU covering add/sub, slt/sltu, xor/or/and, and shifts by `op2[4:0]`.
- **RVFI:** outputs are produced for the retiring instruction in the cycle after exec.

The following are kept:
- Parameter list and port list, so `wrapper.sv`, `picorv32_axi` and `picorv32_wb` still elaborate.
- The upstream `FORMAL` restrict properties and equivalent look-ahead and state-validity asserts.
- The `PICORV32_TESTBUG_001` to `005` mutation hooks.

All other modules (`picorv32_regs`, `pcpi_mul`, `pcpi_fast_mul`, `pcpi_div`, `axi`, `axi_adapter`, `wb`) are unchanged. They are not instantiated by the new core.

## Why this is the causal cone of the assertion

The insn_add assertions at cycle 20 depend on:
- which word was fetched as the ADD (`rvfi_insn`),
- the PC it was fetched from and the next PC,
- the values read from rs1/rs2, which come from reset-arbitrary register contents plus writes by earlier retired instructions,
- the ALU sum,
- the rd write-back reporting,
- the absence of trap and memory access.

M keeps each of these as real state and datapath:
- instruction fetch from free `mem_rdata` with free stalls,
- a PC register,
- the register file with writes from earlier instructions,
- the ALU,
- the RVFI reporting.

Operand values are not hardwired. `rvfi_valid` is not suppressed. The ADD result flows through the same register file that earlier LUI/ADDI/ADD/etc. wrote.

## Information and behaviours removed

These are legal original behaviours lost. Any trace that uses one of them before the cycle-20 ADD is either impossible in M or ends in trap, so it is not checked.

1. **RVC.** All compressed instructions are gone, including C.ADD, C.LI, C.MV and others that set operand registers. Also gone: 32-bit ADDs fetched at a halfword-aligned PC, split across two words through `mem_16bit_buffer` / `prefetched_high_word` / `mem_la_secondword`. That split fetch path is a real upstream bug surface.
2. **Loads and stores.** All data-memory traffic is gone: LB/LH/LW/LBU/LHU/SB/SH/SW, `mem_do_rdata`/`mem_do_wdata`, `mem_wordsize`, misaligned-access traps, and `rvfi_mem_*` for data. Operand registers can no longer be set by loads.
3. **Control flow.** Branches, JAL and JALR are gone. The ADD is always at PC = PROGADDR_RESET + 4k. ADD after a taken branch or jump, and link-register writes, are lost. So is the `latched_branch` write-back path.
4. **SYSTEM instructions.** RDCYCLE[H], RDINSTR[H] and the CSR RVFI fields are gone, as are ECALL/EBREAK and FENCE. FENCE is legal and a NOP upstream; here it traps.
5. **PCPI.** MUL and DIV (ALTOPS results via `pcpi_fast_mul` / `pcpi_div`) are gone, along with the PCPI handshake and timeout.
6. **IRQ and trace.** IRQ logic, q-registers, custom instructions and the trace port are gone. IRQ was disabled in the wrapper anyway.
7. **Upstream micro-architecture:**
   - two-stage decoder (`mem_rdata_latched` then `mem_rdata_q`, `decoder_trigger` / `decoder_pseudo_trigger`),
   - prefetch overlapping exec (`mem_do_prefetch`),
   - `mem_state` machine and look-ahead address generation from `next_pc`,
   - `cpu_state_ld_rs1` / `ld_rs2` / `shift` / `stmem` / `ldmem`,
   - `alu_out_q`, `latched_*`,
   - `count_cycle` / `count_instr`,
   - STACKADDR x2 initialisation (`STACKADDR` must stay at its default).
8. **Upstream RVFI staging.** Upstream reports instruction N when N+1 launches. It uses `dbg_insn_opcode` / `dbg_rs*val` / `dbg_insn_addr` and captures `rvfi_rd_*` at the next fetch's `cpuregs_write`. M reports N directly. Bugs in that staging, which is exactly what `TESTBUG_003`/`004`/`005` model upstream, are only reproduced here by analogy.
9. **Retirement timing.** Timing differs from upstream, so the set of instruction prefixes that can retire by cycle 20 differs. It is about six instructions at 3 cycles each plus stalls.

## Expected relation to upstream

- **Not equivalent.** M is not the same CPU. A PASS on M does not imply a PASS upstream.
- **Upstream fail may be missed.** An upstream FAIL caused by any item above would not be found.
- **A fail on M is not transferable either.** A FAIL on M may or may not correspond to an upstream bug.
- **What M is good for:** a small, checkable causal model of "ADD result = sum of register values that earlier ALU instructions wrote, reported correctly on RVFI".
- **What would lift the result to upstream:** a refinement check showing upstream and M agree on RVFI retirement records for subset-only programs. That check is not provided.

Expected BMC cost is far lower. There is no 16-bit buffer, prefetch, PCPI divider/multiplier or counter state, and the state is roughly `reg_pc`, `insn_q`, 3 state bits, the register file and RVFI registers. This is a hypothesis.
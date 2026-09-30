# property_proposal.md

The property text is unchanged: the upstream `rvfi_insn_check` with `RISCV_FORMAL_INSN_MODEL rvfi_insn_add`, channel 0, `RISCV_FORMAL_CHECK_CYCLE 20`, `RISCV_FORMAL_RESET_CYCLES 1`, BMC depth 21 with skip 20, and the same defines in insn_add_ch0.sby.

The design under check is different, so the obligation discharged is different and narrower. The claim that may be made from a PASS is only this:

> For the reduced core M in this picorv32.v, fetching arbitrary 32-bit words with arbitrary stalls of at most 4 cycles (same wrapper), suppose the instruction retiring on RVFI at cycle 20 is a 32-bit ADD. Then the checks in rvfi_insn_check hold for it: rs1/rs2 address agreement, x0 reads as zero, rd_addr, rd_wdata == rs1_rdata + rs2_rdata (0 if rd==x0), pc_wdata == pc_rdata + 4, no memory access, and trap == 0. This holds for every prefix of up to about six preceding instructions drawn from the supported subset {LUI, AUIPC, OP-IMM, OP(RV32I)}. Those instructions can set the ADD operand registers through the real register file.

A PASS says nothing about upstream PicoRV32 unless there is a separate refinement argument. That argument would show that, for traces made only of the supported subset, upstream PicoRV32 produces the same RVFI retirement sequence as M. Nothing here establishes that argument.

## Recommended auxiliary obligations (additions, not replacements)

1. **Non-vacuity cover.** Run it in the same harness, placed in the testbench or a bind:
   `cover(!reset && check && spec_valid && !trap && rs1_addr != 0 && rs2_addr != 0 && rs1_addr != rs2_addr && rd_wdata != 0 && rvfi_order >= 2)`
   Optionally strengthen it with a witness that an earlier retirement wrote `rs1_addr`. This shows the check is reached with a nonzero ADD after preceding register-writing instructions.
2. **Mutation sanity.** Each of the following should FAIL the unchanged insn_add_ch0 check on M:
   - `PICORV32_TESTBUG_003` (rd_addr^1)
   - `PICORV32_TESTBUG_004` (rd_wdata^1)
   - `PICORV32_TESTBUG_005` (pc_wdata^4)

   `TESTBUG_001` and `TESTBUG_002` corrupt only the architectural register write. They are expected to PASS insn_add, as they are expected to upstream, because only the reg check detects them.
3. **Suggested cross-check.** Run upstream insn_add_ch0 on the original core under an added assumption that every rvfi_insn is in the supported subset. This gives an empirical comparison point; it is not an equivalence proof.

None of these have been run.
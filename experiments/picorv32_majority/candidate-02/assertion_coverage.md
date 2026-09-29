# Candidate 02: register-read abstraction (no Formal)

This candidate selects the upstream `RISCV_FORMAL_BLACKBOX_REGS` source branch. For x0, reads still return zero. For nonzero source registers, reads may choose arbitrary 32-bit values each cycle. The original decode, ALU, M, C, memory, CSR, and RVFI paths remain. This is an intended overapproximation of register values, but no behavioral inclusion or property result was checked.

| Task family | Count | Code-reading status |
|---|---:|---|
| RV32I instructions | 37 | Local operation paths remain; register-history contexts unknown |
| M instructions | 8 | MUL/DIV engines and local paths remain; register-history contexts unknown |
| C instructions | 25 | Compressed decode and local paths remain; register-history contexts unknown |
| CSR | 10 | Counter/CSR paths remain; effects of arbitrary source reads need review |
| Register/PC/order | 6 | `reg_ch0` read-after-write meaning is lost; the other five need separate review |

All 80 instruction/CSR task names still have their original implementation paths. **This is not a claim that 80/86 assertions are preserved**: arbitrary read values can create impossible dependent-instruction histories and false counterexamples. The 80% research target remains unmeasured.

## Mapping to the source

- Candidate lines 59–61 enable the upstream abstraction branch.
- Original register read block around lines 1350–1373 becomes two `$anyseq` reads in candidate lines 1360–1375; zero-register handling remains explicit.
- The register write and RVFI write-data logic remains, but writes no longer constrain later reads.
- Original adapter modules after line 2517 are omitted because this wrapper instantiates only `picorv32`.

## Task names by family

### RV32I instructions (37)

insn_add_ch0, insn_addi_ch0, insn_and_ch0, insn_andi_ch0, insn_auipc_ch0, insn_beq_ch0, insn_bge_ch0, insn_bgeu_ch0, insn_blt_ch0, insn_bltu_ch0, insn_bne_ch0, insn_jal_ch0, insn_jalr_ch0, insn_lb_ch0, insn_lbu_ch0, insn_lh_ch0, insn_lhu_ch0, insn_lui_ch0, insn_lw_ch0, insn_or_ch0, insn_ori_ch0, insn_sb_ch0, insn_sh_ch0, insn_sll_ch0, insn_slli_ch0, insn_slt_ch0, insn_slti_ch0, insn_sltiu_ch0, insn_sltu_ch0, insn_sra_ch0, insn_srai_ch0, insn_srl_ch0, insn_srli_ch0, insn_sub_ch0, insn_sw_ch0, insn_xor_ch0, insn_xori_ch0

### M instructions (8)

insn_div_ch0, insn_divu_ch0, insn_mul_ch0, insn_mulh_ch0, insn_mulhsu_ch0, insn_mulhu_ch0, insn_rem_ch0, insn_remu_ch0

### C instructions (25)

insn_c_add_ch0, insn_c_addi16sp_ch0, insn_c_addi4spn_ch0, insn_c_addi_ch0, insn_c_and_ch0, insn_c_andi_ch0, insn_c_beqz_ch0, insn_c_bnez_ch0, insn_c_j_ch0, insn_c_jal_ch0, insn_c_jalr_ch0, insn_c_jr_ch0, insn_c_li_ch0, insn_c_lui_ch0, insn_c_lw_ch0, insn_c_lwsp_ch0, insn_c_mv_ch0, insn_c_or_ch0, insn_c_slli_ch0, insn_c_srai_ch0, insn_c_srli_ch0, insn_c_sub_ch0, insn_c_sw_ch0, insn_c_swsp_ch0, insn_c_xor_ch0

### Register/PC/order (6)

causal_ch0, liveness_ch0, pc_bwd_ch0, pc_fwd_ch0, reg_ch0, unique_ch0

### CSR (10)

csr_ill_c00_ch0, csr_ill_c02_ch0, csr_ill_c80_ch0, csr_ill_c82_ch0, csrc_inc_mcycle_ch0, csrc_inc_minstret_ch0, csrc_upcnt_mcycle_ch0, csrc_upcnt_minstret_ch0, csrw_mcycle_ch0, csrw_minstret_ch0

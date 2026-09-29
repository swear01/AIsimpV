# Candidate 01: assertion-intent inspection (no Formal)

This is a code-reading hypothesis, not an assertion pass rate or an abstraction certificate. The candidate changes only the PCPI configuration and implementation inside `picorv32`, then removes modules after `picorv32_regs`. The original checker files and wrapper are unchanged. An instruction task can still lose histories that include a removed M instruction, so even an unchanged instruction code path is not a full-task guarantee.

| Task family | Count | Code-reading status | Candidate evidence |
|---|---:|---|---|
| RV32I instruction semantics | 37 | plausible for histories without M; full task unknown | Decode around lines 695–1040, ALU 1130–1200, register file 1216–1260, RVFI 1890–1980 |
| Compressed instruction semantics | 25 | plausible for histories without M; full task unknown | Compressed fetch/decode around lines 800–940, shared execution and RVFI paths |
| CSR semantics | 10 | plausible for histories without M; full task unknown | `count_cycle`/`count_instr` and CSR RVFI fields around lines 1340–1480 and 1980–2080 |
| M multiply/divide semantics | 8 | lost | PCPI engines removed at lines 255–261; `WITH_PCPI=0` at line 169 |
| Register/PC/order/liveness/causality | 6 | partial or unknown | Register, PC and RVFI state remains, but histories containing M are no longer representable |

Candidate code paths for 72/86 named instruction/CSR tasks remain present, and 8/86 M paths are deliberately removed. **Do not quote 72/86 as retained coverage**: those 72 tasks may rely on broader histories or contain subtle timing relationships. There is no measured 80% result in this round.

## Explicit task names

### RV32I instructions — plausible_non_M_history

insn_add_ch0, insn_addi_ch0, insn_and_ch0, insn_andi_ch0, insn_auipc_ch0, insn_beq_ch0, insn_bge_ch0, insn_bgeu_ch0, insn_blt_ch0, insn_bltu_ch0, insn_bne_ch0, insn_jal_ch0, insn_jalr_ch0, insn_lb_ch0, insn_lbu_ch0, insn_lh_ch0, insn_lhu_ch0, insn_lui_ch0, insn_lw_ch0, insn_or_ch0, insn_ori_ch0, insn_sb_ch0, insn_sh_ch0, insn_sll_ch0, insn_slli_ch0, insn_slt_ch0, insn_slti_ch0, insn_sltiu_ch0, insn_sltu_ch0, insn_sra_ch0, insn_srai_ch0, insn_srl_ch0, insn_srli_ch0, insn_sub_ch0, insn_sw_ch0, insn_xor_ch0, insn_xori_ch0

### M instructions — lost

insn_div_ch0, insn_divu_ch0, insn_mul_ch0, insn_mulh_ch0, insn_mulhsu_ch0, insn_mulhu_ch0, insn_rem_ch0, insn_remu_ch0

### C instructions — plausible_non_M_history

insn_c_add_ch0, insn_c_addi16sp_ch0, insn_c_addi4spn_ch0, insn_c_addi_ch0, insn_c_and_ch0, insn_c_andi_ch0, insn_c_beqz_ch0, insn_c_bnez_ch0, insn_c_j_ch0, insn_c_jal_ch0, insn_c_jalr_ch0, insn_c_jr_ch0, insn_c_li_ch0, insn_c_lui_ch0, insn_c_lw_ch0, insn_c_lwsp_ch0, insn_c_mv_ch0, insn_c_or_ch0, insn_c_slli_ch0, insn_c_srai_ch0, insn_c_srli_ch0, insn_c_sub_ch0, insn_c_sw_ch0, insn_c_swsp_ch0, insn_c_xor_ch0

### Register/PC/order — partial_or_unknown

causal_ch0, liveness_ch0, pc_bwd_ch0, pc_fwd_ch0, reg_ch0, unique_ch0

### CSR — plausible_non_M_history

csr_ill_c00_ch0, csr_ill_c02_ch0, csr_ill_c80_ch0, csr_ill_c82_ch0, csrc_inc_mcycle_ch0, csrc_inc_minstret_ch0, csrc_upcnt_mcycle_ch0, csrc_upcnt_minstret_ch0, csrw_mcycle_ch0, csrw_minstret_ch0

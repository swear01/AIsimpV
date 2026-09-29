# Pinned upstream assertion-intent inventory

Source: YosysHQ/riscv-formal `c992aa61fdfe0846c5ed90324c596202a1c69b76`, `cores/picorv32/checks.cfg`, generated task filenames. Original core: YosysHQ/picorv32 `ef203c2b0a3fb793280f5114941416c425c5b461`. There are 86 generated assertion tasks and one separate cover task. The 3 hand-written SBY tasks are outside this denominator. These are distinct task names, not a statistically independent behavior sample.

A named instruction check relates RVFI decode/operands/result/PC/memory fields to that instruction's upstream ISA model. The other checks concern register read-after-write consistency, PC linkage, retirement order/liveness/causality, or CSR behavior. They are reference questions for a human to inspect; no checker is executed in this experiment. The complete upstream checker sources remain at the pinned riscv-formal revision. Do not count a task as retained merely because a corresponding instruction opcode or RVFI output exists: nonzero operands, dependent instructions, memory effects and branch/PC relations must remain representable.

Wrapper configuration: COMPRESSED_ISA=1, ENABLE_FAST_MUL=1, ENABLE_DIV=1, BARREL_SHIFTER=1; unconstrained mem_ready and mem_rdata, same resetn inversion. This is the target configuration, not all PicoRV32 parameter combinations.

## RV32I instructions (37)

insn_add_ch0, insn_addi_ch0, insn_and_ch0, insn_andi_ch0, insn_auipc_ch0, insn_beq_ch0, insn_bge_ch0, insn_bgeu_ch0, insn_blt_ch0, insn_bltu_ch0, insn_bne_ch0, insn_jal_ch0, insn_jalr_ch0, insn_lb_ch0, insn_lbu_ch0, insn_lh_ch0, insn_lhu_ch0, insn_lui_ch0, insn_lw_ch0, insn_or_ch0, insn_ori_ch0, insn_sb_ch0, insn_sh_ch0, insn_sll_ch0, insn_slli_ch0, insn_slt_ch0, insn_slti_ch0, insn_sltiu_ch0, insn_sltu_ch0, insn_sra_ch0, insn_srai_ch0, insn_srl_ch0, insn_srli_ch0, insn_sub_ch0, insn_sw_ch0, insn_xor_ch0, insn_xori_ch0

## M instructions (8)

insn_div_ch0, insn_divu_ch0, insn_mul_ch0, insn_mulh_ch0, insn_mulhsu_ch0, insn_mulhu_ch0, insn_rem_ch0, insn_remu_ch0

## C instructions (25)

insn_c_add_ch0, insn_c_addi16sp_ch0, insn_c_addi4spn_ch0, insn_c_addi_ch0, insn_c_and_ch0, insn_c_andi_ch0, insn_c_beqz_ch0, insn_c_bnez_ch0, insn_c_j_ch0, insn_c_jal_ch0, insn_c_jalr_ch0, insn_c_jr_ch0, insn_c_li_ch0, insn_c_lui_ch0, insn_c_lw_ch0, insn_c_lwsp_ch0, insn_c_mv_ch0, insn_c_or_ch0, insn_c_slli_ch0, insn_c_srai_ch0, insn_c_srli_ch0, insn_c_sub_ch0, insn_c_sw_ch0, insn_c_swsp_ch0, insn_c_xor_ch0

## Register/PC/order (6)

causal_ch0, liveness_ch0, pc_bwd_ch0, pc_fwd_ch0, reg_ch0, unique_ch0

## CSR (10)

csr_ill_c00_ch0, csr_ill_c02_ch0, csr_ill_c80_ch0, csr_ill_c82_ch0, csrc_inc_mcycle_ch0, csrc_inc_minstret_ch0, csrc_upcnt_mcycle_ch0, csrc_upcnt_minstret_ch0, csrw_mcycle_ch0, csrw_minstret_ch0

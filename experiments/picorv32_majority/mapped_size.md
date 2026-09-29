# PicoRV32：Design Compiler mapped-cell 實驗

這次改用本機 Synopsys Design Compiler W-2024.09-SP4 和 FreePDK45 v1.1、25°C standard-cell library。所有行都以 `picorv32` 為 top、`COMPRESSED_ISA=1`、`ENABLE_FAST_MUL=1`、`ENABLE_DIV=1`、`BARREL_SHIFTER=1`、20 ns clock、相同 library 和 `compile -map_effort medium -area_effort high -ungroup_all` 映射。`report_area` 的 cell 數與 `get_cells -hierarchical` 一致；結果沒有 memory macro 或 black box。數字是**映射後的 standard cells**，不是 Yosys generic cells，也不是晶片放置繞線後的面積。

候選 03–05 是這次由 Codex GPT-6 根據原 RTL 已有的實作選項直接構造的工程對照，不是三次獨立的 freestyle 生成；這些數字不能當作 LLM 自主改寫成功率。

| RTL | 不含 RVFI 的實際算術版 | 有 RVFI 的實際算術版 | 上游 RVFI/ALTOPS 版 |
|---|---:|---:|---:|
| 原版 | 30,108 cells；44,452.0 area | 32,595；50,049.7 | 21,668；35,219.0 |
| 候選 01：移除 M | 未量 | 20,068（−38.4%）；32,767.5 | 20,068（−7.4%）；32,767.5 |
| 候選 03：單埠暫存器檔 | 未量 | 30,534（−6.3%）；47,846.6 | 19,604（−9.5%）；33,011.9 |
| 候選 04：8 步迭代 M | 未量 | 28,751（−11.8%）；45,586.9 | 21,829（+0.7%）；35,614.1 |
| **候選 05：移除 M＋單埠暫存器檔** | **15,636（−48.1%）；25,107.6** | **17,982（−44.8%）；30,546.1** | **17,982（−17.0%）；30,546.1** |

Area 欄採用 library 的 `Total cell area`；括號內百分比只比較同一欄的原版。第一欄不定義 `RISCV_FORMAL`、`DEBUGNETS`、`RISCV_FORMAL_ALTOPS`。第二欄定義前兩者，保留 RVFI 觀察介面，但 M 使用真實算術。第三欄再定義 `RISCV_FORMAL_ALTOPS`，與上游 `checks.cfg` 的 source 巨集一致。這是三種不同電路；不跨欄比較百分比。

## 改動和行為代價

- 候選 01 移除了 M 乘除法；8 個 M 指令任務的行為直接失去。其他 72 個指令／CSR 任務的相關路徑還在，但完整任務行為未判定。
- 候選 03 只把核心預設 `ENABLE_REGS_DUALPORT` 從 1 改成 0。上游已有單埠讀取與額外 `cpu_state_ld_rs2` 狀態；暫存器內容仍由寫入決定，但指令延遲會變。
- 候選 04 在固定 `ENABLE_FAST_MUL=1` 介面下選用上游 8 步迭代乘法器，並在 `RISCV_FORMAL_ALTOPS` 時輸出與原 fast engine 相同的替代算式。M 指令運算仍可進行，延遲則改變；上游 ALTOPS 版的 mapped cells **沒有減少**。
- 候選 05 結合候選 01 與 03，得到此輪最小的 mapped netlist。它適合展示「多數非 M 任務意圖」的縮減嘗試，**不能宣稱已保留 80% assertion**：除 M 的 8 項以外，額外 cycle 也可能影響 liveness、PC 或其他檢查。
- 候選 02 的 `$anyseq` 在 DC 前端報 `VER-110: Function '$anyseq' not defined`，沒有可比較的 mapped-cell 數。先前的 41.8% 是 Yosys 對驗證模型的 generic-cell 統計。

沒有跑 Formal、BMC 或 assertion suite。VCS 2025.06 的小型模擬顯示：候選 05 與原版在同一段 7 條非 M 指令上的 RVFI 退休紀錄相同；候選 04 的 fast／8 步乘法器在一般算術和 ALTOPS 模式各通過 16 組 MUL、MULH、MULHSU、MULHU 對照，且在 20 cycles 內回覆。這些只支持所測路徑，不足以估計 assertion 保留率。

## 重現

在此 repository 根目錄執行；`PICO_RTL` 指向要比較的原版或候選檔。正式版把 `PICO_DEFINES` 設為 `RISCV_FORMAL DEBUGNETS RISCV_FORMAL_ALTOPS`；實際算術＋RVFI 版設為 `RISCV_FORMAL DEBUGNETS`；不含 RVFI 版設為空字串。每次在獨立工作目錄執行 DC，避免覆寫 `WORK`。

```sh
source /apps/eda/synopsys/synthesis.sh 2024.09-sp4
case_root="$PWD/experiments/picorv32_majority"
run_dir="$PWD/results/picorv32_majority/dc/reproduce"
mkdir -p "$run_dir"
(
  cd "$run_dir"
  PICO_RTL="$case_root/candidate-05/picorv32.v" \
  PICO_DB=/apps/cad/cell_library/CBDK45_FreePDK_TSRI_v1.1/lib/freepdk45_v1.1_t25.db \
  PICO_PARAMS='COMPRESSED_ISA=1,ENABLE_FAST_MUL=1,ENABLE_DIV=1,BARREL_SHIFTER=1' \
  PICO_DEFINES='RISCV_FORMAL DEBUGNETS RISCV_FORMAL_ALTOPS' \
  dc_shell -no_gui -f "$case_root/mapped_size.tcl" -output_log_file dc.log > console.txt 2>&1
)
rg 'MAPPED_CELL_COUNT=|Number of cells:|Total cell area:|Number of macros/black boxes:' "$run_dir/dc.log"
```

完整 DC/VCS 原始 log 保存在本地被 Git 忽略的 `results/picorv32_majority/`。RTL、DC Tcl 和兩個模擬 testbench 納入版本控制；library 檔不隨 repo 發布。

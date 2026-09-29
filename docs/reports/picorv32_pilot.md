# PicoRV32 完整核心、上游 ADD property：自由改寫初探

2026-09-29。本輪把原始 design 改為完整的 [PicoRV32](https://github.com/YosysHQ/picorv32/tree/ef203c2b0a3fb793280f5114941416c425c5b461) `picorv32.v`（3,049 行），目標是 [riscv-formal](https://github.com/YosysHQ/riscv-formal/tree/c992aa61fdfe0846c5ed90324c596202a1c69b76) 上游 `checks.cfg` 產生的 `insn_add_ch0`。原始 wrapper 啟用 compressed ISA、fast MUL、DIV 與 barrel shifter；原始 property 使用 `rvfi_insn_check` 及 `rvfi_insn_add`。完整原始檔、來源 hash、候選與可點選的[前後對照頁](../../experiments/picorv32/index.html)均保存在 repo。

本機未安裝 Boolector；可攜的 [SBY task](../../experiments/picorv32/upstream/insn_add_ch0.sby)只把上游產生的絕對路徑改為相對路徑，並改用 Z3。property、wrapper、reset/check cycle 與 depth 21 保留。所有 BMC 敘述均指這個 Z3 變體，不能當成上游 Boolector 執行結果。`expect pass,fail` 是產生器原有設定，判讀以 engine 與 SBY status 為準。

| 候選 | 生成輸入 | 產物 | 原始 ADD checker 下的結果 | 人工判讀 |
| --- | --- | --- | --- | --- |
| [01](../../experiments/picorv32/candidate-01/review.html) | 含 780 KB `rvfi_macros.vh`；request 約 979 KB，API 回報 407,950 prompt tokens | 612 行，ADD-only 兩狀態模型；七個其他模組改成固定輸出 | formal frontend PASS，64→39 check cells；Z3 BMC 120 秒未得結論 | 有實質改寫，但丟掉非 ADD 行為、改變 fetch 握手與暫存器 reset；RVFI order 停在零。 |
| [02](../../experiments/picorv32/candidate-02/review.html) | 巨型 macro 只供 formal 工具，未送給生成模型；request 約 146 KB，API 回報 56,538 prompt tokens | 270 行，只有 `picorv32` module；不保留暫存器檔，ADD 來源值與結果均回報零 | formal frontend PASS，64→39 check cells；Z3 BMC 約 1 秒 PASS；cover 在第 20 拍到達 `check && spec_valid && !trap` | 原始 checker 的 ADD 算式用**候選自報的**來源值計算，故零加零可通過；其他合法來源值與指令軌跡沒有被保留。 |

兩次都是 `deepseek-flash` API alias、reasoning effort high、同一 prompt 原則，沒有模型工具；gateway 未提供可釘住的實際 checkpoint。**這兩次不是嚴格 A/B**：除了 macro 輸入範圍不同，只有各一個樣本。第 01 次巨大 macro 把「較小 CPU」重新變成超長上下文；第 02 次真正縮短輸入後，仍產生更窄的 ADD 報告器。不能由此估算 DeepSeek Flash 的一般成功率，也不能單獨證明模型能力或上下文長度是主因。

原始設計與兩份候選在相同上游 ADD checker 下均能通過 Yosys formal frontend；這只確定 elaboration。[formal 結果紀錄](../../experiments/picorv32/formal_results.json)列出各次狀態。原始設計的 Z3 BMC 在進入第 20 拍求解後約 5 分 37 秒仍無結論，人工停止。候選 01 的 120 秒 BMC 亦無結論。候選 02 的 BMC PASS 和 ADD cover 排除了「完全沒有 ADD 事件」這一種空泛情況，仍**沒有**證明候選覆蓋原核心行為，更不能把它的 1 秒和原始任務未完成的時間報成有效加速。候選 02 也違反了完整檔案替代品的要求：七個上游 module 宣告缺失，雖然目標 wrapper 的 frontend 仍 PASS。

最有展示價值的具體差異是 [候選 02 的 RVFI ADD 區塊](../../experiments/picorv32/candidate-02/picorv32.v#L230)：`rvfi_rs1_rdata`、`rvfi_rs2_rdata`、`rvfi_rd_wdata` 全部設為零；[上游 ADD 規格](../../experiments/picorv32/upstream/insn_add.v#L45)從 RVFI 回報的來源值計算結果，[checker](../../experiments/picorv32/upstream/rvfi_insn_check.sv#L169)再比較結果。因此 checker 通過並不能回答「原 PicoRV32 執行 ADD 是否被這個模型保留」。這個案例直接顯示為何研究需要分開記錄**簡化構想、原 property 結果、與原設計的關係**。

第二個乾淨分析 session 未看到生成者說明，指出兩份候選均把完整 CPU 縮成 ADD-only，並辨識出多個具體行為缺口。人工再核對了本頁五項代表性改動。分析原文保留在各候選目錄；候選 01 的分析有一處行號超出原檔末行，因此網頁只採用人工確認、且經位置檢查的卡片。網頁中的程式碼取自固定快照，生成者的說明與人工判讀分開顯示。

下一步若要檢驗「模型不夠強」而非繼續擴大 design，應固定第 02 次的完整輸入、同一上游 ADD task 與檢查方式，換一個**版本明確**的更強模型做相同次數的獨立生成。成功門檻至少要包含非零來源運算元與先前合法指令造成的狀態；單看 ADD checker PASS 會獎勵這次的錯誤簡化。

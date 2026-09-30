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

## 2026-09-30：換 Claude Sonnet 5.5 的單次對照

以 [Claude API `claude-sonnet-5-5`](https://platform.claude.com/docs/en/models/sonnet-5-5/overview) 重跑第 02 次的**同一份 user message 與 frozen input bundle**，沒有模型工具。重建舊 DeepSeek request 的 SHA-256 為 `227354af914a2f0b587432db25bff33adff9ddc30e572fec62c056d6ea89f378`，與[舊生成紀錄](../../experiments/picorv32/candidate-02/generation.json)一致；兩次的 user message SHA-256 均為 `4606973177bfdb2e8b9c6059897492d6d7495f22b2f77021da95d5bc7bd9a3f6`。Sonnet 設為 high effort，使用 Anthropic 的 JSON schema 輸出；DeepSeek 原請求使用 `json_object`。這是相同任務內容的換模型試跑，API 輸出約束仍有差別。

| 觀察 | DeepSeek Flash 候選 02 | [Sonnet 5.5 候選](../../experiments/picorv32/candidate-sonnet-5-5/picorv32.v) |
| --- | --- | --- |
| 產物 | 270 行、只有主核心 module；無暫存器檔，RVFI ADD 運算元與結果固定為零 | 2,125 行；保留原檔八個 module 宣告、暫存器檔、ALU 加法和 RVFI 寫回路徑；針對 formal wrapper 的參數組合特化，其他參數組合不再保證 |
| 原 checker 的 frontend | PASS，64→39 check cells | PASS，64→39 check cells，八個 module 均存在 |
| 原 checker 的 Z3 BMC | 約 1 秒 PASS；另有 ADD cover | 第 20 拍 assertion 求解約 10 分 29 秒後仍無結論，人工停止；**沒有 PASS/FAIL** |
| 相依、非零 ADD 軌跡 | 同一指令序列沒有退休事件 | 與原核心的四筆 RVFI 事件一致；`ADDI x1,5`、`ADDI x2,7` 後，`ADD x3,x1,x2` 回報 `5 + 7 = 12` |

[可重跑的序列檢查](../../experiments/picorv32/candidate-sonnet-5-5/verify_sequence.py)用 Yosys `sim` 對原版、兩個候選送入相同四條指令，並比對 RVFI。其[完整軌跡](../../experiments/picorv32/candidate-sonnet-5-5/directed_trace.json)和[生成、驗證紀錄](../../experiments/picorv32/candidate-sonnet-5-5/verification.json)保留在 repo。原始檔為 3,049 行，Sonnet 產物為 2,125 行（少約 30.3%），但行數與 frontend check cells 都不是硬體面積或證明速度。

在 repo 根目錄執行 `python3 experiments/picorv32/candidate-sonnet-5-5/verify_sequence.py`；需要 Yosys 置於 PATH。BMC 使用同一份 `upstream/insn_add_ch0.sby`，本輪工具為 Yosys 0.69、Z3 4.15.4 及 SymbiYosys `b1a1e98`。完整 API request、response 與求解 log 留在本機 `results/picorv32/sonnet-5-5/`，沒有放入 Git。

這個結果顯示：在**這一次**相同任務內容的生成中，Sonnet 避開了 DeepSeek 02 的「只回報零值 ADD」退化，並保留一條真實的非零相依 ADD 路徑。它仍自行限縮了參數範圍，原 ADD BMC 未取得結論，也沒有與原核心的行為包含或等價證明。每個模型只有一個樣本，DeepSeek 使用未釘住實際 checkpoint 的 gateway alias，兩個 API 的結構化輸出機制和 tokenization 不同；目前**不能確認模型能力是差異的唯一原因，或估算成功率**。下一步若要作因果比較，需固定輸入與評分，對每個模型做多次獨立生成，並以非零相依指令及行為關係作為成功條件。

候選雖保留八個 module 宣告，但**不能當通用 PicoRV32 檔案替換**：主核心的參數介面仍存在，實作卻忽略 formal wrapper 以外的配置。另以 `PROGADDR_RESET=4` 重跑同一指令 ROM，原核心第一筆從 PC 4 退休 `ADDI x2,x0,7`，候選卻從 PC 0 退休 `ADDI x1,x0,5`。檔內 AXI/WB wrapper 仍轉送參數，因此其預設配置也不受保證。`picorv32_pcpi_mul` 被改成固定輸出 stub，直接使用或啟用迭代 MUL 不會保留乘法行為。這些是生成產物本身的限制；本報告保留原始回應，不把後續人工修補算進這次模型表現。

## 2026-09-30：Opus 5.5 medium 的單一 assertion 改寫

使用相同 frozen 輸入檔和原 rewrite prompt，另加[單一 assertion 提示詞](../../experiments/picorv32/candidate-opus-5-5-medium/prompt_delta.txt)，要求比參數特化更激進，但明示失去的原核心行為。這輪使用 `claude-opus-5-5`、`medium` effort；Sonnet 輪使用 high effort 且沒有新增指示，所以不能把兩份結果的差異只歸因於模型。完整[候選與人工評估](../../experiments/picorv32/candidate-opus-5-5-medium/review.md)、[生成紀錄](../../experiments/picorv32/candidate-opus-5-5-medium/generation.json)和[驗證摘要](../../experiments/picorv32/candidate-opus-5-5-medium/verification.json)已保存。

Opus 把主核心從原版 2,106 行、Sonnet 1,349 行，縮為 370 行；全檔為 1,319 行。它保留取指、暫存器檔、部分 RV32I ALU 與 RVFI，移除 compressed、load/store、branch/jump、PCPI MUL/DIV、CSR 等合法執行路徑，並改變退休時序。模型自己將產物定義為 partial model，不宣稱替代原核心。

同一個 Yosys 展開流程下，Sonnet／Opus 的 generic cells 為 1,203／248，`$dff` cells 為 153／31；這是結構縮減的證據，並非面積或證明速度。原 `insn_add_ch0` checker 在 Opus 候選上的 Yosys frontend PASS；同一個 Z3 BMC 設定約 2.41 秒 PASS。`ADDI 5; ADDI 7; ADD` 的非零相依軌跡回報 `5 + 7 = 12`；JasperGold 在原 checker 下證明 33/33 assertions，並找到第 20 拍 ADD cover。另一個只增加 cover 的檢查找到第 20 拍非零 `5 + 7 = 12` 且此前至少兩筆退休紀錄。RVFI 結果低位突變會讓原 Z3 checker FAIL，排除了對該欄位完全不敏感的解讀。這些結果證明**受限模型自己的** ADD check 可達且通過；沒有原核心與受限模型的等價、行為包含或 refinement 證明。由於 Opus 排除大量原核心可達歷史，不能把它與 Sonnet 的未完成 BMC 當作同一義務的速度比較。

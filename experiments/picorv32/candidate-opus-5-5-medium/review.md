# Opus 5.5 medium：單一 ADD assertion 改寫評估

這是一次 `claude-opus-5-5`、`medium` effort 的獨立生成。輸入檔 hash 與 Sonnet 5.5 試跑相同；沿用原本 rewrite prompt，另加 `prompt_delta.txt`，明確要求更激進地聚焦 `insn_add_ch0`。因此兩次產物差異同時包含模型、effort 和提示詞差異，不能單獨歸因於模型能力。模型原始四份輸出依原樣保存；`generation.json` 記錄雜湊與用量。

## 改寫的範圍

原始檔 3,049 行、主 `picorv32` module 2,106 行；Sonnet 是 2,125／1,349 行；Opus 是 1,319／370 行。Opus 直接重寫主核心為 fetch、iwait、exec、trap 四個狀態，保留記憶體取指、32×32 暫存器檔、部分 RV32I ALU 與 RVFI ADD 回報；其餘七個 module 宣告及模組本文與上游逐位元組相同，但新主核心不再呼叫其中的 PCPI 單元。這是有實質狀態和資料路徑刪減的 partial model，並非原核心的參數特化。

代價也很清楚：壓縮指令、load/store、branch/jump、PCPI MUL/DIV、CSR 等原核心合法路徑在主核心消失；其他參數大多被忽略。原 checker 雖沿用，這些路徑無法形成第 20 拍 ADD 的前序歷史。退休時序亦改變。模型在 `environment.md` 和 `explanation.md` 明示這些限制，沒有宣稱與原核心等價。

## 實測

- 原 checker 的 Yosys frontend：原版／候選均 PASS，候選保留八個 module 宣告；formal check cells 64／47。這是 elaboration 和檢查物件數，並非面積或證明難度。
- 用同一個 Yosys 0.69+post 與原 checker 做 `prep -flatten` 後，Sonnet／Opus 的 generic cell 數為 1,203／248；其中 `$dff` 為 153／31、`$mux` 為 540／72，兩者均仍有一個 register-file memory cell 與 39 個 `$check`。這說明有實際展開後的結構刪減；cell 數不等於實體面積或求解難度。
- 同一條 `ADDI x1,5; ADDI x2,7; ADD x3,x1,x2; EBREAK` 的 Yosys `sim`：原版、Sonnet、Opus 前三筆 RVFI 紀錄在忽略時間後一致，ADD 為 `5 + 7 = 12`；Opus 的退休時間較早，第四筆 EBREAK 的 RVFI 欄位與原版不同。逐筆值在 `directed_trace.json`。
- 原封不動的 `insn_add_ch0` checker，Yosys SMTBMC／Z3，depth 21、skip 20：Opus 候選在本機約 2.41 秒 PASS。`PICORV32_TESTBUG_004` 把 RVFI `rd_wdata` 低位反轉後，同一檢查約 4.51 秒 FAIL，反例落在結果比較。
- JasperGold 2025.03 以相同 checker／wrapper 做有界設定：33／33 assertions proven，原有第 20 拍 ADD cover 可達。另在**獨立執行的 checker 副本**只增加 cover，找到第 20 拍 `rs1=5, rs2=7, rd=12, rvfi_order>=2`；原 checker 的 assertions 未因此改動。

這些檢查證明 Opus 小核心在指定任務下有可達且非零的 ADD，並能被一個 RVFI 結果突變擊敗。**它們沒有建立與原 PicoRV32 的行為包含、等價或 refinement。** 這次的 2.41 秒與 Sonnet 被人工停止的 10 分 29 秒也不是同一行為義務的有效加速比：Opus 排除了大量合法前序指令和時序。完整工具 log 留在本機 Git-ignored `results/picorv32/opus-5-5-medium-single-assertion/`；可分享的狀態摘要在 `verification.json`。

## 判讀

Sonnet 的固定參數特化不是單一 assertion 簡化的極限。Opus 展示可以保留真實暫存器相依、同時大幅縮小核心；這份產物適合研究「受限直線 ALU 程式的 ADD 回報」，不能作為完整 PicoRV32 的驗證替身。還能再縮小指令子集，但每刪一種前序指令，能代表的原核心執行歷史就再減少。要將候選上的 PASS 轉移到原核心，仍需另行證明兩者在所宣稱子集的退休紀錄關係。

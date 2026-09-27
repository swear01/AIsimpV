# Freestyle RTL rewrite：第一份端到端案例

2026-09-28，第一輪 3 次獨立生成中的 **第 1 次**。完整方法與週二、週三交付見[執行計畫](../freestyle_rewrite_plan_20260930.md)；本頁只記已執行結果。

| 候選 | 生成 | 前端（原／候選，含 property 接線） | 觀察 |
| --- | --- | --- | --- |
| 01 | DeepSeek Flash，單輪成功；無編譯修補、無人工語意提示 | PASS／PASS；各保留一個 assertion cell | 2394 行原 crossbar → 116 行單一路徑讀取模型；property 本文未改，環境說明縮窄 |
| 02 | NOT_RUN | NOT_RUN | 待執行 |
| 03 | NOT_RUN | NOT_RUN | 待執行 |

候選 01 把 master 0 讀取直接送到 slave 0，所有寫入與其他端口被固定為 inactive。它顯示模型會把「讀取回覆 stall 時保持」重述為一個暫存器的 hold 條件；同時刪掉原題中地址解碼、路由與交易控制。生成者自己把它稱作 reduced observation model，並宣告只考慮 master 0／slave 0 流量。這份候選可以作為**局部問題的提議**，目前不能把其 property 結果推回原 crossbar。

獨立分析沒有看到生成者的 `explanation.md`，也辨認出單一路徑、固定輸出與環境變更。人工核對找到一個具體握手疑點：候選在 slave 的 `RREADY=0` 時仍可能鎖住 `RVALID/RDATA`；當 master 解除 stall，slave 才完成握手，候選可能再次鎖住同一筆回覆。此處是來源碼逐拍推導，尚未用模擬或 formal 重播。獨立分析另有兩處可核對的錯誤：把 17 行的原 property 引到第 18 行，並將本輪本來就未啟用的上游 FORMAL suite 視為候選刪除的驗證內容。

[互動對照頁](../../experiments/freestyle_axilxbar/candidate-01/review.html)保留完整 RTL、property、環境文字與 unified diff；四張卡片的行號對應固定快照。生成者說明、獨立分析原文、人工卡片及[執行 metadata](../../experiments/freestyle_axilxbar/candidate-01/run.json)分開保存。原始 API request/response 與 Yosys log 保存在本機工作區的 `artifacts/freestyle-axilxbar-20260928/`，不隨 Git 發布；`results/` 為 Git 忽略的臨時副本。

原版與候選的設計、property 先各自 elaboration；事後又把同一 property 實際接到兩版 top，用 Yosys 0.69 執行 `hierarchy -check; proc; check` 並確認一個 `$check` cell，皆 PASS。這是前端合法性及接線結果；**沒有執行 BMC、prove、等價或 soundness 檢查**。原始上游 formal suite 不屬於本輪題目。生成 API 回報 39,498 input／15,185 output tokens；獨立分析為 41,776 input／43,286 output tokens，其中 40,746 output tokens 為 reasoning。request 到 response 的檔案時間差約 91／235 秒，並非端到端精確計時。

下一步按計畫以完全相同輸入與模型設定執行 02、03，再做未改寫 control 與兩個代表性案例的人工核對。這一例只能說明模型提出了哪種局部化、我們能辨認哪些缺口，不能據此估計模型一般抽象能力。

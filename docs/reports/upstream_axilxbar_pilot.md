# 上游 axilxbar formal property：三次自由改寫初探

2026-09-28。這輪要看 LLM 能否針對**實際設計、實際 property**提出有用的 RTL 簡化。起點是 ZipCPU/wb2axip commit `2e8d3bc2d26ddc33d1881022a2a2b9d3f0c16b9b` 的 4×8 AXI-lite crossbar，以及原始 `axilxbar.v` 中 `CHECK_MASTER_GRANTS` 的 [read-grant assertions](../../experiments/upstream_axilxbar/upstream/rtl/axilxbar.v#L1741)。原始 `faxil_slave.v`、`faxil_master.v` 與 [SBY 設定](../../experiments/upstream_axilxbar/upstream/bench/formal/axilxbar.sby) 也在生成輸入中。這與前一輪自寫 stalled-response property 的流程試跑是不同任務；兩輪結果不合併。

模型可以改設計和 property，輸出必須說明環境變動。三次獨立生成均使用 DeepSeek Flash、相同 prompt 與來源快照；三筆 `request_sha256` 都是 `13eee972c763124517948b0cf4a26e3aff50cae987b639f9ebc2d7d53c6492b7`。原版和候選用相同 Yosys formal frontend 檢查；另一個看不到生成者解說的 request 分析完整程式碼與 diff，最後人工核對關鍵行。未執行 BMC、無界 prove、等價或 abstraction soundness 檢查。

上游 `prf4x8_lp` task 使用 16-bit address。本輪凍結的生成題目使用上游 RTL 預設的 32-bit address，因為直接 `hierarchy -chparam` 在本機 Yosys 0.69 觸發內部 assertion。生成後另以保留全部 AXI ports 的 wrapper 設定上游 4×8、16-bit address、`OPT_LOWPOWER=1`；原版與三份候選均通過這組**額外的 frontend 檢查**。這不是執行上游 SBY proof task。[task](../../experiments/upstream_axilxbar/task.json) 與[來源 SHA-256](../../experiments/upstream_axilxbar/source.sha256.json) 固定可重跑輸入。

| 候選 | 輸出與前端 | 設計實際變化 | 對原題的判讀 |
| --- | --- | --- | --- |
| [01](../../experiments/upstream_axilxbar/candidate-01/review.html) | 初版是 patch 文字，frontend FAIL；一次只給編譯錯誤的修補後 PASS。formal check cells 905→618 | 修補版改寫 read-grant assertion；關掉 `FORMAL` 後，原版與候選同為 2664 design cells | **沒有看到功能 RTL 的實質簡化。** 它還誤刪整段 `CHECK_MASTERS`、`faxil_slave` 實例與 outstanding 檢查，生成者卻宣稱沒有其他變動。 |
| [02](../../experiments/upstream_axilxbar/candidate-02/review.html) | 初版 PASS；formal check cells 905→211 | 用組合式固定優先權 grant 取代狀態機；但所有 AXI 輸出固定為 0，非 formal opt 後 top 為 0 cells | **有新的內部表示，卻沒有可接受的 read transaction。** 保留下來的 assertion 只問另一個組合式系統。生成者有列出主要失去的行為。 |
| [03](../../experiments/upstream_axilxbar/candidate-03/review.html) | 初版 PASS；formal check cells 905→180 | 約 290 行的 read-focused 狀態模型，非 formal opt 後 949 cells；保留部分 AR/R 轉送 | **最值得追查的候選**，但只追蹤單一 grant、移除原 formal checker。第一筆 AR 接受後若緊接另一個 slave 的 AR，可能沿舊 grant 送錯 slave；目前是程式碼推導，尚未重播 trace。 |

表中的 formal check cells 是 frontend 產物數量，包含被留下的檢查結構；減少可能純粹因為刪掉 assertions 或 assumptions。design cells 是同一組 `read_verilog -sv; hierarchy; proc; opt; stat` 命令得到的結構數，也不是 solver 時間或正確性分數。每份候選的完整程式碼、生成者說明、盲分析、人工註記與來源對照都可從[對照入口](../../experiments/upstream_axilxbar/index.html)開啟。

獨立分析本身也提供一個重要結果：01 的第一份盲分析只看目標 assertion，錯說「其他部分未變」，漏掉被刪的 `CHECK_MASTERS`。把**機械產生的完整 diff**一併交給第二次盲分析後，它才指出這段刪除；兩版分析都保留在 [candidate-01](../../experiments/upstream_axilxbar/candidate-01)。未改寫原檔的對照則被分析器辨認為[沒有實質改動](../../experiments/upstream_axilxbar/unchanged_control_analysis.json)。因此分析文字只能輔助人工定位，不能代替看 diff。

這三例能回答的是：模型會提出 property 改寫、組合式 grant、縮減狀態機等不同表示；一旦開放整個 design/property，候選也容易漏掉上游 checker 或合法交易。目前**沒有一份**具備足夠證據可稱為原 crossbar 的正確抽象。若要深入研究 03，下一步應先重播具體 AR/response 序列，釐清新舊狀態與觀察事件的對應，再決定要不要投入正式的行為包含檢查。三份同一設計、同一 property 的探索不能估計一般成功率。

完整 API request/response、frontend 命令與 Yosys logs 保存在本機工作區的 `artifacts/upstream-axilxbar-20260928/`；Git 追蹤的頁面與 JSON 保留可公開檢視的結果摘要。

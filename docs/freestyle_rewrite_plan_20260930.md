# 9/30 報告：LLM 自由改寫 RTL 驗證問題的初步探索

後續選題修正：本文是衍生 property 的第一版計畫與流程試跑紀錄。主要研究證據已改用[上游 axilxbar formal assertions 的三次獨立實驗](reports/upstream_axilxbar_pilot.md)；兩組任務與候選不混算。

日期：2026-09-28，Asia/Taipei。這是新研究問題；[9/23 的 certificate pilot](wednesday_plan.md) 是既有成果，不計入本輪三份候選。

## 研究問題與可說的結論

觀察 LLM 收到一份有實際控制互動的 RTL 與一個起始 safety property 後，能自主提出哪些 design、property 或環境的簡化；再查明改寫實際保留或失去哪些資訊。本輪只量「提出候選」與「人能否追溯、質疑候選」，不量一般化的正確率、soundness 或 solver 加速。

原 design、property、環境是不可改的**研究紀錄**，不是候選輸出的約束。候選可改 RTL、property、介面與前提；任何新增前提或刪掉的情境，都必須在結果中顯示。分析時將候選暫分為：實質重述、有條件或局部的簡化、失去原題內容、未判定。類別是事後判讀，不是生成白名單。

## 固定案例

使用 ZipCPU/wb2axip commit `2e8d3bc2d26ddc33d1881022a2a2b9d3f0c16b9b` 的 `rtl/axilxbar.v`、`rtl/addrdecode.v`、`rtl/skidbuffer.v`，保留上游檔頭與 Apache-2.0 授權。指定 top `axilxbar`，採原始 RTL 的預設參數：`NM=4`、`NS=8`、`C_AXI_ADDR_WIDTH=32`、`C_AXI_DATA_WIDTH=32`、`OPT_LOWPOWER=1`。本輪只使用下述**衍生的單一 property**，不宣稱重跑完整上游 formal suite。原擬用 16-bit address、`OPT_LOWPOWER=0`，但本機兩套 Yosys 0.69 對這份來源執行 `hierarchy -chparam` 均觸發同一內部 assertion；預設組態可正常 elaboration。錯誤 log 留在本機 run 目錄。

起始 property：對 master 0，若在時鐘邊緣觀察到 `S_AXI_RVALID[0] && !S_AXI_RREADY[0]`，且相鄰兩次觀察均不在 reset，下一次邊緣的 `S_AXI_RVALID[0]`、`S_AXI_RDATA[0+:32]`、`S_AXI_RRESP[0+:2]` 應保持。起始環境不另加 AXI transaction assumptions；clock/reset 與 assertion 的精確寫法保存在 case 檔。此題可能比上游受假設約束的 property 強；若原題本身有反例，保留這個結果，先調整並重新凍結**兩邊一致**的題目，再開始正式生成。

原版與候選都用同一個公開記錄的 Yosys 前端命令做 parsing、參照解析、參數 elaboration 與 structural check。`FORMAL` 不在 design frontend 中啟用，以免引入整份上游 property suite。候選若更改 top／介面，前端命令依候選 manifest 指定，不偷偷把它改回原介面。前端成功只表示可 elaboration，不表示 property 或抽象正確。

## 實驗流程

1. **凍結任務。** 保存來源 commit、三份上游檔、原始 property、設計組態、工具版本、命令與 SHA-256。先跑原題的前端檢查。完成後不改生成輸入；修題須另立版本。
2. **生成三份候選。** 固定 `deepseek-flash`、本機既有 gateway、`reasoning_effort=high`、`max_tokens=65536`，各用全新單輪 request；完整原始 bundle 與 prompt 相同，單次 HTTP 上限 600 秒。每輪可自由提交完整設計、改寫 property、環境差異及簡短說明。保留第一次輸出；只容許一次以實際 compiler 錯誤為內容的修補，不給語意提示。失敗、截斷、沒交檔都列入三次分母。每輪記錄 model/endpoint、request/response hash、token usage、時間、產物 hash、人工介入。
3. **只做前端檢查。** 原版與候選都記 `PASS`、`FAIL` 或 `NOT_RUN` 及完整 log。檢查候選聲稱的檔案、top、依賴及 property 接線是否真的存在；若 property 介面改了，須使用候選宣告的接線，缺少接線就標 `BINDING_UNKNOWN`。確認 assertion cell 存在；不把 frontend pass 當 correctness。若候選完全改為非 RTL 問題，保存原輸出並標成 `NON_RTL`，不要硬改成 RTL 來湊 pass。
4. **獨立解讀。** 每份候選使用新的分析 request。先給原始與候選程式碼、property、環境及 frontend log；先不給生成者說明或生成歷程。分析者只列具體改動位置、被省略資訊、保留關係、property/環境變化、可疑事件序列和未判定事項，不評分、不修改候選。原版原封不動的 control 也給相同指令；合理輸出應辨認沒有實質改寫。
5. **人工核對。** 先看 diff、原始與候選邏輯，再比對生成者和分析者文字。至少核對兩個最有代表性的改動或失敗；每張改動卡片明列核對範圍與狀態：未核對、程式碼支持此解讀、有具體疑點、關係不明。未讀到的部分不視為已檢查。
6. **展示。** 靜態頁讀固定快照與 JSON。可看完整原/候選 RTL、property/環境、一般 diff、前端結果；概念卡片可連到原版與新版的多個行範圍，並分開顯示生成者說明、獨立解讀與人工註記。行號由固定檔案快照驗證。三份全部在總覽，報告詳談兩例。網頁只呈現證據，不顯示「sound」勾選。

生成提示的必要邊界：以原始驗證問題為出發點，提出更簡單且可能有助於處理原問題的候選；允許更改 RTL、property、介面與前提；交代改動、與原題的**預期**關係及新增前提。關係不確定可標猜想。不要要求 h/J/w、certificate、固定原變數或事前 mapping。分析提示要求逐項指向實際檔案／行號，不能把「未找到問題」寫成「已證明正確」。完整 prompt 隨 run 封存。

## 9/28–9/30 執行與停損

| 時間（台灣） | 交付 | 停損規則 |
| --- | --- | --- |
| 週一 9/28 | 凍結原題並通過前端；第一份獨立候選及第一版對照頁 | 若 `axilxbar` 原題前端無法建立，診斷缺檔／語法／工具；仍不通時改用 repo 內已能 elaboration 的公開設計，另記選題變更 |
| 週二 9/29 白天 | 同設定完成其餘兩份、一次固定編譯修補上限、乾淨分析與 control | API 故障可重試一次同請求，明記 transport retry；不可換模型後仍併入同組 |
| 週二 20:00 | 停止擴大功能；人工核對兩例、修正頁面定位錯誤 | 若未收滿三份，保留失敗列與原輸出；不以人工撰寫候選補位 |
| 週二 22:00 | 凍結 JSON、網頁與報告材料 | 週三只演示凍結資料，避免依賴現場 API |

第一個端到端 goal 的驗收：一份真實模型候選（成功或失敗都保留原始證據）、原題與候選各一份前端結果、一份獨立解讀、一個能把改動卡片連回真實行號的本機頁面。後續兩份是同一研究計畫的擴充，不因第一份成功就預告結果。

報告依序展示：固定問題與自由度、三份完整總表、一個有意思的實質改寫、一個具體失敗或疑點、可支持的結論與下一步。若三份都失敗，報告三種失敗的實際證據。任何「正確抽象」、「原題已證明」、「更快」的說法，都須另有相應檢查；本輪前端與人工分析不提供這些結論。

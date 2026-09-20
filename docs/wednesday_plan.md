# 週三報告執行計畫：中小型 RTL rewrite 的可驗證性

日期：2026-09-21（一），Asia/Taipei。報告日：2026-09-23（三）；採週二 20:00 凍結功能、22:00 凍結結果與材料。若報告時間另有安排，保留這個較早截止點。

本文件取代 9/20 計畫的後續排程，舊文件與原八週研究計畫保留。這是待執行計畫；表中的預估規模與候選公式不是已完成實驗。

範圍已確認：人工指定 rewrite／證書、固定 C/A 的 LLM certificate discovery，以及 LLM joint RTL＋certificate 生成都納入本輪工作。先建立 gold 可驗證性，再執行兩個有預算上限的 LLM pilots。人工指導 coding agent 寫出的候選不能算成自主發現成功。GitHub issues 記錄每項依賴與實際狀態。

## 1. 週三要交付的結論

報告主題建議：**「中小型 RTL 狀態改寫：對應證書、性質保持與失敗分析」**。

要回答四個問題：

1. 改寫是否真的改變狀態表示或刪除內部狀態，而不只是改名？
2. 獨立 checker 能否證明原始設計的指定觀察行為被包含？
3. 通過證書的抽象，是否仍能證明原先凍結的 safety property？
4. 成本與失敗原因是什麼：前端、證書、抽象過粗、solver，或原始設計違規？

成功標準是取得可重跑的正例與負例。狀態變少、證書通過、property 可證、端到端變快是四種不同結果，分別報告。

## 2. 起點：已完成與尚未完成

| 項目 | 目前證據 |
| --- | --- |
| P1 counter、P5 stalled producer | 已完成手工模型及真實 RTL 路徑；既有 89 項測試通過，包含錯 certificate、假反例與真 bug 對照。 |
| Checker | h/J/w、五項義務、初始集合非空、型別/hash/clock 綁定已有實作。 |
| Property backend | 已有全狀態一步證明與 tiny 完整枚舉；較大模型不能依靠枚舉。 |
| skidbuffer DW=8 | 未改上游 RTL、FORMAL 未啟用時成功匯入，實測 18 state bits；尚無新 certificate/property 結果。 |
| AVR pipeline | 原始 embedded assertion 在 write_btor 遇到 `$check`，尚未接入。 |
| sfifo | 原始 memory write 遇到 `$memwr_v2`；尚未接入。 |
| 工具 | 現有 isolated YoWASP Yosys、Z3 可用。`yowasp-yosys-smtbmc --help` 可執行；`yowasp-sby --version` 回 `unknown SBY version`，尚未確認 prove flow。須保存 package/source hashes，不能編造 SBY 版本。 |
| LLM discovery | 尚未執行，不能把現有結果歸因於自主生成。 |

既有完成證據見 `../SPRINT_REPORT.md`。本計畫不以新規劃覆寫歷史結果。

## 3. 固定 test set 與分母

主矩陣為 **4 個新 design/config/property tasks**，包含 **1 個人工 control＋3 個公開 RTL 實例，公開設計共 2 個家族**。既有 P1/P5 是回歸附件，FIFO 是額外挑戰；兩者都不混入新主矩陣成功率。

| ID | 來源／設定 | 凍結的主 property | 正例 rewrite | 規模：C → A，待實測者明列 |
| --- | --- | --- | --- | --- |
| R1-fsm | 人工 3-state FSM；one-hot 3 bits | idle/busy/done 三個觀察恰有一個成立 | one-hot → 2-bit binary；J 為合法 one-hot | 預估 3 → 2 design bits |
| R2-skid8 | ZipCPU skidbuffer，DW=8 | 未 reset 的 output stall 必須保持 valid/data | 刪除內部 r_data；兩個 valid 改為 occupancy | C 已測 18；A 預估 10 design bits |
| R3-skid32 | 同一 skidbuffer，DW=32 | 與 R2 相同 | 同一改寫族，測寬度擴大 | 預估 66 → 34 design bits |
| R4-pipe32 | AVR 原始 32-bit pipeline | `d == p + q || d == 0`，32-bit 模數加法 | 兩個 pipeline state → 一個 sum state＋自由分解 | design 預估 96 → 64；monitor 64 → 64；合計 160 → 128 |

主矩陣每題預先指定三種 attempt，共 **12 筆基本 attempt 記錄**：

- **A-good＋gold certificate**：測改寫可證且有用。
- **A-coarse＋自己的正確 certificate**：測行為包含成立，但必要關係被丟掉。
- **同一 A-good＋錯 certificate**：測 checker 拒絕；不能改寫 A 後再稱是 certificate-only 對照。

這代表 8 個主要 distinct C/A pairs、12 個基本 certificate attempts。修正或重跑會增加 attempt 數，必須另記，不能仍稱只有 12 次。錯證書、參數變體與 timing repeats 都不是新設計家族。

R1 若宣稱等價重編碼，另跑反向 certificate；沒有反向證據就只報已驗證單向包含。R2/R3/R4 若宣稱嚴格抽象，保存一條 A 可行、C exact replay 不可行的觀察 trace；沒有此證據則標 strictness UNKNOWN。

**最低報告內容**：所有四題都有明確結果或阻礙；至少以 skidbuffer 與 pipeline 兩個公開家族嘗試完整流程。未完成的列保留 UNSUPPORTED／UNKNOWN／NOT_RUN，不以自製案例替換後宣稱公開案例成功。

## 4. 具體 rewrite 候選

以下公式用於固定人工 gold 候選；全部仍須由實際 RTL 匯出後驗證。

### R1：FSM 重編碼

C 從 `001` 開始，在 advance 時依序 `001 → 010 → 100 → 001`，其餘時間 hold。A 從 `00` 開始，對應 `00 → 01 → 10 → 00`。

- h：`001/010/100` 分別映到 `00/01/10`；非法 concrete 狀態的 h 必須仍是 total expression。
- J：C 恰為上述三個合法 one-hot 值之一；不能靠假設 J 成立省略 INIT_J/STEP_J。
- O：相同的 idle/busy/done BV1 輸出；C 對三個合法編碼作 equality decode，A 對三個對應編碼作 equality decode。
- A-coarse：允許自由選擇 2-bit 下一狀態，包括 `11`；`11` 解碼為三個觀察全不成立。w 選取原始下一狀態的編碼，預期 gate 可過但 property 有可達反例。
- 錯 certificate：J 漏掉一個可達狀態，應由 INIT_J 或 STEP_J 擋住。

### R2/R3：skidbuffer 的 occupancy＋資料抽象

固定參數：`OPT_OUTREG=1, OPT_LOWPOWER=0, OPT_PASSTHROUGH=0, OPT_INITIAL=1`。

記 C 的內部 valid 為 r、輸出 valid 為 v、內部 data 為 b、輸出 data 為 q。A 保留 q，將 r/v 改成 2-bit n，刪除 b。

```text
h.n = r ? 2 : (v ? 1 : 0)
h.q = q
J   = r => v
w.z = b

A.o_ready = (n != 2)
A.o_valid = (n != 0)
A.o_data  = q

n' = reset ? 0 :
     n==0 ? (i_valid ? 1 : 0) :
     n==1 ? (i_ready ? (i_valid ? 1 : 0) : (i_valid ? 2 : 1)) :
     n==2 ? (i_ready ? 1 : 2) : 0

q' = (n==0 || i_ready) ? (n==2 ? z : i_data) : q
```

初值 n=q=0；n=3 需有明確 total transition，且由初值不可達的主張要有證據。LOWPOWER=0 時 reset 不直接清除 data；不得為方便把 q 的 reset 行為改掉。

主 contract 固定 `O=(o_ready,o_valid,o_data)`，E=true，reset 是每拍自由的同步公共輸入，保持原 RTL 的 reset next-state 行為。主 property 為：

```text
o_valid_t && !i_ready_t && !i_reset_t
    => o_valid_(t+1) && o_data_(t+1)==o_data_t
```

這明確標記為 **upstream RTL 上的衍生 port-level task**。它不載入上游整份 FORMAL harness；該 harness 有初始 reset、upstream hold assumptions 及跨兩個 sampling 時刻的 reset guards。上述 property 是較強的 hold 要求，不能將此結果寫成「完整上游 SBY suite 通過」。B0/A 都使用同一個衍生 contract。

A-coarse 保留 n 的控制轉移，但讓 q 每拍取自由 z；其 w 必須改成 C 的 q-next 函數，而不能沿用 `w=b`。預期包含關係仍成立，但 stall hold 可被違反。錯 certificate 使用 A-good，但令 w=0，確認 STEP_MAP 能產生反例。

至少 cover：有效輸入被接受、buffer 滿、輸出 stall、解除 stall、reset 與 stall 相遇，避免只驗到沒有傳輸的行為。

### R4：pipeline 的 sum 表示

記原始 `stageOne=a, stageTwo=b, dataOut=d, tmp_stageOne=p, tmp_stageTwo=q`。A 的 design state 為 s,d；monitor state 仍為 p,q。全部沿用原始零初值。

```text
h.s = a + b                 // BV32 模數加法
h.d = d; h.p = p; h.q = q
J = true
w.z = a

A.stageOne_view = z
A.stageTwo_view = s - z
s' = (dataIn + c1) + (z & c2)
d' = reset ? 0 : s

trusted history monitor（C/A 相同更新定義）：
p' = stageOne_view
q' = stageTwo_view

O = (d,p,q)
P = (d == p + q) || (d == 0)
```

C 的兩個 view 就是 a/b。A 提供 z 與 s-z；同一 w=z=a 使兩個 view 與原 a/b 對應。證書同時覆蓋 monitor state 的初始化與一步更新，不允許直接把 monitor 改成「永遠安全」。property、monitor 初值／位寬／history-update 定義均凍結；改變的 view 接線也是被檢查的改寫內容。

原同步 reset **只清除 d**，a/b/p/q 並不因 reset 一起清零；A 也不能額外清除 s/p/q。O 明確包含原 property 所需的 p/q，不能壓成一個固定為真或假的 bad bit。

A-coarse 把 `stageTwo_view` 改成獨立自由 z2，其餘保持上述結構；w=(a,b) 可匹配 C，但丟失 `stageOne_view + stageTwo_view == s` 關係。預期原 P 出現可達假反例。錯 certificate 可令 `h.s=a` 而非 a+b，保持相同 A 與 contract，預期 STEP_MAP 被拒絕。

這兩個公开家族的 properties 可能很容易直接證明；選它們是為了驗證非局部 rewrite，不預設它們能提供加速。

## 5. 最小工程工作與驗收

所有 code changes 使用獨立 branch/worktree，初始實作基底為 `AIsimpV` 的 `5606127cf7b85eb1e3ba59fb5c1c008774868847`。只使用 Codex 內建 subagents 或 Codex on HAPI。以下是待實作工單，不是假裝已有的 CLI。

| 工單 | 內容 | 完成條件／預算 |
| --- | --- | --- |
| T1 固定來源與 contracts | 保存兩個 upstream revisions、檔頭、參數；建立 R1–R4 IDs；描述 reset/sampling/observations/monitor | C 與 contract 在候選生成前完成 hash；約 1–2 工時 |
| T2 正常 direct baseline | 使用現有 YoWASP SBY／smtbmc＋Z3 跑固定 harness 的 prove；保留正常 preprocessing | 至少一個已知 safe 與已知 bug 校準；保存 proof 方法、版本/hash、命令與失敗；約 2–3 工時 |
| T3 前端窄幅接入 | 保持 Yosys→BTOR2→typed IR；處理指定 pipeline property 的受信任 extraction、必要 operator／同步 reset 描述 | 不默默刪 assertion；原 property 有外接等義 monitor，相關 state 被保留；約 2–3 工時 |
| T4 公開 gold rewrites | 先 skid8、pipeline32，成功後沿同契約做 skid32 | 真正 C/A RTL 各自匯出；完整 INIT/STEP/OBS gate；約 3–5 工時 |
| T5 負例與 R1 | coarse A、錯 certificate、FSM J；既有 tiny BUG 流程回歸 | 每次有獨立 candidate ID；任一假接受優先修復；約 2–3 工時 |
| T6 生成工作區與兩個 LLM pilots | 固定輸入包／可信快照、候選與 feedback 日誌；certificate-only 及 joint rewrite | 完整保存成功／失敗，最多 8 次／30 分鐘 machine search；工程約 3–5 工時 |
| T7 重跑與報告 | 固定版本後乾淨重跑、成本表、兩個公開案例 before/after 圖、反例與限制 | Tue 22:00 前 evidence index＋結果表＋報告材料；約 3–4 工時 |

人工主線估算 **13–20 工時**；LLM 工作區／provenance 與兩個 pilot 另估 **3–5 工時**，合計 **16–25 工時**，可部分平行。這是規劃預算，不是已完成工作，也不保證所有 gold 或自動候選都通過。

最小語意擴充：明確登錄「同步 reset 作為普通公共輸入，沒有額外 reset sequence assumption」的 profile。若現行 schema 無法表達，新增最小版本並測試，不將含 reset 的 task 冒充原本的「無 reset」設定。週三不為這個 pilot 實作通用 temporal assumption 系統。

assertion extraction 必須保存來源位置、原始 predicate、取樣、monitor 狀態與 hash。只有在原 assertion 已由固定等義 harness 承接後，才可從 design-only export 移出該 assertion；不能只照錯誤提示亂加 clock/reset 轉換 pass。

SBY 是現有 Yosys 上的 property proof driver，不新增手寫的第二套 RTL/SMT2 parser。Certificate 保持 BTOR2 路徑；C/A 的來源、參數、正規化及 property backend 輸入都需 hash 綁定，核對兩條 proof harness 指向同一個設計語意。

目前沒有需要使用者安裝的系統套件。先對已存在的 isolated tools 做 proof smoke；真的缺少系統依賴時，再提供確切套件與用途。不要為小型 pilot 先安裝完整新 EDA 平台。

## 6. 每題都走同一個驗證流程

1. **B0**：原始 C＋凍結 contract，使用正常前處理和正式 proof backend。
2. **改寫／編譯**：保留 C、A、來源版本與預處理後規模；不能以人工模型替代失敗的 RTL export。
3. **Certificate**：initial nonempty＋五項義務；w 僅在 certificate harness 出現。UNKNOWN/timeout 一律不接受。
4. **Property**：只有 A＋相同 contract；所有新 z 每拍自由。C 的 J 不能成為 A 的 assumption；需要 A 自己的 invariant 時另證。以 prove／完整歸納／完整 reachability 才能標 SAFE。BMC 無反例只標 BOUNDED(k)。
5. **反例**：確認 abstract trace 從合法 initial 出發並違反原 P，再在 C 固定公共 inputs/observations 做 exact replay。
6. **分類**：certificate rejection、spurious trace、unknown、unsupported 與 concrete BUG 分开。另一條 concrete bug 必須標明來源，不能假稱原抽象 trace replay 成功。
7. **封存**：全部 queries、raw solver outputs、trace、hash、time 與失敗 attempt 都留存。

先用一個固定 engine：`smtbmc z3` 的 `prove`，初始 depth 20，C/A 對稱使用。若未完成工具資格檢查，保留 ENGINE_UNAVAILABLE，不能退回有限枚舉後宣稱公平比較。日後加 PDR 屬後續配置，不在看到哪題有利後臨時挑 engine。

若外部 trace 格式 adapter 成為瓶頸，可用人工構造的短 trace，分別以 A-prefix SAT、P 違反與 C-prefix UNSAT/SAT 驗證；明列 trace 是人工構造。這保留證據強度，但不冒充自動 counterexample extraction。

新增的必要測試只針對改動風險：reset/stall 邊界、32-bit overflow/subtraction、monitor 一拍對齊、正規化未改觀察、錯位寬與 stale hashes、自由 z 未被限制。沿用既有測試與 helpers，不另建測試框架。

## 7. 預算與公平成本

| 類別 | 初始上限 |
| --- | --- |
| 單次 RTL export | 60 秒 |
| 單 certificate SMT query | 10 秒；有明確理由才提高到 30 秒，仍受總 cap |
| 一份 certificate 全流程 | 120 秒總 wall time，包含失敗義務 |
| B0 或 A 的一次 property proof | 各 120 秒，同一 engine／設定 |
| replay 或 strictness probe | 每次 30 秒 |
| 每個新主 task 的正式 machine budget | 30 分鐘，包含所有候選、B0、失敗與重跑；四題最多 2 小時 machine wall budget（串行上界） |
| 人工候選 | 每題預指定 2 個 A；另 1 份錯 certificate；gold 修正最多再 2 次，全部計入 |

首次 qualification 可做 smoke；先固定本次 run 的 source/tool/config/contract hashes，再於週二下午執行報告矩陣；20:00 後停止功能修改。若要給 runtime 比較，每個固定配置跑 3 次，保留原值與中位數，計入上述總 budget；避免與其他 solver job 爭用 CPU。不能只留下最好的那次。

```text
T_workflow = Σ generation + Σ frontend + Σ certificate
           + Σ abstract_property + Σ replay/strictness/refinement
T_B0 = concrete preprocessing + concrete property proof
```

人工發現時間分列 human_minutes，機器成本不代表完整人工方法成本。B0 參考時間通常不重加到候選 workflow；若實際拿 B0 search 作為找 bug 的 fallback，該次計入 workflow。suite wall time另外列，避免重複加總。

model size 同時報 design state、monitor state、nondet bits、正常 preprocessing 後 state/cells。若一般 COI/DCE 已把同樣邏輯消掉，必須明列，不能把 raw RTL 位數减少當成本收益。

## 8. 到週三的排程與停止點

| 時段（台灣） | 工作 | 必須有的可檢視產物 |
| --- | --- | --- |
| 週一上午 | T1 contracts、工具 prove smoke；T2/T3 可平行 | 固定 task manifest、可用的 B0、前端缺口清單 |
| 週一下午 | skid8 与 pipeline32 gold RTL／certificate | 每題至少首次完整 attempt，成功或失敗都留 log |
| 週一晚間 | 修正有限次候選；skid32 scaling | 公開案例 gate/property 初步矩陣 |
| 週二上午 | A-coarse、錯 certificate、replay；R1 FSM；已具資格的 LLM pilots | 正例／過粗／錯證書分離；非平凡 J 案例 |
| 週二下午 | 固定來源重跑、B0/A 成本、必要反例與 cover | 正式 results.csv/json＋證據索引 |
| 週二 20:00 | 停止新增功能 | 冻结 source/tool/config/contract hashes |
| 週二 22:00 | 凍結報告 | before/after、結果表、限制、重跑包 |
| 週三報告前 | 只做展示命令及數字核對 | 預存結果可離線展示，不依賴現場長 solver run |

調整規則：

- 工具資格檢查 2 工時仍無法完成：診斷阻礙、限定等義替代路徑；不把「有 executable」當成 proof 成功。
- 週一結束仍無任何公開 RTL gate 成果：週二集中 skid8，暫停 FIFO；LLM 工作可繼續準備輸入隔離與記錄，但不在缺少 gold 的情況下冒稱正式可驗證 pilot。其餘主列保留真實未完成狀態。
- pipeline extraction／monitor 對齊超過 3 工時仍不可靠：列 UNSUPPORTED，報告前不寫通用 SVA parser 救場。
- 任一 negative 被誤接受、w 洩漏到 property 或 clock/reset 對不上：暫停新案例，修正後重跑所有受影響結果。
- Gate 通過而 P 失敗：先保留這個研究結果；不改 P、強化 E 或限制 z 讓它「通過」。
- 時間不足時先取消 FIFO、額外 timing repeats；LLM pilots、R1 或公開案例若未完成仍留在預登記表與 issues，不能改分母美化成功率。

開發依 issue dependency 分波平行：先 contracts 與 formal 工具資格；再由不同 Codex agents 分別負責 skidbuffer、pipeline、FSM 與生成工作區。主 agent 擁有共享 checker/schema/runner 的整合，避免多個工作同時改同一介面。每個 issue 列 owner_paths；先合併依賴，再開消費該介面的工作。solver timing 測量期間不平行搶資源。

## 9. LLM 自動探索的必要 pilots 與 FIFO 額外挑戰

**LLM 必要 pilot A：固定 C/A 找 certificate。** 固定 R2-skid8 的已驗證 gold pair；若沒有可靠的 gold 結果，明列 BLOCKED 與原因。最多 4 次候選、15 分鐘。保存首個回答與最多 3 次依實際 checker 回饋的修正；這是單次探索紀錄，不是正式無回饋／有回饋 ablation。

**LLM 必要 pilot B：joint RTL＋certificate。** 在相同 skid8 task，只提供 C、contract、介面與允許的語意，讓 agent 提出 A，再以新 manifest 產生／修正 certificate。最多 4 次候選、15 分鐘。A 的每次修改都重做 frontend、綁定與全部 obligations。

兩個 pilots 合計最多 8 個生成 attempts／30 分鐘，與人工主矩陣的 12 個基本 attempts 及最多 2 小時 machine budget 分開報告。使用固定的既有 Codex model/config，保存實際模型識別、prompt、formal feedback、所有候選、耗時、可取得的 token 數與人工介入；不能猜測拿不到的 API 費用。只有一個 task／run 時不做成功率泛化或 feedback 優勢宣稱。

候選工作區與可信檢查端須先建立邊界。C、contract、checker、tests、gold certificate、acceptance records 不能由生成端修改；自主探索的輸入包不包含 gold mapping／本計畫的候選公式。若無法阻止生成端讀取 gold 或修改可信輸入，就明列隔離未完成，不稱為獨立 discovery。每次檢查都以可信快照重驗 hashes，保存原始候選，不只留修好後的版本。

生成環境／記錄功能可與 gold 開發平行準備；依赖的 gold pair 與 checker 資格完成後才執行正式 pilot。若截止時某 pilot 未完成或所有候選失敗，對應 issue 留 open 並報真實結果，不悄悄把必要項改回 optional。

**FIFO 額外挑戰**：只有兩個公開家族已收齐核心證據才開始，先 sfifo 4×8 再 16×8。有限 memory 可探索 Yosys 展開，但未初始化 memory 保持任意初值，不能補零。未完成 symbolic-init／memory 語意與對照檢查就保持 UNSUPPORTED；不納入本次主成功率。

## 10. 結果表與報告內容

最小主表：

| Task | rewrite／來源 | C/A design＋monitor bits | certificate | abstract property | replay／strictness | B0 time | workflow time | 原因 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R1-fsm | 待執行 | 待量測 | NOT_RUN | NOT_RUN | NOT_RUN | — | — | — |
| R2-skid8 | 待執行 | 待量測 | NOT_RUN | NOT_RUN | NOT_RUN | — | — | — |
| R3-skid32 | 待執行 | 待量測 | NOT_RUN | NOT_RUN | NOT_RUN | — | — | — |
| R4-pipe32 | 待執行 | 待量測 | NOT_RUN | NOT_RUN | NOT_RUN | — | — | — |

每列下方以 good/coarse/bad-cert 三個 attempt 展開，report schema另存 seed/run、candidate hashes、各義務與成本分項。附帶的 `rewrite_results_template.csv` 有 12 筆 NOT_RUN 記錄，量測欄位留白；它是執行模板，不是已完成結果。

建議 8 頁、約 10–12 分鐘：

1. 問題：狀態改寫後如何建立可驗證語意對應；研究目標與本次 scope。
2. Test set：4個新tasks、其中2個公開家族／3個公開實例；原始/衍生property標記。
3. Skidbuffer before/after：兩個 valid＋內部 data → occupancy＋保留輸出data；h/J/w。
4. Pipeline before/after：a/b → s=a+b；同一自由分解如何保留兩個 monitor 的關係。
5. 主結果表：accepted、property結果、反例、時間；所有失敗可見。
6. 兩個 LLM pilots：候選與修正鏈、真實 verdict、成本及人工介入；與人工 gold 分開。
7. 一個錯 certificate 與一個 sound-but-coarse A：為何兩者需要不同處理。
8. 結論與下一步：目前證成的範圍；LLM discovery／memory／效能各自還缺什麼。

交付物：固定來源與 contracts、全部候選及 certificate、results.csv/json、queries/logs/traces、兩張可讀 before/after 示意、報告講稿與一個已實際跑過的 reproduce entry point。報告圖只從最後凍結的 RTL/model 製作。

可用敘述必須按實際結果填數字，例如：「在 X/Y 個預先指定的 task 中，指定 rewrite 通過包含關係檢查；其中 Z 個在自由 nondeterminism 下仍可證目標 property。」公開家族、參數實例與人工 calibration 分開給數字。

不能提前寫：所有中小 RTL 通用、LLM 自主 rewrite 已有效、比正常 formal engine 快、完整 upstream property suite 已重現、或所有 accepted rewrite 都是嚴格抽象。

## 11. 來源與版本

- [AVR dataset](https://github.com/aman-goel/avr/blob/9a76dc632066c4416cebccda3a4974a4f8adede8/tests/README.md)；[pipeline RTL](https://github.com/aman-goel/avr/blob/9a76dc632066c4416cebccda3a4974a4f8adede8/tests/opensource/pipeline/pipeline.v)。
- [ZipCPU skidbuffer RTL](https://github.com/ZipCPU/wb2axip/blob/2e8d3bc2d26ddc33d1881022a2a2b9d3f0c16b9b/rtl/skidbuffer.v)；[原 SBY 設定](https://github.com/ZipCPU/wb2axip/blob/2e8d3bc2d26ddc33d1881022a2a2b9d3f0c16b9b/bench/formal/skidbuffer.sby)。
- [ZipCPU sfifo RTL](https://github.com/ZipCPU/wb2axip/blob/2e8d3bc2d26ddc33d1881022a2a2b9d3f0c16b9b/rtl/sfifo.v)。
- [SBY 官方格式／prove 說明](https://symbiyosys.readthedocs.io/en/latest/reference.html)。
- 本地候選查證及 smoke 記錄：`benchmark_shortlist.md`；目前 checker 語意：`semantics_v0.md`。

## 12. GitHub 工單與平行順序

公開專案：[swear01/AIsimpV](https://github.com/swear01/AIsimpV)。[總追蹤 #1](https://github.com/swear01/AIsimpV/issues/1) 與 [週三里程碑](https://github.com/swear01/AIsimpV/milestone/1) 記錄實際進度。下表是發布時的依賴；即時狀態以 issue 為準，新實驗初始均為 NOT_RUN。

| 工單 | 執行前置 | 責任範圍 |
| --- | --- | --- |
| [#2 來源與 contracts](https://github.com/swear01/AIsimpV/issues/2) | 可立即認領 | 固定上游來源、四題 contract、同步 reset profile |
| [#3 B0 與正式 property backend](https://github.com/swear01/AIsimpV/issues/3) | #2；工具資格檢查可先做 | proof driver、SAFE／BUG／UNKNOWN 校準 |
| [#4 前端接入](https://github.com/swear01/AIsimpV/issues/4) | #2 | BTOR2 adapter、原 assertion／monitor 保持 |
| [#5 skidbuffer 8/32](https://github.com/swear01/AIsimpV/issues/5) | #2、#3、#4 | R2/R3 gold、coarse、bad certificate 與證據 |
| [#6 pipeline32](https://github.com/swear01/AIsimpV/issues/6) | #2、#3、#4 | R4 sum-state 改寫、monitor、負例 |
| [#7 FSM 與獨立負例檢查](https://github.com/swear01/AIsimpV/issues/7) | #2、#3、#4；公開案例 review 待 #5/#6 | R1 非平凡 J、重編碼與獨立核對 |
| [#8 LLM 工作區與記錄](https://github.com/swear01/AIsimpV/issues/8) | #2 | 最小生成隔離、可信輸入與完整 provenance |
| [#9 固定 C/A 找 certificate](https://github.com/swear01/AIsimpV/issues/9) | #3、#4、#8，以及 #5 的 R2 gold 證據 | 最多 4 次／15 分鐘的真實 Codex pilot |
| [#10 自動 RTL＋certificate](https://github.com/swear01/AIsimpV/issues/10) | #9 有真實終態即可，不要求成功；其餘同 #9 | 獨立 context，最多 4 次／15 分鐘 |
| [#11 重跑、證據包與報告](https://github.com/swear01/AIsimpV/issues/11) | #2–#10 有結果或明確阻礙；表格可先做 | 人工／LLM 分表、成本、八頁報告與重跑命令 |
| [#12 FIFO 額外挑戰](https://github.com/swear01/AIsimpV/issues/12) | #11 完成後 | 可延期，不計入週三必要里程碑 |

整合負責人為 @swear01；執行 agent 認領時在 issue 記錄 branch、worktree 與檔案責任。第一波可平行做 #2 的語意／來源凍結及 #3 的工具資格檢查；第二波 #3/#4/#8；介面固定後 #5/#6/#7 各自獨立。共享 checker/schema/CLI 修改由主 agent 整合。#9 只需 #5 的 R2 部分有可靠證據，不必等待 skid32 完成。

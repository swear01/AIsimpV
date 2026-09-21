# 實際驗證時間：固定 RTL 改寫的配對量測

本次回答的是「已保存的改寫是否縮短實際 property proof，以及節省是否足以支付證書與轉換成本」。正式量測之前已在 [#17](https://github.com/swear01/AIsimpV/issues/17) 固定 [protocol](../timing_protocol.md)。原有 Wednesday 數據不覆寫。

## 證書究竟證明什麼

令原始模型狀態為 s、公共輸入為 u，下一狀態函數為 F_C；抽象模型的下一狀態為 F_A，另有自由輸入 z。證書提供當前狀態映射 h、原始模型上的 invariant J，以及選擇抽象輸入的 witness w。

| 義務 | 必須對所有符合條件的狀態／輸入成立 |
| --- | --- |
| 初始化 invariant | I_C(s) ⇒ J(s) |
| invariant 保持 | J(s) ⇒ J(F_C(s,u)) |
| 初始對應 | I_C(s) ⇒ I_A(h(s)) |
| 一步匹配 | J(s) ⇒ F_A(h(s),u,w(s,u)) = h(F_C(s,u)) |
| 觀察保持 | J(s) ⇒ O_A(h(s),u,w(s,u)) = O_C(s,u) |

[Checker](../../rtl_relate/checker.py) 將五個式子的反例逐一交給 Z3；全部 UNSAT 且 concrete 初始集合另經 SAT 確認非空，才接受。先驗 C/A/contract hashes、h/w 完整覆蓋與型別／位寬，不能換 property 後沿用舊證書。

由初始化與歸納，每條原始執行都可取 a_t=h(s_t)、z_t=w(s_t,u_t)，得到觀察相同的抽象執行，建立指定觀察下的 traces(C) ⊆ traces(A)。這是符號一步模擬關係的證明，覆蓋任意長度的合法執行。

接著，[property backend](../../rtl_relate/formal.py) 完全不接收 h/J/w，也不加入 J 假設。z 每拍自由；只有 base check 和 k-induction 都通過才報 SAFE。因此 A 滿足凍結的 safety property 才能經包含關係推出 C 滿足它。前端、encoding、Yosys、Z3 仍屬信任基礎，沒有另外檢查 solver proof object。

## 改寫的內容與研究強度

- FSM：one-hot → binary 的狀態重編碼；指定觀察下已證雙向等價。
- 人工 skid：valid flags → occupancy，刪去內部 buffered data，以任意資料取代，但保留 stall 時 output hold。
- Pipeline：(a,b) → s=a+b，使用相關的自由分解 (z,s−z)，保留 property 所需的加法關係。
- 保存的 LLM joint：保留兩個 valid bits，刪去 r_data；它與人工 occupancy 抽象的 state bits 一樣，結構不同。

因此縮 bit 是改寫的量化結果之一。抽象也增加可行行為，較少 state bits 並不直接代表較容易求解。現在只有兩個公開家族、三個參數實例及人工 FSM；hold／sum properties 都可由正常 B0 很快證明，尚不構成難例 benchmark，也未證明超越既有抽象方法。

## 量測方法與成本界線

每個固定 pair 兩輪記錄暖機＋八輪正式重複；C→A／A→C 各四輪，跨輪旋轉候選順序，工具串行。同一 frozen contract、工具、depth 20 與 timeout 120 秒。C/A 都取各自已檢查 export 的 normalized RTL，然後各自執行正常 proof preparation；與舊單次數據的部分 raw RTL 起點不同，不能直接混合計算。

1. **Property 時間**：完整 prove_rtl 呼叫的 wall time，含工具辨識、正常前處理、SMTBMC base／induction 與 evidence I/O。
2. **求解程序時間**：base＋induction 子程序 wall time，包含 SMTBMC／Z3 啟動及通訊，並非單獨 Z3 CPU time。
3. **已知候選驗證流程**：重新轉換 C/A＋certificate＋A property＋協調成本，以 pair wall 減去 C property 實際時間計算；不含 per-record 報表寫入，該成本保留於 suite wall。

B0 主比較是直接驗證準備好的 C；第三項把 C/A export 都計入新方法，屬本 runner 驗收已知候選的成本，不能外推成所有抽象系統的必要成本。找候選、人工準備，以及研究用途的 reverse/strictness/cover 未混入這次固定候選重驗。既有三次研究 runs 的生成／失敗／驗證 charged 合計 435.134 秒仍單列，沒有把保存的 LLM 候選當成零成本發現。

全為 fresh 工具程序、warm OS/filesystem cache；沒有清 cache 或宣稱獨占硬體。load／CPU affinity、工具來源、每輪 hashes、原始 logs、命令、timings 與所有失敗均保存。這是單機 pilot 的描述統計，沒有從少數重複估計一般成功率或保證統計顯著。

## 實測結果

**沒有觀察到穩定的 property-proof 加速；pipeline 在八輪全部較慢。** 五個固定候選的 40 組正式配對與 10 組暖機全部完成 certificate ACCEPTED、C/A SAFE；這不是新增五個設計家族。

下表為八輪的中位數，單位秒。C/A property 比較不含 certificate；最後一欄才加入轉換、證書與協調成本。

| 固定候選 | C property | A property | A 較快的配對 | 已知候選驗證流程 |
| --- | ---: | ---: | ---: | ---: |
| FSM 重編碼 | 0.587 | 0.572 | 6/8 | 1.331 |
| 人工 skid8 | 0.578 | 0.592 | 3/8 | 1.378 |
| 人工 skid32 | 0.592 | 0.611 | 2/8 | 1.385 |
| pipeline32 sum-state | 0.618 | 1.070 | 0/8 | 1.848 |
| LLM skid8 保存候選 | 0.579 | 0.590 | 1/8 | 1.355 |

FSM 的中位數僅差約 0.016 秒，C 範圍 0.545–0.616 秒、A 範圍 0.554–0.626 秒；八輪中六輪 A 較快，沒有據此宣稱可靠加速。兩個人工 skid 與 LLM skid8 的 property 中位數都稍慢，分散範圍亦重疊。全部五個候選的驗收流程都比直接 C property proof 更慢。

| 固定候選 | C 求解程序 | A 求解程序 | 配對 speedup C/A 中位數 |
| --- | ---: | ---: | ---: |
| FSM 重編碼 | 0.171 | 0.166 | 1.046 |
| 人工 skid8 | 0.167 | 0.171 | 1.026 |
| 人工 skid32 | 0.177 | 0.186 | 0.949 |
| pipeline32 sum-state | 0.206 | 0.663 | 0.313 |
| LLM skid8 保存候選 | 0.171 | 0.167 | 0.994 |

Speedup 大於 1 表示 A 較快；此欄是逐輪比值的中位數，不是左右兩個中位數相除。所有逐輪值、range、paired seconds saved 與勝出次數見 [完整 JSON](data/verification-timing.json)。

Pipeline 的完整 property 中位數增加約 **73%**；求解程序中位數約為 C 的 **3.22 倍**。慢點主要出現在 base：C 0.114 秒、A 0.564 秒；induction 則為 0.094／0.097 秒。兩邊都完成相同 20-step base，且相同 induction step 成功。因此慢點不能只歸因為 certificate 或一般工具啟動。

同時，pipeline 前處理後 state bits 雖從 257 降為 225，cells 仍是 20，SMT 模型檔由 14,914 增至 15,126 bytes；A 另有一個 subtraction cell。這支持「state bits 不是求解難度的充分指標」。自由分解及算術表示如何影響 solver 是下一個待隔離的假說；尚未做因果 ablation，不能宣稱單一 subtraction 就是全部根因。

本次 suite wall **103.216 秒**，暖機 pair 合計 **20.830 秒**、正式 pair 合計 **82.011 秒**，剩餘為報表及協調。外層命令 wall 103.277 秒另保存。可用 CPU affinity 為 32 個 cores，記錄的 1-minute load 約 0.64–1.23；不宣稱獨占主機。八輪每個候選的 C/A 模型 SMT hash 各自一致，沒有在中途換候選、工具或 property。

## 對研究下一步的影響

現在可以支持非局部表示改寫及可驗證包含關係，也取得一個 LLM 自動刪除資料狀態的案例；**這些候選尚不支持 verification acceleration。** 後續應優先尋找正常前處理後 B0 仍困難的 property，並讓候選選擇依實際 proof cost，而不是只依 state bits。對 pipeline 應先研究如何避免破壞 solver 容易利用的算術表示，再擴大 agent 搜尋。這些是後續工作，本輪不把它們當已完成結果。

## 重跑

獨立資料審核另核對全部 50 pairs、300 個 certificate queries、100 份 proof
與 900 個 proof artifact hashes，並重算所有統計；結果
[PASS，0 差異](data/verification-timing-audit.json)。自動審核 2.746 秒另計。
這是保存證據與統計的獨立檢查，未新增求解或模型呼叫。

原始模型、queries、logs、每輪結果與 source snapshot 保留於
[timing evidence ZIP](https://github.com/swear01/AIsimpV/releases/download/wednesday-pilot-2026-09-21/AIsimpV-verification-timing-evidence.zip)；
[封存索引](data/verification-timing-index.json)提供下載檔雜湊。

```sh
python3 scripts/measure_verification.py --out results/timing-new-run
```

使用全新目錄與既有 pinned tools；worktree 可透過 RTL_RELATE_YOSYS 指定已安裝的 YoWASP。此命令不呼叫 LLM，成功需要所有暖機及正式 pair 均完成 certificate ACCEPTED 和 C/A SAFE。缺少／失敗的正式 pair 使該候選 INCOMPLETE，不產生篩掉失敗的 median。

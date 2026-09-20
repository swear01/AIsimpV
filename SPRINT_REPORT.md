# RTL abstraction feasibility：實際執行報告

2026-09-20。這是已執行結果；原研究計畫與第一階段工單保持不變。

已跑通兩個預先指定的 gold fixture 家族，包含真正 RTL 匯出、獨立 certificate gate、自由 nondeterminism 的 property checking 與 exact concrete replay。89 項測試通過。尚未證成驗證加速、LLM discovery 或五家族可行性。

## 1. 真實 RTL 結果

| Case | C → A state bits | Certificate | Abstract property | 最終結果 |
| --- | --- | --- | --- | --- |
| p1 | 2 → 1 | ACCEPTED | SAFE | SAFE |
| p5_hold | 5 → 3 | ACCEPTED | SAFE | SAFE |
| p5_coarse | 5 → 3 | ACCEPTED | ABSTRACT_CEX | SPURIOUS_TRACE |
| p5_bug | 5 → 3 | ACCEPTED | ABSTRACT_CEX | BUG |

同樣四個 case 的手工模型路徑也得到相同結果。P1 與 P5 hold 均保存一條 A 可執行而 C 不可執行的觀察前綴，作為本案例嚴格抽象的證據。所有 SAFE 均由自由 z 下的全狀態一步證明取得，沒有把 bounded 無反例當成無界安全。

**P5 bug 的證據來源必須分清楚：**首次 abstract CEX 在 C_bug 仍不可行。Runner 隨後由 exact concrete search 找到另一條違規執行，再以 SMT replay 確認 FEASIBLE。結果記錄 `bug_source=different trace from exact concrete search`；原始抽象 trace 仍保留 INFEASIBLE，不冒稱已被具體化。

## 2. 正負測試與獨立核對

- 89 個 unittest 全部通過：58 個 checker/process 測試、5 組 frontend 測試、3 組 IR 測試、8 個獨立 oracle 測試、12 個 property/replay 測試、3 個成本與 verdict 測試。組內包含多個 subcases，不把它們當獨立設計數。
- 真實 RTL 匯出包含六個不同 source fixtures，與獨立整數語意核對 520 個 state/input valuations。
- 正式 demo 額外保存 10 個 intentional mutants 的完整結果，全部符合預期：7 個 CERTIFICATE_REJECTED、3 個 ERROR，沒有錯誤接受。
- 包含錯 init/step/observation/witness、J=false、非歸納 J、漏 state/z、位寬／hash 不符、空 initial、Mealy 共同 witness、fresh-z、solver unknown/timeout/error。
- 單 query timeout 為 5 秒。Solver 模型保留在 raw output 及 counterexample_smt；symbol_bindings 對應原模型 IDs。

本輪確實發現並修復三類問題：solver 版本查詢失敗未分類；frontend 丟掉 clock identity 導致違反 frozen clock 仍接受；concrete fallback 非成功結果漏計成本。對應回歸與獨立 Codex 審查已確認修正。沒有未解決的已知 false ACCEPTED/SAFE/BUG。這不是工具本身的形式證明。

## 3. 成本：單次 feasibility pilot，不是效能 benchmark

單位秒；frontend 包含 C 與 A 的真實轉換。Total 包含 frontend、certificate、abstract property、replay、使用過的 concrete fallback（含失敗）及 strictness probes。B0 是本原型的直接 concrete proof 參考；不是已凍結的競爭性 baseline。

| RTL case | Frontend | Certificate | A property | Replay + concrete search | Strictness | Total machine | Direct C reference |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| p1 | 1.0166 | 0.1423 | 0.0347 | 0.0000 | 0.0388 | 1.2325 | 0.8333 |
| p5_hold | 0.4813 | 0.0937 | 0.0175 | 0.0000 | 0.0379 | 0.6304 | 0.2765 |
| p5_coarse | 0.5114 | 0.1269 | 0.0737 | 0.0467 | 0.0000 | 0.7587 | 0.2871 |
| p5_bug | 0.4896 | 0.1457 | 0.0578 | 0.1076 | 0.0000 | 0.8006 | 0.2938 |

本次完整 demo wall time：5.4952 秒，包含手工／RTL 八列、mutants、對照、證據輸出與所有嘗試。每個 case 另存 wall_seconds，並未把失敗時間丟掉。

這些 tiny properties 在 concrete 上本來就很容易證。本次新方法有額外成本，不能拿 state bits 減少或 abstract proof runtime 當作加速。未量測人工準備／研究開發成本，未做多 seed 統計；沒有 LLM 搜尋實驗或 API 成本數據。

## 4. 已執行重跑命令

工作目錄：`~/.agent-worktrees/rtl-relate/wednesday-feasibility-20260920`。

重建隔離安裝的指令是 `sh scripts/bootstrap_yosys.sh`；本次安裝由前端工作直接執行相同的 uv venv／pinned install 步驟。以下三條驗證命令已實際執行：

```bash
python3 -m unittest discover -s tests -v
python3 -m rtl_relate demo --out results/pilot-20260920-release
python3 -m rtl_relate check results/pilot-20260920-release/rtl/p1/certificate/concrete.json results/pilot-20260920-release/rtl/p1/certificate/abstract.json fixtures/contracts/p1.json results/pilot-20260920-release/rtl/p1/certificate/certificate.json --out results/cli-recheck-p1
```

以上三條實際執行成功；單獨 check 的結果是 ACCEPTED。重跑請改用新的 output directory，避免覆盖舊結果。另已在清空 PYTHONPATH、Python -I 下只加入本專案路徑，成功 import 並檢查 P1，沒有 NeuroAbs 相依。

工具：Python 3.14.6；Z3 4.15.4；YoWASP Yosys 0.69.0.0.post1233／Yosys 0.69 git 9f75ca1f9。安裝隔離於 `.tools/yosys-venv`，未安裝系統套件。詳見 `docs/environment.md`。

本次執行的 Python source-set digest：`40fa84d5674914906290fc1a80971c29859226748743aeaf6b6cd1518eb780b0`。實驗執行於尚未提交的 task worktree，環境檔記錄的 Git bootstrap HEAD `8253476b91fd84acaa0ab344a187288e65629764` 不是實作完成版本；以上 source digest 才是這次程式內容的識別。已核對它與最終實作 commit `5606127cf7b85eb1e3ba59fb5c1c008774868847` 的 Python source-set 相同，並在本地 `results/revision.json` 保存對應。歷史 results 與工具安裝未加入 Git；公開 checkout 可用上述命令產生新的完整證據。

## 5. 工單完成範圍與限制

| 原工單 | 狀態 |
| --- | --- |
| T00 獨立 package／環境 | 完成；baseline 未封存但不阻擋 |
| T01 v0 語意與 contract | 完成：single positive clock、E=true、無 reset、凍結 init/observations/property |
| T02 typed IR／binding | 已實作所列 Bool/BV/ite/logical/arithmetic/unsigned comparison/extract/concat/extensions；完整 state/witness/hash 檢查與型別測試 |
| T03 五項 obligations／結果 | 完成；保留非空檢查、各 query、raw output、hashes、timing |
| T04 P1／獨立列舉 | 完成；包括必要負例與 vacuity／共享 witness／fresh-z |
| T05 harness 分離 | 完成目前 P1/P5 範圍；property/replay 限 Moore 觀察及一步 safety predicate |
| T06 真實 RTL frontend | 完成 P1/P5 六份 source；單一路徑、差分測試及 gate 整合 |
| T07 五家族 | 部分完成：P1、P5；P2、P3、P4 未實作 |

尚未實作：LLM certificate discovery／joint RTL generation、一般 relation R、Mealy property/replay、非平凡環境、reset protocol、symbolic memory、多 clock、liveness、retiming、非 tiny symbolic reachability、NeuroAbs baseline、完整成本對照。

Certificate gate 與 property backend 的信任邊界仍包含 Yosys、adapter、typed encoding、checker、有限狀態 explorer 與 Z3；沒有 solver proof-kernel 檢查。Gold cert 是預先指定語意的 fixture，不能當作 agent discovery 成功率。

## 6. 星期三五頁報告建議

1. 問題與 frozen contract：讓狀態表示改變後，仍能把安全證明帶回 C。
2. P1：2-bit counter → 1-bit done，展示 h/w 與正負義務。
3. P5：同樣 sound 的兩份抽象，一份保留 hold 能證 property，一份過粗只有假反例。
4. 真／假反例及 checker 防線：展示 clock regression、共同 witness、exact replay 和不同 concrete bug trace 的來源。
5. 實測成本與限制：可驗證／有用已有 tiny RTL 證據，值得／加速仍未證成。

本報告當時的下一步為 P2 one-hot → binary，配合正確且非平凡的 J；目前 accepted gold 都是 J=true。後續範圍已擴大為公開 RTL 與兩個 LLM pilots，最新排程見 [9/23 執行計畫](docs/wednesday_plan.md)；本報告中的既有結果保持原始範圍。

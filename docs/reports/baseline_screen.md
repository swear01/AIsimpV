# 約十秒級 RTL baseline 篩選與證書方法定位

已找到兩個接近目標區間的公開 RTL 參數實例：**ZipCPU 同步讀 FIFO，64×32 與 256×32**。三次 fresh-process 確認均為 SAFE，中位數 **5.772／7.313 秒**。這是下一輪改寫的 B0 資格確認，**尚未產生 A、證書或加速結果**。

## 方法是不是既有做法

目前 checker 可理解為關係 `R(s,a) = J(s) ∧ a=h(s)` 的 forward simulation：每個 concrete step 都存在匹配的 abstract step，`w(s,u)` 提供抽象自由輸入的存在選擇。用狀態映射與單步推理建立行為包含，是既有 refinement-mapping 方法；h/J/w 三欄是本專案選用的格式，不是所有 over-approximation 工具共用的標準。參見 [Abadi–Lamport 原文 §1.2、§5](https://lamport.azurewebsites.net/pubs/abadi-existence.pdf)。

Over-approximation 是更廣的目標。[Cousot–Cousot abstract interpretation](https://www.di.ens.fr/~cousot/COUSOTpapers/POPL77.shtml) 提供抽象語意框架；[Graf–Saïdi predicate abstraction](https://www.csl.sri.com/papers/grafsaidi97/) 用 predicates 劃分狀態並建構抽象轉移。這些方法不必生成本專案形式的抽象 RTL 或證書。

[Certifying Phase Abstraction §5](https://arxiv.org/html/2405.04297v1#S5) 也已有 simulation、invariant 與獨立 checker 的硬體驗證設計，但其 witness circuit 不是我們的 nondeterministic-choice function w。研究貢獻應放在 LLM 找到有用非局部改寫／對應，以及完整成本收益，不能把 simulation 原理本身當成新理論。當前函數式 h 格式不含 history/prophecy 或不同步數匹配，是充分但不完備的證書方法。

## 實際找到的候選

來源為 [ZipCPU sfifo.v](https://github.com/ZipCPU/wb2axip/blob/2e8d3bc2d26ddc33d1881022a2a2b9d3f0c16b9b/rtl/sfifo.v)，revision `2e8d3bc2d26ddc33d1881022a2a2b9d3f0c16b9b`。使用公開 RTL 原本支援的 `BW=32`、`LGFLEN=6/8`、同步讀、無空讀／滿寫 bypass；RTL bytes 不改。這是同一 FIFO 家族的兩個容量實例，不是兩個獨立家族。

採用 [上游 sfifo.sby](https://github.com/ZipCPU/wb2axip/blob/2e8d3bc2d26ddc33d1881022a2a2b9d3f0c16b9b/bench/formal/sfifo.sby) 的 prove depth 4、SFIFO define 與同步讀設定，engine 明確選 Z3。使用原本所有 assertions，涵蓋 fill/flags、資料對應與 twin-write ordering monitor。每個配置保留 28 assert cells（其中 2 個 A 為 constant）、0 assume cells，以及 5 個 cover cells；本次沒有執行 cover analysis。這不是單一 hold property。

| 同步讀 FIFO | memory 容量 | 三次 proof 秒數 | 中位數 | 求解程序中位數 | 結果 |
| --- | ---: | --- | ---: | ---: | --- |
| 64×32 | 2,048 bits | 5.710／5.794／5.772 | 5.772 | 5.621 | 3/3 SAFE |
| 256×32 | 8,192 bits | 7.241／7.313／7.360 | 7.313 | 7.151 | 3/3 SAFE |

正式確認前的探索數據分別為 6.240／7.806 秒，沒有混入上述中位數。三輪輪換兩個候選順序；奇數次重複不是完全平衡的順序設計，僅作可重現性確認，不作顯著性宣稱。工具串行、fresh processes、warm OS cache，不宣稱獨占主機。

64-entry 的 base／induction 中位數為 **0.172／5.439 秒**；256-entry 為 **0.226／6.925 秒**。主要成本確實在求解，並非刻意增加前處理、取消優化或提高 BMC 深度。這些是本機與這個工具設定下的時間，不是所有機器的固定 runtime，也尚未比較其他 solver／PDR engine。

前處理後 FF bits 為 223／231，包含原生 formal monitors；memory 另外是 2,048／8,192 bits，未展開為 FF。同步讀原碼只初始化 `mem[0]` 的 32 bits，其餘 **2,016／8,160 bits 保持未知**。沒有為了證明而全 memory 補零；也不能把 FF 欄位冒稱為整個設計狀態大小。

## 搜尋範圍與全部結果

計畫與調整先記在 [issue #19](https://github.com/swear01/AIsimpV/issues/19) 和 [protocol](../baseline_screen_protocol.md)。探索依結果調整候選，故本表不是預先凍結的加速 benchmark。AVR 使用固定 revision `9a76dc632066c4416cebccda3a4974a4f8adede8` 與每個 README 指定的 top file，包含 s1269b 的 `_mod.v`；原始 assertions、reset/init、assumptions 不改。

| 首次有效篩選 task | 結果 | 秒 | 備註 |
| --- | --- | ---: | --- |
| s1269b | SAFE | 0.945 | 仍很快 |
| rcu | UNKNOWN | 45.018 | base 45 s timeout |
| buffer_alloc | UNKNOWN | 45.014 | base 45 s timeout |
| branch_predictor | CEX | 0.306 | native CEX；initial 被 translate_off 包住，非已確認 design BUG |
| usb_phy | BOUNDED | 0.858 | base 通過，induction 未成立 |
| sdlx | BOUNDED | 1.250 | base 通過，induction 未成立 |
| vsa16 | SAFE | 0.441 | 正常前處理後仍很快 |
| huffman_decoder | SAFE | 0.434 | 排除：plain 的輸出表無 255，property 組合恆真 |
| heap | BOUNDED | 5.479 | base 通過，induction 未成立 |
| am2910 | BOUNDED | 2.429 | base 通過，induction 未成立 |
| instruction_buffer | SAFE | 0.323 | 仍很快 |
| sfifo_sync8 | SAFE | 1.889 | 原始同步讀 16×8 |
| sfifo_async8 | SAFE | 1.821 | 原始非同步讀 16×8 |
| sfifo_sync32 | SAFE | 1.854 | 同步讀 16×32 參數實例 |
| sfifo_sync32_d32 | SAFE | 4.098 | 同步讀 32×32 容量掃描 |
| sfifo_sync32_d64 | SAFE | 6.240 | 後續三次確認 |
| sfifo_sync32_d256 | SAFE | 7.806 | 後續三次確認 |

另外保留 FIFO 首次三筆 preparation ERROR：目前 Yosys 對 edge-triggered `$check` 要先執行 `async2sync` 再 `chformal -lower`。依工具診斷補上正常單 clock formal preparation，加入真實 edge-assertion SAFE/CEX/no-assert 回歸後，才在新目錄重跑。錯誤不是 property failure，且沒有啟動 solver；原始 logs 與各版 driver snapshot 都保留。

總計 **17 個參數化 tasks、26 個 attempts**，包含 3 次 preparation errors 和 6 次確認。全部 per-case 計時合計 **165.899 秒**，solver 程序 **161.510 秒**，六次 suite wall 合計 **171.344 秒**。未把失敗刪除或將 UNKNOWN/BOUNDED 算 SAFE；資料與原始 timings 見 [JSON](data/baseline-screen.json)。獨立審核的 1,200 項資料／hash／證據一致性檢查通過，見 [audit](data/baseline-screen-audit.json)；這是紀錄稽核，不是第二個 theorem prover。

本 runner 的 per-case 時間涵蓋 source copy、普通 RTL preparation、模型讀取及 base/induction；末尾 artifact hashing 和 result.json 寫入在此時間之外，計入 suite wall。下載固定原碼及工具 identity 亦在 suite wall，未混入每題 proof 時間。solver 時間含 SMTBMC／Z3 啟動與通訊，並非純 Z3 CPU time。此 native assertion 路徑與舊 contract-harness 實驗起點不同，不能直接拼成舊表的加速比。

## 下一個改寫任務與尚未完成的部分

優先以 **64×32 FIFO** 作第一個較有求解成本的 rewrite 任務，成功後驗證同一方法是否能延伸至 256×32。潛在方向是縮減完整 memory 表示，保留 property 需要的 occupancy、被追蹤資料與順序關係；這只是待測假說，不能先假設刪 memory 後仍可證。

當前 certificate frontend 仍不支援這裡所需的 symbolic/partial initialization、memory 與原生 formal monitor 介接；B0 成功不代表整條 h/J/w 流程已接通。下一關是原始 property/anyconst/clock/reset 語意凍結及前端支援，再做人工 A＋certificate，先量 certificate＋abstract proof 是否小於本次 B0。**本輪 certificate check 與 abstract proof 都是 NOT_RUN，沒有任何加速結論。**

## 重跑

Linux、Python 3.11+、既有 pinned YoWASP Yosys 與 Z3；runner 會下載並核對固定來源 SHA-256。
```sh
python3 scripts/screen_baselines.py --out results/fifo-confirm-new \
  --tasks sfifo_sync32_d64 sfifo_sync32_d256 --depth 4 --repeats 3
```

發布前另讓 CLI 預設採用 catalog 的深度（AVR 20、FIFO 4），避免未指定參數時將 FIFO 誤跑成 depth 20；原始 run driver snapshots 未更動。

使用新 output 目錄。Worktree 可設定 `RTL_RELATE_YOSYS` 指向已安裝工具。原始模型、queries、logs、未初始化 memory metadata、全部 attempts 與 source snapshots 收在 [evidence ZIP](https://github.com/swear01/AIsimpV/releases/download/wednesday-pilot-2026-09-21/AIsimpV-baseline-screen-evidence.zip)；本次不需要系統套件安裝。

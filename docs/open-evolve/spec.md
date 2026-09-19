# AlphaEvolve × NautilusTrader 交易策略演化系統規格

- 狀態：設計草案，尚未實作。
- 目標路徑：`docs/open-evolve/spec.md`。
- 版本：v0.2，取代上一版草案。
- 設計依據：使用者提供的《AlphaEvolve × NautilusTrader 交易策略演化系統決策備忘錄》。

本規格獨立定義策略搜尋空間、Feature Engine、成交環境與評估流程。Repository 僅提供 NautilusTrader API／版本及 data API 的介接參考；不沿用其中的策略、indicators、研究結論、時間尺度或策略晉級流程。

文中「核心決策」沿用原始備忘錄；「工程提案」是為了落實該決策而補充的介面與行為；「待定設定」需在正式 evolution 開始前確定。本文以 AlphaEvolve 表示 policy 演化角色，實際使用的搜尋框架及其 API 另行選定。

## 1. 系統目標與邊界

### 1.1 核心決策

AlphaEvolve 搜尋交易 policy。固定環境將 TradeTick 與十檔委託簿轉為 MarketState，再把 MarketState 與 PositionState 交給候選策略。候選策略只輸出 TargetPosition。

```text
TradeTick + OrderBookDepth10
          │
          ▼
固定 Feature Engine / causal feature cache
          │ MarketState
          ▼
NautilusTrader Strategy wrapper ◄── 已確認的 PositionState
          │
          ▼
    evolved policy()
          │ TargetPosition
          ▼
固定 Risk Gate / Execution Controller
          │ MARKET orders
          ▼
NautilusTrader 撮合、成交、部位與帳務
          │
          ▼
固定 Evaluator
          │ evolution-only feedback
          ▼
AlphaEvolve 產生下一個 candidate
```

同一次搜尋中的 candidate 必須面對相同資料、特徵、撮合假設、風控與評分規則。研究者修改固定環境時，需建立新的 experiment contract，不能將不同 contract 的 fitness 混入同一排名。

### 1.2 第一版範圍

| 項目 | 決策 |
| --- | --- |
| 市場 | 單一標的、單一 venue，明訂商品及帳戶模型 |
| 輸入資料 | `TradeTick`、`OrderBookDepth10` |
| 委託簿 | `L2_MBP` |
| 交易方式 | MARKET taker execution |
| 部位大小 | 固定基準數量 `Q` |
| 演化項目 | 進場時機、交易方向、退場條件及其規則參數 |
| 固定項目 | Features、rolling windows、呼叫時機、execution、size、risk limits、Evaluator |
| 評估 | Temporal folds、latency scenarios、portfolio metrics、100ms／1s markout |
| 最終測試 | Evolution 結束前隔離的 final holdout |

第一版不預設任何既有策略或 bar pattern，也不指定以 1 分鐘 kbar 為研究單位。特徵的時間窗口與 policy 呼叫頻率應依 TradeTick + L10 的可用資料解析度及本系統的 timing-alpha 目標設定。

### 1.3 第二階段範圍

以下不進入 v1：

- LIMIT execution、cancel/replace、maker queue position 與 hidden-liquidity 模型。
- Position sizing 演化、可演化 Feature Engine、多標的配置。
- 策略交易會改變後續歷史市場路徑的 market impact model。
- DSL 與其他新的 policy 表示法。

顯示深度消耗仍屬 v1 成交契約；它與後續 market impact model 是不同問題。不能因 market impact 暫不實作，就假設 MARKET orders 可重複使用無限流動性。

## 2. Policy 搜尋空間

### 2.1 函式介面

工程提案：以 deterministic Python function 作為第一版 candidate。

```python
policy(market: MarketState, position: PositionState) -> TargetPosition
```

Policy 可以組合提供的特徵、比較閾值、執行有限數值運算與條件分支，決定進出場。Policy 不負責資料讀取、rolling statistics、下單或帳務。

候選程式的可修改範圍限於函式本體及受同一限制的局部 helper。輸入 schema、外層 wrapper、Evaluator 與 backtest configuration 不在演化範圍。

### 2.2 TargetPosition

工程提案：輸出固定 enum，將方向與 quantity 分離。

| 輸出 | 目標部位 |
| --- | --- |
| `FLAT` | `0` |
| `LONG` | `+Q` |
| `SHORT` | `-Q` |

`Q` 由 experiment contract 固定，符合 instrument quantity precision、lot size 與 minimum notional。輸出 `LONG` 不代表再買一份 `Q`，而是維持目標淨部位 `+Q`。

允許的方向取決於商品與帳戶模型。若實驗要演化多空，必須使用支援該曝險的商品／帳戶；現貨 cash account 不可憑空建立可放空假設。商品類型、short permission 及適用資金成本列為開跑前待定設定。

### 2.3 PositionState

固定 wrapper 從 Nautilus 已確認的 fills、orders 與 positions 建立唯讀快照。工程提案包含：

| 欄位 | 語意 |
| --- | --- |
| `signed_quantity` | 當前實際淨部位，partial fill 時可能不等於 `Q` |
| `average_entry_price` | 當前持倉均價；flat 時為 missing |
| `holding_time_ns` | 從 flat 轉為持倉後經過的模擬時間 |
| `unrealized_return_bps` | 以當前可見價格計算的方向性持倉報酬；明訂價格來源 |
| `order_pending` | 是否存在尚未確認終態的 execution request |

這些欄位讓 policy 能表達止盈、止損、持有時間與反轉退出條件，不需直接存取 portfolio API。已送出但未成交的數量不能冒充實際持倉。

不提供歷史 fitness、累積回測績效、fold ID、資料索引、未來價格或完整 Nautilus 物件參照。Account-level risk 由固定風控處理。

### 2.4 Policy state 與執行限制

工程提案：v1 不提供 candidate 自訂的跨呼叫可變狀態。市場歷史統計由 Feature Engine 維護，持倉歷史摘要由 PositionState 提供，避免 global state、未重置的記憶與自行重算 features。

禁止 candidate 存取檔案、網路、catalog、feature cache 陣列、Nautilus internals、系統時鐘、未授權 imports、反射及動態程式執行。實際允許的數學操作、程式大小、CPU／memory／執行時間配額在 contract 中固定。

非法輸出、例外、違禁操作或超出配額時，候選策略標記為 `invalid_candidate`；不得把錯誤靜默轉成有利的 `FLAT` 並繼續排名。

Python allowlist、AST 檢查與唯讀 dataclass 都不是完整安全邊界。正式 evolution 需將不受信任的 policy 放在受限 runtime，與持有完整資料的 Nautilus runner 隔離，只透過當次快照與 TargetPosition 傳遞資訊。隔離方式與逐事件 IPC 成本在工程驗證階段決定，不能只靠 prompt 防止 future access。

## 3. 固定 Feature Engine 與 MarketState

### 3.1 設計原則

Feature Engine 將已可取得的 TradeTick 與 L10 狀態轉成固定 schema 的 MarketState。它與 policy 分別版本化；同一次 evolution 不修改 feature formula、window、normalization 或 missing-data policy。

Policy 可以從固定欄位組合交易條件，但不能要求新窗口、改動指標公式或讀取完整歷史序列。Feature Engine 不計算用來回饋 candidate 的 forward returns、markout 或績效標籤。

### 3.2 第一版特徵集合

下表依原始備忘錄定義，不繼承 repository 的 indicators。窗口長度、採樣方式與有效資料門檻屬待定設定。

令最佳 bid／ask 為 `b1`、`a1`，其數量為 `qb1`、`qa1`。

| 特徵 | 定義／實作要求 |
| --- | --- |
| Mid | `(b1 + a1) / 2` |
| Spread | 同時可保留 price units；標準化值為 `10_000 × (a1 - b1) / mid` bps |
| Microprice | `(a1 × qb1 + b1 × qa1) / (qb1 + qa1)`；提供相對 mid 偏離 |
| Book imbalance | 固定深度 `K ≤ 10` 的 `(Σ bid_qty - Σ ask_qty) / (Σ bid_qty + Σ ask_qty)` |
| OFI | 從連續可見 book snapshots 推導的 flow proxy，處理最佳價移動與數量變化，再於固定窗口聚合 |
| Trade imbalance | 固定窗口內 `(buy_volume - sell_volume) / (buy_volume + sell_volume)` |
| Return | 固定價格來源與 lookback 的 simple 或 log return，選定後不變 |
| Volatility | 固定 return sampling 與窗口的 realized-volatility 定義 |

L10 snapshots 無法揭露兩次快照之間所有新增、撤單與成交事件，因此 OFI 必須標示為 snapshot-derived proxy，不宣稱等同完整逐筆 order-event OFI。實作前要鎖定其價格變動分支與聚合公式。

Trade imbalance 優先使用 TradeTick 的已知 aggressor side；unknown side 不可用未來行情推斷。Contract 定義排除方式與有效覆蓋率。

MarketState 另需包含必要的品質資訊：feature readiness、book age、trade age、missing flags。零分母、無成交窗口與資料缺口應有明確語意，不能將未知值一律視為中性市場。

### 3.3 更新與呼叫時機

工程提案：Feature Engine 按已排序市場事件增量更新，wrapper 在固定的 decision schedule 取得快照並呼叫 policy。可採每次有效 trade/book 更新，或固定節流間隔；兩者都屬可行設定，但不能交由 candidate 自選，也不能在同一搜尋中混用。

尚未完成 warm-up、缺少有效兩側 book 或必要 feature 不可用時，wrapper 不允許新增曝險。已有部位依固定風控處置，而非讓 candidate 自行利用缺值分支繞過限制。

若 feature 使用固定 bucket 聚合，row 的可知時間必須是 bucket 結束之後，不得以 bucket 內最後一筆 tick 的時間代表完整 bucket 已可用。這是因果性要求，不代表指定任何 bar 週期或策略形式。

### 3.4 Cache

Feature Engine 的市場計算與 candidate 無關，應預先計算或增量計算後 cache。Cache key 至少包含：

- Instrument 與原始資料內容指紋。
- Feature code/schema version、windows 與 normalization。
- Event ordering、availability model、warm-up 與缺值規則。

Cache 不包含 candidate position、orders、PnL 或 future labels。Runner 只傳遞當時可見的快照，candidate 不取得陣列、iterator 或索引。

Cached 與 streaming 計算必須在相同事件順序下產生一致結果。同 timestamp 的後續事件不能透過 timestamp-only lookup 提早可見；cache 對齊需保留穩定 event ordinal 或等價的因果識別。

## 4. 資料與時間契約

### 4.1 Data API 邊界

沿用 repository 已提供的 catalog reader，僅作為原始 Nautilus objects 的讀取入口：

```python
from data.nautilus_catalog import make_catalog
from nautilus_trader.model.data import OrderBookDepth10
from nautilus_trader.model.identifiers import InstrumentId

catalog = make_catalog()
instrument_id = InstrumentId.from_str(instrument_id_text)

trades = catalog.trade_ticks(
    instrument_ids=[instrument_id],
    start=start,
    end=end,
)
depths = catalog.query(
    OrderBookDepth10,
    identifiers=[str(instrument_id)],
    start=start,
    end=end,
)
```

實作參照僅限 [`data/README.md`](../../data/README.md) 與 [`data/nautilus_catalog.py`](../../data/nautilus_catalog.py) 的介面及連線設定。正式跑批需依資料量分段讀取，不能把範例誤當成必須一次載入全部歷史。

讀取既有 Parquet catalog，不觸發 conversion、不寫 S3。保留目前 `ParquetDataCatalog(...)` 建構方式、path-style 設定與 Rust storage `endpoint_url`；credentials 由 runtime environment 提供，不寫入 candidate、manifest、feedback 或報告。

### 4.2 原始時間與 sequence

保留 `ts_event`、`ts_init` 與資料來源實際提供的 vendor sequence。各欄位需記錄來源語意，不能假設 `ts_init` 一定是交易者收到行情的時間。

若某種事件沒有 vendor sequence，標記缺失；不能自造數值並宣稱已還原交易所順序。不同 channel 的 sequence 也不一定可直接比較。

Contract 必須固定：

1. Nautilus replay 使用的 clock 與原始時間的映射。
2. 同 timestamp 的 trade/book 排序與穩定 tie-break。
3. 市場更新、feature 更新、policy callback、order arrival 與 fill notification 的先後。
4. 重複事件、時間逆序、缺口與過期 book 的處理。

若原始資料不足以還原跨 channel 的真實順序，需披露假設；對該順序敏感的結果需另做固定情境比較。

### 4.3 可用時間與 latency

區分三種時間：

- 市場事件發生時間。
- 策略可取得該事件／feature 的時間。
- 訂單到達模擬 venue 並可能成交的時間。

Candidate 只能根據第二種時間已可取得的資訊做決策，成交依第三種時間的 book 狀態決定。不能觀察尚未收到的行情，也不能回到觸發決策前的價格成交。

Observation latency、feature/policy compute latency、order transit latency 與必要的 confirmation latency 應在 contract 中分開記錄。所選 Nautilus latency API 未直接涵蓋的部分，由固定 wrapper／調度層處理，不得宣稱只設定一個 order latency 就已模擬全部延遲。

若 observation latency 會改變策略可見的事件順序，cache/replay 必須配合；不能只延後送單而讓 policy 繼續讀取零延遲 feature。

## 5. NautilusTrader 成交與執行環境

### 5.1 固定成交層

NautilusTrader 負責唯一正式的 fills、positions 與 account accounting。Feature cache 和 candidate 都不自行估算成交來取代 Nautilus 結果。

v1 使用 `L2_MBP`、`OrderBookDepth10` 與 `TradeTick`。MARKET orders 依到達時的可用對手方深度成交，不研究 queue position、cancel priority 或 maker fill probability。

L10 回放仍有觀測限制：只有十檔深度、快照間缺少完整委託事件、策略交易不會改寫後續歷史行情。因此 Nautilus 是固定的成交評估層，不是無誤的真實市場重建。

### 5.2 Backtest contract

正式 evolution 前鎖定以下設定：

| 分類 | 必填內容 |
| --- | --- |
| 環境 | Nautilus/Python 版本、dependency lock、程式版本、隨機模型 seed |
| 商品與資金 | Instrument metadata、venue、account/OMS model、short permission、初始資產、估值幣別 |
| 資料 | 實際覆蓋區間、資料指紋、排序、clock、缺口與 warm-up |
| Policy 輸入 | Feature schema、windows、decision schedule、runtime 配額 |
| 訂單 | MARKET、固定 `Q`、precision、pending/retry/反向切換行為 |
| Latency | 各延遲成分、基準與 stress scenarios |
| 成本 | Taker fees、費用幣別換算、適用 funding/borrow 成本、額外 slippage（若有） |
| 流動性 | Depth consumption、snapshot refresh、partial fills、深度不足與 price protection |
| 風控 | 最大曝險、order rate、最長持有時間、損失限制與停機處理 |
| 評估 | Folds、gates、metric definitions、ranking/fitness、holdout protocol |

MARKET 掃檔已包含 spread 與可見深度造成的成交價差。若另加 slippage penalty，需說明其代表的額外誤差，避免重複扣除同一成本。

### 5.3 Liquidity consumption

工程提案：啟用並驗證所選 Nautilus 版本的 liquidity-consumption 行為，確保同一可用深度不能被多筆策略訂單重複使用。

需要以合成資料驗證：

- MARKET order 是否逐檔使用 L2 深度。
- Partial fill 與未成交剩餘量如何結束或拒絕。
- 十檔不足時是否存在超出資料支持的成交假設。
- 下一個 depth snapshot 如何更新先前的模擬消耗。
- `trade_execution` 是否改變 matching 行為，以及是否可能繞過指定深度限制。

不能將最後一檔價格當成無限深度。若原生設定不能滿足契約，先縮小允許 size／訂單條件，或建立受信任的固定適配層並測試；candidate 不得修改撮合器。

### 5.4 Execution Controller

工程提案：採有限狀態機，將 TargetPosition 轉成實際 MARKET orders。

- 依 confirmed position 與 pending order 計算剩餘差額；重複相同 target 不重複下單。
- 同時最多一筆 in-flight order。等待期間保存最新 target，確認後重新經過 risk checks。
- 多空反向採先平倉、確認 flat、再建立另一方向的固定部位，不直接送出 `2Q` 反轉單。
- Partial fill、reject、retry 與 order timeout 採固定行為；timeout 不等於已取消，不盲目重送。
- Candidate 決定正常退場；固定最大持有時間、損失限制與 kill switch 可覆寫其決策。
- Book 無效時禁止新增曝險。若已有部位卻無法取得有效成交資料，標記事故並依預定規則結束，不能虛構平倉 fill。

以上行為是降低重複送單與回測漏洞的工程提案，不屬演化搜尋空間。

### 5.5 Fold 起訖與 reset

每個 fold/scenario 使用相同起始資金、flat position、乾淨 risk/execution state。Warm-up 只建構 features，不交易、不計分。

Fold 結尾預留固定平倉區間，停止新進場並讓 Nautilus 執行退出，計入 fees 與 latency。未成功平倉時依固定 failure policy 處理，不能刪除尾端虧損或以無成本 mid 取代成交。

可使用 low-level `BacktestEngine` reuse/reset 降低成本，但必須先證明與 fresh engine 等價：orders、positions、account、timers、book consumption、feature cursor 及 risk counters 不得跨 candidate/fold 殘留。

## 6. Evaluator

### 6.1 評估單位

基本評估單位為：

```text
candidate × temporal fold × latency scenario
```

Evaluator 先保存每個單位的原始 metrics，再做 fold/scenario aggregation。不能只輸出單一 Sharpe，或省略不利區間。

### 6.2 四類指標

| 類別 | 第一版指標 |
| --- | --- |
| 獲利能力 | Net PnL、Profit Factor、Expectancy |
| 風險 | Sharpe、Sortino、Max Drawdown |
| 交易行為 | Trade count、turnover；輔以 fill count、holding time、exposure、reject/partial-fill rate |
| Microstructure quality | 100ms／1s markout、markout coverage、latency sensitivity |

計算口徑：

- **Net PnL**：期末與期初 net equity 差，包含 fees 及適用資金成本；帳務需能與 Nautilus fills/account 對帳。
- **Sharpe／Sortino**：使用固定時間格的 net equity returns，包含空倉時間；sampling interval、annualization、risk-free rate 與 downside target 需固定。不使用不規則 tick returns 或逐筆交易 returns 冒充同頻率績效序列。
- **Max Drawdown**：由 net equity curve 計算 peak-to-trough，明訂金額與比例口徑。
- **Trade count**：工程提案以 flat → position → flat 的 completed round trip 計數，partial fills 不膨脹成多筆獨立交易。
- **Profit Factor**：淨獲利 round trips 總和除以淨虧損絕對值；每筆交易分攤完整進出場成本。
- **Expectancy**：completed round trip 的平均 net PnL。
- **Turnover**：工程提案為 `Σ abs(fill_quantity × fill_price) / initial_equity`；不同長度 fold 另報每日值。

零交易、零波動、無 downside samples、無虧損交易造成的未定義或無限指標，需有固定 validity/capping 規則。不能用任意 epsilon 產生極大分數，也不能跳過無效 fold 後計算 median。

### 6.3 Markout

對 fill `i`，令成交時間為 `t_i`、價格為 `p_i`，買進方向 `s_i = +1`、賣出 `s_i = -1`，歷史 book midpoint 為 `m(t)`：

```text
fill_markout_bps(i, h)
  = 10_000 × s_i × (m(t_i + h) - p_i) / p_i

mid_move_bps(i, h)
  = 10_000 × s_i × (m(t_i + h) - m(t_i)) / m(t_i)

h ∈ {100ms, 1s}
```

`fill_markout` 包含跨 spread 的成本與後續價格變化；`mid_move` 輔助判斷方向性 timing。另報扣除該筆 fee 的版本，但它仍不是完整 round-trip net PnL。

工程提案：`m(t)` 使用不晚於目標時間的最近有效 book，設最大 quote age；成交當時的 mid 亦遵守 replay 次序。若資料不足以支援 100ms 診斷，標記 missing 並回報 coverage，不能拿很久之後的下一筆 quote 偽裝成 100ms markout。

報告至少包含 notional-weighted mean、median、positive ratio 與 coverage，並拆分 entry／exit／forced liquidation。Ranking 使用哪一種 markout aggregation 必須在 contract 鎖定，以免 exit fills 掩蓋 entry timing 品質。

Evaluator 可為 markout 讀取未來 quote，但這些資料不得回流到 MarketState。Positive markout 是 timing 的診斷訊號，仍需結合完整交易成本、持有風險與跨期績效判斷。

### 6.4 第一階段：hard constraints

原始備忘錄要求先淘汰不合格 candidate，再排序。第一版 gates 包含：

- 最低交易筆數。
- 最大 drawdown 上限。
- Turnover 上限。
- Worst-fold Sharpe 下限。

工程上另需檢查 candidate validity、資料／markout coverage、風控違規與未完成平倉。哪些 gate 套用於每 fold、每 scenario 或整體 aggregation，以及確切數值，需在 evolution 前鎖定。

建議對必要 folds/scenarios 逐一檢查交易數、drawdown 與 coverage，並對每個 scenario 計算 worst-fold Sharpe，避免以有利情境抵銷不合格結果。這是待確認的 gate aggregation 提案，不將未指定數值寫成既定要求。

Status 至少區分 `valid`、`invalid_candidate`、`constraint_failed`、`infrastructure_error`。基礎設施故障不得變成策略分數，也不能因此漏掉不利 fold。

### 6.5 第二階段：ranking／fitness

保留以下評估向量：

- Median fold Sharpe。
- Worst-fold Sharpe。
- Fold performance dispersion。
- Sortino、Profit Factor。
- 100ms／1s markout。
- Max Drawdown。
- Policy complexity。

本規格不替原始備忘錄追加固定的 lexicographic 優先序，也不宣稱某組權重已最佳化。實作上將 score policy 版本化，固定 metrics 的方向、normalization、clipping、missing 處理、scenario aggregation 與 complexity 定義。

若演化框架需要 scalar fitness，可採下列概念形式，正式公式與權重待 ablation 決定：

```text
fitness = weighted_quality_metrics
          - drawdown_penalty
          - instability_penalty
          - complexity_penalty
```

所有不同單位的指標需先經固定尺度轉換。Complexity 可用 AST node/branch count 等程式結構度量，不用註解或格式長度。Failing candidate 不可藉其他分數抵銷 hard constraints。

Ablation 僅使用 evolution data，且每個排名方案建立獨立 contract/run。正式搜尋途中不能看到結果後更換權重，再把先前結果視為同一個無偏比較；final holdout 不參與權重選擇。

## 7. 資料切割與 final holdout

### 7.1 Evolution feedback 就是訓練訊號

AlphaEvolve 會根據 evaluator feedback 修改程式，因此反覆使用的 validation periods 都屬於搜尋流程。報告統一稱為 evolution folds，不將其描述成 untouched out-of-sample。

Evolution set 切成多個 temporal folds，完整候選評估使用固定 fold 集合。Evaluator 關注 median fold、worst fold 與分散程度，不只看串接後的單一 equity curve。

每 fold 明訂 warm-up、scoring、exit buffer 與 diagnostic tail。持倉及 forward markout 不得跨進下一個獨立評分區間而未處理；依最大持有時間、診斷 horizon 與 latency 設定 purge／embargo 或等價邊界規則。Feature warm-up 只能使用當時之前的資料。

### 7.2 Latency scenarios

至少配置基準與較不利 latency 情境，數值依資料 timestamp 語意及預期執行環境制定。Candidate 在同一組固定情境下接受測試，不能自選最有利情境。

Scenario 聚合方式在 ranking contract 中固定，報告保留個別情境的 metrics 與相對退化幅度。只在零延遲獲利的策略，不應因平均分數漂亮就被視為已有可執行 edge。

### 7.3 Holdout 隔離流程

1. 搜尋開始前確定 final holdout 邊界、存取權限與最終候選選擇規則。
2. Evolution workers、LLM prompts、ranking 及人工選策流程不讀取 holdout 的績效、診斷或資料摘要來調整策略。
3. Evolution 結束後，依事前規則選定最終 candidate，凍結 source、features、execution、risk、Evaluator 與 dependencies。
4. 由獨立 final evaluator 執行 holdout，完整報告結果，不因不佳而改選另一個 candidate。
5. 若依 holdout 結果修改策略或評估規則，該段資料即成為已使用的研究資料，後續需另取新的 untouched holdout。

允許記錄清楚的 infrastructure-failure 重跑；不得把調參後的重跑稱為同一次 final test。資料跨度不足時，結論只能限定在已測試期間，不能宣稱跨 regime 穩健。

## 8. 搜尋流程、產物與成本

### 8.1 Evolution loop

```text
凍結 experiment contract 與 holdout
  -> 讀取資料、品質檢查、建立 causal feature cache
  -> 產生 seed policies
  -> AlphaEvolve 修改 policy candidate
  -> 語法／權限／配額檢查與 synthetic smoke test
  -> Nautilus 執行 folds × latency scenarios
  -> hard constraints
  -> ranking／fitness 與有限 feedback
  -> 保存 candidate lineage
  -> 下一代，直到固定 budget／stop condition
  -> 凍結最終 candidate
  -> final holdout
```

Seed policies 由本規格的 MarketState 與 TargetPosition 介面建立，不預設採用 repo 的任何策略。工程驗證可使用 always-flat、固定方向、簡單閾值 policy 作測試 fixtures；它們不代表已成立的 alpha，也不強迫正式搜尋採用特定策略家族。

### 8.2 Evaluation result

每次評估保存：

- Candidate source/hash、parent IDs、generation、生成設定與實際 feedback。
- Contract hash、資料指紋、feature version、Nautilus/dependency version、seeds。
- 各 fold/scenario metrics、validity、constraint violations、ranking／fitness。
- Fills、positions、account/equity 診斷及重現資訊。
- Runtime、peak memory、timeout/error classification。

演化器只取得 evolution-only feedback；candidate runtime 不取得完整評估資料表。Logs 與報告不得包含 credentials。相同 candidate 與 contract 應能重現評估結果；LLM 生成若不可完全重現，仍需保存原始候選程式與 lineage。

### 8.3 回測成本

第一版先將固定 rolling statistics 與 microstructure features cache，避免每個 candidate 重算。Candidate result cache 使用 source、contract、data、feature 與 seed hashes，不能跨不同假設誤用結果。

Benchmark 每 candidate/fold/scenario 的 event count、執行時間、memory 與 policy 隔離成本，再設定 search budget。已確定違反必要 gate 的 candidate 可提早淘汰，但記錄為不完整失敗評估，不用未完成 folds 產生排名。

Low-level engine reuse/reset 需先驗證等價性。Numba、C++、平行化與資料格式最佳化放在流程可運行且 profiler 指出瓶頸之後；最佳化不得改變因果順序、policy outputs、fills 或 scoring。

## 9. 實作模組與 API 對接

以下是責任劃分，不要求立即建立大型框架：

| 模組 | 責任 |
| --- | --- |
| Data adapter | 呼叫現有 catalog API、保留 Nautilus objects、建立資料 manifest |
| Replay/availability adapter | 固定排序、可用時間與資料品質規則 |
| Feature Engine | 固定 features、readiness、causal cache |
| Policy contract/runtime | 驗證候選程式、隔離執行、輸入輸出檢查 |
| Nautilus Strategy wrapper | 接收事件、取得快照、呼叫 policy、接收 execution confirmations |
| Execution Controller/Risk Gate | TargetPosition 到 MARKET orders 的固定狀態機 |
| Backtest runner | Folds/scenarios、engine lifecycle、結果收集 |
| Evaluator | Metrics、hard constraints、ranking、feedback |
| Evolution adapter | 對接演化框架、candidate lineage、budget |
| Final evaluator | 在凍結後獨立執行 holdout |

API 參照以 repository 的 lock 所記錄的 NautilusTrader `1.228.0` 為起點，不把版本號當成已完成 runtime 驗證：

- 現有 data API 提供 `TradeTick`／`OrderBookDepth10`，可交給 `BacktestEngine.add_data(...)`。
- 該版本的 Actor API 宣告包含 `subscribe_trade_ticks(...)`、`subscribe_order_book_depth(...)`、`on_trade_tick(...)` 與 `on_order_book_depth(...)`，作為 Strategy wrapper 的事件介接基礎。
- Backtest API 宣告包含 `OrderBookDepth10` 處理，以及 `book_type`、`trade_execution`、`liquidity_consumption` 等 simulation 設定／狀態。實際建構參數、排序與成交行為仍需驗證。

核對來源：

- [NautilusTrader v1.228.0 Actor API 宣告](https://github.com/nautechsystems/nautilus_trader/blob/v1.228.0/nautilus_trader/common/actor.pxd)
- [NautilusTrader v1.228.0 Backtest API 宣告](https://github.com/nautechsystems/nautilus_trader/blob/v1.228.0/nautilus_trader/backtest/engine.pxd)
- [`data/README.md`](../../data/README.md)
- [`data/nautilus_catalog.py`](../../data/nautilus_catalog.py)

本次只核對 data 介面與上游版本的 API 宣告；目前本機環境未安裝可供 import 的 NautilusTrader，未執行成交行為測試。

## 10. 驗收條件

| 項目 | 驗收要求 |
| --- | --- |
| 搜尋邊界 | Candidate 只能改 policy，不可修改 features、size、execution、risk 或 Evaluator |
| 因果性 | 修改／追加未來資料，不影響之前的 MarketState、TargetPosition 與已發生成交 |
| Event ordering | 同 timestamp trade/book/arrival/callback 順序固定，cache 與 replay 一致 |
| Feature correctness | Synthetic events 可手算驗證各 feature、warm-up、缺值與窗口邊界 |
| Policy isolation | Future index、檔案／網路、反射、global state、無限迴圈及超額資源受阻擋或配額限制 |
| Taker fills | MARKET 掃檔、fees、latency、partial fills、深度不足及 liquidity consumption 符合 contract |
| Execution state | 相同 target 不重複下單，pending/反向/拒單不造成非預期曝險 |
| Metrics | 手算 fixtures 驗證 net PnL、round trips、drawdown、turnover、markout 與未定義指標政策 |
| Fold isolation | 不跨 fold 保留持倉、risk counters 或 candidate state；reset 與 fresh run 等價 |
| Ranking | Hard constraints 不被高分抵銷；原始 fold/scenario metrics 與 score 可重建 |
| Holdout | Evolution 不接觸 holdout，最終測試前能證明 source/contract 已凍結 |
| Reproducibility | 相同 source/contract/data/seeds 產生一致評估；失敗結果保留 |
| 成本 | 可量測並預估指定 search budget 所需時間與資源 |

單元測試使用 synthetic Nautilus objects，不需真實 catalog 連線。真實資料整合測試另行配置 read-only credentials，不將秘密放入 fixtures。

系統驗收不要求一定搜尋到盈利策略。它必須能把沒有 edge、過度 turnover、延遲脆弱、資料不足及模擬漏洞區分開，並留下可重現的判斷依據。

## 11. 開跑前待定設定

以下項目不是由現有 repo 的研究內容決定，需針對本系統選定並封存：

1. 演化框架／版本、LLM、seed generation、允許語法、candidate budget 與停止條件。
2. 單一 instrument、商品／帳戶模型、允許方向、初始資金與固定 `Q`。
3. Evolution folds、final holdout、warm-up、exit buffer、邊界隔離與實際資料覆蓋。
4. Feature windows、OFI proxy 公式、return/volatility sampling、decision schedule、staleness/coverage 門檻。
5. Event ordering、clock mapping、各 latency 成分與 stress scenarios。
6. Fees、適用資金成本、depth consumption、snapshot refresh、partial-fill/retry 規則。
7. Risk limits、最長持有時間、order-rate limits、runtime 資源配額。
8. Equity-return sampling、hard thresholds、markout aggregation、fitness normalization/weights、complexity 定義。

在這些設定尚未完成時，可以實作介面、資料驗證與 synthetic tests，但不能將未封存條件下的搜尋結果當作正式評估。後續擴大搜尋空間或修改成交假設，都需建立新 contract 與新的對照實驗。

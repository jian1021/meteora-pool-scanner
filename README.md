# Meteora 全池扫描与筛选器 V3.1

基于 **Python + Streamlit** 的 Meteora 流动池扫描与筛选工具。自动扫描 Meteora 官方 API 上可通过真实接口获取的 **DLMM** 与 **DAMM v1** 流动池，按市值、成交量、TVL、Fees/TVL 等条件筛选，帮助寻找适合赚取 LP 手续费的机会。

> **明确排除 DAMM v2：本项目不扫描、不展示 DAMM v2 池子，也不扫描其他 Solana DEX。**
>
> **所有数据均来自真实 API，绝不生成模拟数据。**

---

## 一、功能概览

| 页面 | 内容 |
|---|---|
| ① 全池扫描 | 自动分页扫描 DLMM / DAMM v1、去重、进度显示、失败重试、断点续扫、手动/定时扫描 |
| ② 筛选条件 | 市值、成交量、TVL、Fees/TVL、池类型、数据完整性；评分权重（可调） |
| ③ 筛选结果 | 排序、分页、指标展示、CSV 导出、一键加入重点池监控、按池地址实时刷新选中池行情 |
| ④ 重点池监控 | 添加/删除/启用/暂停、刷新指标、保存快照、反转信号（与评分分开） |
| ⑤ 历史数据 | 单池历史快照表与趋势图、CSV 导出 |
| ⑥ 飞书报警设置 | Webhook 测试、阈值配置、发送记录与失败原因 |
| ⑦ API 状态与错误日志 | 接口信息、限频、扫描状态、错误日志 |
| ⑧ 使用说明 | 口径说明与免责声明 |
| ⑨ 价格区间计算 | **双数据源**：输入池地址（DEX Paprika **池级 K 线**，ATR 周期 15m/30m/1h）或代币（CoinGecko 代币 K 线，ATR 周期 1d/1h/30m）；用 ta 库计算 ATR，按倍数（默认 1.5）计算上价/下价区间 |

页面顶部固定展示：当前扫描池类型、DLMM/DAMM v1 已发现数量、已处理数量、符合筛选数量、市值缺失数量、API 失败数量、最后扫描时间、实际数据覆盖范围。

---

## 二、安装与运行

要求：**Python 3.10+**（已在 Python 3.14 上验证），可运行于 macOS 与 Windows。

### 方式一：一键脚本

* Windows：双击 `run_windows.bat`
* macOS / Linux：`chmod +x run_macos.sh && ./run_macos.sh`

脚本会自动创建虚拟环境、安装依赖并启动应用（浏览器打开 http://localhost:8501）。

### 方式二：手动

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

### 配置飞书（可选）

复制 `.env.example` 为 `.env`，填写：

```
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxx
FEISHU_WEBHOOK_SECRET=            # 若机器人开启签名校验则填写
COINGECKO_API_KEY=                # 可选；页面⑨ 代币数据源，填写后自动切换到 pro 域名（限频更宽松）
DEXPAPRIKA_API_KEY=               # 可选但强烈建议；页面⑨ 池地址数据源，免费注册：https://console.dexpaprika.com。
                                 # 填写后解锁 15m/30m 粒度 + 最近 7 天；留空仅支持 1h 且最近 24 小时。
DEXPAPRIKA_BASE_URL=https://api.dexpaprika.com
```

`.env` 已被 `.gitignore` 忽略，**不会**被提交到 Git，密钥不硬编码。

---

## 三、API 验证结果（开发前已实测）

> 开发严格遵循“先验证 API，再开发功能”。以下均为对官方接口的实际调用验证结果。

| 数据源 | 基础地址 | 接口 | 实测要点 |
|---|---|---|---|
| **DLMM** | `https://pool-discovery-api.datapi.meteora.ag` | `GET /pools?page_size=&category=all&filter_by=pool_type=dlmm&after_key=` | **游标分页**（`after_key`/`has_more`，`page`/`offset` 被忽略）；`page_size` 上限 **1000**；限频 **25 RPS** |
| **DLMM** | 同上 | `GET /pools?page_size=1&category=all&filter_by=pool_address={address}` | 单池实时状态，字段同列表 |
| **DLMM K线** | `https://dlmm.datapi.meteora.ag` | `GET /pools/{address}/ohlcv?timeframe=1h` | 真实 K 线（5m/30m/1h/2h/4h/12h/24h）用于扫描页的 24h 价格趋势；**单次最多返回最近 10 根**；15min/1d 均实测返回 400，**不提供** |
| **CoinGecko** | `https://api.coingecko.com/api/v3`（配置 Key 后自动切换 `https://pro-api.coingecko.com/api/v3`） | `GET /search?query=`、`GET /simple/price?ids=&vs_currencies=usd`、`GET /coins/{id}/ohlc?vs_currency=usd&days=` | 页面 ⑨ 数据源；OHLC 粒度官方限制：days=1 为 **30 分钟**（**无更细粒度**），days=2~30 为 4 小时；免费域名限频较严（实测触发 429，客户端自动等待 60s 重试） |
| **DAMM v1** | `https://damm-api.meteora.ag` | `GET /pools/search?page=&size=` | 分页全量列举；`size` 实测上限约 **300**；限频 **10 RPS** |
| **DAMM v1** | 同上 | `GET /pools?address={addr}` | 单池实时状态 |
| **DEX Paprika** | `https://api.dexpaprika.com` | `GET /networks/solana/pools/{addr}`、`GET /networks/solana/pools/{addr}/ohlcv?interval=&limit=&start=` | 页面 ⑨ **池级 K 线**数据源；鉴权头 `Authorization: <api_key>`（裸 Key，无 Bearer）；**`start=` 必填**（`-24h`/`-7d`），缺省返回 400；免费注册 Key 解锁 10m/15m/30m 粒度与最近 7 天回看（30 req/min，100k credits/30d），无 Key 仅 1h/6h/12h/24h 与最近 24 小时；默认请求 UA 被网关拦截为 402（本项目客户端自带 UA，正常 200）；额外压测 20 连发 0 次 429 |
| **Jupiter（备用）** | `https://lite-api.jup.ag` | `GET /tokens/v2/search?query=mint1,mint2` | 补齐 DAMM 代币名称/符号/市值，支持逗号批量 |

关键实测结论：

1. **DLMM**（pool-discovery）列表接口一次性返回 Meteora 前端「Token Info」面板全部字段：`token_x/y` 的 `market_cap`/`fdv`/`holders`/`top_holders_pct`(前10持仓占比%)/`dev_balance_pct`(开发方持仓占比%)/`has_freeze_authority`/`has_mint_authority`，以及池级 `tvl`/`volume`/`fee`/`fee_tvl_ratio`/`fee_pct`/`pool_price`/`pool_price_change_pct`/**`open_positions`(开仓人数)**/`dlmm_params.bin_step`/`pool_created_at`。字段为**扁平数字**（非 `{24h}` 对象）。
2. **DAMM v1** 列表接口**不返回代币名称、符号与市值**，仅有 mint 地址；因此通过 **Jupiter 备用接口**按 mint 补齐，并在数据库记录 `data_source` 与口径（`market_cap` 或 `fdv`），满足“备用 API 需记录来源、更新时间与 Mint 地址”的要求。
3. **口径差异**（已在代码中区分，不混用）：
   * DLMM 的 `apr` 字段实测等于当日 `fee_tvl_ratio.24h`（即“当日 Fees/TVL 百分比”），并非年化 APR；`apy` 为按日复利年化。
   * DAMM v1 的 `apr` 为静态年化（日费率×365），`trade_apy` 为复利年化。
   * 因此本程序**自行按公式计算** Fees/TVL，并将年化统一标注为“静态年化估算”。
4. `GET /pools`（DAMM v1，不带 address）会报 “Address cannot be empty”，故全量列举必须使用 `/pools/search`。
5. **pool-discovery 不含 DAMM v1**（`filter_by=pool_type=damm_v1` 实测返回 0 条；`category` 仅 `all` 有效），故 DAMM v1 仍使用 `damm-api.meteora.ag`。
6. **DLMM OHLCV 限制**（实测）：单次请求**最多返回最近 10 根** K 线，`limit/count/start_time/end_time/from/to` 等参数均不影响返回数量；`timeframe` 仅接受 `5m/30m/1h/2h/4h/12h/24h`，`15m/15min/1d/1D` 均返回 400。页面 ①/③/⑤ 的价格趋势仅使用官方 `24h` K 线；页面 ⑨ 的池级 ATR 使用 DEX Paprika（详见 API 表第 8 条）。
7. **CoinGecko OHLC 粒度限制**（实测）：`/coins/{id}/ohlc` 的粒度随 `days` 变化——`days=1` → 30 分钟（48 根）、`days=7/30` → 4 小时（42/180 根）；**官方不提供 15 分钟及更细粒度**，页面 ⑨ 的 **1h 由 30m 聚合、1d 由 4h 聚合**得到。免费公共域名限频较严（实测触发 429），客户端统一在超时/429 时自动退避等待后重试。
8. **DEX Paprika 池级 OHLCV**（实测）：页面 ⑨ 的**池地址模式**数据源。`GET /networks/solana/pools/{addr}/ohlcv?interval={10m/15m/30m/1h/…}&limit={≤1000}&start={-24h/-7d}` 返回数组 `[{time_open,time_close,open,high,low,close,volume}]`；`start` 缺失 → 400，无 Key 时超出 24 小时窗口 → 403，5m 及更细粒度需付费档；免费注册 Key 实测：`15m/30m/1h` 各取最近 7 天分别 652/332/167 根。池详情 `/pools/{addr}` 返回 `id(=地址)`、`dex_id`、`tokens`（含 symbol）、`last_price_usd`（用于“当前价格”），**池不存在返回 404**。Meteora 官方 DLMM OHLCV 虽也提供池级 K 线但**单次固定最近 10 根**（见第 6 条），故池级 ATR 采用 DEX Paprika。

---

## 四、指标口径与计算

* **市值**：优先流通市值 `market_cap`，缺失时使用 `fdv` 并标注口径。DLMM 来自官方接口；DAMM v1 来自 Jupiter 备用接口。
* **Fees/TVL** = `24h 手续费收入 ÷ TVL × 100%`（仅当两者口径一致时计算）。
* **静态年化手续费收入估算** = `24h 手续费收入 × 365`。
* **静态年化手续费率估算** = `24h 手续费收入 × 365 ÷ TVL × 100%`。
  > 上述均为**静态年化估算**，不代表未来 APR 或实际收益。
* **价格趋势**：优先使用真实 K 线判定 上涨/下跌/横盘/趋势不明；DAMM v1 无 K 线接口，仅显示涨跌幅并标注“趋势数据不足”。
* **价格区间（页面 ⑨）**：**双数据源**，均用现成技术指标库 **ta**（`ta.volatility.AverageTrueRange`，Wilder 算法）计算 ATR，按倍数（默认 1.5）计算区间：`上价 = 当前价格 + 倍数 × ATR`、`下价 = 当前价格 − 倍数 × ATR`。
  * **池地址模式（默认）**：输入 **Solana 池地址** → DEX Paprika `/pools/{addr}/ohlcv` 获取**池级 K 线**，当前价格取池详情 `last_price_usd`。ATR 周期可选 **15m / 30m / 1h**（免费注册 Key 实测支持最近 7 天；无 Key 仅 1h、最近 24 小时）。
  * **代币模式**：输入代币（符号 / 名称 / CoinGecko ID）→ CoinGecko `/coins/{id}/ohlc` 获取代币 K 线，当前价格取 `/simple/price`。ATR 周期可选 **1d / 1h / 30m**：30m 为 CoinGecko 官方最细粒度（days=1），1h 由 30m 实时聚合，1d 由官方 4h K 线聚合（days=30）。
  * 所选样本数超过可用 K 线数时自动使用最大可用样本数并在界面标注。区间仅作观察参考，不构成投资建议。
* **配置手续费率**：DLMM 取 `pool_config.base_fee_pct`；DAMM v1 取 `total_fee_pct`。**高配置费率 ≠ 高收益**，仅作参考。
* **市值筛选**：代币 X / Y 分别判断；支持“任一代币满足”（默认）与“两个代币均满足”。市值缺失/为零/异常 → 标记“市值数据不足”，**默认不通过**（不默认放行）。市值筛选在展示前执行，另提供“显示未通过筛选的池子”开关排查数据。

---

## 五、评分系统（手续费机会观察评分，0~100）

默认权重（可在页面调整，并展示公式）：

| 分项 | 默认权重 |
|---|---|
| 24h 成交量 | 25 |
| 24h Fees/TVL | 25 |
| TVL | 20 |
| 历史手续费收入稳定性 | 15 |
| 价格波动风险 | 15 |

* 各指标先归一化（对数归一化）/分档到 0~100，再按权重加权。
* 市值 > 100 万美元属于**硬性筛选条件**，不作为加分项。
* 历史稳定性/波动数据不足时，对应分项不计入并明确标记，剩余权重按比例重分配。
* **评分仅用于筛选排序，不代表未来盈利概率。**

---

## 六、数据库（SQLite）

数据库默认位于 `data/meteora.db`（可用 `DB_PATH` 修改），程序关闭后数据不丢失。表：

* `pools`：池地址、池类型、两代币 Mint/名称/符号/市值、首次发现时间、最后更新时间、数据来源、TVL、成交量、手续费、费率、Fees/TVL、价格、评分相关指标等。
* `snapshots`：历史快照（时间、TVL、成交量、手续费、费率、Fees/TVL、市值、价格与涨跌、评分、完整性、信号）。
* `scan_status`：已扫描页数、已发现/已处理/失败数量、上次扫描位置、最后扫描时间、状态。
* `api_errors`：API 错误日志。
* `watchlist`：重点池监控列表（启用/暂停）。
* `alerts`：报警发送记录（去重键、成功/失败与失败原因）。
* `tokens`：代币元数据缓存（Jupiter 备用来源）。
* `settings`：页面可调参数（筛选条件、评分权重）、DLMM 断点续扫游标。

扫描采用 **WAL 模式 + 线程锁**；DLMM 断点续扫通过 `settings` 中的游标 `after_key` 实现，DAMM v1 通过 `scan_status.last_position`（页码）实现。

---

## 七、飞书报警

* Webhook 与签名密钥从 `.env` 读取，**不硬编码、不提交 Git**。
* 支持：测试报警、新发现符合条件池（汇总）、市值首次达标、成交量/Fees-TVL 达阈值、重点池指标变化。
* 报警内容含：池类型、池地址、代币名称、Mint 地址、市值、TVL、成交量、手续费收入、Fees/TVL、评分、触发原因、更新时间。
* 相同池子+事件按时间窗去重（新池/市值 24h、阈值 6h、监控变化 3h），并保存发送记录与失败原因。

---

## 八、测试

```bash
python -m unittest discover -s tests -v      # 或  pytest
```

覆盖：筛选规则、评分、技术指标（RSI/趋势/信号）、价格区间计算（上/下价公式、ATR 与 **ta 库**结果一致、K线不足自动降样本数、30m→1h 聚合、DEX Paprika 池级 OHLCV 解析与池详情解析）、数据库、API 解析（DLMM/DAMM/Jupiter 字段映射）、飞书消息与去重、扫描游标分页/去重/断点续扫。

---

## 九、项目结构

```
.
├── app.py                      # Streamlit 主程序（9 个页面 + 顶部状态栏）
├── requirements.txt
├── .env.example                # 环境变量示例（复制为 .env）
├── .gitignore
├── run_windows.bat             # Windows 启动脚本
├── run_macos.sh                # macOS/Linux 启动脚本
├── conftest.py
├── src/
│   ├── config.py               # 配置与默认参数（限频/分页/默认筛选/权重）
│   ├── models.py               # TokenInfo / PoolRecord
│   ├── api_client.py           # 限频 + 重试 + 超时 的 HTTP 客户端
│   ├── providers/
│   │   ├── dlmm.py             # DLMM 官方接口（pool-discovery，含 Token Info 全字段）
│   │   ├── damm_v1.py          # DAMM v1 官方接口
│   │   ├── jupiter.py          # Jupiter 备用接口（补齐名称/市值）
│   │   ├── coingecko.py        # CoinGecko 数据源（页面⑨代币模式：搜索/价格/OHLC K线）
│   │   └── dexpaprika.py       # DEX Paprika 数据源（页面⑨池地址模式：池详情/池级 OHLCV）
│   ├── db.py                   # SQLite 数据访问层
│   ├── scanner.py              # 全池扫描（分页/去重/续扫/进度）
│   ├── filters.py              # 筛选逻辑
│   ├── scoring.py              # 评分系统
│   ├── indicators.py           # RSI(3)/趋势/信号（基于真实 K 线）
│   ├── price_range.py          # 页面⑨：池地址（DEX Paprika 池级K线）/代币（CoinGecko）+ ta 库 ATR → 上/下价区间
│   ├── feishu.py               # 飞书 Webhook
│   ├── alerts.py               # 报警评估编排
│   └── monitor.py              # 重点池监控
└── tests/                      # 单元测试
```

---

## 十、实际覆盖范围、数据缺失与限制

* **覆盖范围**：取决于官方 API 可访问页面，**不等于链上全部历史/现存池**。页面顶部展示每种池的已发现数量与 API 报告数量。
* **DAMM v1 代币市值**依赖 Jupiter 备用接口；若某代币在各数据源均无市值，则标记“市值数据不足”，默认不通过筛选。
* **DAMM v1 无 K 线接口**，趋势/RSI 等信号仅对 DLMM 生效；DAMM v1 的波动风险退化为用 24h 涨跌幅近似，并在评分说明中标注。
* **页面 ⑨ 的 ATR 数据口径**：
  * **池地址模式（DEX Paprika 池级 K 线）**：免费注册 Key 支持 15m/30m/1h、最近 7 天；**无 Key 时仅 1h 可用**（且仅最近 24 小时），15m/30m 会被 API 拒绝（403）；`1d` 池级粒度不在免费档（需 Dev/Pro），故池模式**不提供 1d**。K 线为指定池的真实交易 OHLCV；若池地址不存在返回提示而非报错。
  * **代币模式（CoinGecko）**：官方仅提供 **30 分钟为最细粒度（无 15min）**，故 15min 需求以 30m 实现、1h 由 30m 聚合、1d 由 4h 聚合；免费公共域名限频较严（实测触发 429 自动退避重试），配置 `COINGECKO_API_KEY` 可切换 pro 域名缓解。
  * 两种模式行情均为请求时的快照，可能随后市变化；ATR 为波动率统计，**不代表未来价格边界**。
* **DLMM 24h 涨跌幅**由 pool-discovery 的 `pool_price_change_pct` 提供；DAMM v1 接口无该字段时为空。
* **代币持仓/授权/开仓字段**（持仓数、前10持仓占比、开发方持仓占比、冻结/铸币授权、开仓人数）由 Meteora 官方 pool-discovery 接口**随 DLMM 扫描一次性返回**，无需外部补齐、无需额外点击；数据缺失的指标如实标注「数据不足（已跳过）」而非误杀。
* **DAMM v1 官方接口不含**上述持仓/授权/开仓字段，相应指标显示「数据不足（已跳过）」。
* **行情为扫描快照**：市值/价格等为**上次扫描时**的值，可能随后市波动而不同。在“③ 筛选结果”页选中行后点击「🔄 刷新选中池实时数据」，按池地址实时重取（无需整池重扫）。
* **「开仓人数」**：DLMM 由 pool-discovery 的 `open_positions` 提供（随扫描获取），已启用于筛选；DAMM v1 无该字段，标记为「数据不足（已跳过）」。
* **首次全量扫描耗时较长**（DLMM 约 13.8 万池 / 138 页；DAMM v1 约 8.6 万池 / 288 页），支持随时停止与断点续扫。

> 若首次测试希望快速体验，可在“全池扫描”页设置“每类型最多页数”（如 2），仅扫描部分页面。

---

## 十一、免责声明

本工具仅用于数据观察与研究，不构成任何投资建议。LP 收益受无常损失、价格波动、手续费分配等多因素影响，请自行评估风险。

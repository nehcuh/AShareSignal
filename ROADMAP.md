# AShareSignal 执行优先级清单（Phase 2）

> 更新日期：2026-04-15  
> 依据：`decison_01.md` — 从"会选股"升级为"会做交易"

---

## 核心决策

下一阶段研究对象从 **feature → label** 升级为 **decision_rule → trade_outcome**。

不再是"找更强信号"，而是把已有信号变成：
- 更少烂交易（veto filter）
- 更好的入场质量（entry timing & execution）
- 更完整的买卖闭环（entry × exit 联合优化）
- 更清醒的市场状态认知（regime filter）

---

## Phase 1 完成情况（已闭环）

| 任务 | 状态 |
|------|------|
| P0.1 移除硬编码 token | ✅ 完成，17 个文件已清理 |
| P0.2 统一配置入口 `src/config.py` | ✅ 完成 |
| P0.3 提取公共函数 `src/utils/common.py` | ✅ 完成 |
| P0.4 `main.py` CLI 入口 | ✅ 完成，`uv run asharesignal` 可用 |
| P0.5 `output/` 生命周期规范 | ✅ 完成，`raw/reports/archive/latest` 结构已建立 |

工程底盘已稳，现在可以全速推进策略研究。

---

## Phase 2 核心目标（未来 4-6 周）

**一句话目标**：建立第一个可回测、可比较、可迭代的"交易决策单元"研究框架，并产出 entry × exit 的最优组合结论。

---

## 第一步：定义 Champion 策略（Baseline）

任何实验都必须有 baseline。在跑新实验前，必须先钉死一个**当前主策略（champion）**。

### Champion 定义

| 维度 | 规则 |
|------|------|
| **信号生成** | `screening.py` 评分体系，每日 11:30 产生信号 |
| **股票池** | 主板非 ST |
| **入选条件** | 当日 screening 输出中 `score >= 100` 且 `rating != '高风险'` |
| **持仓数量** | 每日最多 Top 5（按 score 排序） |
| **默认入场** | 13:00 一次性买入（下午开盘价） |
| **默认出场** | T+1 开盘卖出 |
| **数据源** | pytdx 分钟数据（下午路径用于 timing 研究） |

### 落地任务

- [x] **Task 2.0.1**：在 `src/config.py` 中增加 `CHAMPION_STRATEGY` 字典，固化上述定义。
- [x] **Task 2.0.2**：新建 `src/backtest_engine.py` — **统一回测引擎**，输入为 `[日期列表, 股票列表, entry_rule, exit_rule]`，输出为 `交易明细 + 组合指标`。
- [x] **Task 2.0.3**：运行 champion baseline 回测，产出 `output/reports/champion_baseline.csv`，记录核心指标（胜率、平均收益、中位数收益、最大回撤、盈亏比、样本数、覆盖率）。

> **验收标准**：`uv run python src/backtest_engine.py --champion` 能一键产出 champion 的完整回测报告。

---

## 第二步：建立实验基础设施

为了支撑 Karpathy 式的 3 层循环（Observation → Rule → Portfolio），需要先补齐 3 个工具：

### Task 2.1：统一回测引擎 `src/backtest_engine.py` ✅ 已完成

**功能要求**：
1. 输入参数：
   - `dates`: 回测日期列表
   - `stock_selector`: 每日股票选择函数（默认 champion 的 `score>=100`）
   - `entry_rule`: 入场规则对象
   - `exit_rule`: 出场规则对象
   - `slippage`: 滑点（默认 0.1%）
2. 输出：
   - `trades_df`: 每笔交易的明细（日期、ts_code、entry_price、entry_time、exit_price、exit_time、pnl、max_dd）
   - `metrics`: 组合指标字典
3. entry_rule / exit_rule 设计成可插拔的类或字典，方便实验切换。

### Task 2.2：实验记录器 `src/experiment_logger.py` ✅ 已完成

每个实验强制记录 8 个字段：
1. 假设是什么
2. 改了哪个唯一变量
3. baseline 是什么
4. 使用的数据区间
5. 样本数是多少
6. 结果指标是什么
7. 是否通过 OOS
8. 最终决策（保留 / 废弃 / 待复核）

输出格式：自动追加到 `wiki/experiments/` 下的 markdown 文件。

### Task 2.3：Champion/Challenger 评估器 `src/champion_evaluator.py` ✅ 已完成

输入 challenger 的 metrics，自动与 champion 比较，输出升级建议：
- `PROMOTE`: 多维度更优，建议升级
- `REJECT`: 收益/回撤/OOS 至少一项明显恶化
- `PENDING`: 样本不足或结果模糊，需要更多数据

**升级门槛**（必须同时满足）：
- OOS 收益不低于 champion
- 最大回撤不恶化
- 样本覆盖率 > 50%
- 加滑点后仍成立

---

## 第三步：4 个专题研究计划

### 专题 1：入场 Veto 研究（Experiment 1）✅ 已完成

**目标**：先排除最差票，减少亏损样本。

**核心假设**：
- 对 champion 入选股票，某些下午行为能显著预测次日失败。

**研究任务**：

1. **数据准备**：
   - 收集 champion 信号票在 T 日下午的分钟数据（13:00 ~ 15:00）。
   - 计算下午路径特征：
     - `pm_return_1330`: 13:30 价格相对 13:00 的收益率
     - `pm_max_drawdown`: 下午最大回撤（%）
     - `pm_am_vol_ratio`: 下午成交量 / 上午成交量
     - `pm_vwap_1330`: 13:30 前的 VWAP
     - `pm_first_30m_return`: 下午开盘后 30 分钟收益

2. **测试 veto 规则**：
   - **Veto A**: `pm_return_1330 < 0`（13:30 仍低于下午开盘价，禁买）
   - **Veto B**: `pm_max_drawdown > 3%`
   - **Veto C**: `pm_am_vol_ratio < 0.5` 或 `> 3.0`
   - **Veto D**: `pm_first_30m_return < -1%`
   - **Veto E**: 组合 veto（A + B + C 的 AND/OR 组合）

3. **输出**：
   - `output/reports/exp01_veto_results.csv`
   - 每个 veto 规则的：胜率变化、平均收益变化、最大回撤变化、覆盖率、champion_evaluator 结论

> **验收标准**：找到至少 1 个能降低平均最大回撤且不显著牺牲胜率的 veto 规则。

---

### 专题 2：入场 Timing 研究（Experiment 2）✅ 已完成

**目标**：判断"快买"还是"确认后买"更适合 champion 信号。

**核心假设**：
- 不同 afternoon path 类型对应不同的最优入场时点。

**研究任务**：

1. **固定时点对照组**：
   - `entry_1300`, `entry_1305`, `entry_1315`, `entry_1330`, `entry_1345`, `entry_1400`, `entry_1430`
   - 直接用对应时点的价格作为买入价

2. **条件触发实验组**：
   - **Trigger A**: 13:30 前重新站上下午 VWAP（13:00~13:30 VWAP）时买入
   - **Trigger B**: 下午首 30 分钟收益转正时买入
   - **Trigger C**: 突破下午开盘后局部高点（13:00~13:30 的高点）时买入
   - **Trigger D**: 下午首次回踩不破上午收盘价时买入

3. **分批成交实验组**：
   - **Scale A**: 13:00 买 50%，13:30 条件确认后补 50%
   - **Scale B**: 13:00 买 30%，13:30 买 30%，14:00 买 40%

4. **Afternoon Path 分型**（Observation Loop）：
   - 把下午走势分为 5 类：
     - `strong_rally`: 开盘即强，单边上行
     - `dip_recovery`: 开盘回落，后面收复
     - `weak_after_spike`: 开盘冲高，随后走弱
     - `high_vol_chop`: 高波动震荡
     - `late_surge`: 尾盘才启动
   - 观察每类路径的最优 entry 是否不同。

5. **输出**：
   - `output/reports/exp02_entry_timing.csv`
   - 各 entry 规则在"买入 → T+1 开盘/10:00/收盘"的收益/回撤/胜率
   - 按 afternoon path 分层的子表

> **验收标准**：找到至少 1 个条件触发 entry，其收益/回撤比在固定时点 baseline 上显著提升。

---

### 专题 3：Entry × Exit 联合优化（Experiment 3）✅ 已完成

**目标**：找"最优交易组合"，不是孤立最优点。

**核心假设**：
- 激进 entry 配快 exit 更好；保守 entry 配趋势 exit 更好。

**研究任务**：

1. **Entry 规则集合**（从 Experiment 2 中精选 3-5 个）：
   - `E1`: champion baseline（13:00 固定买入）
   - `E2`: 最优固定时点（如 13:30）
   - `E3`: 最优条件触发（如 Trigger A）
   - `E4`: 最优 veto + entry 组合（如 E1 + Veto A）

2. **Exit 规则集合**：
   - `X1`: T+1 开盘卖
   - `X2`: T+1 10:00 卖
   - `X3`: T+1 收盘卖
   - `X4`: 跌破 T+1 VWAP 卖
   - `X5`: 回撤超 3% 止损，否则收盘卖

3. **组合矩阵回测**：
   - 行：entry 规则
   - 列：exit 规则
   - 单元格：期望收益、胜率、最大回撤、盈亏比、样本数

4. **输出**：
   - `output/reports/exp03_entry_exit_matrix.csv`
   - `wiki/experiments/exp03_conclusion.md` — 明确写出"当前最优组合"及其逻辑

> **验收标准**：产出 4×5 完整矩阵，并给出经 champion_evaluator 认证的"推荐交易组合"。

---

### 专题 4：市场状态分层研究（Experiment 4）✅ 已完成

**目标**：弄清楚策略到底在哪种市场环境下有效/失效。

**核心假设**：
- champion 策略只在特定 regime 下有效，需要 regime filter 或仓位调整。

**研究任务**：

1. **Regime 标签定义**：
   - `market_direction`: 上证指数当日涨跌幅分档（`<-1%`, `-1%~1%`, `>1%`）
   - `limit_up_count`: 涨停家数分档（`<50`, `50~100`, `>100`）
   - `market_volatility`: 上证 5 日波动率分档
   - `sector_strength`: 当日领涨板块强度（可选，先用简单代理）

2. **为 champion baseline 的每个交易日贴上 regime 标签**。

3. **按 regime 分组统计 champion 表现**：
   - 胜率、平均收益、最大回撤、盈亏比

4. **测试 regime filter**：
   - 在某些 regime 下完全停用策略（空仓），观察组合整体指标是否改善。

5. **输出**：
   - `output/reports/exp04_regime_analysis.csv`
   - `wiki/experiments/exp04_regime_conclusion.md`

> **验收标准**：识别出至少 1 种"策略应停用"的市场状态，且停用后组合夏普/回撤显著改善。

---

## 实验执行节奏（建议）

| 周次 | 重点任务 | 预计产出 |
|------|----------|----------|
| 第 1 周 | Task 2.0（Champion 定义）+ Task 2.1/2.2/2.3（基础设施） | `backtest_engine.py` + `champion_baseline.csv` |
| 第 2 周 | Experiment 1（Veto） | `exp01_veto_results.csv` + 至少 1 个有效 veto |
| 第 3 周 | Experiment 2（Timing） | `exp02_entry_timing.csv` + 最优 entry 规则 |
| 第 4 周 | Experiment 3（Entry × Exit） | `exp03_entry_exit_matrix.csv` + 推荐组合 |
| 第 5 周 | Experiment 4（Regime） + Experiment 5（Pre-Veto） | `exp04_regime_analysis.csv` + `exp05_pre_veto_results.csv` + 升级主策略 |
| 第 6 周 | 整合与升级主策略 | 新版 `main_strategy.py` + 更新 CLI |

---

## 本周最优先的 3 件事

1. **钉死 Champion 策略定义**（Task 2.0）
   - 没有 champion，所有实验都无法比较。

2. **搭建统一回测引擎**（Task 2.1）
   - 这是 4 个实验的共用基础设施，一次性投入，后续收益极大。

3. **跑通 Champion Baseline**（Task 2.0.3）
   - 产出第一份定量基准报告，作为所有 challenger 的比较对象。

---

## 新增/修改的文件清单

| 文件 | 说明 |
|------|------|
| `src/config.py` | 追加 `CHAMPION_STRATEGY` 配置 |
| `src/backtest_engine.py` | 新建：统一回测引擎 |
| `src/experiment_logger.py` | 新建：实验记录器 |
| `src/champion_evaluator.py` | 新建：Champion/Challenger 评估器 |
| `src/experiment_01_veto.py` | 新建：Veto 研究 |
| `src/experiment_02_entry_timing.py` | 新建：Timing 研究 |
| `src/experiment_03_entry_exit_matrix.py` | 新建：联合优化矩阵 |
| `src/experiment_04_regime.py` | 新建：Regime 研究 |
| `wiki/experiments/` | 新建：实验日志目录 |
| `output/reports/exp*.csv` | 实验报告输出 |

---

## 关键红线

在 Phase 2 完成前，**不建议**：
- 新增第 6 个数据源
- 新增更复杂的 ML 预测模型
- 扩大真实资金仓位
- 同时修改 entry、exit、veto、regime 多个变量做"大杂烩实验"

每轮实验**只允许改一个决策点**。

---

*本清单由 `decison_01.md` 驱动生成。建议每周一根据上周实验结果微调本周计划，但 Champion 定义和回测引擎必须本周完成。*

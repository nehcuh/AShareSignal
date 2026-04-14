---
title: Autoresearch 迭代循环
type: concept
tags: [方法论, autoresearch, Karpathy, 策略迭代]
created: 2026-04-14
updated: 2026-04-14
related_files:
  - src/autoresearch.py
  - src/experiment_006.py
  - research_log.md
---

# Autoresearch 迭代循环

## 概念概述

Autoresearch 是 AShareSignal 项目的核心研究方法论，源自 Andrej Karpathy 的"假设→实验→验证→记录→迭代"自动化研究理念。在项目中通过 `autoresearch.py` 的 `AutoResearch` 类实现，用于系统化地发现和验证对次日涨跌有预测力的特征组合。

## 核心原理

### 五步循环

```
    ┌──────────────────────────────────────┐
    │                                      │
    ▼                                      │
[提出假设] → [设计实验] → [快速验证] → [记录结果] → [迭代优化]
    ▲                                      │
    │                                      │
    └──────────────────────────────────────┘
```

1. **提出假设 (Hypothesis)**
   - 基于已有观察或直觉，提出一个可验证的假设
   - 例如："深跌反弹信号（日内跌幅>2%但收盘收回>60%位置）可以预测次日上涨"
   - 记录在 `Experiment` dataclass 的 `hypothesis` 字段中

2. **设计实验 (Experiment Design)**
   - 选择一组候选特征（如 `morning_max_down`, `rebound_strength`, `rsi_oversold`）
   - 确定评估指标（相关性、五分组差异、上涨率）
   - 创建 `Experiment` 对象，设定 `features` 列表

3. **快速验证 (Validate)**
   - `BacktestEngine.run_backtest()` 运行回测
   - 对股票池中每个交易日的每只股票提取特征，匹配次日实际涨跌
   - `BacktestEngine.evaluate_feature()` 评估每个特征的预测能力：
     - Pearson 相关性
     - 五分位分组分析（Q1-Q5 上涨率差异）
     - 区分度（Q5 vs Q1 的上涨率差和收益差）

4. **记录结果 (Log)**
   - `ResearchLogger.log_experiment()` 将结果写入 `research_log.md`
   - 记录假设、特征、状态、结果、结论
   - 所有实验自动编号和归档

5. **迭代优化 (Iterate)**
   - `systematic_feature_scan()` 自动扫描所有数值特征
   - 按相关性排序，发现新的强特征
   - 基于发现设计下一轮假设（如 Experiment 006 基于 005 的发现）

### 实验数据结构

```python
@dataclass
class Experiment:
    id: str                    # 实验编号（如 "005"）
    name: str                  # 实验名称
    hypothesis: str            # 假设描述
    features: List[str]        # 使用的特征列表
    status: ExperimentStatus   # PENDING / RUNNING / SUCCESS / FAILED
    result: Dict               # 回测结果数据
    timestamp: str             # 时间戳
    notes: str                 # 结论和备注
```

## 涉及的模块

| 模块 | 角色 |
|------|------|
| `autoresearch.py` | 核心框架：AutoResearch, DataLoader, FeatureEngineer, BacktestEngine, ResearchLogger |
| `experiment_006.py` | 实验006实现：基于005发现的深度特征工程（AdvancedFeatureEngineer） |
| `research_log.md` | 实验日志输出文件 |

## 数据流

```
assets/池子_20251104.xlsx
    │
    ▼
DataLoader.load_stock_pool()    ← 加载股票池（日期→股票列表）
DataLoader.fetch_daily_data()   ← 获取日线数据（Tushare API）
BacktestEngine.get_trading_days() ← 获取交易日历
    │
    ▼
FeatureEngineer.extract_all_features()  ← 提取特征
  ├── _extract_price_features()         ← 基础价格特征
  ├── _extract_hist_features()          ← 历史统计特征
  ├── _extract_technical_features()     ← 技术指标（RSI, KDJ）
  └── _extract_morning_features()       ← 上午模式特征（日线模拟）
    │
    ▼
BacktestEngine.run_backtest()   ← 匹配次日涨跌标签
BacktestEngine.evaluate_feature() ← 评估特征预测力
    │
    ▼
AutoResearch.systematic_feature_scan() ← 特征排名
ResearchLogger.log_experiment()  ← 写入日志
    │
    ▼
output/autoresearch_dataset.csv ← 输出数据集
research_log.md                 ← 输出实验日志
```

## 实验历史

### Experiment 005: 全面特征集测试
- **假设**: 系统化提取的所有特征可以有效预测次日涨跌
- **特征**: price_pos_20, dist_to_ma5, rsi_6, kdj_j, morning_gap_pct, volume_ratio
- **发现**:
  - `morning_max_down` 是最强特征 (corr ≈ 0.067)
  - `return_mean_20` 分组差异最大 (15.71%)
  - RSI 与次日涨跌负相关（超卖股票反而表现更好）

### Experiment 006: 深度特征工程
- **假设**: 基于005的发现，设计更精细的特征可以提升预测力
- **新增特征**: deep_rebound, rebound_strength, gap_down_reversal, gap_reversal_strength, gap_up_trap, trend_divergence, vol_regime
- **结果**: 识别出一系列合成特征（反弹强度、低开逆转、高开诱多陷阱等）

## 当前状态与挑战

1. **特征工程瓶颈** — 基础特征的预测力有限（相关性在 0.05-0.07 量级），需要引入更多维度（资金流向、板块联动等）
2. **回测框架优化** — 当前回测速度受限于 Tushare API 调用，可考虑本地数据缓存
3. **实验追踪** — 当前仅写 Markdown 日志，可升级为结构化实验追踪系统（如 MLflow）
4. **出场条件** — 当前仅研究次日涨跌（T+1），尚未研究何时卖出

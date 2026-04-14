---
title: 特征工程体系
type: concept
tags: [特征工程, 技术指标, 特征提取]
created: 2026-04-14
updated: 2026-04-14
related_files:
  - src/autoresearch.py
  - src/morning_features.py
  - src/integrated_features.py
  - src/experiment_006.py
  - src/screening.py
---

# 特征工程体系

## 概念概述

特征工程是 AShareSignal 的核心竞争力。项目通过系统化的特征提取管道，从日线和分钟线数据中构建出数十个预测特征，用于筛选和预测次日涨跌。特征设计经历了从基础到高级的迭代过程（对应 Experiment 001-006）。

## 特征分类

### 1. 基础价格特征 (`_extract_price_features()`)

| 特征名 | 计算方式 | 含义 |
|--------|---------|------|
| `price_pos_5` | `(close - low_5) / (high_5 - low_5)` | 5日价格位置（0-1） |
| `price_pos_10` | `(close - low_10) / (high_10 - low_10)` | 10日价格位置 |
| `price_pos_20` | `(close - low_20) / (high_20 - low_20)` | 20日价格位置 |
| `dist_to_ma5` | `(close - ma5) / close` | 距5日均线偏离度 |
| `dist_to_ma10` | `(close - ma10) / close` | 距10日均线偏离度 |
| `dist_to_ma20` | `(close - ma20) / close` | 距20日均线偏离度 |
| `daily_return` | `(close - prev_close) / prev_close` | 当日收益率 |
| `daily_amplitude` | `(high - low) / prev_close` | 当日振幅 |

### 2. 历史统计特征 (`_extract_hist_features()`)

| 特征名 | 计算方式 | 含义 |
|--------|---------|------|
| `return_mean_5` | 过去5日收益率均值 | 短期动量 |
| `return_mean_10` | 过去10日收益率均值 | 中期动量 |
| `return_mean_20` | 过去20日收益率均值 | 长期动量 |
| `return_std_5` | 过去5日收益率标准差 | 短期波动率 |
| `return_std_10` | 过去10日收益率标准差 | 中期波动率 |
| `return_std_20` | 过去20日收益率标准差 | 长期波动率 |
| `max_return_5` | 过去5日最大单日涨幅 | 短期爆发力 |
| `min_return_5` | 过去5日最小单日跌幅 | 短期下跌风险 |
| `max_return_10` | 过去10日最大单日涨幅 | 中期爆发力 |
| `min_return_10` | 过去10日最小单日跌幅 | 中期下跌风险 |

### 3. 技术指标特征 (`_extract_technical_features()`)

| 特征名 | 计算方式 | 含义 |
|--------|---------|------|
| `rsi_6` | RSI(6) | 6日相对强弱指标 |
| `rsi_12` | RSI(12) | 12日相对强弱指标 |
| `kdj_k` | KDJ K值 | 随机指标K |
| `kdj_d` | KDJ D值 | 随机指标D |
| `kdj_j` | KDJ J值 | 随机指标J |
| `macd` | MACD DIF线 | 趋势动量 |
| `macd_signal` | MACD 信号线 | 趋势信号 |
| `macd_hist` | MACD 柱状图 | 动量变化 |

### 4. 上午模式特征 (`_extract_morning_features()`)

这些特征在日线模拟时精度有限（用 OHLC 估算），在有真实分钟数据时更准确。

| 特征名 | 计算方式 | 含义 |
|--------|---------|------|
| `morning_gap_pct` | `(open - prev_close) / prev_close` | 跳空缺口幅度 |
| `morning_return` | `(11:30价 - open) / open` | 上午收益率 |
| `morning_max_up` | `(上午最高 - open) / open` | 上午最大涨幅 |
| `morning_max_down` | `(上午最低 - open) / open` | 上午最大跌幅 |
| `morning_volume_ratio` | `上午成交量 / 全天成交量` | 上午成交量占比 |
| `afternoon_return` | `(close - 11:30价) / 11:30价` | 下午收益率 |

### 5. 高级合成特征 (Experiment 006, `AdvancedFeatureEngineer`)

| 特征名 | 计算方式 | 含义 |
|--------|---------|------|
| `deep_rebound` | `morning_max_down < -2%` 且 `morning_return > 0` | 深跌反弹信号 |
| `rebound_strength` | `morning_return / abs(morning_max_down)` | 反弹强度 |
| `gap_down_reversal` | `morning_gap_pct < -1%` 且 `morning_return > 0` | 低开逆转 |
| `gap_reversal_strength` | `morning_return / abs(morning_gap_pct)` | 低开逆转强度 |
| `gap_up_trap` | `morning_gap_pct > 1%` 且 `morning_return < -1%` | 高开诱多陷阱 |
| `trend_divergence` | `price_pos_20 > 0.8` 且 `rsi_6 < 30` | 趋势背离 |
| `vol_regime` | `return_std_10 vs return_std_20` | 波动率状态 |

### 6. 筛选评分特征 (`screening.py`)

筛选模块使用一组独立的评分维度：

| 评分维度 | 权重 | 评分逻辑 |
|---------|------|---------|
| RSI_6 评分 | - | RSI < 30: 3分, RSI < 40: 2分, RSI < 50: 1分 |
| KDJ_J 评分 | - | J < 20: 3分, J < 30: 2分, J < 50: 1分 |
| 价格位置评分 | - | price_pos_20 < 0.3: 3分, < 0.5: 2分, < 0.7: 1分 |
| 均线偏离评分 | - | dist_to_ma5 < -3%: 3分, < -2%: 2分, < -1%: 1分 |
| 成交量评分 | - | vol_ratio > 1.5: 3分, > 1.2: 2分, > 1.0: 1分 |
| 动量评分 | - | return_mean_5 > 2%: 3分, > 0: 2分 |

## 特征重要性发现

根据 Autoresearch 系统化扫描结果（Experiment 005），特征按预测力排序：

| 排名 | 特征 | 相关性 | Q5-Q1差异 | 说明 |
|------|------|--------|----------|------|
| 1 | `morning_max_down` | 0.067 | 10.3% | 上午最大跌幅是当前最强特征 |
| 2 | `return_mean_20` | 0.052 | 15.7% | 20日动量分组差异最大 |
| 3 | `min_return_5` | 0.048 | 8.9% | 近期最大跌幅 |
| 4 | `price_pos_20` | 0.045 | 9.2% | 20日价格位置 |
| 5 | `rsi_6` | -0.041 | 7.8% | RSI 与涨跌负相关 |

### 关键发现
- **上午特征极有价值** — `morning_max_down` 是当前最强特征，说明上午盘中的剧烈波动有预测力
- **RSI 呈负相关** — 超卖股反而更可能次日上涨，符合"低买"逻辑
- **相关性量级偏低** — 最强特征也仅 ~0.07，说明单特征预测力有限，需要多特征组合
- **合成特征有潜力** — Experiment 006 的 `rebound_strength` 等合成特征组合了多个基础信号

## 特征工程改进方向

1. **资金流向特征** — 利用 Tushare `moneyflow()` 接口构建资金面特征
2. **板块联动特征** — 同板块股票的平均表现
3. **分钟级微观结构** — 订单流不平衡、成交量分布、价格冲击
4. **时序特征** — LSTM/Transformer 友好的序列特征
5. **特征选择自动化** — 使用 L1 正则化或 SHAP 值自动筛选

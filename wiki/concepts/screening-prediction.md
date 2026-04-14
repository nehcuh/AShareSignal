---
title: 筛选与预测策略
type: concept
tags: [筛选, 预测, 策略, 评分模型]
created: 2026-04-14
updated: 2026-04-14
related_files:
  - src/screening.py
  - src/screen_mainboard_today.py
  - src/screen_today.py
  - src/screen_today_pytdx.py
  - src/screen_today_tushare.py
  - src/predict_next_day.py
  - src/predict_hybrid.py
  - src/predict_real_minute.py
---

# 筛选与预测策略

## 概念概述

AShareSignal 的策略层分为两个子系统：**筛选（Screening）** 和 **预测（Prediction）**。筛选系统基于技术指标评分，从给定股票池中选出当前最值得关注的股票；预测系统使用机器学习模型，预测股票次日上涨的概率。

## 筛选系统

### 设计思路
筛选系统采用**多维度技术评分**方法，对每只股票在多个技术维度上打分（0-3分），然后加权汇总，选出总分最高的股票。

### 评分模型

```python
# screening.py 中的评分逻辑（简化）
scores = {
    'rsi':     rsi_score(rsi_6),       # RSI 超卖得分
    'kdj':     kdj_score(kdj_j),       # KDJ 低位得分
    'position': position_score(price_pos_20),  # 价格位置得分
    'ma_dist': ma_dist_score(dist_to_ma5),     # 均线偏离得分
    'volume':  volume_score(vol_ratio), # 量能得分
    'momentum': momentum_score(return_mean_5), # 动量得分
}
total_score = sum(scores.values())
```

| 维度 | 满分 | 3分条件 | 2分条件 | 1分条件 |
|------|------|--------|--------|--------|
| RSI_6 | 3 | < 30 | < 40 | < 50 |
| KDJ_J | 3 | < 20 | < 30 | < 50 |
| 价格位置 | 3 | < 0.3 | < 0.5 | < 0.7 |
| 均线偏离 | 3 | < -3% | < -2% | < -1% |
| 成交量 | 3 | ratio > 1.5 | > 1.2 | > 1.0 |
| 动量 | 3 | > 2% | > 0% | — |

**最高可能得分**: 18分

### 筛选流程
```
股票池加载 → 日线数据获取 → 指标计算 → 评分 → 排序 → 输出推荐
```

### 多版本筛选实现

由于分钟数据获取渠道不同，项目维护了多个筛选版本：

| 模块 | 数据源 | 使用场景 |
|------|--------|---------|
| `screening.py` | Tushare 日线 | 通用筛选（仅日线指标） |
| `screen_mainboard_today.py` | akshare 实时 | 今日主板实时筛选 |
| `screen_today.py` | akshare + 新浪分钟 | 今日筛选（含上午特征） |
| `screen_today_pytdx.py` | pytdx 分钟 | 今日筛选（通达信版） |
| `screen_today_tushare.py` | Tushare 分钟 | 今日筛选（Tushare版） |

### 主板筛选特殊逻辑

`screen_mainboard_today.py` 有独立的股票筛选逻辑：
- 直接从东方财富获取实时行情
- 使用 `_is_main_board()` 过滤只保留主板股票
- 使用 `_is_st_stock()` 排除 ST 股票
- 内置评分逻辑，不完全依赖 screening.py

## 预测系统

### 设计思路
预测系统使用**监督学习**方法，以股票特征为输入，次日是否上涨为标签（二分类），训练机器学习模型。

### 三种预测模式

#### 1. 纯日线预测 (`predict_next_day.py`)
- **输入**: 日线技术指标（RSI, KDJ, MACD, 价格位置等）
- **模型**: RandomForest, GradientBoosting, LogisticRegression
- **流程**:
  ```
  股票池 → 日线特征 → 模型训练 → 预测 → 排序 → 输出
  ```
- **特点**: 最简单，不依赖分钟数据

#### 2. 混合预测 (`predict_hybrid.py`)
- **输入**: 日线特征 + 模拟上午特征（用日线OHLC估算）
- **模型**: 同上
- **流程**:
  ```
  股票池 → 日线特征 → 上午特征(模拟) → 合并 → 模型训练 → 预测
  ```
- **特点**: 兼顾分钟级信息，但模拟精度有限

#### 3. 真实分钟数据预测 (`predict_real_minute.py`)
- **输入**: 日线特征 + 真实分钟数据提取的上午特征
- **模型**: 同上
- **流程**:
  ```
  股票池 → 日线特征 → 真实分钟特征 → 合并 → 模型训练 → 预测
  ```
- **特点**: 最准确，但依赖分钟数据可用性

### 模型训练流程 (`train_model.py`)

```python
# 简化流程
1. build_dataset() → 构建特征矩阵 X 和标签 y
2. train_test_split() → 时间序列分割（不能用随机分割！）
3. model.fit(X_train, y_train) → 训练模型
4. model.predict_proba(X_test) → 预测概率
5. 评估指标: AUC, 精确率, 召回率, F1
```

### 数据集构建 (`build_dataset.py`)

- **正样本**: 次日上涨的股票
- **负样本**: 次日下跌的股票
- **特征**: 所有提取的特征列
- **标签**: `next_day_return > 0` → 1, 否则 → 0
- **输出**: `output/autoresearch_dataset.csv`

## 当前挑战

### 筛选系统
1. **评分阈值固定** — 当前评分阈值是经验设定，未经过参数优化
2. **权重未优化** — 各维度等权，未使用历史数据优化权重
3. **缺乏行业/板块维度** — 仅使用个股技术指标

### 预测系统
1. **样本不平衡** — 股票池中上涨股票比例偏高（存在选择偏差）
2. **特征相关性弱** — 单特征与标签的相关性在 0.05-0.07 量级
3. **过拟合风险** — 特征数多、样本量少（约52个交易日 × 每日若干股票）
4. **时间泄露风险** — 必须严格使用 T-1 日数据预测 T 日

### 出场条件（核心痛点）
- 当前仅研究"次日涨不涨"，未研究"何时卖"
- `research_timing.py` 开始了出场时机研究，但尚未完成
- 可能的出场策略：次日开盘卖、次日冲高卖、固定持有期

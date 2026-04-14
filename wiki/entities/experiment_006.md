---
title: experiment_006.py — 深度特征工程实验
type: entity
tags: [实验, 特征工程, 高级特征]
created: 2026-04-14
updated: 2026-04-14
related_files:
  - src/experiment_006.py
  - src/autoresearch.py
  - research_log.md
---

# experiment_006.py — 深度特征工程实验

## 模块概述

`experiment_006.py` 是 Autoresearch 实验 006 的独立实现，基于实验 005 的发现，设计了更精细的**合成特征**。该模块的核心是 `AdvancedFeatureEngineer` 类，它在基础特征之上构建了"深跌反弹"、"低开逆转"、"高开诱多陷阱"等高级交易概念特征。

## 背景

实验 005 的系统化特征扫描发现：
- `morning_max_down`（上午最大跌幅）是预测力最强的单特征
- `return_mean_20`（20日动量）的分组差异最大
- 基于这些发现，实验 006 假设：**组合基础特征的合成信号可以提升预测力**

## 核心类

### `AdvancedFeatureEngineer`

```python
class AdvancedFeatureEngineer:
    """高级特征工程师 — 在基础特征之上构建合成特征"""
    
    def extract_advanced_features(self, basic_features: pd.Series) -> Dict:
        """从基础特征中提取高级合成特征
        参数: 基础特征 Series（来自 FeatureEngineer）
        返回: 高级特征字典
        """
```

### 合成特征定义

#### 1. 深跌反弹 (deep_rebound)
```python
deep_rebound = 1 if (morning_max_down < -0.02 and morning_return > 0) else 0
```
**含义**: 上午曾跌超2%，但收盘收红。表示强烈的买方力量介入。

#### 2. 反弹强度 (rebound_strength)
```python
rebound_strength = morning_return / abs(morning_max_down) if morning_max_down < 0 else 0
```
**含义**: 反弹幅度占最大跌幅的比例。值越大表示买方力量越强。

#### 3. 低开逆转 (gap_down_reversal)
```python
gap_down_reversal = 1 if (morning_gap_pct < -0.01 and morning_return > 0) else 0
```
**含义**: 低开超1%但上午收红。经典的逆转形态。

#### 4. 低开逆转强度 (gap_reversal_strength)
```python
gap_reversal_strength = morning_return / abs(morning_gap_pct) if morning_gap_pct < 0 else 0
```
**含义**: 逆转幅度占低开幅度的比例。

#### 5. 高开诱多陷阱 (gap_up_trap)
```python
gap_up_trap = 1 if (morning_gap_pct > 0.01 and morning_return < -0.01) else 0
```
**含义**: 高开超1%但上午收跌超1%。经典的诱多形态（看跌信号）。

#### 6. 趋势背离 (trend_divergence)
```python
trend_divergence = 1 if (price_pos_20 > 0.8 and rsi_6 < 30) else 0
```
**含义**: 价格在20日高位但RSI超卖。可能意味着价格拉回后反弹乏力。

#### 7. 波动率状态 (vol_regime)
```python
vol_regime = return_std_10 / return_std_20 if return_std_20 > 0 else 1
```
**含义**: 短期波动率与长期波动率的比值。>1 表示波动放大，<1 表示波动收敛。

## 实验流程

```python
# experiment_006.py 主流程
def run_experiment_006():
    # 1. 使用 AutoResearch 框架加载数据
    auto = AutoResearch()
    pool = auto.data_loader.load_stock_pool()
    
    # 2. 运行回测获取基础特征数据集
    dataset = auto.backtest_engine.run_backtest(pool, auto.data_loader, auto.feature_engineer)
    
    # 3. 应用高级特征工程
    advanced_fe = AdvancedFeatureEngineer()
    enhanced_dataset = dataset.apply(advanced_fe.extract_advanced_features, axis=1)
    
    # 4. 评估高级特征的预测力
    for feature in ['deep_rebound', 'rebound_strength', 'gap_down_reversal', ...]:
        result = auto.backtest_engine.evaluate_feature(enhanced_dataset, feature)
        print(f"{feature}: corr={result['correlation']:.4f}")
    
    # 5. 系统化扫描所有特征（基础+高级）
    ranking = auto.systematic_feature_scan(enhanced_dataset)
    
    # 6. 记录实验结果
    auto.research_logger.log_experiment(experiment)
```

## 模块依赖

```
experiment_006.py
    ├── autoresearch.py (AutoResearch, BacktestEngine)
    └── research_log.md (输出)
```

## 关键发现

- 合成特征 `rebound_strength` 和 `gap_reversal_strength` 在组合使用时可能提升预测力
- 二元信号特征（deep_rebound, gap_down_reversal）的覆盖率较低，需要更大样本验证
- `gap_up_trap` 作为看跌信号，可以用于过滤掉部分假信号

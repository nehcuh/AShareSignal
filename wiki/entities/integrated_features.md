---
title: integrated_features.py — 整合特征模块
type: entity
tags: [特征, 整合, 日线, 分钟]
created: 2026-04-14
updated: 2026-04-14
related_files:
  - src/integrated_features.py
  - src/morning_features.py
  - src/autoresearch.py
  - src/predict_hybrid.py
---

# integrated_features.py — 整合特征模块

## 模块概述

`integrated_features.py` 是特征整合层，负责将**日线技术指标特征**和**上午高频特征**合并为统一的特征向量。它是多数据源特征融合的关键桥梁。

## 核心职责

1. **合并日线特征和分钟特征** — 将两个不同来源的特征字典合并为一个 Series
2. **特征对齐** — 处理两个来源的特征索引不一致问题
3. **缺失值处理** — 当分钟数据不可用时，用日线模拟值填充
4. **特征标准化** — 对特定特征进行归一化处理

## 工作流程

```
日线数据 (Tushare)              分钟数据 (pytdx/akshare/新浪)
    │                                │
    ▼                                ▼
FeatureEngineer                  morning_features
(autoresearch.py)                .extract_morning_features()
    │                                │
    ▼                                ▼
日线特征 Dict                    上午特征 Dict
    │                                │
    └────────────┬───────────────────┘
                 │
                 ▼
         integrated_features.py
         (合并 + 缺失值填充 + 标准化)
                 │
                 ▼
         完整特征向量 → 筛选/预测/回测
```

## 使用场景

- `predict_hybrid.py` — 混合预测时，合并日线模拟特征和真实分钟特征
- `screen_today.py` — 今日筛选时，构建完整特征集
- 回测分析 — 评估完整特征集的预测力

## 关键设计

### 降级策略
当分钟数据不可用时：
1. 优先使用真实分钟数据提取的上午特征
2. 次选使用日线 OHLC 模拟的上午特征（来自 autoresearch.py）
3. 最后使用 NaN 填充，由下游模型处理缺失值

这种降级策略确保了即使分钟数据缺失，系统仍能正常运行。

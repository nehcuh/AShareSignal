---
title: morning_features.py — 上午高频特征提取
type: entity
tags: [特征提取, 分钟数据, 上午特征]
created: 2026-04-14
updated: 2026-04-14
related_files:
  - src/morning_features.py
  - src/autoresearch.py
  - src/screen_today.py
  - src/predict_real_minute.py
---

# morning_features.py — 上午高频特征提取

## 模块概述

`morning_features.py` 负责从**真实分钟数据**中提取上午交易时段（09:30-11:30）的高频特征。与 `autoresearch.py` 中用日线模拟的上午特征不同，本模块使用真实分钟 K 线数据，能提取更精确和更丰富的上午交易特征。

## 核心函数

### `extract_morning_features(minute_data: pd.DataFrame) -> Dict[str, float]`

从分钟 K 线数据中提取上午特征。

**输入**: 分钟 K 线 DataFrame，需包含列：
- `time` / `datetime`: 时间戳
- `open`, `high`, `low`, `close`: OHLC
- `volume`: 成交量

**输出**: 特征字典

### 提取的特征

#### 价格类特征
| 特征名 | 说明 |
|--------|------|
| `morning_open` | 上午开盘价（09:30 第一根K线的 open） |
| `morning_close` | 上午收盘价（11:30 最后一根K线的 close） |
| `morning_high` | 上午最高价 |
| `morning_low` | 上午最低价 |
| `morning_return` | `(morning_close - morning_open) / morning_open` |
| `morning_max_up` | `(morning_high - morning_open) / morning_open` |
| `morning_max_down` | `(morning_low - morning_open) / morning_open` |
| `morning_amplitude` | `(morning_high - morning_low) / morning_open` |
| `morning_gap_pct` | `(morning_open - prev_close) / prev_close` |

#### 成交量类特征
| 特征名 | 说明 |
|--------|------|
| `morning_volume` | 上午总成交量 |
| `morning_vol_ratio_first30` | 前30分钟成交量 / 后60分钟成交量 |
| `morning_vol_distribution` | 成交量在时间上的分布偏度 |

#### 微观结构特征
| 特征名 | 说明 |
|--------|------|
| `morning_trend_strength` | 上午趋势强度（线性回归斜率） |
| `morning_reversal_count` | 上午反转次数（涨→跌→涨） |
| `morning_vwap` | 上午成交量加权平均价 |
| `close_vs_vwap` | 收盘价相对VWAP位置 |

## 使用场景

```python
# 在 predict_real_minute.py 中的使用
from morning_features import extract_morning_features

minute_data = minute_manager.get_minute_data(code, date)
if minute_data is not None:
    morning_feats = extract_morning_features(minute_data)
    # 合并到日线特征中
    all_features = {**daily_features, **morning_feats}
```

## 与日线模拟的对比

| 特征 | 日线模拟 (autoresearch.py) | 真实分钟 (本模块) |
|------|--------------------------|-----------------|
| `morning_return` | 用 `(high+low+close)/3` 估算 | 精确的 11:30 价格 |
| `morning_max_down` | 用 `low` 近似 | 精确的上午最低价 |
| `morning_volume_ratio` | 无法计算 | 精确的上午成交量占比 |
| `morning_vwap` | 无法计算 | 完整VWAP |
| `morning_trend_strength` | 无法计算 | 可计算 |

## 数据来源

本模块不直接获取数据，依赖上游模块传入分钟 DataFrame：
- `pytdx_minute.py` → pytdx 分钟数据
- `sina_minute.py` → 新浪分钟数据
- `akshare_minute.py` → akshare 分钟数据
- `minute_data_manager.py` → 统一缓存管理

## 注意事项

1. 分钟数据的时间格式不统一，需在函数内部标准化
2. 部分数据源可能缺失某些分钟的 K 线，需处理缺失值
3. 09:25-09:30 的集合竞价数据是否包含，取决于数据源

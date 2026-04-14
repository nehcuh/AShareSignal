---
title: screening.py — 股票筛选评分系统
type: entity
tags: [筛选, 评分, 技术指标]
created: 2026-04-14
updated: 2026-04-14
related_files:
  - src/screening.py
  - src/screen_mainboard_today.py
  - src/screen_today.py
  - src/screen_today_pytdx.py
  - src/screen_today_tushare.py
  - output/screening_*.csv
---

# screening.py — 股票筛选评分系统

## 模块概述

`screening.py` 是项目的**通用筛选引擎**，基于技术指标多维度评分，从给定股票池中筛选出当前最具潜力的股票。它是多个 `screen_today_*.py` 版本的共享评分逻辑来源。

## 核心函数

### `screen_stocks(stock_pool_path, eval_date, top_n=10)`
主入口函数，执行完整筛选流程。

```python
def screen_stocks(stock_pool_path, eval_date, top_n=10):
    """
    参数:
      stock_pool_path: 股票池 Excel 文件路径
      eval_date: 评估日期 (YYYYMMDD)
      top_n: 返回前 N 只股票
    返回:
      DataFrame: 推荐股票列表 + 各维度评分
    """
```

**流程**:
1. 加载股票池 → 获取该日期的股票列表
2. 对每只股票获取 Tushare 日线数据
3. 计算技术指标（RSI, KDJ, 均线, 量比）
4. 多维度评分（6 个维度，每个 0-3 分）
5. 汇总得分排序
6. 输出前 top_n 只股票

### 评分维度详解

```python
def _score_rsi(rsi_6):
    """RSI_6 评分 — 超卖得分高"""
    if rsi_6 < 30: return 3   # 严重超卖
    elif rsi_6 < 40: return 2 # 偏弱
    elif rsi_6 < 50: return 1 # 略弱
    return 0

def _score_kdj(kdj_j):
    """KDJ_J 评分 — J值低位得分高"""
    if kdj_j < 20: return 3   # 极度超卖
    elif kdj_j < 30: return 2 # 超卖
    elif kdj_j < 50: return 1 # 偏弱
    return 0

def _score_position(price_pos_20):
    """价格位置评分 — 低位得分高"""
    if price_pos_20 < 0.3: return 3   # 20日低位
    elif price_pos_20 < 0.5: return 2 # 中低位
    elif price_pos_20 < 0.7: return 1 # 中位
    return 0

def _score_ma_dist(dist_to_ma5):
    """均线偏离评分 — 远低于均线得分高"""
    if dist_to_ma5 < -0.03: return 3  # 远低于MA5
    elif dist_to_ma5 < -0.02: return 2
    elif dist_to_ma5 < -0.01: return 1
    return 0

def _score_volume(vol_ratio):
    """量能评分 — 放量得分高"""
    if vol_ratio > 1.5: return 3  # 明显放量
    elif vol_ratio > 1.2: return 2
    elif vol_ratio > 1.0: return 1
    return 0

def _score_momentum(return_mean_5):
    """动量评分 — 短期上涨动量"""
    if return_mean_5 > 0.02: return 3  # 强势
    elif return_mean_5 > 0: return 2   # 正动量
    return 0
```

### 辅助函数

```python
def is_main_board(code: str) -> bool:
    """判断是否主板股票（6/0/3 开头但排除创业板300和科创板688）"""

def is_st_stock(name: str) -> bool:
    """判断是否ST股票（名称包含 ST 或 *ST）"""

def load_stock_pool(file_path: str) -> Dict[str, List[str]]:
    """加载股票池Excel文件"""
```

⚠️ **注意**: `is_main_board()`, `is_st_stock()`, `load_stock_pool()` 在多个模块中重复定义。

## 模块间关系

```
screening.py (本模块：通用评分逻辑)
    │
    ├── screen_mainboard_today.py (独立实现，akshare实时数据)
    ├── screen_today.py (调用本模块评分，akshare+新浪分钟)
    ├── screen_today_pytdx.py (调用本模块评分，pytdx分钟)
    └── screen_today_tushare.py (调用本模块评分，Tushare分钟)
```

## 输出格式

```csv
code,name,total_score,rsi_score,kdj_score,position_score,ma_score,volume_score,momentum_score,rsi_6,kdj_j,price_pos_20,...
```

**输出路径**: `output/screening_{date}.csv`

## 改进方向

1. **权重优化** — 当前等权，可使用历史数据优化各维度权重
2. **动态阈值** — 评分阈值应根据市场状态动态调整
3. **板块维度** — 增加板块相对强度评分
4. **去重整合** — 将重复的辅助函数抽取为公共模块

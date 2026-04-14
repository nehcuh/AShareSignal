---
title: 数据管道
type: concept
tags: [数据管道, 数据源, tushare, akshare, pytdx]
created: 2026-04-14
updated: 2026-04-14
related_files:
  - src/autoresearch.py
  - src/akshare_minute.py
  - src/pytdx_minute.py
  - src/pytdx_minute_data.py
  - src/pytdx2_adapter.py
  - src/sina_minute.py
  - src/minute_data_manager.py
---

# 数据管道

## 概念概述

AShareSignal 项目的数据管道负责从多个数据源获取 A 股行情数据，涵盖日线和分钟线两个粒度。由于单一数据源存在限流、付费、稳定性等问题，项目采用了**多数据源冗余设计**，维护了 4 条独立的数据获取通道。

## 数据源架构

```
                    ┌─────────────────────┐
                    │   数据消费方          │
                    │  (特征提取/筛选/预测)   │
                    └──────┬──────────────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
     ┌────────▼───┐  ┌─────▼────┐  ┌───▼────────┐
     │  日线数据   │  │ 分钟数据  │  │ 辅助数据    │
     │  (Tushare) │  │ (多源)   │  │ (Tushare)  │
     └────┬───────┘  └──┬──┬──┬─┘  └───┬────────┘
          │             │  │  │         │
          ▼             ▼  ▼  ▼         ▼
     ┌─────────┐  ┌────────────────┐  ┌──────────────┐
     │ Tushare │  │ akshare pytdx  │  │ 涨跌停 交易日 │
     │ Pro API │  │ pytdx2  新浪    │  │ 资金流向      │
     └─────────┘  └────────────────┘  └──────────────┘
```

## 日线数据 (Tushare Pro)

### 接口调用

| 数据类型 | Tushare 接口 | 频率限制 | 用途 |
|---------|-------------|---------|------|
| 日线行情 | `daily()` | 500次/分钟 | OHLCV、涨跌幅 |
| 每日指标 | `daily_basic()` | 500次/分钟 | 换手率、PE、PB |
| 资金流向 | `moneyflow()` | 500次/分钟 | 买卖盘资金 |
| 涨跌停 | `stk_limit()` | 500次/分钟 | 涨跌停价格 |
| 交易日历 | `trade_cal()` | 500次/分钟 | 开收盘日期 |

### Token 管理（⚠️ 技术债）
- **当前状态**：Token 硬编码在至少 6 个源文件中（autoresearch.py, screening.py, predict_next_day.py, batch_verify_all_dates.py, research_timing.py, generate_report.py）
- **Token 值**：`[REDACTED]`（不在 wiki 中记录）
- **应有方案**：统一使用环境变量 `TUSHARE_TOKEN` 或配置文件

## 分钟数据（四通道）

### 通道 1: Tushare 分钟数据
- **接口**: `stk_mins()` (Tushare Pro)
- **限制**: 每天2次调用，需付费订阅
- **缓存**: `data/minute_cache/` (pickle 格式)
- **管理器**: `minute_data_manager.py` → `MinuteDataManager` 类

### 通道 2: akshare (东方财富)
- **接口**: `ak.stock_zh_a_hist_min_em()` (东方财富)
- **特点**: 无需 API Key，但偶尔被反爬
- **备用方案**: `akshare_minute.py` 使用 curl 直接调用东方财富 API
- **使用场景**: `screen_today.py`、`screen_mainboard_today.py`

### 通道 3: pytdx (通达信)
- **协议**: 通达信私有协议，直连通达信数据服务器
- **适配器**: `pytdx_minute.py` (标准版), `pytdx2_adapter.py` (pytdx2版)
- **限制**: 无调用次数限制，需维护服务器地址
- **缓存**: `data/pytdx_cache/`, `data/pytdx_timing_cache/`
- **使用场景**: `screen_today_pytdx.py`, `batch_verify_pytdx.py`, `research_timing.py`

### 通道 4: 新浪财经
- **接口**: `ak.stock_zh_a_hist_min_em(symbol, period="5", adjust="")` 通过 akshare 获取新浪数据
- **特点**: 无 Key 无限制，数据范围有限
- **缓存**: `data/sina_minute_cache/`
- **使用场景**: `batch_verify_all_dates.py`

## 数据缓存策略

### 缓存目录结构
```
data/
├── minute_cache/          # Tushare 分钟数据 (pickle)
│   └── {code}_{date}.pkl  # 按股票代码+日期缓存
├── pytdx_cache/           # pytdx 分钟数据 (pickle)
├── pytdx_timing_cache/    # 出场时机研究缓存
└── sina_minute_cache/     # 新浪分钟数据
```

### 缓存逻辑
- 优先检查本地缓存，命中则直接加载
- 未命中时调用 API 获取并写入缓存
- `MinuteDataManager.get_minute_data(code, date)` 统一管理

## 股票池数据

- **来源文件**: `assets/池子_20251104.xlsx`
- **格式**: Excel 表格，包含约 52 个交易日的股票推荐池
- **加载方式**: `openpyxl` → pandas DataFrame
- **日期处理**: Excel 日期可能需要 +3 个月偏移（⚠️ 不一致问题）
- **用途**: 回测基准数据集

## 数据流时序

### 盘中实时流程
```
09:30-11:30  上午交易时段
    │
    ├─ akshare/pytdx 获取实时分钟数据
    ├─ morning_features 提取上午特征
    │
11:30        上午收盘
    │
    ├─ 运行筛选策略（screen_today_*.py）
    ├─ 运行预测模型（predict_*.py）
    │
    └─ 输出推荐股票列表
```

### 盘后/回测流程
```
回测日 T-1    回测日 T
    │            │
    ├─ 获取 T-1 日线数据
    ├─ 获取 T 日线数据（验证用）
    ├─ 提取 T-1 特征
    ├─ 匹配 T 日涨跌（标签）
    │
    └─ 评估特征/策略表现
```

## 已知问题与改进方向

1. **Token 硬编码** → 迁移到环境变量或配置文件
2. **缓存格式不统一** → 统一使用 parquet 格式
3. **日期偏移不一致** → 统一日期处理逻辑
4. **分钟数据通道选择** → 自动降级（Tushare → akshare → pytdx → 新浪）
5. **数据质量校验** → 缺失数据检测与自动补全

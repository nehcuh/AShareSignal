---
title: AShareSignal 项目架构总览
type: overview
tags: [架构, 总览, 技术栈]
created: 2026-04-14
updated: 2026-04-14
related_files:
  - pyproject.toml
  - main.py
  - src/autoresearch.py
  - src/screening.py
  - src/screen_mainboard_today.py
---

# AShareSignal 项目架构总览

## 1. 项目定位

AShareSignal 是一个 **A 股量化信号系统**，目标是根据当日上午的盘中行情特征，预测并筛选出次日有较大概率上涨的股票。项目采用 **Karpathy Autoresearch 方法论**（假设 → 实验 → 验证 → 记录 → 迭代）作为核心研究范式，通过系统化的特征工程和回测验证来迭代优化策略。

### 当前痛点
1. **出场条件研究** — 何时卖出（次日何时/何价位出场）尚未建立有效模型
2. **信号筛选优化** — 当前策略的次日上涨率区分度不够，需要更精细的特征和筛选规则

## 2. 技术栈

| 类别 | 技术 | 说明 |
|------|------|------|
| 语言 | Python 3.12+ | 项目要求 >= 3.12 |
| 包管理 | uv | 使用 uv 管理依赖和虚拟环境 |
| 数据源-日线 | Tushare Pro | 日线行情、每日指标、资金流向、涨跌停、交易日历 |
| 数据源-分钟线 | akshare | 东方财富实时行情、新浪财经分钟数据 |
| 数据源-分钟线 | pytdx/pytdx2 | 通达信服务器分钟数据，无 API 限制 |
| 数据源-分钟线 | 新浪财经 | 通过 akshare 获取，无 Key 无限制 |
| 机器学习 | scikit-learn | RandomForest, GradientBoosting, LogisticRegression |
| 数据处理 | pandas, numpy | 核心数据处理 |
| Excel | openpyxl | 读取股票池 Excel 文件 |

## 3. 项目结构

```
AShareSignal/
├── pyproject.toml           # 项目配置与依赖
├── main.py                  # 项目入口（当前仅占位）
├── PROJECT_CONTEXT.md       # 会话交接文档
├── CLAUDE.md                # Claude Code 配置
├── assets/
│   └── 池子_20251104.xlsx   # 历史股票池数据（约52个交易日）
├── data/                    # 数据缓存目录
│   ├── minute_cache/        # Tushare 分钟数据缓存 (pickle)
│   ├── pytdx_cache/         # pytdx 分钟数据缓存
│   ├── pytdx_timing_cache/  # 出场时机研究缓存
│   └── sina_minute_cache/   # 新浪分钟数据缓存
├── output/                  # 输出目录
│   ├── autoresearch_dataset.csv
│   ├── screening_*.csv
│   ├── predictions_*.csv
│   └── morning_pattern_analysis.csv
├── research_log.md          # Autoresearch 实验日志
└── src/                     # 源代码（29个模块）
    ├── autoresearch.py          # 🔥 核心引擎：Autoresearch 迭代框架
    ├── screening.py             # 股票池二次筛选（技术指标评分）
    ├── screen_mainboard_today.py # 今日主板实时筛选（akshare）
    ├── screen_today.py          # 今日筛选（akshare+新浪分钟数据）
    ├── screen_today_pytdx.py    # 今日筛选（pytdx版）
    ├── screen_today_tushare.py  # 今日筛选（Tushare版）
    ├── experiment_006.py        # 实验006：深度特征工程
    ├── feature-engineering 层:
    │   ├── morning_features.py   # 上午高频特征提取（Tushare分钟）
    │   ├── integrated_features.py # 整合特征（日线+上午高频）
    │   └── minute_data_manager.py # 分钟数据缓存管理
    ├── prediction 层:
    │   ├── predict_next_day.py   # 次日上涨预测（日线特征）
    │   ├── predict_hybrid.py     # 混合预测（真实分钟+日线模拟）
    │   └── predict_real_minute.py # 真实分钟数据预测
    ├── data-source 层:
    │   ├── akshare_minute.py     # akshare分钟数据（curl备选方案）
    │   ├── pytdx_minute.py       # pytdx分钟数据管理器
    │   ├── pytdx_minute_data.py  # pytdx分钟数据获取
    │   ├── pytdx2_adapter.py     # pytdx2适配器
    │   └── sina_minute.py        # 新浪财经分钟数据
    ├── backtest 层:
    │   ├── backtest_morning.py   # 上午特征回测
    │   ├── backtest_screening.py # 筛选策略回测
    │   ├── build_dataset.py      # 训练数据集构建
    │   └── train_model.py        # ML模型训练
    ├── verification 层:
    │   ├── batch_verify_all_dates.py # 批量验证（新浪数据）
    │   └── batch_verify_pytdx.py     # 批量验证（pytdx数据）
    ├── research 层:
    │   ├── research_timing.py    # 出场时机研究
    │   ├── analyze_discrimination.py # 区分度分析
    │   ├── accumulate_pool_data.py   # 股票池数据积累
    │   ├── download_pool_minute.py   # 批量下载分钟数据
    │   └── generate_report.py        # 研究报告生成
    └── ...
```

## 4. 核心数据流

```
数据源层                     特征层                     策略层                    输出
┌──────────┐            ┌──────────┐            ┌──────────────┐         ┌──────────┐
│ Tushare  │──日线──────▶│          │            │              │         │          │
│ Pro API  │──指标──────▶│ Feature  │───特征───▶│ Screening    │──推荐──▶│ CSV报告  │
└──────────┘            │ Engineer │            │ Strategy     │         │ 终端输出 │
┌──────────┐            │          │            │ (评分/评级)   │         └──────────┘
│ akshare  │──分钟──────▶│          │            └──────┬───────┘
│ 实时行情  │            └──────────┘                   │
└──────────┘                                           ▼
┌──────────┐            ┌──────────┐            ┌──────────────┐         ┌──────────┐
│ pytdx    │──分钟──────▶│ Minute   │───特征───▶│ Prediction   │──概率──▶│ 预测结果 │
│ 通达信    │            │ Manager  │            │ (混合预测)    │         │ 推荐评级 │
└──────────┘            └──────────┘            └──────┬───────┘         └──────────┘
┌──────────┐                                           │
│ 新浪财经  │──分钟──────▶ (复用特征层)                    ▼
└──────────┘            ┌──────────────────────────────────────┐
                        │ BacktestEngine / AutoResearch        │
                        │ (回测验证 → 特征排名 → 迭代优化)       │
                        └──────────────────────────────────────┘
```

## 5. 关键架构决策

### 5.1 多数据源冗余设计
项目同时维护了 4 种分钟数据获取通道（Tushare、akshare、pytdx、新浪财经），原因是：
- Tushare 分钟数据需要付费订阅且有每日调用限制（每天2次）
- akshare 分钟数据通过东方财富接口获取，但偶尔被反爬
- pytdx 通过通达信协议获取，无限制但需维护服务器列表
- 新浪财经通过 akshare 接入，稳定但数据范围有限

### 5.2 日线模拟 vs 真实分钟数据
由于分钟数据获取受限，项目采用了"混合预测"策略：
- 有真实分钟数据时使用真实数据提取特征
- 没有时用日线数据（OHLC）模拟上午特征
- `morning_gap_pct`、`morning_return` 等特征在日线模拟时精度有限

### 5.3 Karpathy Autoresearch 方法论
核心引擎 `autoresearch.py` 实现了系统化的研究循环：
1. **提出假设** — 如"深跌反弹信号可以预测次日上涨"
2. **设计实验** — 选择特征集，定义评估指标
3. **快速验证** — BacktestEngine 运行回测
4. **记录结果** — ResearchLogger 写入 Markdown 日志
5. **迭代优化** — 基于特征排名和相关性分析调整特征集

### 5.4 未来数据泄露防护
筛选和评估代码中严格使用 `eval_date` 参数：
- 评估某日股票时，只使用该日前一天及之前的数据计算指标
- 通过 `stock_data[stock_data["trade_date"] < eval_date]` 过滤

## 6. 模块分层

| 层级 | 模块 | 职责 |
|------|------|------|
| **核心引擎** | autoresearch.py | Autoresearch 框架、DataLoader、FeatureEngineer、BacktestEngine |
| **数据获取** | akshare_minute.py, pytdx_minute.py, pytdx_minute_data.py, pytdx2_adapter.py, sina_minute.py, minute_data_manager.py | 分钟数据下载、缓存管理 |
| **特征工程** | morning_features.py, integrated_features.py, experiment_006.py | 特征提取、整合、高级特征 |
| **筛选策略** | screening.py, screen_mainboard_today.py, screen_today.py, screen_today_pytdx.py, screen_today_tushare.py | 多版本筛选实现 |
| **预测模型** | predict_next_day.py, predict_hybrid.py, predict_real_minute.py | 次日涨跌预测 |
| **回测验证** | backtest_morning.py, backtest_screening.py, build_dataset.py, train_model.py | 回测分析、ML训练 |
| **批量验证** | batch_verify_all_dates.py, batch_verify_pytdx.py | 多日批量验证 |
| **研究工具** | research_timing.py, analyze_discrimination.py, accumulate_pool_data.py, download_pool_minute.py, generate_report.py | 出场研究、区分度分析、数据积累 |

## 7. 已知技术债

### 已修复（2026-04-15）
1. ~~**Token 硬编码**~~ — 已统一改为环境变量 `TUSHARE_TOKEN`，`.env.example` 已提供
2. ~~**重复代码**~~ — `is_main_board()`、`is_st_stock()`、`get_trading_days()` 已提取到 `src/utils/common.py`；`load_stock_pool()` 已统一并支持日期偏移参数
4. ~~**缺乏统一配置**~~ — 已建立 `src/config.py` 集中管理路径、数据源优先级、策略参数

### 待修复
3. **日期映射不一致** — 股票池日期处理逻辑不统一（有的 +3 个月，有的直接使用）。已通过 `load_stock_pool(add_real_date=, date_offset_months=)` 参数化，但调用点仍需统一评审
5. **main.py 占位** — 项目入口文件仅有 `print("Hello from asharesignal!")`
6. **无测试代码** — 缺少单元测试
7. **出场规则未闭环** — 尚未建立完整 exit strategy

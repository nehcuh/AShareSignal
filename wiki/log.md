---
title: AShareSignal Wiki 操作日志
type: log
tags: [日志, wiki]
created: 2026-04-14
updated: 2026-04-14
related_files: []
---

# 操作日志

## 2026-04-14 Wiki 初始化

**操作人**: Hermes Agent (自动)
**操作类型**: INIT — 项目 Wiki 初始化

### 完成的工作

1. **项目结构扫描**
   - 发现 29 个 Python 模块（`src/` 目录下）
   - 识别 4 个主要依赖：akshare, pytdx, tushare, scikit-learn
   - 确认数据源：tushare(日线)、akshare(分钟线/实时行情)、pytdx(通达信分钟线)、新浪财经(分钟线)

2. **源文件阅读与理解**
   - 逐一阅读所有 29 个 `.py` 文件的开头和关键逻辑
   - 理解 autoresearch.py 为核心引擎，使用 Karpathy 方法论（假设→实验→验证→记录→迭代）
   - 识别项目主线：数据获取 → 特征工程 → 筛选/预测 → 回测验证

3. **Git 历史了解**
   - 初始提交：`feat: Initialize AShareSignal project`
   - 第二次提交：`feat: Add real-time main board stock screening tool`

4. **Wiki 页面创建**
   - `schema.md` — wiki 约定与规范
   - `index.md` — 内容目录
   - `log.md` — 本文件
   - `overview.md` — 架构总览
   - `concepts/autoresearch-loop.md` — Autoresearch 迭代循环概念
   - `concepts/data-pipeline.md` — 数据管道概念
   - `concepts/feature-engineering.md` — 特征工程概念
   - `concepts/screening-strategy.md` — 筛选策略概念
   - `concepts/exit-strategy.md` — 出场策略概念
   - 29 个 `entities/*.md` 实体页面（每个 Python 模块对应一个）

### 发现的问题

- 多个文件中硬编码了 Tushare Token（已在 wiki 中标记为 `[REDACTED]`）
- Token 管理不统一：至少 6 个文件各自硬编码 token
- 代码中存在大量重复的工具函数（如 `load_stock_pool`, `get_trading_days`, `is_main_board`, `is_st_stock`）
- 股票池日期映射逻辑不一致（有的加3个月，有的直接使用）

### 建议的下一步

- 将公共函数抽取到 `src/utils.py` 或 `src/common.py`
- 统一 Token 管理到环境变量或配置文件
- 建立统一的日期处理规范

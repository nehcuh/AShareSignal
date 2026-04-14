---
title: Wiki 约定与规范
type: schema
tags: [wiki, 规范, 约定]
created: 2026-04-14
updated: 2026-04-14
related_files: []
---

# Wiki 约定与规范 (Schema)

本文档定义了 AShareSignal 项目 wiki 的组织方式、命名约定和内容规范。

## 1. 目录结构

```
wiki/
├── index.md              # 内容目录与导航
├── schema.md             # 本文件 — wiki 约定
├── log.md                # 操作日志
├── overview.md           # 架构总览
├── concepts/             # 概念页面（跨模块的系统性概念）
│   ├── autoresearch-loop.md
│   ├── data-pipeline.md
│   ├── feature-engineering.md
│   ├── exit-strategy.md
│   └── screening-strategy.md
└── entities/             # 模块页面（每个核心 .py 文件一个页面）
    ├── autoresearch.md
    ├── screening.md
    ├── predict-hybrid.md
    ├── ...
```

## 2. YAML Frontmatter 规范

每个页面必须以 YAML frontmatter 开头，包含以下字段：

```yaml
---
title: 页面标题          # 必填，中文
type: 页面类型           # 必填，取值：overview | concept | entity | schema | log | index
tags: [标签列表]         # 必填，至少一个
created: YYYY-MM-DD      # 创建日期
updated: YYYY-MM-DD      # 最后更新日期
related_files:           # 关联的源文件路径列表
  - src/xxx.py
---
```

### type 枚举值说明

| type | 说明 | 示例 |
|------|------|------|
| `index` | 目录导航页 | index.md |
| `schema` | 规范约定 | schema.md |
| `log` | 操作日志 | log.md |
| `overview` | 总览页面 | overview.md |
| `concept` | 概念/架构页面 | concepts/autoresearch-loop.md |
| `entity` | 模块/实体页面 | entities/autoresearch.md |

## 3. 命名约定

- **概念页面**：使用小写英文 + 连字符，如 `autoresearch-loop.md`
- **实体页面**：与源文件同名（去掉 `.py`，下划线改连字符），如 `autoresearch.md` 对应 `autoresearch.py`
- **标签**：使用中文标签，如 `[数据源, tushare, 特征工程]`
- **文件路径**：使用相对于项目根目录的路径

## 4. 内容规范

### 概念页面 (concept)
必须包含以下章节：
1. **概念概述** — 一段话概括
2. **核心原理** — 详细解释原理和设计思路
3. **涉及的模块** — 列出关联模块和文件
4. **数据流** — 描述数据如何在各模块间流转
5. **当前状态与挑战** — 实施现状、已知问题

### 实体页面 (entity)
必须包含以下章节：
1. **模块概述** — 一段话概括
2. **核心类与函数** — 列出主要类和函数签名
3. **数据流** — 输入/输出
4. **依赖关系** — 依赖的模块和外部库
5. **关键逻辑** — 重要的算法或业务逻辑
6. **注意事项** — 已知问题、TODO、限制

## 5. 安全规范

- **绝不记录 API Token 实际值**，使用 `[REDACTED]` 替代
- 不记录服务器 IP 地址等敏感信息（除非是公开的通达信服务器列表）
- 不记录具体的交易策略参数中的实盘金额

## 6. 更新规则

- 每次修改源代码后，应同步更新对应的 entity 页面
- 新增概念或架构变更时，更新 concept 页面和 overview.md
- 每次操作记录到 log.md
- 更新时修改 frontmatter 中的 `updated` 字段

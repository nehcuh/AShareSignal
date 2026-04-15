# Output 目录生命周期规范

> 生效日期：2026-04-15

---

## 目录结构

```
output/
├── raw/              # 原始日度输出（screening、tracking、analysis）
├── reports/          # 汇总报告（performance、factor comparison、tracking xlsx）
├── archive/          # 按月归档的历史文件
│   ├── 202602/
│   └── 202603/
└── latest/           # 当前有效版本的软链接
    ├── latest_daily_approx.csv -> ../raw/screening_YYYYMMDD_daily_approx.csv
    ├── latest_final_top5.csv -> ../raw/screening_YYYYMMDD_final_top5.csv
    └── latest_minute_precise.csv -> ../raw/screening_YYYYMMDD_minute_precise.csv
```

---

## 文件分类规则

### 1. `raw/` — 原始日度输出
包含每日运行产生的原始数据文件：
- `screening_YYYYMMDD_daily_approx.csv`
- `screening_YYYYMMDD_final_top5.csv`
- `screening_YYYYMMDD_minute_precise.csv`
- `stock_tracking_YYYYMMDD.csv`
- `stock_analysis_result_YYYYMMDD.csv`
- `historical_filter/` 等历史分析目录

### 2. `reports/` — 汇总报告
包含跨日期的汇总分析结果：
- `signal*_performance_*.csv`
- `signal*_factor_comparison*.csv`
- `stock_pool_tracking_total.xlsx`

### 3. `archive/YYYYMM/` — 按月归档
非当前月份（`< 当前年月`）的 `raw/` 类型文件自动移入此目录，避免 `raw/` 无限膨胀。

### 4. `latest/` — 当前有效版本
通过软链接指向 `raw/` 中最新日期的关键文件，方便脚本和外部工具直接读取"当前版本"。

---

## 命名规范

### Screening 输出
| 文件名模板 | 说明 |
|-----------|------|
| `screening_{YYYYMMDD}_daily_approx.csv` | 日度粗筛结果 |
| `screening_{YYYYMMDD}_final_top5.csv` | 精选 Top5 |
| `screening_{YYYYMMDD}_minute_precise.csv` | 分钟级精确结果 |

### 报告输出
| 文件名模板 | 说明 |
|-----------|------|
| `signal{N}_performance_{MMDD}_{MMDD}.csv` | 信号 N 在日期区间的表现跟踪 |
| `signal{N}_factor_comparison.csv` | 信号 N 的因子对比分析 |
| `stock_pool_tracking_total.xlsx` | 股票池总体跟踪汇总 |

---

## 维护方式

运行以下脚本可自动整理新增文件：

```bash
uv run python scripts/organize_output.py
```

该脚本会：
1. 将根目录下未分类的文件按规则移入 `raw/` 或 `reports/`
2. 将旧月份文件移入 `archive/YYYYMM/`
3. 更新 `latest/` 软链接

---

## 红线

- **不要**在 `output/` 根目录下直接堆积文件
- **不要**手动删除 `archive/` 中的文件（研究资产）
- **不要**直接覆盖 `latest/` 中的软链接（应通过 `organize_output.py` 更新）

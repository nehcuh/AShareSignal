# exp03_entry_exit_matrix

> 记录时间: 2026-04-15 16:37

## 1. 假设

激进 entry（13:00 开盘）配快 exit（10:00）更优，或保守 entry 配趋势 exit 更优

## 2. 唯一变量

exit timing & stop-loss rules

## 3. Baseline

E1_pm_open_X1_open

## 4. 数据区间

20260320 ~ 20260414

## 5. 样本数

75

## 6. 结果指标

```json
{
  "baseline": {
    "name": "E1_pm_open_X1_open",
    "total_trades": 75,
    "win_rate": 46.67,
    "avg_return": 0.1025,
    "portfolio_max_dd": 3.1435
  },
  "challenger": {
    "name": "E4_E1_plus_Veto_A_X5_dd3_stop",
    "total_trades": 42,
    "win_rate": 71.43,
    "avg_return": 1.4279,
    "portfolio_max_dd": 2.2395
  }
}
```

## 7. OOS 验证

✅ 通过

## 8. 最终决策

**保留**

## 备注

推荐组合: E4_E1_plus_Veto_A × X5_dd3_stop，详见 /Users/huchen/Projects/AShareSignal/output/reports/exp03_entry_exit_matrix.csv

---


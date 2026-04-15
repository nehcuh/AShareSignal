# exp02_entry_timing

> 记录时间: 2026-04-15 16:28

## 1. 假设

对 champion 信号票，真实下午开盘价（13:00）买入优于用收盘价代理，且越早买入组合回撤越小

## 2. 唯一变量

entry timing: 从收盘价代理切换为真实 13:00 pm_open

## 3. Baseline

E1_baseline_close

## 4. 数据区间

20260320 ~ 20260414

## 5. 样本数

80

## 6. 结果指标

```json
{
  "baseline": {
    "name": "E1_baseline_close",
    "total_trades": 80,
    "win_rate": 16.2,
    "avg_return": -1.3,
    "max_drawdown": -6.77,
    "portfolio_max_dd": 17.3,
    "profit_loss_ratio": 0.69,
    "coverage": 94.1
  },
  "challenger": {
    "name": "E2_1300",
    "total_trades": 75,
    "win_rate": 46.7,
    "avg_return": 0.1,
    "max_drawdown": -7.0,
    "portfolio_max_dd": 3.14,
    "profit_loss_ratio": 999,
    "coverage": 94.1
  }
}
```

## 7. OOS 验证

✅ 通过

## 8. 最终决策

**保留 — 建议更新 Champion Baseline 的 entry_price 为真实 pm_open**

## 备注

关键发现：1) 收盘价代理严重低估表现；2) 13:00 开盘买是最优固定时点，胜率 46.7%，组合回撤仅 3.14%；3) 条件触发规则未优于简单固定时点

---


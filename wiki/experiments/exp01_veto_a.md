# exp01_veto_a

> 记录时间: 2026-04-15 16:24

## 1. 假设

对 score>=60 的股票，若 13:30 仍低于下午开盘价（pm_return_1330 < 0），则禁买能降低最大回撤

## 2. 唯一变量

entry veto 规则: pm_return_1330 < 0

## 3. Baseline

champion_baseline

## 4. 数据区间

20260320 ~ 20260414

## 5. 样本数

80

## 6. 结果指标

```json
{
  "baseline": {
    "name": "champion_baseline",
    "total_trades": 80,
    "win_rate": 16.2,
    "avg_return": -1.3,
    "median_return": -1.26,
    "max_drawdown": -6.77,
    "portfolio_max_dd": 17.3,
    "profit_loss_ratio": 0.69,
    "coverage": 94.1
  },
  "challenger": {
    "name": "Veto_A",
    "total_trades": 47,
    "win_rate": 19.1,
    "avg_return": -1.24,
    "median_return": 0,
    "max_drawdown": -4.53,
    "portfolio_max_dd": 15.64,
    "profit_loss_ratio": 0.76,
    "coverage": 94.1
  }
}
```

## 7. OOS 验证

✅ 通过

## 8. 最终决策

**保留 — 通过 Champion Evaluator (PROMOTE)，建议作为候选升级规则纳入 Timing 联合测试**

## 备注

否决 33/80 (41.2%) 交易，组合最大回撤从 17.30% 降至 15.64%，胜率从 16.2% 升至 19.1%

---


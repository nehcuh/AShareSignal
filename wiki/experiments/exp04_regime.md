# exp04_regime

> 记录时间: 2026-04-15 16:41

## 1. 假设

champion 策略在某些市场 regime 下应停用（空仓），以改善整体组合表现

## 2. 唯一变量

regime filter: market_direction != up(>1%)

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
    "total_trades": 80,
    "win_rate": 46.25,
    "avg_return": 0.1235,
    "median_return": -0.1686,
    "max_drawdown": -6.9962,
    "portfolio_max_dd": 3.1435,
    "profit_loss_ratio": 1.3164,
    "coverage": 94.12,
    "daily_std": 0.9449,
    "sharpe_approx": 0.1307,
    "name": "champion_baseline"
  },
  "challenger": {
    "name": "market_direction != up(>1%)",
    "total_trades": 60,
    "win_rate": 48.33,
    "avg_return": 0.2087,
    "portfolio_max_dd": 2.9023
  }
}
```

## 7. OOS 验证

✅ 通过

## 8. 最终决策

**保留**

## 备注

最优 filter: market_direction != up(>1%)，详见 /Users/huchen/Projects/AShareSignal/output/reports/exp04_regime_analysis.csv

---


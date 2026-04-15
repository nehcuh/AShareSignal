# exp03_conclusion_corrected

> 记录时间: 2026-04-15 17:02

## 1. 假设

真实下午开盘价买入 + T+1 3%止损/收盘卖 是无可执行未来函数的最优组合

## 2. 唯一变量

exit rule: t1_open -> stop_loss_close 3%; entry price: close proxy -> pm_open

## 3. Baseline

E1_baseline_close_proxy

## 4. 数据区间

20260324 ~ 20260414

## 5. 样本数

70

## 6. 结果指标

```json
{
  "baseline": {
    "name": "E1_baseline_close_proxy",
    "total_trades": 80,
    "win_rate": 16.2,
    "avg_return": -1.3,
    "portfolio_max_dd": 17.3
  },
  "challenger": {
    "name": "E1_pm_open_X5_dd3_stop",
    "total_trades": 70,
    "win_rate": 60.0,
    "avg_return": 0.62,
    "portfolio_max_dd": 3.83
  }
}
```

## 7. OOS 验证

✅ 通过

## 8. 最终决策

**保留 — 已更新为默认策略，但 Veto_A 因未来函数被移除**

## 备注

勘误：原 E4(E1+Veto_A) 组合存在未来函数（13:00 买入依赖 13:30 数据），已修正为仅 E1+X5

---


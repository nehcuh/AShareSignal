# exp01_veto_a_test

> 记录时间: 2026-04-15 16:17

## 1. 假设

对 score>=60 的股票，若 13:30 仍低于下午开盘价则禁买，可降低最大回撤

## 2. 唯一变量

entry veto 规则: pm_return_1330 < 0

## 3. Baseline

champion_baseline (score>=60, T+1开盘卖出)

## 4. 数据区间

20260320 ~ 20260414

## 5. 样本数

80

## 6. 结果指标

```json
{
  "win_rate": 16.2,
  "avg_return": -1.3,
  "max_drawdown": -6.77
}
```

## 7. OOS 验证

❌ 未通过

## 8. 最终决策

**废弃**

## 备注

这是一个测试记录

---


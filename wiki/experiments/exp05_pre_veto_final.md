# exp05_pre_veto_final

> 记录时间: 2026-04-15 19:07

## 1. 假设

上午最后5分钟（11:25-11:30）跌幅超0.5%的信号，下午开盘买入表现显著变差，可用作13:00前可执行的veto

## 2. 唯一变量

veto_rules: 增加 last_5m_return >= -0.5%

## 3. Baseline

E1_pm_open_X5_no_veto

## 4. 数据区间

20260324 ~ 20260414

## 5. 样本数

70

## 6. 结果指标

```json
{
  "baseline": {
    "name": "E1_pm_open_X5_no_veto",
    "total_trades": 70,
    "win_rate": 60.0,
    "avg_return": 0.62,
    "portfolio_max_dd": 3.83
  },
  "challenger": {
    "name": "E1_pm_open_X5_pre_veto_B",
    "total_trades": 67,
    "win_rate": 64.2,
    "avg_return": 0.96,
    "portfolio_max_dd": 1.9
  }
}
```

## 7. OOS 验证

✅ 通过

## 8. 最终决策

**保留 — 已固化为 CHAMPION_STRATEGY 默认 veto**

## 备注

效果：胜率 60.0%->64.2%，平均收益 +0.62%->+0.96%，组合回撤 3.83%->1.90%，否决约4.3%交易

---


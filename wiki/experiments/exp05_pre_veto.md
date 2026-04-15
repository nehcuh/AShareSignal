# exp05_pre_veto

> 记录时间: 2026-04-15 19:02

## 1. 假设

上午收盘前（11:20-11:30）的某些特征可以预测下午开盘后表现，从而构建 13:00 之前可执行的 veto

## 2. 唯一变量

pre-veto: last_5m_return < -0.5%

## 3. Baseline

no_veto

## 4. 数据区间

20260324 ~ 20260414

## 5. 样本数

70

## 6. 结果指标

```json
{
  "baseline": {
    "name": "no_veto",
    "total_trades": 70,
    "avg_return": 0.6190042857142858
  },
  "challenger": {
    "name": "last_5m_return < -0.5%",
    "total_trades": 63,
    "avg_return": 0.8595
  }
}
```

## 7. OOS 验证

✅ 通过

## 8. 最终决策

**保留**

## 备注

最优代理规则: last_5m_return < -0.5%，相关性最强特征: low_time_position

---


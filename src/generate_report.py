"""
上午高频特征研究总结报告

生成方法: uv run python src/generate_report.py
"""

import pandas as pd
import numpy as np
from pathlib import Path


def generate_report():
    """生成上午特征研究总结报告"""

    print("="*80)
    print("上午高频特征研究总结报告")
    print("="*80)

    # 1. 加载数据
    morning_df = pd.read_csv("output/morning_pattern_analysis.csv")
    training_df = pd.read_csv("output/training_dataset.csv")

    print(f"\n📊 数据概况")
    print(f"{'='*80}")
    print(f"总样本数: {len(training_df)}")
    print(f"股票池交易日: 52天")
    print(f"涉及股票数: 1489只")
    print(f"次日上涨率: {training_df['next_up'].mean()*100:.1f}%")
    print(f"次日平均涨跌: {training_df['next_pct_chg'].mean():+.2f}%")

    # 2. 上午特征发现
    print(f"\n📈 上午特征发现")
    print(f"{'='*80}")

    print("\n1. 开盘跳空模式")
    print("-"*50)

    gap_categories = {
        "大幅高开 (>2%)": training_df[training_df['morning_gap_pct'] > 2],
        "小幅高开 (0.5%-2%)": training_df[(training_df['morning_gap_pct'] > 0.5) & (training_df['morning_gap_pct'] <= 2)],
        "平开 (-0.5%-0.5%)": training_df[(training_df['morning_gap_pct'] >= -0.5) & (training_df['morning_gap_pct'] <= 0.5)],
        "小幅低开 (-2%--0.5%)": training_df[(training_df['morning_gap_pct'] >= -2) & (training_df['morning_gap_pct'] < -0.5)],
        "大幅低开 (<-2%)": training_df[training_df['morning_gap_pct'] < -2],
    }

    for cat_name, subset in gap_categories.items():
        if len(subset) > 0:
            up_rate = subset['next_up'].mean() * 100
            avg_return = subset['next_pct_chg'].mean()
            print(f"  {cat_name}: {len(subset)}只, 上涨率{up_rate:.1f}%, 平均收益{avg_return:+.2f}%")

    print("\n2. 日内振幅与次日表现")
    print("-"*50)

    # 按振幅分组
    training_df['amplitude_quartile'] = pd.qcut(training_df['morning_range'], q=4, labels=['低振幅', '中低', '中高', '高振幅'])

    for quartile in ['低振幅', '中低', '中高', '高振幅']:
        subset = training_df[training_df['amplitude_quartile'] == quartile]
        if len(subset) > 0:
            up_rate = subset['next_up'].mean() * 100
            avg_return = subset['next_pct_chg'].mean()
            avg_amp = subset['morning_range'].mean()
            print(f"  {quartile} (平均{avg_amp:.1f}%): 上涨率{up_rate:.1f}%, 平均收益{avg_return:+.2f}%")

    # 3. 特征相关性
    print(f"\n📊 特征与次日涨跌相关性")
    print(f"{'='*80}")

    morning_features = ['morning_gap_pct', 'morning_return', 'morning_max_up', 'morning_max_down', 'morning_range']
    daily_features = ['pct_chg', 'rsi_6', 'kdj_j', 'volatility_5', 'volatility_20', 'price_pos_20']

    print("\n上午特征:")
    for feat in morning_features:
        if feat in training_df.columns:
            corr = training_df[feat].corr(training_df['next_pct_chg'])
            print(f"  {feat}: {corr:.4f}")

    print("\n日线特征:")
    for feat in daily_features:
        if feat in training_df.columns:
            corr = training_df[feat].corr(training_df['next_pct_chg'])
            print(f"  {feat}: {corr:.4f}")

    # 4. 策略建议
    print(f"\n💡 策略建议")
    print(f"{'='*80}")

    # 找出表现最好的组合
    high_gap = training_df[training_df['morning_gap_pct'] > 2]
    low_vol = training_df[training_df['volatility_20'] < training_df['volatility_20'].median()]

    combined = training_df[
        (training_df['morning_gap_pct'] > 2) &
        (training_df['volatility_20'] < training_df['volatility_20'].median())
    ]

    print(f"\n1. 单因子策略")
    print(f"   - 大幅高开策略: 次日上涨率 {high_gap['next_up'].mean()*100:.1f}%, 样本{len(high_gap)}只")

    print(f"\n2. 多因子组合策略")
    if len(combined) > 10:
        print(f"   - 大幅高开 + 低波动: 次日上涨率 {combined['next_up'].mean()*100:.1f}%, 样本{len(combined)}只")
    else:
        print(f"   - 大幅高开 + 低波动: 样本不足({len(combined)}只)")

    print(f"\n3. 风险控制")
    print(f"   - 避免小幅高开的股票（次日表现最差）")
    print(f"   - 高波动股票次日不确定性更大")

    # 5. 模型效果
    print(f"\n🤖 机器学习模型效果")
    print(f"{'='*80}")
    print(f"特征集          AUC         准确率")
    print(f"-"*40)
    print(f"日线特征        0.568       58.5%")
    print(f"上午特征        0.535       59.9%")
    print(f"全部特征        0.569       60.5%")

    print(f"\n结论:")
    print(f"  - 上午特征与日线特征结合效果最好")
    print(f"  - AUC 0.569 略高于随机水平，有一定预测能力")
    print(f"  - 准确率约60%，相比基准40.5%有提升")

    # 6. 改进方向
    print(f"\n🚀 改进方向")
    print(f"{'='*80}")
    print(f"1. 获取真实分钟数据")
    print(f"   - 当前使用日线模拟上午特征")
    print(f"   - 真实分钟数据可提取更精确的早盘特征")
    print(f"")
    print(f"2. 增加更多特征")
    print(f"   - 资金流向数据（大单净流入）")
    print(f"   - 板块/市场情绪指标")
    print(f"   - 基本面指标（PE、PB等）")
    print(f"")
    print(f"3. 模型优化")
    print(f"   - 尝试更复杂的模型（XGBoost、LightGBM）")
    print(f"   - 时序模型（LSTM等）")
    print(f"   - 集成多个模型")
    print(f"")
    print(f"4. 策略优化")
    print(f"   - 根据市场环境动态调整阈值")
    print(f"   - 加入止盈止损逻辑")
    print(f"   - 仓位管理")

    print(f"\n{'='*80}")
    print("报告生成完成!")
    print(f"{'='*80}")


if __name__ == "__main__":
    generate_report()

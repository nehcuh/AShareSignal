"""
上午高频特征回测分析
验证上午特征对次日涨跌的预测能力
"""

import tushare as ts
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import List

from config import pro
from utils.common import get_trading_days, load_stock_pool, get_next_trading_day


def analyze_morning_pattern(df: pd.DataFrame) -> pd.DataFrame:
    """
    分析上午价格行为模式对次日涨跌的预测能力

    这里使用日线数据中的开盘/收盘/最高/最低价来模拟上午行为
    """
    results = []

    for _, row in df.iterrows():
        open_price = row["open"]
        close_price = row["close"]
        pre_close = row["pre_close"]
        high = row["high"]
        low = row["low"]
        vol = row["vol"]

        # 1. 开盘跳空特征
        gap_pct = (open_price - pre_close) / pre_close * 100

        # 2. 开盘强度（开盘后第一小时的假设表现）
        # 用开盘价到收盘价的中间位置模拟上午收盘
        simulated_morning_close = (open_price + close_price) / 2

        # 3. 上午涨跌幅（模拟）
        morning_return_pct = (simulated_morning_close - pre_close) / pre_close * 100

        # 4. 开盘位置（相对前日收盘）
        if gap_pct > 2:
            gap_category = "大幅高开"
        elif gap_pct > 0.5:
            gap_category = "小幅高开"
        elif gap_pct > -0.5:
            gap_category = "平开"
        elif gap_pct > -2:
            gap_category = "小幅低开"
        else:
            gap_category = "大幅低开"

        # 5. 日内趋势（上午假设）
        if close_price > open_price:
            morning_trend = "上涨"
        elif close_price < open_price:
            morning_trend = "下跌"
        else:
            morning_trend = "横盘"

        # 6. 振幅特征
        amplitude = (high - low) / open_price * 100

        # 7. 相对前日波动
        prev_amplitude = row.get("prev_amplitude", 5)
        vol_expansion = amplitude / prev_amplitude if prev_amplitude > 0 else 1

        results.append({
            "ts_code": row["ts_code"],
            "trade_date": row["trade_date"],
            "gap_pct": round(gap_pct, 2),
            "gap_category": gap_category,
            "morning_return_pct": round(morning_return_pct, 2),
            "morning_trend": morning_trend,
            "amplitude": round(amplitude, 2),
            "vol_expansion": round(vol_expansion, 2),
            "next_pct_chg": row.get("next_pct_chg", 0),
            "next_up": row.get("next_up", 0),
        })

    return pd.DataFrame(results)


def analyze_patterns_discrimination(pattern_df: pd.DataFrame) -> None:
    """分析不同上午模式的次日表现"""

    print("\n" + "="*80)
    print("一、开盘跳空模式分析")
    print("="*80)

    for category in ["大幅高开", "小幅高开", "平开", "小幅低开", "大幅低开"]:
        subset = pattern_df[pattern_df["gap_category"] == category]
        if len(subset) == 0:
            continue

        up_rate = subset["next_up"].mean() * 100
        avg_next_return = subset["next_pct_chg"].mean()

        print(f"\n【{category}】({len(subset)} 只)")
        print(f"  次日上涨率: {up_rate:.1f}%")
        print(f"  次日平均涨跌: {avg_next_return:+.2f}%")

    print("\n" + "="*80)
    print("二、上午趋势模式分析")
    print("="*80)

    for trend in ["上涨", "下跌", "横盘"]:
        subset = pattern_df[pattern_df["morning_trend"] == trend]
        if len(subset) == 0:
            continue

        up_rate = subset["next_up"].mean() * 100
        avg_next_return = subset["next_pct_chg"].mean()

        print(f"\n【上午{trend}】({len(subset)} 只)")
        print(f"  次日上涨率: {up_rate:.1f}%")
        print(f"  次日平均涨跌: {avg_next_return:+.2f}%")

    print("\n" + "="*80)
    print("三、开盘跳空 vs 次日涨跌相关性")
    print("="*80)

    # 计算相关性
    corr = pattern_df["gap_pct"].corr(pattern_df["next_pct_chg"])
    print(f"\n开盘跳空幅度与次日涨跌相关性: {corr:.4f}")

    if corr > 0.1:
        print("  → 正相关：高开股票次日倾向于继续上涨")
    elif corr < -0.1:
        print("  → 负相关：高开股票次日倾向于回落（高开低走）")
    else:
        print("  → 相关性弱：开盘跳空对次日涨跌预测力有限")

    print("\n" + "="*80)
    print("四、量化分组分析")
    print("="*80)

    # 按开盘跳空幅度分组
    pattern_df["gap_quintile"] = pd.qcut(pattern_df["gap_pct"], q=5, labels=["Q1(最低)", "Q2", "Q3", "Q4", "Q5(最高)"], duplicates="drop")

    print(f"\n{'分组':<12} {'样本数':<10} {'次日上涨率':<12} {'次日平均涨跌':<12}")
    print("-" * 50)

    for q in pattern_df["gap_quintile"].cat.categories:
        subset = pattern_df[pattern_df["gap_quintile"] == q]
        if len(subset) == 0:
            continue
        up_rate = subset["next_up"].mean() * 100
        avg_return = subset["next_pct_chg"].mean()
        print(f"{q:<12} {len(subset):<10} {up_rate:.1f}%{'':<6} {avg_return:+.2f}%")

    print("\n" + "="*80)
    print("五、策略建议")
    print("="*80)

    # 找出表现最好和最差的模式
    category_stats = []
    for category in pattern_df["gap_category"].unique():
        subset = pattern_df[pattern_df["gap_category"] == category]
        if len(subset) > 5:  # 只考虑样本量足够的类别
            category_stats.append({
                "category": category,
                "count": len(subset),
                "up_rate": subset["next_up"].mean(),
                "avg_return": subset["next_pct_chg"].mean()
            })

    if category_stats:
        stats_df = pd.DataFrame(category_stats)
        best = stats_df.loc[stats_df["avg_return"].idxmax()]
        worst = stats_df.loc[stats_df["avg_return"].idxmin()]

        print(f"\n✅ 最优模式: {best['category']}")
        print(f"   次日上涨率: {best['up_rate']*100:.1f}%, 平均收益: {best['avg_return']:+.2f}%")

        print(f"\n⚠️  最差模式: {worst['category']}")
        print(f"   次日上涨率: {worst['up_rate']*100:.1f}%, 平均收益: {worst['avg_return']:+.2f}%")

        print("\n" + "-"*50)
        print("【实用建议】")

        # 根据数据给出具体建议
        if best["category"] == "大幅低开" and best["avg_return"] > 0:
            print("1. 大幅低开的股票可能存在'低开高走'反弹机会")
        elif best["category"] == "平开" and best["avg_return"] > 0:
            print("1. 平开股票可能更稳定，适合保守策略")

        if worst["category"] == "大幅高开" and worst["avg_return"] < 0:
            print("2. 避免追高：大幅高开的股票次日倾向于回落")

        if abs(corr) > 0.15:
            print(f"3. 开盘跳空幅度可作为次日预测的重要参考（相关系数 {corr:.2f}）")
        else:
            print("3. 仅依赖开盘跳空幅度不足以预测次日走势，需结合其他指标")


def main():
    """主函数：分析上午模式对次日涨跌的预测能力"""

    excel_path = Path(__file__).parent.parent / "assets" / "池子_20251104.xlsx"
    pool_df = load_stock_pool(str(excel_path), add_real_date=True)

    print("="*80)
    print("上午高频特征回测分析")
    print("="*80)
    print(f"\n股票池: {len(pool_df)} 个交易日")
    print(f"日期范围: {pool_df['real_date'].min()} ~ {pool_df['real_date'].max()}")

    # 获取交易日历
    min_date = pool_df["real_date"].min().strftime("%Y%m%d")
    max_date = (pool_df["real_date"].max() + timedelta(days=30)).strftime("%Y%m%d")
    trading_days = get_trading_days(min_date, max_date)

    # 收集所有股票
    all_stocks = set()
    for codes in pool_df["stock_list"]:
        all_stocks.update(codes)

    print(f"涉及股票: {len(all_stocks)} 只")

    # 获取日线数据
    print("\n获取历史数据...")
    stock_list = list(all_stocks)
    start_fetch = (datetime.strptime(min_date, "%Y%m%d") - timedelta(days=30)).strftime("%Y%m%d")

    all_daily = []
    for i in range(0, len(stock_list), 100):
        batch = stock_list[i:i+100]
        df = pro.daily(ts_code=",".join(batch), start_date=start_fetch, end_date=max_date)
        if df is not None and len(df) > 0:
            all_daily.append(df)
            print(f"  批次 {i//100+1}: {len(df)} 条")

    if not all_daily:
        print("未获取到数据")
        return

    daily_df = pd.concat(all_daily, ignore_index=True)
    print(f"总共 {len(daily_df)} 条日线记录")

    # 计算前日振幅（用于量比计算）
    daily_df = daily_df.sort_values(["ts_code", "trade_date"])
    daily_df["prev_amplitude"] = daily_df.groupby("ts_code").apply(
        lambda x: ((x["high"] - x["low"]) / x["open"] * 100).shift(1)
    ).reset_index(level=0, drop=True)

    # 提取上午模式样本
    print("\n提取上午价格模式...")
    all_patterns = []

    for idx, row in pool_df.iterrows():
        pool_date = row["real_date"].strftime("%Y%m%d")
        ts_codes = row["stock_list"]

        next_date = get_next_trading_day(pool_date, trading_days)
        if next_date is None:
            continue

        # 获取pool_date当天的数据（模拟上午筛选时已收盘）
        pool_data = daily_df[daily_df["trade_date"] == pool_date]
        next_data = daily_df[daily_df["trade_date"] == next_date]

        for code in ts_codes:
            day_row = pool_data[pool_data["ts_code"] == code]
            if len(day_row) == 0:
                continue

            next_row = next_data[next_data["ts_code"] == code]
            if len(next_row) == 0:
                continue

            day_dict = day_row.iloc[0].to_dict()
            day_dict["next_pct_chg"] = next_row.iloc[0]["pct_chg"]
            day_dict["next_up"] = 1 if next_row.iloc[0]["pct_chg"] > 0 else 0

            all_patterns.append(day_dict)

    if not all_patterns:
        print("无有效样本")
        return

    pattern_df = pd.DataFrame(all_patterns)
    print(f"总样本数: {len(pattern_df)}")

    # 分析上午模式
    analyzed_df = analyze_morning_pattern(pattern_df)

    # 分析区分度
    analyze_patterns_discrimination(analyzed_df)

    # 保存结果
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    analyzed_df.to_csv(output_dir / "morning_pattern_analysis.csv", index=False, encoding="utf-8-sig")
    print(f"\n详细结果已保存: output/morning_pattern_analysis.csv")


if __name__ == "__main__":
    main()

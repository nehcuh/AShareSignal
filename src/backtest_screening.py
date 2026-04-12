"""
筛选策略回测分析
验证评分是否能够有效区分次日涨跌
"""

import tushare as ts
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional

TUSHARE_TOKEN = "fd6cf8fc8404cf6f93ca6091c1e603d9bc3a65f5a536c77dbb882e60"
ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()


def load_stock_pool(excel_path: str) -> pd.DataFrame:
    """加载股票池"""
    df = pd.read_excel(excel_path)
    df["pool_date"] = pd.to_datetime(df["pool_date"])
    df["stock_list"] = df["pool_data"].str.split(",")
    return df


def get_trading_days(start_date: str, end_date: str) -> List[str]:
    """获取交易日列表"""
    cal = pro.trade_cal(exchange="SSE", start_date=start_date, end_date=end_date)
    return sorted(cal[cal["is_open"] == 1]["cal_date"].tolist())


def get_prev_trading_day(trade_date: str, trading_days: List[str]) -> Optional[str]:
    """获取前一个交易日"""
    for i, d in enumerate(trading_days):
        if d == trade_date and i > 0:
            return trading_days[i - 1]
    for d in reversed(trading_days):
        if d < trade_date:
            return d
    return None


def get_next_trading_day(trade_date: str, trading_days: List[str]) -> Optional[str]:
    """获取下一个交易日"""
    for d in trading_days:
        if d > trade_date:
            return d
    return None


def calc_rsi(close: pd.Series, period: int = 6) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, np.inf)
    return 100 - (100 / (1 + rs))


def calc_kdj(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 9) -> dict:
    low_n = low.rolling(window=n).min()
    high_n = high.rolling(window=n).max()
    rsv = (close - low_n) / (high_n - low_n + 1e-10) * 100
    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    j = 3 * k - 2 * d
    return {"k": k, "d": d, "j": j}


def calc_macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> dict:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    macd = (dif - dea) * 2
    return {"macd": macd, "dif": dif, "dea": dea}


def calculate_score(stock_data: pd.DataFrame) -> int:
    """计算评分（只用前一天及之前的数据）"""
    if len(stock_data) < 5:
        return 50

    close = stock_data["close"]
    high = stock_data["high"]
    low = stock_data["low"]
    pct_chg = stock_data["pct_chg"]

    rsi = calc_rsi(close)
    kdj = calc_kdj(high, low, close)
    macd_dict = calc_macd(close)

    rsi_val = rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50
    kdj_j = kdj["j"].iloc[-1] if not pd.isna(kdj["j"].iloc[-1]) else 50

    up_days = sum(pct_chg.tail(5) > 0)
    down_days = sum(pct_chg.tail(5) < 0)

    score = 50

    if rsi_val > 70:
        score -= 15
    elif rsi_val < 30:
        score += 10

    if kdj_j > 80:
        score -= 10
    elif kdj_j < 20:
        score += 10

    if (
        len(macd_dict["dif"]) > 1
        and macd_dict["dif"].iloc[-1] > macd_dict["dea"].iloc[-1]
        and macd_dict["dif"].iloc[-2] <= macd_dict["dea"].iloc[-2]
    ):
        score += 10
    elif (
        len(macd_dict["dif"]) > 1
        and macd_dict["dif"].iloc[-1] < macd_dict["dea"].iloc[-1]
        and macd_dict["dif"].iloc[-2] >= macd_dict["dea"].iloc[-2]
    ):
        score -= 10

    if up_days >= 4:
        score -= 10
    elif down_days >= 4:
        score += 10

    return score


def main():
    excel_path = Path(__file__).parent.parent / "assets" / "池子_20251104.xlsx"
    pool_df = load_stock_pool(str(excel_path))

    print("=" * 80)
    print("股票池筛选策略回测分析报告")
    print("=" * 80)

    print(f"\n股票池: {len(pool_df)} 个交易日")
    print(
        f"日期范围: {pool_df['pool_date'].min().strftime('%Y-%m-%d')} ~ {pool_df['pool_date'].max().strftime('%Y-%m-%d')}"
    )

    min_date = pool_df["pool_date"].min().strftime("%Y%m%d")
    max_date = (pool_df["pool_date"].max() + timedelta(days=30)).strftime("%Y%m%d")
    trading_days = get_trading_days(min_date, max_date)

    all_stocks = set()
    for codes in pool_df["stock_list"]:
        all_stocks.update(codes)

    print(f"涉及股票: {len(all_stocks)} 只")

    print("\n获取历史数据...")
    stock_list = list(all_stocks)
    start_fetch = (
        datetime.strptime(min_date, "%Y%m%d") - timedelta(days=120)
    ).strftime("%Y%m%d")

    all_daily = []
    for i in range(0, len(stock_list), 100):
        batch = stock_list[i : i + 100]
        df = pro.daily(
            ts_code=",".join(batch), start_date=start_fetch, end_date=max_date
        )
        if df is not None and len(df) > 0:
            all_daily.append(df)
            print(f"  批次 {i // 100 + 1}: {len(df)} 条")

    if not all_daily:
        print("未获取到数据")
        return

    daily_df = pd.concat(all_daily, ignore_index=True)
    print(f"总共 {len(daily_df)} 条日线记录")

    print("\n计算评分并匹配次日涨跌...")
    all_results = []

    for idx, row in pool_df.iterrows():
        pool_date = row["pool_date"].strftime("%Y%m%d")
        ts_codes = row["stock_list"]

        prev_date = get_prev_trading_day(pool_date, trading_days)
        next_date = get_next_trading_day(pool_date, trading_days)

        if prev_date is None or next_date is None:
            continue

        next_data = daily_df[daily_df["trade_date"] == next_date]

        for code in ts_codes:
            stock_data = daily_df[daily_df["ts_code"] == code].copy()
            stock_data = stock_data[stock_data["trade_date"] < pool_date].sort_values(
                "trade_date"
            )

            if len(stock_data) < 5:
                continue

            score = calculate_score(stock_data)

            latest = stock_data.iloc[-1]

            next_row = next_data[next_data["ts_code"] == code]
            if len(next_row) == 0:
                continue

            next_pct = next_row.iloc[0]["pct_chg"]

            if score >= 50:
                risk_level = "低风险"
            elif score >= 35:
                risk_level = "中风险"
            else:
                risk_level = "高风险"

            all_results.append(
                {
                    "pool_date": pool_date,
                    "ts_code": code,
                    "prev_close": latest["close"],
                    "prev_pct_chg": latest["pct_chg"],
                    "score": score,
                    "risk_level": risk_level,
                    "next_date": next_date,
                    "next_pct_chg": next_pct,
                    "next_up": 1 if next_pct > 0 else 0,
                    "next_down": 1 if next_pct < 0 else 0,
                }
            )

    if not all_results:
        print("无有效数据")
        return

    result_df = pd.DataFrame(all_results)

    print("\n" + "=" * 80)
    print("一、评价目标")
    print("=" * 80)
    print("""
目标：在股票池公布的当天（T日），使用 T-1日及之前的技术指标，
      评估股票的风险等级，从而避免买入次日（T+1日）会下跌的股票。

核心约束：
1. 不能使用未来数据（T日及之后的数据）
2. 只能基于历史数据做出判断
3. 评估结果用于指导 T 日的买入决策
    """)

    print("\n" + "=" * 80)
    print("二、评价方式")
    print("=" * 80)
    print("""
评分公式（基础分 50 分）：

【加分项】
- RSI_6 < 30（超卖）: +10分
- KDJ_J < 20（超卖）: +10分
- MACD 金叉: +10分
- 连续下跌 >= 4天: +10分

【减分项】
- RSI_6 > 70（超买）: -15分
- KDJ_J > 80（超买）: -10分
- MACD 死叉: -10分
- 连续上涨 >= 4天: -10分

风险等级划分：
- 低风险: score >= 50
- 中风险: 35 <= score < 50
- 高风险: score < 35

技术指标含义：
- RSI_6: 6日相对强弱指标，衡量超买超卖
- KDJ_J: 随机指标J值，反映价格位置
- MACD: 指数平滑异同移动平均线，判断趋势
    """)

    print("\n" + "=" * 80)
    print("三、回测结果")
    print("=" * 80)

    total = len(result_df)
    print(f"\n总样本数: {total}")

    for risk in ["低风险", "中风险", "高风险"]:
        subset = result_df[result_df["risk_level"] == risk]
        if len(subset) == 0:
            continue

        up_count = subset["next_up"].sum()
        down_count = subset["next_down"].sum()
        avg_pct = subset["next_pct_chg"].mean()
        win_rate = up_count / len(subset) * 100

        print(f"\n【{risk}】({len(subset)} 只)")
        print(f"  次日上涨: {up_count} 只 ({win_rate:.1f}%)")
        print(f"  次日下跌: {down_count} 只 ({100 - win_rate:.1f}%)")
        print(f"  次日平均涨跌: {avg_pct:.2f}%")

    print("\n" + "=" * 80)
    print("四、区分度分析")
    print("=" * 80)

    low = result_df[result_df["risk_level"] == "低风险"]
    mid = result_df[result_df["risk_level"] == "中风险"]
    high = result_df[result_df["risk_level"] == "高风险"]

    if len(low) > 0 and len(high) > 0:
        low_win = low["next_up"].sum() / len(low) * 100
        high_win = high["next_up"].sum() / len(high) * 100
        low_avg = low["next_pct_chg"].mean()
        high_avg = high["next_pct_chg"].mean()

        print(
            f"\n低风险 vs 高风险 次日上涨率差异: {low_win:.1f}% - {high_win:.1f}% = {low_win - high_win:.1f}%"
        )
        print(
            f"低风险 vs 高风险 次日平均涨跌差异: {low_avg:.2f}% - {high_avg:.2f}% = {low_avg - high_avg:.2f}%"
        )

        if low_win > high_win and low_avg > high_avg:
            print("\n✅ 评分有效：低风险股票次日表现优于高风险股票")
        elif low_win < high_win and low_avg < high_avg:
            print("\n❌ 评分反向：低风险股票次日表现反而更差！")
        else:
            print("\n⚠️ 评分区分度有限：低风险和高风险表现接近")

    print("\n" + "=" * 80)
    print("五、详细统计")
    print("=" * 80)

    score_bins = [(0, 30), (30, 40), (40, 50), (50, 60), (60, 70), (70, 100)]
    print("\n按评分区间统计次日表现:")
    print(f"{'评分区间':<12} {'样本数':<10} {'上涨率':<12} {'平均涨跌':<12}")
    print("-" * 50)

    for low_s, high_s in score_bins:
        subset = result_df[
            (result_df["score"] >= low_s) & (result_df["score"] < high_s)
        ]
        if len(subset) == 0:
            continue
        win_rate = subset["next_up"].sum() / len(subset) * 100
        avg_pct = subset["next_pct_chg"].mean()
        print(
            f"{low_s}-{high_s:<10} {len(subset):<10} {win_rate:.1f}%{'':<6} {avg_pct:+.2f}%"
        )

    print("\n" + "=" * 80)
    print("六、结论与建议")
    print("=" * 80)

    low_avg_pct = low["next_pct_chg"].mean() if len(low) > 0 else 0
    mid_avg_pct = mid["next_pct_chg"].mean() if len(mid) > 0 else 0
    high_avg_pct = high["next_pct_chg"].mean() if len(high) > 0 else 0

    low_win_rate = low["next_up"].sum() / len(low) * 100 if len(low) > 0 else 50
    high_win_rate = high["next_up"].sum() / len(high) * 100 if len(high) > 0 else 50

    print(f"""
1. 当前评分方法的区分度: {abs(low_win_rate - high_win_rate):.1f}% (低风险上涨率 - 高风险上涨率)

2. 各风险等级次日平均涨跌:
   - 低风险: {low_avg_pct:+.2f}%
   - 中风险: {mid_avg_pct:+.2f}%
   - 高风险: {high_avg_pct:+.2f}%

3. 评估:
""")

    if abs(low_win_rate - high_win_rate) < 5:
        print("   ⚠️ 区分度不足：低风险和高风险股票的次日表现差异很小")
        print("   建议：需要优化评分公式或引入更多有效指标")
    elif low_win_rate < high_win_rate:
        print("   ❌ 评分反向：低风险股票表现反而不如高风险")
        print("   建议：需要重新审视评分逻辑")
    else:
        print("   ✅ 评分有一定区分度，但可能还需要优化")

    print("""
4. 改进建议:
   - 增加更多技术指标（如布林带、OBV等）
   - 考虑基本面因素（如PE、PB等）
   - 使用机器学习方法自动学习有效特征
   - 对不同市场环境（牛市/熊市）使用不同权重
    """)

    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    result_df.to_csv(
        output_dir / "backtest_screening.csv", index=False, encoding="utf-8-sig"
    )
    print(f"\n详细数据已保存: output/backtest_screening.csv")


if __name__ == "__main__":
    main()

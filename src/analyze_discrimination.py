"""
股票池次日涨跌区分度分析
核心：只用池子日及之前数据预测次日涨跌
"""

import tushare as ts
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional

from config import pro
from utils.common import get_trading_days, load_stock_pool, get_next_trading_day


def calc_rsi(close: pd.Series, period: int = 6) -> pd.Series:
    """计算RSI"""
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, np.inf)
    return 100 - (100 / (1 + rs))


def calc_kdj(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 9) -> dict:
    """计算KDJ"""
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
    """计算MACD"""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    macd = (dif - dea) * 2
    return {"macd": macd, "dif": dif, "dea": dea}


def extract_features(
    stock_data: pd.DataFrame, ts_code: str, pool_date: str
) -> Optional[dict]:
    """
    从股票历史数据提取特征（只用pool_date及之前的数据）
    """
    data = stock_data[stock_data["trade_date"] <= pool_date].copy()

    if len(data) < 20:
        return None

    data = data.sort_values("trade_date").reset_index(drop=True)
    latest = data.iloc[-1]

    close = data["close"]
    high = data["high"]
    low = data["low"]
    vol = data["vol"]
    pct_chg = data["pct_chg"]

    rsi_6 = calc_rsi(close, 6)
    rsi_12 = calc_rsi(close, 12)

    kdj = calc_kdj(high, low, close)

    macd_dict = calc_macd(close)

    ma_5 = close.rolling(5).mean()
    ma_10 = close.rolling(10).mean()
    ma_20 = close.rolling(20).mean()
    ma_60 = close.rolling(60).mean()

    vol_ma_5 = vol.rolling(5).mean()
    vol_ma_10 = vol.rolling(10).mean()

    bias_5 = (close - ma_5) / ma_5 * 100
    bias_10 = (close - ma_10) / ma_10 * 100

    high_20 = high.rolling(20).max()
    low_20 = low.rolling(20).min()
    price_pos_20 = (close - low_20) / (high_20 - low_20 + 1e-10)

    up_days_5 = sum(pct_chg.tail(5) > 0)
    up_days_10 = sum(pct_chg.tail(10) > 0)

    return {
        "ts_code": ts_code,
        "pool_date": pool_date,
        "close": latest["close"],
        "pct_chg": latest["pct_chg"],
        "rsi_6": round(rsi_6.iloc[-1], 2) if not pd.isna(rsi_6.iloc[-1]) else 50,
        "rsi_12": round(rsi_12.iloc[-1], 2) if not pd.isna(rsi_12.iloc[-1]) else 50,
        "kdj_k": round(kdj["k"].iloc[-1], 2) if not pd.isna(kdj["k"].iloc[-1]) else 50,
        "kdj_d": round(kdj["d"].iloc[-1], 2) if not pd.isna(kdj["d"].iloc[-1]) else 50,
        "kdj_j": round(kdj["j"].iloc[-1], 2) if not pd.isna(kdj["j"].iloc[-1]) else 50,
        "macd": round(macd_dict["macd"].iloc[-1], 4)
        if not pd.isna(macd_dict["macd"].iloc[-1])
        else 0,
        "macd_dif": round(macd_dict["dif"].iloc[-1], 4)
        if not pd.isna(macd_dict["dif"].iloc[-1])
        else 0,
        "macd_dea": round(macd_dict["dea"].iloc[-1], 4)
        if not pd.isna(macd_dict["dea"].iloc[-1])
        else 0,
        "ma_5": round(ma_5.iloc[-1], 2)
        if not pd.isna(ma_5.iloc[-1])
        else latest["close"],
        "ma_10": round(ma_10.iloc[-1], 2)
        if not pd.isna(ma_10.iloc[-1])
        else latest["close"],
        "ma_20": round(ma_20.iloc[-1], 2)
        if not pd.isna(ma_20.iloc[-1])
        else latest["close"],
        "close_above_ma5": 1 if latest["close"] > ma_5.iloc[-1] else 0,
        "close_above_ma10": 1 if latest["close"] > ma_10.iloc[-1] else 0,
        "close_above_ma20": 1 if latest["close"] > ma_20.iloc[-1] else 0,
        "ma5_above_ma10": 1 if ma_5.iloc[-1] > ma_10.iloc[-1] else 0,
        "ma10_above_ma20": 1 if ma_10.iloc[-1] > ma_20.iloc[-1] else 0,
        "bias_5": round(bias_5.iloc[-1], 2) if not pd.isna(bias_5.iloc[-1]) else 0,
        "bias_10": round(bias_10.iloc[-1], 2) if not pd.isna(bias_10.iloc[-1]) else 0,
        "price_pos_20": round(price_pos_20.iloc[-1], 4)
        if not pd.isna(price_pos_20.iloc[-1])
        else 0.5,
        "vol_ratio": round(latest["vol"] / vol_ma_5.iloc[-1], 2)
        if vol_ma_5.iloc[-1] > 0
        else 1,
        "vol_ma_ratio": round(vol_ma_5.iloc[-1] / vol_ma_10.iloc[-1], 2)
        if vol_ma_10.iloc[-1] > 0
        else 1,
        "up_days_5": up_days_5,
        "up_days_10": up_days_10,
        "pct_chg_1": round(pct_chg.iloc[-1], 2),
        "pct_chg_2": round(pct_chg.iloc[-2], 2) if len(pct_chg) > 1 else 0,
        "pct_chg_3": round(pct_chg.iloc[-3], 2) if len(pct_chg) > 2 else 0,
    }


def analyze_discrimination(df: pd.DataFrame) -> pd.DataFrame:
    """分析各特征对次日涨跌的区分度"""

    up = df[df["next_up"] == 1]
    down = df[df["next_down"] == 1]

    features = [
        "rsi_6",
        "rsi_12",
        "kdj_k",
        "kdj_d",
        "kdj_j",
        "macd",
        "macd_dif",
        "macd_dea",
        "close_above_ma5",
        "close_above_ma10",
        "close_above_ma20",
        "ma5_above_ma10",
        "ma10_above_ma20",
        "bias_5",
        "bias_10",
        "price_pos_20",
        "vol_ratio",
        "vol_ma_ratio",
        "up_days_5",
        "up_days_10",
        "pct_chg_1",
        "pct_chg_2",
        "pct_chg_3",
    ]

    results = []
    for f in features:
        if f not in df.columns:
            continue

        up_mean = up[f].mean()
        down_mean = down[f].mean()
        up_std = up[f].std()
        down_std = down[f].std()

        diff = up_mean - down_mean
        pooled_std = np.sqrt((up_std**2 + down_std**2) / 2)
        effect = abs(diff / pooled_std) if pooled_std > 0 else 0

        results.append(
            {
                "feature": f,
                "up_mean": round(up_mean, 3),
                "down_mean": round(down_mean, 3),
                "diff": round(diff, 3),
                "effect_size": round(effect, 3),
                "direction": "涨>跌" if diff > 0 else "跌>涨",
                "discrimination": "强"
                if effect > 0.3
                else ("中" if effect > 0.1 else "弱"),
            }
        )

    return pd.DataFrame(results).sort_values("effect_size", ascending=False)


def main():
    excel_path = Path(__file__).parent.parent / "assets" / "池子_20251104.xlsx"
    pool_df = load_stock_pool(str(excel_path), add_real_date=True, date_offset_months=3)

    print(f"股票池: {len(pool_df)} 个交易日")
    print(f"日期范围: {pool_df['real_date'].min()} ~ {pool_df['real_date'].max()}")

    min_date = pool_df["real_date"].min().strftime("%Y%m%d")
    max_date = (pool_df["real_date"].max() + timedelta(days=30)).strftime("%Y%m%d")
    trading_days = get_trading_days(min_date, max_date)
    print(f"交易日历: {len(trading_days)} 天")

    all_results = []
    all_stocks = set()
    for codes in pool_df["stock_list"]:
        all_stocks.update(codes)

    print(f"\n获取 {len(all_stocks)} 只股票的历史数据...")
    stock_list = list(all_stocks)

    all_daily = []
    for i in range(0, len(stock_list), 100):
        batch = stock_list[i : i + 100]
        start = (datetime.strptime(min_date, "%Y%m%d") - timedelta(days=120)).strftime(
            "%Y%m%d"
        )
        df = pro.daily(ts_code=",".join(batch), start_date=start, end_date=max_date)
        if df is not None and len(df) > 0:
            all_daily.append(df)
            print(f"  批次 {i // 100 + 1}: {len(df)} 条")

    if not all_daily:
        print("未获取到数据")
        return

    daily_df = pd.concat(all_daily, ignore_index=True)
    print(f"总共 {len(daily_df)} 条日线记录")

    print("\n提取特征并获取次日涨跌...")
    for idx, row in pool_df.iterrows():
        pool_date = row["real_date"].strftime("%Y%m%d")
        ts_codes = row["stock_list"]

        next_date = get_next_trading_day(pool_date, trading_days)
        if next_date is None:
            continue

        next_data = daily_df[daily_df["trade_date"] == next_date]

        for code in ts_codes:
            stock_data = daily_df[daily_df["ts_code"] == code]
            if len(stock_data) < 20:
                continue

            features = extract_features(stock_data, code, pool_date)
            if features is None:
                continue

            next_row = next_data[next_data["ts_code"] == code]
            if len(next_row) == 0:
                continue

            next_pct = next_row.iloc[0]["pct_chg"]
            features["next_pct_chg"] = round(next_pct, 4)
            features["next_up"] = 1 if next_pct > 0 else 0
            features["next_down"] = 1 if next_pct < 0 else 0

            all_results.append(features)

        print(
            f"  {row['pool_date'].strftime('%Y-%m-%d')} -> {next_date}: {len([r for r in all_results if r['pool_date'] == pool_date])} 只"
        )

    if not all_results:
        print("无有效数据")
        return

    result_df = pd.DataFrame(all_results)

    print("\n" + "=" * 80)
    print("次日涨跌统计")
    print("=" * 80)
    print(f"总样本: {len(result_df)}")
    print(
        f"次日上涨: {result_df['next_up'].sum()} ({result_df['next_up'].mean() * 100:.1f}%)"
    )
    print(
        f"次日下跌: {result_df['next_down'].sum()} ({result_df['next_down'].mean() * 100:.1f}%)"
    )
    print(f"次日平均涨跌: {result_df['next_pct_chg'].mean():.2f}%")

    print("\n" + "=" * 80)
    print("特征区分度分析（按effect_size降序）")
    print("=" * 80)
    analysis = analyze_discrimination(result_df)
    print(analysis.to_string())

    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    result_df.to_csv(
        output_dir / "feature_analysis.csv", index=False, encoding="utf-8-sig"
    )
    analysis.to_csv(
        output_dir / "discrimination_analysis.csv", index=False, encoding="utf-8-sig"
    )

    print("\n" + "=" * 80)
    print("结论：有区分度的特征")
    print("=" * 80)

    strong = analysis[analysis["discrimination"] == "强"]
    medium = analysis[analysis["discrimination"] == "中"]

    if len(strong) > 0:
        print("\n【强区分度】(effect_size > 0.3)")
        for _, r in strong.iterrows():
            print(
                f"  {r['feature']}: 涨股={r['up_mean']:.2f}, 跌股={r['down_mean']:.2f}, {r['direction']}, effect={r['effect_size']:.3f}"
            )

    if len(medium) > 0:
        print("\n【中区分度】(0.1 < effect_size <= 0.3)")
        for _, r in medium.iterrows():
            print(
                f"  {r['feature']}: 涨股={r['up_mean']:.2f}, 跌股={r['down_mean']:.2f}, {r['direction']}, effect={r['effect_size']:.3f}"
            )

    print(f"\n结果已保存:")
    print(f"  - output/feature_analysis.csv")
    print(f"  - output/discrimination_analysis.csv")


if __name__ == "__main__":
    main()

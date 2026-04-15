"""
生成训练数据集
整合日线特征和上午特征，匹配次日涨跌
"""

import tushare as ts
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional, Dict

from config import pro
from utils.common import get_trading_days, load_stock_pool, get_next_trading_day


def extract_daily_features(ts_code: str, daily_df: pd.DataFrame, eval_date: str) -> Optional[Dict]:
    """提取日线特征（使用eval_date之前的数据）"""
    data = daily_df[
        (daily_df["ts_code"] == ts_code) &
        (daily_df["trade_date"] <= eval_date)
    ].copy().sort_values("trade_date")

    if len(data) < 20:
        return None

    # 当日数据（T日，股票池筛选日）
    current_day = data.iloc[-1]

    # 历史数据（用于计算指标）
    hist_data = data.iloc[:-1] if len(data) > 1 else data

    close = hist_data["close"]
    high = hist_data["high"]
    low = hist_data["low"]
    vol = hist_data["vol"]
    pct_chg = hist_data["pct_chg"]

    # 基础特征
    features = {
        "ts_code": ts_code,
        "pool_date": eval_date,
        "close": current_day["close"],
        "open": current_day["open"],
        "high": current_day["high"],
        "low": current_day["low"],
        "pre_close": current_day["pre_close"],
        "pct_chg": current_day["pct_chg"],
        "vol": current_day["vol"],
        "amount": current_day.get("amount", 0),
    }

    # 技术指标
    if len(close) >= 5:
        ma_5 = close.tail(5).mean()
        features["ma_5"] = round(ma_5, 2)
        features["price_to_ma5"] = round((current_day["close"] / ma_5 - 1) * 100, 2)

    if len(close) >= 10:
        ma_10 = close.tail(10).mean()
        features["ma_10"] = round(ma_10, 2)
        features["ma5_above_ma10"] = 1 if features.get("ma_5", 0) > ma_10 else 0

    if len(close) >= 20:
        ma_20 = close.tail(20).mean()
        features["ma_20"] = round(ma_20, 2)
        features["price_pos_20"] = round(
            (current_day["close"] - close.tail(20).min()) / (close.tail(20).max() - close.tail(20).min() + 1e-10), 4
        )

    # RSI
    if len(close) >= 7:
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(6).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(6).mean()
        rs = gain / loss.replace(0, np.inf)
        rsi_6 = (100 - (100 / (1 + rs))).iloc[-1]
        features["rsi_6"] = round(rsi_6, 2) if not pd.isna(rsi_6) else 50

    # KDJ
    if len(close) >= 10:
        low_9 = low.tail(9).min()
        high_9 = high.tail(9).max()
        rsv = (current_day["close"] - low_9) / (high_9 - low_9 + 1e-10) * 100
        k = rsv
        d = rsv
        j = 3 * k - 2 * d
        features["kdj_k"] = round(k, 2)
        features["kdj_d"] = round(d, 2)
        features["kdj_j"] = round(j, 2)

    # 波动率
    if len(pct_chg) >= 5:
        features["volatility_5"] = round(pct_chg.tail(5).std(), 2)
    if len(pct_chg) >= 20:
        features["volatility_20"] = round(pct_chg.tail(20).std(), 2)

    # 涨跌统计
    if len(pct_chg) >= 5:
        features["up_days_5"] = int((pct_chg.tail(5) > 0).sum())
    if len(pct_chg) >= 10:
        features["up_days_10"] = int((pct_chg.tail(10) > 0).sum())

    # 开盘跳空特征（模拟上午特征）
    features["morning_gap_pct"] = round((current_day["open"] - current_day["pre_close"]) / current_day["pre_close"] * 100, 2)
    features["morning_return"] = round((current_day["close"] - current_day["pre_close"]) / current_day["pre_close"] * 100, 2)
    features["morning_max_up"] = round((current_day["high"] - current_day["open"]) / current_day["open"] * 100, 2)
    features["morning_max_down"] = round((current_day["low"] - current_day["open"]) / current_day["open"] * 100, 2)
    features["morning_range"] = round((current_day["high"] - current_day["low"]) / current_day["open"] * 100, 2)

    # 日内趋势
    if current_day["close"] > current_day["open"]:
        features["intraday_trend"] = 1  # 上涨
    elif current_day["close"] < current_day["open"]:
        features["intraday_trend"] = -1  # 下跌
    else:
        features["intraday_trend"] = 0  # 横盘

    return features


def build_dataset():
    """构建完整训练数据集"""

    excel_path = Path(__file__).parent.parent / "assets" / "池子_20251104.xlsx"
    pool_df = load_stock_pool(str(excel_path))

    print("="*80)
    print("训练数据集生成")
    print("="*80)
    print(f"\n股票池: {len(pool_df)} 个交易日")
    print(f"日期范围: {pool_df['pool_date'].min()} ~ {pool_df['pool_date'].max()}")

    # 获取交易日历
    min_date = pool_df["pool_date"].min().strftime("%Y%m%d")
    max_date = (pool_df["pool_date"].max() + timedelta(days=30)).strftime("%Y%m%d")
    trading_days = get_trading_days(min_date, max_date)

    # 收集所有股票
    all_stocks = set()
    for codes in pool_df["stock_list"]:
        all_stocks.update(codes)

    print(f"涉及股票: {len(all_stocks)} 只")

    # 获取日线数据（包含股票池日期当天）
    print("\n获取历史数据...")
    stock_list = list(all_stocks)
    start_fetch = (datetime.strptime(min_date, "%Y%m%d") - timedelta(days=60)).strftime("%Y%m%d")

    all_daily = []
    for i in range(0, len(stock_list), 100):
        batch = stock_list[i:i+100]
        df = pro.daily(ts_code=",".join(batch), start_date=start_fetch, end_date=max_date)
        if df is not None and len(df) > 0:
            all_daily.append(df)
        if (i // 100 + 1) % 5 == 0:
            print(f"  进度: {i+1}/{len(stock_list)}")

    daily_df = pd.concat(all_daily, ignore_index=True)
    print(f"总共 {len(daily_df)} 条日线记录")

    # 提取特征并匹配次日涨跌
    print("\n提取特征并匹配次日涨跌...")
    all_samples = []

    for idx, row in pool_df.iterrows():
        pool_date = row["pool_date"].strftime("%Y%m%d")
        ts_codes = row["stock_list"]

        # 获取下一个交易日
        next_date = get_next_trading_day(pool_date, trading_days)
        if next_date is None:
            continue

        # 获取次日涨跌数据
        next_data = daily_df[daily_df["trade_date"] == next_date]

        for code in ts_codes:
            # 提取特征
            features = extract_daily_features(code, daily_df, pool_date)
            if features is None:
                continue

            # 匹配次日涨跌
            next_row = next_data[next_data["ts_code"] == code]
            if len(next_row) == 0:
                continue

            next_pct = next_row.iloc[0]["pct_chg"]
            features["next_date"] = next_date
            features["next_pct_chg"] = round(next_pct, 4)
            features["next_up"] = 1 if next_pct > 0 else 0

            all_samples.append(features)

        if (idx + 1) % 10 == 0:
            print(f"  进度: {idx+1}/{len(pool_df)}")

    # 保存数据集
    result_df = pd.DataFrame(all_samples)

    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)

    result_df.to_csv(output_dir / "training_dataset.csv", index=False, encoding="utf-8-sig")

    print(f"\n{'='*80}")
    print(f"数据集生成完成!")
    print(f"{'='*80}")
    print(f"总样本数: {len(result_df)}")
    print(f"次日上涨: {result_df['next_up'].sum()} ({result_df['next_up'].mean()*100:.1f}%)")
    print(f"次日下跌: {len(result_df) - result_df['next_up'].sum()} ({(1-result_df['next_up'].mean())*100:.1f}%)")
    print(f"\n文件保存: output/training_dataset.csv")

    return result_df


if __name__ == "__main__":
    build_dataset()

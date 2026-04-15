"""
整合特征提取：日线特征 + 上午高频特征
用于预测股票池次日涨跌
"""

import tushare as ts
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from dataclasses import dataclass

from config import pro


@dataclass
class FeatureConfig:
    """特征提取配置"""
    use_morning_data: bool = True  # 是否使用上午高频数据
    morning_freq: str = "5min"     # 分钟频率
    daily_lookback: int = 20       # 日线回溯天数
    fallback_to_daily: bool = True # 没有分钟数据时是否用日线模拟


def get_daily_features(
    ts_code: str,
    daily_df: pd.DataFrame,
    eval_date: str
) -> Optional[Dict]:
    """
    提取日线特征（使用eval_date之前的数据）
    """
    # 只使用eval_date之前的数据
    data = daily_df[
        (daily_df["ts_code"] == ts_code) &
        (daily_df["trade_date"] < eval_date)
    ].copy().sort_values("trade_date")

    if len(data) < 20:
        return None

    close = data["close"]
    high = data["high"]
    low = data["low"]
    vol = data["vol"]
    pct_chg = data["pct_chg"]

    latest = data.iloc[-1]

    # 基础指标
    ma_5 = close.rolling(5).mean().iloc[-1]
    ma_10 = close.rolling(10).mean().iloc[-1]
    ma_20 = close.rolling(20).mean().iloc[-1]

    # 趋势
    trend_short = 1 if latest["close"] > ma_5 else 0
    trend_mid = 1 if latest["close"] > ma_10 else 0
    ma_alignment = 1 if ma_5 > ma_10 > ma_20 else 0

    # 波动率
    volatility_5 = pct_chg.tail(5).std()
    volatility_20 = pct_chg.tail(20).std()

    # 涨跌天数
    up_days_5 = (pct_chg.tail(5) > 0).sum()
    up_days_10 = (pct_chg.tail(10) > 0).sum()

    # 连涨/连跌
    consecutive_up = 0
    consecutive_down = 0
    for p in reversed(pct_chg.tolist()):
        if p > 0:
            consecutive_up += 1
            consecutive_down = 0
        elif p < 0:
            consecutive_down += 1
            consecutive_up = 0
        else:
            break

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(6).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(6).mean()
    rs = gain / loss.replace(0, np.inf)
    rsi_6 = (100 - (100 / (1 + rs))).iloc[-1]

    # KDJ
    low_9 = low.rolling(9).min()
    high_9 = high.rolling(9).max()
    rsv = (close - low_9) / (high_9 - low_9 + 1e-10) * 100
    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    j = 3 * k - 2 * d

    # 价格位置（20日区间）
    high_20 = high.tail(20).max()
    low_20 = low.tail(20).min()
    price_pos_20 = (latest["close"] - low_20) / (high_20 - low_20 + 1e-10)

    # 量比 (最近1日 vs 最近5日平均)
    vol_ma_5 = vol.tail(5).mean()
    volume_ratio = latest["vol"] / vol_ma_5 if vol_ma_5 > 0 else 1

    # 振幅
    amplitude = (latest["high"] - latest["low"]) / latest["open"] * 100

    return {
        # 基础价格
        "close": latest["close"],
        "pre_close": latest["pre_close"],
        "pct_chg": latest["pct_chg"],
        "amplitude": round(amplitude, 2),

        # 趋势
        "trend_short": trend_short,
        "trend_mid": trend_mid,
        "ma_alignment": ma_alignment,
        "price_to_ma5": round((latest["close"] / ma_5 - 1) * 100, 2) if ma_5 > 0 else 0,

        # 技术指标
        "rsi_6": round(rsi_6, 2) if not pd.isna(rsi_6) else 50,
        "kdj_k": round(k.iloc[-1], 2) if not pd.isna(k.iloc[-1]) else 50,
        "kdj_d": round(d.iloc[-1], 2) if not pd.isna(d.iloc[-1]) else 50,
        "kdj_j": round(j.iloc[-1], 2) if not pd.isna(j.iloc[-1]) else 50,
        "price_pos_20": round(price_pos_20, 4),

        # 波动率
        "volatility_5": round(volatility_5, 2) if not pd.isna(volatility_5) else 0,
        "volatility_20": round(volatility_20, 2) if not pd.isna(volatility_20) else 0,

        # 量价
        "volume_ratio": round(volume_ratio, 2),
        "up_days_5": int(up_days_5),
        "up_days_10": int(up_days_10),
        "consecutive_up": consecutive_up,
        "consecutive_down": consecutive_down,
    }


def simulate_morning_features_from_daily(
    daily_df: pd.DataFrame,
    ts_code: str,
    eval_date: str
) -> Optional[Dict]:
    """
    从日线数据模拟上午特征（当无法获取分钟数据时使用）

    假设：
    - 如果当日已经收盘，用当日数据模拟
    - 如果当日未收盘，基于前几日的早盘模式模拟
    """
    # 获取eval_date当天的数据（即T日，股票池筛选日）
    day_data = daily_df[
        (daily_df["ts_code"] == ts_code) &
        (daily_df["trade_date"] == eval_date)
    ]

    if len(day_data) == 0:
        return None

    latest = day_data.iloc[0]

    # 基于日线模拟上午特征
    open_price = latest["open"]
    close_price = latest["close"]
    pre_close = latest["pre_close"]
    high_price = latest["high"]
    low_price = latest["low"]

    # 开盘跳空
    gap_pct = (open_price - pre_close) / pre_close * 100

    # 假设上午占全天60%的波动，用中间价模拟上午收盘
    # 这是一个简化假设，实际应使用真实分钟数据
    simulated_morning_close = (open_price + close_price) / 2

    # 上午涨跌幅（假设值）
    morning_return = (simulated_morning_close - pre_close) / pre_close * 100
    morning_change = (simulated_morning_close - open_price) / open_price * 100

    # 最大涨跌幅假设
    max_up = (high_price - open_price) / open_price * 100
    max_down = (low_price - open_price) / open_price * 100

    # 假设上午振幅占全天60%
    morning_range = (high_price - low_price) / open_price * 100 * 0.6

    return {
        "morning_gap_pct": round(gap_pct, 2),
        "morning_return": round(morning_return, 2),
        "morning_change": round(morning_change, 2),
        "morning_max_up": round(max_up, 2),
        "morning_max_down": round(max_down, 2),
        "morning_range": round(morning_range, 2),
        "morning_volatility": 0,  # 无法从日线计算
        "morning_total_vol": 0,   # 无法从日线计算
        "morning_avg_vol": 0,
        "morning_close_position": 0.5,  # 默认中间位置
        "morning_first_half_return": round(morning_change / 2, 2),
        "morning_second_half_return": round(morning_change / 2, 2),
        "morning_trend_consistency": 0,
        "morning_last_30min_return": round(morning_change / 3, 2),
        "morning_vwap_deviation": 0,
        "morning_n_bars": 0,
        "data_source": "daily_simulated",
    }


def extract_all_features(
    ts_codes: List[str],
    pool_date: str,
    daily_df: pd.DataFrame,
    config: FeatureConfig = FeatureConfig()
) -> pd.DataFrame:
    """
    为股票池提取完整特征（日线 + 上午高频）

    Args:
        ts_codes: 股票代码列表
        pool_date: 股票池日期 (YYYYMMDD) - 当日中午筛选
        daily_df: 日线数据DataFrame（需包含pool_date当天数据）
        config: 特征提取配置
    """
    all_results = []

    for ts_code in ts_codes:
        # 1. 提取日线特征（使用pool_date之前的数据）
        daily_features = get_daily_features(ts_code, daily_df, pool_date)
        if daily_features is None:
            continue

        result = {"ts_code": ts_code, "pool_date": pool_date}
        result.update(daily_features)

        # 2. 提取或模拟上午特征
        if config.use_morning_data:
            # 尝试获取真实分钟数据
            from morning_features import get_morning_minutes, extract_morning_features

            min_df = get_morning_minutes(ts_code, pool_date, config.morning_freq)

            if min_df is not None:
                morning_features = extract_morning_features(min_df)
                if morning_features:
                    morning_features["data_source"] = "minute"
                    result.update(morning_features)
                elif config.fallback_to_daily:
                    simulated = simulate_morning_features_from_daily(daily_df, ts_code, pool_date)
                    if simulated:
                        result.update(simulated)
            elif config.fallback_to_daily:
                simulated = simulate_morning_features_from_daily(daily_df, ts_code, pool_date)
                if simulated:
                    result.update(simulated)

        all_results.append(result)

    return pd.DataFrame(all_results)


def build_training_dataset(
    pool_df: pd.DataFrame,
    daily_df: pd.DataFrame,
    trading_days: List[str],
    config: FeatureConfig = FeatureConfig()
) -> pd.DataFrame:
    """
    构建训练数据集：为每个股票池日期提取特征，并匹配次日涨跌

    Args:
        pool_df: 股票池DataFrame
        daily_df: 日线数据DataFrame
        trading_days: 交易日列表
        config: 特征配置
    """
    all_samples = []

    for idx, row in pool_df.iterrows():
        pool_date = row["real_date"].strftime("%Y%m%d")
        ts_codes = row["stock_list"]

        # 获取下一个交易日
        next_date = None
        for d in trading_days:
            if d > pool_date:
                next_date = d
                break

        if next_date is None:
            continue

        print(f"处理日期: {pool_date} -> 次日: {next_date}")

        # 提取特征（使用pool_date当天及之前数据）
        features_df = extract_all_features(ts_codes, pool_date, daily_df, config)

        if features_df.empty:
            continue

        # 获取次日涨跌数据
        next_day_data = daily_df[daily_df["trade_date"] == next_date]

        # 合并特征与次日涨跌
        for _, feat_row in features_df.iterrows():
            ts_code = feat_row["ts_code"]
            next_row = next_day_data[next_day_data["ts_code"] == ts_code]

            if len(next_row) > 0:
                next_pct = next_row.iloc[0]["pct_chg"]

                sample = feat_row.to_dict()
                sample["next_date"] = next_date
                sample["next_pct_chg"] = round(next_pct, 4)
                sample["next_up"] = 1 if next_pct > 0 else 0
                sample["next_down"] = 1 if next_pct < 0 else 0

                all_samples.append(sample)

        print(f"  有效样本: {len([s for s in all_samples if s.get('pool_date') == pool_date])}")

    return pd.DataFrame(all_samples)


if __name__ == "__main__":
    from analyze_discrimination import load_stock_pool, get_trading_days
    from datetime import timedelta

    # 测试
    excel_path = Path(__file__).parent.parent / "assets" / "池子_20251104.xlsx"
    pool_df = load_stock_pool(str(excel_path))

    # 获取交易日历
    min_date = pool_df["real_date"].min().strftime("%Y%m%d")
    max_date = (pool_df["real_date"].max() + timedelta(days=30)).strftime("%Y%m%d")
    trading_days = get_trading_days(min_date, max_date)

    # 获取日线数据
    all_stocks = set()
    for codes in pool_df["stock_list"]:
        all_stocks.update(codes)

    print(f"获取 {len(all_stocks)} 只股票的日线数据...")

    all_daily = []
    stock_list = list(all_stocks)
    start_fetch = (datetime.strptime(min_date, "%Y%m%d") - timedelta(days=120)).strftime("%Y%m%d")

    for i in range(0, len(stock_list), 100):
        batch = stock_list[i:i+100]
        df = pro.daily(ts_code=",".join(batch), start_date=start_fetch, end_date=max_date)
        if df is not None and len(df) > 0:
            all_daily.append(df)
            print(f"  批次 {i//100+1}: {len(df)} 条")

    daily_df = pd.concat(all_daily, ignore_index=True)
    print(f"\n总共 {len(daily_df)} 条日线记录")

    # 构建训练数据集
    print("\n构建训练数据集...")
    dataset = build_training_dataset(
        pool_df.head(5),  # 先测试前5天
        daily_df,
        trading_days,
        config=FeatureConfig(use_morning_data=True, fallback_to_daily=True)
    )

    print(f"\n数据集大小: {len(dataset)}")
    if len(dataset) > 0:
        print("\n特征预览:")
        print(dataset.head())

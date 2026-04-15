"""
上午高频行情特征提取模块
利用当日中午筛选前的上午分钟级行情数据提取特征

核心思路：
- 股票池是当日中午筛选出来的，可以获取当日上午（9:30-11:30）的高频数据
- 相比日线，分钟级数据包含更丰富的盘中信息
"""

import tushare as ts
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Tuple

from config import pro


def get_morning_minutes(
    ts_code: str, trade_date: str, freq: str = "5min"
) -> Optional[pd.DataFrame]:
    """
    获取股票当日上午分钟级行情数据

    Args:
        ts_code: 股票代码
        trade_date: 交易日期 (YYYYMMDD)
        freq: 分钟频率，支持 1min, 5min, 15min, 30min, 60min

    Returns:
        上午（9:30-11:30）的分钟级数据
    """
    try:
        # Tushare Pro 的分钟数据接口需要订阅权限
        # stk_mins 接口参数: ts_code, start_date, end_date, freq
        start_time = f"{trade_date} 09:30:00"
        end_time = f"{trade_date} 11:30:00"

        # 注意：实际调用需要足够的积分权限
        df = pro.stk_mins(
            ts_code=ts_code,
            start_date=start_time,
            end_date=end_time,
            freq=freq
        )

        if df is None or len(df) == 0:
            return None

        df = df.sort_values("trade_time").reset_index(drop=True)
        return df

    except Exception as e:
        # 如果没有权限或数据，返回None
        print(f"  获取分钟数据失败 {ts_code}: {e}")
        return None


def extract_morning_features(min_df: pd.DataFrame) -> Optional[Dict]:
    """
    从上午分钟级数据中提取特征

    特征列表：
    1. 开盘特征：开盘价相对前收盘的跳空幅度
    2. 涨跌幅：上午累计涨跌幅、最大涨幅、最大跌幅
    3. 成交量：上午成交量、每分钟平均成交量
    4. 波动率：上午振幅、波动率标准差
    5. 价格行为：最高/最低价出现时间、收盘相对位置
    6. 趋势：上午前半段vs后半段涨跌幅对比
    """
    if min_df is None or len(min_df) < 5:
        return None

    # 确保数据按时间排序
    df = min_df.copy()

    # 基础价格数据
    open_price = df["open"].iloc[0]  # 上午第一根K线开盘价（即当日开盘价）
    close_price = df["close"].iloc[-1]  # 上午最后一根K线收盘价
    high_price = df["high"].max()
    low_price = df["low"].min()
    pre_close = df.get("pre_close", open_price)  # 前收盘价

    # 1. 开盘跳空幅度 (%)
    gap_pct = (open_price - pre_close) / pre_close * 100 if pre_close > 0 else 0

    # 2. 上午累计涨跌幅 (%)
    morning_return = (close_price - pre_close) / pre_close * 100 if pre_close > 0 else 0
    morning_change = (close_price - open_price) / open_price * 100  # 从开盘到上午收盘

    # 3. 最大涨幅/最大跌幅 (相对开盘价)
    max_up = (high_price - open_price) / open_price * 100
    max_down = (low_price - open_price) / open_price * 100

    # 4. 上午振幅
    morning_range = (high_price - low_price) / open_price * 100

    # 5. 波动率 (收盘价变化的标准差)
    returns = df["close"].pct_change().dropna() * 100
    volatility = returns.std() if len(returns) > 1 else 0

    # 6. 成交量特征
    total_vol = df["vol"].sum() if "vol" in df.columns else 0
    avg_vol = df["vol"].mean() if "vol" in df.columns and len(df) > 0 else 0

    # 7. 价格位置特征（收盘在高低点区间的位置，0=最低点，1=最高点）
    if high_price != low_price:
        close_position = (close_price - low_price) / (high_price - low_price)
    else:
        close_position = 0.5

    # 8. 上午前后趋势对比（分两段）
    mid_idx = len(df) // 2
    first_half_return = (df["close"].iloc[mid_idx] - df["open"].iloc[0]) / df["open"].iloc[0] * 100
    second_half_return = (df["close"].iloc[-1] - df["open"].iloc[mid_idx]) / df["open"].iloc[mid_idx] * 100

    # 9. 趋势强度（前半段 vs 后半段）
    trend_consistency = 1 if first_half_return * second_half_return > 0 else -1

    # 10. 最后30分钟趋势（临近中午的表现）
    last_30min = df.tail(3) if len(df) >= 3 else df
    last_30min_return = (last_30min["close"].iloc[-1] - last_30min["open"].iloc[0]) / last_30min["open"].iloc[0] * 100

    # 11. Vwap 偏离度 (收盘价相对于成交量加权均价的位置)
    if "vol" in df.columns and total_vol > 0:
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        vwap = (typical_price * df["vol"]).sum() / total_vol
        vwap_deviation = (close_price - vwap) / vwap * 100
    else:
        vwap_deviation = 0

    return {
        "morning_gap_pct": round(gap_pct, 2),
        "morning_return": round(morning_return, 2),
        "morning_change": round(morning_change, 2),
        "morning_max_up": round(max_up, 2),
        "morning_max_down": round(max_down, 2),
        "morning_range": round(morning_range, 2),
        "morning_volatility": round(volatility, 4),
        "morning_total_vol": int(total_vol),
        "morning_avg_vol": round(avg_vol, 2),
        "morning_close_position": round(close_position, 4),
        "morning_first_half_return": round(first_half_return, 2),
        "morning_second_half_return": round(second_half_return, 2),
        "morning_trend_consistency": trend_consistency,
        "morning_last_30min_return": round(last_30min_return, 2),
        "morning_vwap_deviation": round(vwap_deviation, 2),
        "morning_n_bars": len(df),
    }


def get_daily_morning_features(
    ts_codes: List[str],
    trade_date: str,
    freq: str = "5min",
    use_fallback: bool = True
) -> pd.DataFrame:
    """
    批量获取多只股票当日上午的高频特征

    Args:
        ts_codes: 股票代码列表
        trade_date: 交易日期 (YYYYMMDD)
        freq: 分钟频率
        use_fallback: 如果没有分钟数据权限，是否使用日线数据模拟上午特征

    Returns:
        包含高频特征的DataFrame
    """
    all_features = []

    print(f"获取 {len(ts_codes)} 只股票的 {trade_date} 上午 {freq} 数据...")

    for i, code in enumerate(ts_codes):
        if (i + 1) % 10 == 0 or i == 0:
            print(f"  进度: {i+1}/{len(ts_codes)}")

        min_df = get_morning_minutes(code, trade_date, freq)

        if min_df is not None:
            features = extract_morning_features(min_df)
            if features:
                features["ts_code"] = code
                features["trade_date"] = trade_date
                features["data_source"] = "minute"
                all_features.append(features)
        else:
            # 如果没有分钟数据，标记为需要回退方案
            all_features.append({
                "ts_code": code,
                "trade_date": trade_date,
                "data_source": "none",
            })

    if not all_features:
        return pd.DataFrame()

    result_df = pd.DataFrame(all_features)

    # 统计成功率
    minute_count = (result_df["data_source"] == "minute").sum()
    print(f"\n数据获取统计:")
    print(f"  成功获取分钟数据: {minute_count}/{len(ts_codes)} ({minute_count/len(ts_codes)*100:.1f}%)")

    return result_df


def merge_with_daily_features(
    morning_df: pd.DataFrame,
    daily_features_df: pd.DataFrame
) -> pd.DataFrame:
    """
    将上午高频特征与日线特征合并
    """
    if morning_df.empty or daily_features_df.empty:
        return pd.DataFrame()

    # 合并数据
    merged = daily_features_df.merge(
        morning_df,
        on=["ts_code", "trade_date"],
        how="left",
        suffixes=("", "_morning")
    )

    return merged


def analyze_morning_features_discrimination(
    df: pd.DataFrame
) -> pd.DataFrame:
    """
    分析上午高频特征对次日涨跌的区分度

    类似于 analyze_discrimination.py，但专注于上午高频特征
    """
    if "next_up" not in df.columns:
        print("数据中没有次日涨跌信息，无法分析区分度")
        return pd.DataFrame()

    up = df[df["next_up"] == 1]
    down = df[df["next_up"] == 0]

    # 上午高频特征列表
    morning_features = [col for col in df.columns if col.startswith("morning_")]

    results = []
    for f in morning_features:
        if f not in df.columns or df[f].isna().all():
            continue

        up_mean = up[f].mean()
        down_mean = down[f].mean()
        up_std = up[f].std()
        down_std = down[f].std()

        diff = up_mean - down_mean
        pooled_std = np.sqrt((up_std**2 + down_std**2) / 2)
        effect = abs(diff / pooled_std) if pooled_std > 0 else 0

        results.append({
            "feature": f,
            "up_mean": round(up_mean, 3),
            "down_mean": round(down_mean, 3),
            "diff": round(diff, 3),
            "effect_size": round(effect, 3),
            "direction": "涨>跌" if diff > 0 else "跌>涨",
            "discrimination": "强" if effect > 0.3 else ("中" if effect > 0.1 else "弱"),
        })

    return pd.DataFrame(results).sort_values("effect_size", ascending=False)


def main():
    """
    测试上午高频特征提取
    """
    from analyze_discrimination import load_stock_pool

    excel_path = Path(__file__).parent.parent / "assets" / "池子_20251104.xlsx"
    pool_df = load_stock_pool(str(excel_path))

    # 取最近一个交易日进行测试
    latest = pool_df.iloc[0]
    trade_date = latest["real_date"].strftime("%Y%m%d")
    ts_codes = latest["stock_list"][:10]  # 先测试前10只

    print(f"测试日期: {trade_date}")
    print(f"测试股票: {ts_codes}")

    # 获取上午高频特征
    morning_df = get_daily_morning_features(ts_codes, trade_date, freq="5min")

    if not morning_df.empty:
        print("\n上午高频特征预览:")
        print(morning_df[["ts_code", "morning_return", "morning_range", "morning_volatility"]].to_string())

    return morning_df


if __name__ == "__main__":
    main()

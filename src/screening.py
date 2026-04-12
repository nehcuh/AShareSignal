"""
股票池二次筛选工具
使用 Tushare API 获取多维度数据，辅助判断次日涨停/跌停风险

重要：为了避免未来数据泄露，评估某日股票时，只使用该日前一天及之前的数据
"""

import tushare as ts
import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timedelta

TUSHARE_TOKEN = "fd6cf8fc8404cf6f93ca6091c1e603d9bc3a65f5a536c77dbb882e60"
ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()

_trading_days_cache = None


def get_trading_days(start_date: str, end_date: str) -> List[str]:
    """获取交易日列表（带缓存）"""
    global _trading_days_cache
    if _trading_days_cache is None:
        cal = pro.trade_cal(exchange="SSE", start_date=start_date, end_date=end_date)
        _trading_days_cache = sorted(cal[cal["is_open"] == 1]["cal_date"].tolist())
    return _trading_days_cache


def get_prev_trading_day(trade_date: str, trading_days: List[str]) -> Optional[str]:
    """获取前一个交易日"""
    for i, d in enumerate(trading_days):
        if d == trade_date and i > 0:
            return trading_days[i - 1]
    for d in reversed(trading_days):
        if d < trade_date:
            return d
    return None


def load_stock_pool(excel_path: str) -> pd.DataFrame:
    """加载股票池Excel文件"""
    df = pd.read_excel(excel_path)
    df["pool_date"] = pd.to_datetime(df["pool_date"])
    df["stock_list"] = df["pool_data"].str.split(",")
    return df


def get_daily_data(
    ts_codes: List[str], start_date: str, end_date: str
) -> Optional[pd.DataFrame]:
    """获取日线行情数据"""
    try:
        all_data = []
        for i in range(0, len(ts_codes), 100):
            batch = ts_codes[i : i + 100]
            df = pro.daily(
                ts_code=",".join(batch), start_date=start_date, end_date=end_date
            )
            if df is not None and len(df) > 0:
                all_data.append(df)

        if all_data:
            return pd.concat(all_data, ignore_index=True)
        return None
    except Exception as e:
        print(f"获取日线数据失败: {e}")
        return None


def get_daily_basic(
    ts_codes: List[str], start_date: str, end_date: str
) -> Optional[pd.DataFrame]:
    """获取每日指标数据（PE、PB、换手率等）"""
    try:
        all_data = []
        for i in range(0, len(ts_codes), 100):
            batch = ts_codes[i : i + 100]
            df = pro.daily_basic(
                ts_code=",".join(batch), start_date=start_date, end_date=end_date
            )
            if df is not None and len(df) > 0:
                all_data.append(df)

        if all_data:
            return pd.concat(all_data, ignore_index=True)
        return None
    except Exception as e:
        print(f"获取每日指标失败: {e}")
        return None


def get_moneyflow(ts_codes: List[str], trade_date: str) -> Optional[pd.DataFrame]:
    """获取个股资金流向"""
    try:
        all_data = []
        for i in range(0, len(ts_codes), 100):
            batch = ts_codes[i : i + 100]
            df = pro.moneyflow(ts_code=",".join(batch), trade_date=trade_date)
            if df is not None and len(df) > 0:
                all_data.append(df)

        if all_data:
            return pd.concat(all_data, ignore_index=True)
        return None
    except Exception as e:
        print(f"获取资金流向失败: {e}")
        return None


def calculate_rsi(prices: pd.Series, period: int = 6) -> pd.Series:
    """计算RSI指标"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_kdj(
    high: pd.Series, low: pd.Series, close: pd.Series, n: int = 9
) -> dict:
    """计算KDJ指标"""
    low_n = low.rolling(window=n).min()
    high_n = high.rolling(window=n).max()
    rsv = (close - low_n) / (high_n - low_n) * 100

    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    j = 3 * k - 2 * d

    return {"k": k, "d": d, "j": j}


def calculate_macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> dict:
    """计算MACD指标"""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    macd = (dif - dea) * 2

    return {"macd": macd, "dif": dif, "dea": dea}


def calculate_screening_score(
    daily_df: pd.DataFrame,
    basic_df: Optional[pd.DataFrame] = None,
    moneyflow_df: Optional[pd.DataFrame] = None,
    eval_date: Optional[str] = None,
) -> pd.DataFrame:
    """
    计算筛选得分

    Args:
        daily_df: 日线数据
        basic_df: 每日指标数据
        moneyflow_df: 资金流向数据
        eval_date: 评估日期 (YYYYMMDD)，只使用该日期前一天及之前的数据计算指标
                   如果为 None，则使用数据中最新日期（注意：可能包含未来数据）

    筛选逻辑:
    1. RSI_6 < 30 超卖可能反弹, > 70 超买风险高
    2. KDJ J值 > 80 超买风险，< 20 超卖可能反弹
    3. MACD 金叉/死叉信号
    4. 换手率过高(>15%)风险大
    5. 量比 > 3 异常放量
    6. 连续上涨/下跌天数
    7. 主力资金净流入为正加分
    """
    if daily_df is None or len(daily_df) == 0:
        return pd.DataFrame()

    results = []

    for ts_code in daily_df["ts_code"].unique():
        stock_data = daily_df[daily_df["ts_code"] == ts_code].sort_values("trade_date")

        if eval_date:
            stock_data = stock_data[stock_data["trade_date"] < eval_date].copy()

        if len(stock_data) < 5:
            continue

        latest = stock_data.iloc[-1]

        close = stock_data["close"]
        high = stock_data["high"]
        low = stock_data["low"]

        rsi = calculate_rsi(close)
        kdj = calculate_kdj(high, low, close)
        macd = calculate_macd(close)

        rsi_val = rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50
        kdj_j = kdj["j"].iloc[-1] if not pd.isna(kdj["j"].iloc[-1]) else 50
        kdj_k = kdj["k"].iloc[-1] if not pd.isna(kdj["k"].iloc[-1]) else 50
        kdj_d = kdj["d"].iloc[-1] if not pd.isna(kdj["d"].iloc[-1]) else 50
        macd_val = macd["macd"].iloc[-1] if not pd.isna(macd["macd"].iloc[-1]) else 0
        macd_dif = macd["dif"].iloc[-1] if not pd.isna(macd["dif"].iloc[-1]) else 0
        macd_dea = macd["dea"].iloc[-1] if not pd.isna(macd["dea"].iloc[-1]) else 0

        pct_chg = stock_data["pct_chg"]
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
            len(macd["dif"]) > 1
            and macd["dif"].iloc[-1] > macd["dea"].iloc[-1]
            and macd["dif"].iloc[-2] <= macd["dea"].iloc[-2]
        ):
            score += 10
        elif (
            len(macd["dif"]) > 1
            and macd["dif"].iloc[-1] < macd["dea"].iloc[-1]
            and macd["dif"].iloc[-2] >= macd["dea"].iloc[-2]
        ):
            score -= 10

        if up_days >= 4:
            score -= 10
        elif down_days >= 4:
            score += 10

        row = {
            "ts_code": ts_code,
            "trade_date": latest["trade_date"],
            "close": latest["close"],
            "pct_chg": latest["pct_chg"],
            "vol": latest["vol"],
            "amount": latest["amount"],
            "rsi_6": round(rsi_val, 2),
            "kdj_k": round(kdj_k, 2),
            "kdj_d": round(kdj_d, 2),
            "kdj_j": round(kdj_j, 2),
            "macd": round(macd_val, 4),
            "macd_dif": round(macd_dif, 4),
            "macd_dea": round(macd_dea, 4),
            "up_days_5": up_days,
            "down_days_5": down_days,
            "score": score,
            "risk_level": "高风险"
            if score < 35
            else ("中风险" if score < 50 else "低风险"),
        }

        results.append(row)

    result_df = pd.DataFrame(results)

    if basic_df is not None and len(basic_df) > 0:
        trade_date = result_df["trade_date"].iloc[0]
        basic_latest = basic_df[basic_df["trade_date"] == trade_date]

        if len(basic_latest) > 0:
            result_df = result_df.merge(
                basic_latest[
                    [
                        "ts_code",
                        "pe",
                        "pb",
                        "turnover_rate",
                        "volume_ratio",
                        "total_mv",
                        "circ_mv",
                    ]
                ],
                on="ts_code",
                how="left",
            )

            result_df.loc[result_df["turnover_rate"] > 20, "score"] -= 10
            result_df.loc[result_df["volume_ratio"] > 3, "score"] -= 5

            result_df["risk_level"] = result_df["score"].apply(
                lambda x: "高风险" if x < 35 else ("中风险" if x < 50 else "低风险")
            )

    if moneyflow_df is not None and len(moneyflow_df) > 0:
        result_df = result_df.merge(
            moneyflow_df[["ts_code", "buy_elg_vol", "sell_elg_vol", "net_mf_vol"]],
            on="ts_code",
            how="left",
        )
        result_df.loc[result_df["net_mf_vol"] > 0, "score"] += 5
        result_df["risk_level"] = result_df["score"].apply(
            lambda x: "高风险" if x < 35 else ("中风险" if x < 50 else "低风险")
        )

    return result_df.sort_values("score", ascending=False)


def screen_stocks_for_date(
    ts_codes: List[str], trade_date: str, lookback_days: int = 30
) -> pd.DataFrame:
    """
    对指定日期的股票池进行筛选

    重要：只使用 trade_date 前一天及之前的数据计算指标，避免未来数据泄露！

    Args:
        ts_codes: 股票代码列表
        trade_date: 交易日期 (YYYYMMDD)，即计划买入的日期
        lookback_days: 回溯天数（用于计算技术指标）
    """
    print(f"\n筛选日期: {trade_date}, 股票数量: {len(ts_codes)}")

    min_start = (
        datetime.strptime(trade_date, "%Y%m%d") - timedelta(days=lookback_days * 3)
    ).strftime("%Y%m%d")
    trading_days = get_trading_days(min_start, trade_date)

    prev_date = get_prev_trading_day(trade_date, trading_days)
    if prev_date is None:
        print("无法获取前一交易日")
        return pd.DataFrame()

    print(f"使用数据截止日期: {prev_date} (前一交易日，避免未来数据泄露)")

    start_date = (
        datetime.strptime(prev_date, "%Y%m%d") - timedelta(days=lookback_days * 2)
    ).strftime("%Y%m%d")

    print("获取日线数据...")
    daily_df = get_daily_data(ts_codes, start_date, prev_date)

    if daily_df is None or len(daily_df) == 0:
        print("未获取到日线数据")
        return pd.DataFrame()

    print(f"获取到 {len(daily_df)} 条日线记录")

    print("获取每日指标...")
    basic_df = get_daily_basic(ts_codes, start_date, prev_date)
    if basic_df is not None:
        print(f"获取到 {len(basic_df)} 条指标记录")

    print("计算筛选得分（只使用前一天及之前的数据）...")
    result = calculate_screening_score(daily_df, basic_df, eval_date=trade_date)

    if len(result) > 0:
        result["target_date"] = trade_date

    return result


def main():
    excel_path = Path(__file__).parent.parent / "assets" / "池子_20251104.xlsx"
    pool_df = load_stock_pool(str(excel_path))

    print(f"加载股票池: {len(pool_df)} 个交易日")
    print(f"日期范围: {pool_df['pool_date'].min()} - {pool_df['pool_date'].max()}")

    latest = pool_df.iloc[0]
    trade_date = latest["pool_date"].strftime("%Y%m%d")
    ts_codes = latest["stock_list"]

    result = screen_stocks_for_date(ts_codes, trade_date)

    if len(result) > 0:
        print("\n" + "=" * 80)
        print("筛选结果")
        print("=" * 80)

        print(f"\n【低风险股票】({len(result[result['risk_level'] == '低风险'])} 只):")
        low_risk = result[result["risk_level"] == "低风险"][
            [
                "ts_code",
                "close",
                "pct_chg",
                "score",
                "rsi_6",
                "kdj_j",
                "up_days_5",
                "down_days_5",
            ]
        ]
        if len(low_risk) > 0:
            print(low_risk.head(10).to_string())

        print(f"\n【高风险股票】({len(result[result['risk_level'] == '高风险'])} 只):")
        high_risk = result[result["risk_level"] == "高风险"][
            [
                "ts_code",
                "close",
                "pct_chg",
                "score",
                "rsi_6",
                "kdj_j",
                "up_days_5",
                "down_days_5",
            ]
        ]
        if len(high_risk) > 0:
            print(high_risk.head(10).to_string())

        print(f"\n【中风险股票】({len(result[result['risk_level'] == '中风险'])} 只)")

        output_path = (
            Path(__file__).parent.parent / "output" / f"screening_{trade_date}.csv"
        )
        output_path.parent.mkdir(exist_ok=True)
        result.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"\n完整结果已保存: {output_path}")

        print(f"\n统计:")
        print(f"  总股票数: {len(result)}")
        print(f"  低风险: {len(result[result['risk_level'] == '低风险'])} 只")
        print(f"  中风险: {len(result[result['risk_level'] == '中风险'])} 只")
        print(f"  高风险: {len(result[result['risk_level'] == '高风险'])} 只")

    return result


if __name__ == "__main__":
    main()

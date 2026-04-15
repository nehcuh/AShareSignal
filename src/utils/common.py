"""
AShareSignal 公共工具函数
提取自各模块中重复定义的通用逻辑
"""

import numpy as np
import pandas as pd
from typing import List, Optional
from pathlib import Path

from config import get_tushare_pro, STOCK_POOL_EXCEL

# =============================================================================
# Trading days
# =============================================================================
_trading_days_cache = {}


def get_trading_days(start_date: str, end_date: str) -> List[str]:
    """获取交易日列表（带缓存）"""
    global _trading_days_cache
    cache_key = f"{start_date}_{end_date}"
    if cache_key not in _trading_days_cache:
        pro = get_tushare_pro()
        cal = pro.trade_cal(exchange="SSE", start_date=start_date, end_date=end_date)
        _trading_days_cache[cache_key] = sorted(
            cal[cal["is_open"] == 1]["cal_date"].tolist()
        )
    return _trading_days_cache[cache_key]


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


# =============================================================================
# Stock filtering
# =============================================================================
def is_main_board(ts_code: str) -> bool:
    """
    判断是否为主板股票
    主板：000XXX、002XXX、001XXX（深圳），600XXX、601XXX、603XXX、605XXX（上海）
    排除：688XXX（科创板）、300XXX、301XXX（创业板）、8XXXXX、430XXX（北交所）
    """
    code = ts_code.split(".")[0]

    if code.startswith("688"):
        return False
    if code.startswith("300") or code.startswith("301"):
        return False
    if code.startswith("8") or code.startswith("430"):
        return False
    if (
        code.startswith("000")
        or code.startswith("001")
        or code.startswith("002")
        or code.startswith("003")
        or code.startswith("600")
        or code.startswith("601")
        or code.startswith("603")
        or code.startswith("605")
    ):
        return True
    return False


def is_st_stock(name: str) -> bool:
    """判断是否为ST股票"""
    if not name:
        return False
    name = str(name).upper()
    return "ST" in name or "*ST" in name or "退" in name


# =============================================================================
# Stock pool loading
# =============================================================================
def load_stock_pool(
    excel_path: Optional[str] = None,
    add_real_date: bool = False,
    date_offset_months: int = 0,
) -> pd.DataFrame:
    """
    加载股票池Excel文件

    Args:
        excel_path: Excel路径，默认使用 config.STOCK_POOL_EXCEL
        add_real_date: 是否添加 real_date 列
        date_offset_months: real_date 相对于 pool_date 的偏移月数
    """
    path = Path(excel_path) if excel_path else STOCK_POOL_EXCEL
    df = pd.read_excel(path)
    df["pool_date"] = pd.to_datetime(df["pool_date"])
    df["stock_list"] = df["pool_data"].str.split(",")
    if add_real_date:
        if date_offset_months:
            df["real_date"] = df["pool_date"] + pd.DateOffset(months=date_offset_months)
        else:
            df["real_date"] = df["pool_date"]
    return df


# =============================================================================
# Technical indicators (from backtest_screening.py)
# =============================================================================
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


def calculate_backtest_score(stock_data: pd.DataFrame) -> int:
    """计算评分（只用前一天及之前的数据）—— Champion Baseline 评分逻辑"""
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

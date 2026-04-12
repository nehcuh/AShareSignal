"""
新浪财经分钟数据获取模块
使用 akshare + 新浪财经获取实时分钟数据

优势：
- 无需 API Key
- 无调用次数限制
- 可获取当天数据
- 适合中午筛选后的下午交易
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, time
from typing import List, Optional, Dict
import pickle
import os

# 禁用代理
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'

import akshare as ak


class SinaMinuteManager:
    """新浪财经分钟数据管理器"""

    def __init__(self, cache_dir: str = "data/sina_minute_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.request_count = 0

    def _get_cache_path(self, ts_code: str, trade_date: str) -> Path:
        """获取缓存路径"""
        code_clean = ts_code.replace('.', '_')
        return self.cache_dir / f"{code_clean}_{trade_date}.pkl"

    def _ts_code_to_sina_symbol(self, ts_code: str) -> str:
        """
        转换为新浪财经代码格式
        000001.SZ -> sz000001
        600000.SH -> sh600000
        """
        code = ts_code.split('.')[0]
        if '.SZ' in ts_code:
            return f"sz{code}"
        elif '.SH' in ts_code:
            return f"sh{code}"
        return code

    def download_minute_data(
        self,
        ts_code: str,
        trade_date: str = None,
        freq: str = "5",
        use_cache: bool = True
    ) -> Optional[pd.DataFrame]:
        """
        下载分钟数据

        Args:
            ts_code: 股票代码 (如 "000001.SZ")
            trade_date: 交易日期 (YYYYMMDD)，None则使用当天
            freq: 分钟频率 ("1", "5", "15", "30", "60")
            use_cache: 是否使用缓存

        Returns:
            包含分钟数据的 DataFrame
        """
        # 默认使用当天日期
        if trade_date is None:
            trade_date = datetime.now().strftime('%Y%m%d')

        # 检查缓存
        cache_path = self._get_cache_path(ts_code, trade_date)
        if use_cache and cache_path.exists():
            with open(cache_path, 'rb') as f:
                return pickle.load(f)

        try:
            symbol = self._ts_code_to_sina_symbol(ts_code)

            print(f"  从新浪财经获取 {ts_code} {trade_date} {freq}分钟数据...")

            # 使用新浪财经接口获取分钟数据
            df = ak.stock_zh_a_minute(symbol=symbol, period=freq, adjust="qfq")

            self.request_count += 1

            if df is None or len(df) == 0:
                print(f"    无数据返回")
                return None

            # 重命名列
            df = df.rename(columns={
                'day': 'datetime',
                'open': 'open',
                'high': 'high',
                'low': 'low',
                'close': 'close',
                'volume': 'vol',
                'amount': 'amount'
            })

            # 转换数值类型
            for col in ['open', 'high', 'low', 'close', 'vol', 'amount']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            # 解析日期时间
            df['datetime'] = pd.to_datetime(df['datetime'])
            df['date'] = df['datetime'].dt.strftime('%Y%m%d')
            df['time'] = df['datetime'].dt.time

            # 筛选指定日期
            df = df[df['date'] == trade_date].copy()

            if len(df) == 0:
                print(f"    无 {trade_date} 的数据")
                return None

            # 筛选上午交易时间 (09:30-11:30)
            morning_df = df[
                (df['time'] >= time(9, 30)) &
                (df['time'] <= time(11, 30))
            ].copy()

            if len(morning_df) == 0:
                print(f"    无上午交易数据")
                return None

            # 计算前收盘价（从第一根K线的涨跌幅反推）
            first_close = morning_df['close'].iloc[0]
            # 新浪数据没有直接提供pre_close，我们用open近似
            morning_df['pre_close'] = morning_df['open'].iloc[0]

            print(f"    成功获取 {len(morning_df)} 条上午记录")

            # 保存缓存
            if use_cache:
                with open(cache_path, 'wb') as f:
                    pickle.dump(morning_df, f)

            return morning_df

        except Exception as e:
            print(f"    获取失败: {e}")
            return None

    def download_batch(
        self,
        ts_codes: List[str],
        trade_date: str = None,
        freq: str = "5",
        delay: float = 0.3
    ) -> Dict[str, pd.DataFrame]:
        """
        批量下载分钟数据

        Args:
            ts_codes: 股票代码列表
            trade_date: 交易日期
            freq: 分钟频率
            delay: 请求间隔（避免过快）

        Returns:
            Dict[股票代码, DataFrame]
        """
        import time

        if trade_date is None:
            trade_date = datetime.now().strftime('%Y%m%d')

        results = {}

        print(f"\n使用新浪财经下载 {len(ts_codes)} 只股票 {trade_date} 的 {freq}分钟数据...")

        for i, code in enumerate(ts_codes):
            print(f"\n[{i+1}/{len(ts_codes)}] {code}")

            df = self.download_minute_data(code, trade_date, freq)
            if df is not None and len(df) > 0:
                results[code] = df

            # 添加延迟
            if delay > 0 and i < len(ts_codes) - 1:
                time.sleep(delay)

        print(f"\n完成: 成功下载 {len(results)}/{len(ts_codes)} 只股票")
        print(f"总请求次数: {self.request_count}")

        return results

    def get_cache_stats(self) -> Dict:
        """获取缓存统计"""
        files = list(self.cache_dir.glob("*.pkl"))
        total_size = sum(f.stat().st_size for f in files)
        return {
            "total_files": len(files),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "cache_dir": str(self.cache_dir)
        }


def extract_sina_morning_features(df: pd.DataFrame) -> Optional[Dict]:
    """
    从新浪财经分钟数据中提取上午特征
    """
    if df is None or len(df) < 3:
        return None

    df = df.sort_values("datetime").reset_index(drop=True)

    # 基础数据
    first_bar = df.iloc[0]
    last_bar = df.iloc[-1]

    open_price = first_bar["open"]
    close_price = last_bar["close"]
    high_price = df["high"].max()
    low_price = df["low"].min()
    pre_close = first_bar.get("pre_close", open_price)

    features = {
        "data_source": "sina_minute",
        "morning_open": float(open_price),
        "morning_pre_close": float(pre_close),
        "morning_gap_pct": round((open_price - pre_close) / pre_close * 100, 4),
        "morning_return": round((close_price - pre_close) / pre_close * 100, 4),
        "morning_change": round((close_price - open_price) / open_price * 100, 4),
        "morning_max_up": round((high_price - open_price) / open_price * 100, 4),
        "morning_max_down": round((low_price - open_price) / open_price * 100, 4),
        "morning_range": round((high_price - low_price) / open_price * 100, 4),
        "morning_close": float(close_price),
        "morning_high": float(high_price),
        "morning_low": float(low_price),
        "n_bars": len(df),
    }

    # 波动率
    if len(df) >= 3:
        df['bar_return'] = df['close'].pct_change()
        features["morning_volatility"] = round(df['bar_return'].std() * 100, 4)

    # 成交量
    if "vol" in df.columns:
        features["morning_total_vol"] = int(df["vol"].sum())
        features["morning_avg_vol"] = round(df["vol"].mean(), 2)

        # 成交量分布
        mid_idx = len(df) // 2
        first_half_vol = df.iloc[:mid_idx]["vol"].sum()
        second_half_vol = df.iloc[mid_idx:]["vol"].sum()
        features["vol_distribution"] = round(second_half_vol / (first_half_vol + 1e-10), 4)

    # 成交额
    if "amount" in df.columns:
        features["morning_total_amount"] = float(df["amount"].sum())

    # 价格位置
    if high_price != low_price:
        features["close_position"] = round((close_price - low_price) / (high_price - low_price), 4)
    else:
        features["close_position"] = 0.5

    # VWAP
    if "vol" in df.columns and df["vol"].sum() > 0:
        total_vol = df["vol"].sum()
        vwap = (df["close"] * df["vol"]).sum() / total_vol
        features["vwap"] = round(float(vwap), 4)
        features["vwap_deviation"] = round((close_price - vwap) / vwap * 100, 4)

    # 分时趋势
    if len(df) >= 6:
        first_30_close = df.iloc[min(5, len(df)//2 - 1)]["close"]
        last_30_close = df.iloc[-1]["close"]
        last_30_open = df.iloc[max(len(df)//2, 0)]["open"]

        features["first_30_return"] = round((first_30_close - open_price) / open_price * 100, 4)
        features["last_30_return"] = round((last_30_close - last_30_open) / last_30_open * 100, 4)

    # 极值点时间
    high_idx = df["high"].idxmax()
    low_idx = df["low"].idxmin()
    features["high_time_position"] = round(high_idx / len(df), 4)
    features["low_time_position"] = round(low_idx / len(df), 4)

    # 涨跌统计
    features["up_bars"] = int((df['close'] > df['open']).sum())
    features["down_bars"] = int((df['close'] < df['open']).sum())

    return features


def test_sina_minute():
    """测试新浪财经分钟数据获取"""
    print("="*80)
    print("新浪财经分钟数据测试")
    print("="*80)

    manager = SinaMinuteManager()

    # 测试股票
    test_codes = ["000001.SZ", "000002.SZ", "600519.SH"]

    # 使用今天日期
    today = datetime.now().strftime('%Y%m%d')
    print(f"当前日期: {today}")

    print(f"\n下载 {today} 上午数据...")

    results = manager.download_batch(test_codes, trade_date=today, freq="5", delay=0.5)

    print(f"\n\n结果汇总:")
    for code, df in results.items():
        print(f"\n{code}: {len(df)} 条记录")
        print(df[['datetime', 'open', 'high', 'low', 'close', 'vol']].head())

        # 提取特征
        features = extract_sina_morning_features(df)
        if features:
            print(f"\n  提取的特征:")
            for k, v in list(features.items())[:10]:
                print(f"    {k}: {v}")

    # 缓存统计
    stats = manager.get_cache_stats()
    print(f"\n\n缓存统计: {stats}")

    return results


if __name__ == "__main__":
    test_sina_minute()

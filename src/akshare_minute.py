"""
akshare 分钟数据获取模块 - Curl 备用方案
使用 curl 获取东方财富分钟数据（绕过 Python requests 限制）
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional, Dict
import pickle
import time
import os
import json
import subprocess


def get_minute_data_via_curl(symbol: str, period: str = "5", start_date: str = None, end_date: str = None) -> Optional[pd.DataFrame]:
    """
    使用 curl 获取分钟数据

    Args:
        symbol: 股票代码 (如 '000001')
        period: 周期 ('1', '5', '15', '30', '60')
        start_date: 开始日期 (YYYYMMDD)
        end_date: 结束日期 (YYYYMMDD)
    """
    # 判断市场
    if symbol.startswith('6'):
        secid = f"1.{symbol}"  # 上海
    else:
        secid = f"0.{symbol}"  # 深圳

    # 构建 URL
    url = (
        f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?fields1=f1,f2,f3,f4,f5,f6"
        f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
        f"&ut=7eea3edcaed734bea9cbfc24409ed989"
        f"&klt={period}&fqt=1"
        f"&secid={secid}"
        f"&beg={start_date or '0'}&end={end_date or '20500000'}"
    )

    try:
        # 使用 curl 获取数据
        result = subprocess.run(
            ['curl', '-s', '-H', 'User-Agent: Mozilla/5.0', url],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            print(f"  curl 失败: {result.stderr}")
            return None

        # 解析 JSON
        data = json.loads(result.stdout)

        if 'data' not in data or data['data'] is None:
            print(f"  无数据返回")
            return None

        klines = data['data'].get('klines', [])
        if not klines:
            print(f"  无 K 线数据")
            return None

        # 解析 K 线数据
        rows = []
        for kline in klines:
            # 格式: 时间,开盘,收盘,最高,最低,成交量,成交额,振幅,涨跌幅,涨跌额,换手率
            parts = kline.split(',')
            if len(parts) >= 6:
                rows.append({
                    'datetime': parts[0],
                    'open': float(parts[1]),
                    'close': float(parts[2]),
                    'high': float(parts[3]),
                    'low': float(parts[4]),
                    'vol': float(parts[5]),
                    'amount': float(parts[6]) if len(parts) > 6 else 0,
                    'amplitude': float(parts[7]) if len(parts) > 7 else 0,
                    'pct_chg': float(parts[8]) if len(parts) > 8 else 0,
                    'change': float(parts[9]) if len(parts) > 9 else 0,
                    'turnover': float(parts[10]) if len(parts) > 10 else 0,
                })

        df = pd.DataFrame(rows)
        return df

    except Exception as e:
        print(f"  获取失败: {e}")
        return None


class AkshareMinuteManager:
    """akshare 分钟数据管理器 - 使用 Curl 方案"""

    def __init__(self, cache_dir: str = "data/akshare_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.request_count = 0

    def _get_cache_path(self, ts_code: str, trade_date: str, freq: str) -> Path:
        """获取缓存路径"""
        code_clean = ts_code.replace('.', '_')
        return self.cache_dir / f"{code_clean}_{trade_date}_{freq}.pkl"

    def _ts_code_to_ak_code(self, ts_code: str) -> str:
        """
        将 Tushare 代码格式转换为 akshare 格式
        000001.SZ -> 000001
        600000.SH -> 600000
        """
        return ts_code.split('.')[0]

    def download_minute_data(
        self,
        ts_code: str,
        trade_date: str,
        freq: str = "5",
        use_cache: bool = True
    ) -> Optional[pd.DataFrame]:
        """
        下载指定日期的分钟数据

        Args:
            ts_code: 股票代码 (如 "000001.SZ")
            trade_date: 交易日期 (YYYYMMDD)
            freq: 分钟频率 ("1", "5", "15", "30", "60")
            use_cache: 是否使用缓存

        Returns:
            包含分钟数据的 DataFrame
        """
        # 检查缓存
        cache_path = self._get_cache_path(ts_code, trade_date, freq)
        if use_cache and cache_path.exists():
            with open(cache_path, 'rb') as f:
                return pickle.load(f)

        try:
            code = self._ts_code_to_ak_code(ts_code)

            print(f"  从 akshare (curl) 获取 {ts_code} {trade_date} {freq}分钟数据...")

            # 使用 curl 获取数据
            df = get_minute_data_via_curl(
                symbol=code,
                period=freq,
                start_date=trade_date,
                end_date=trade_date
            )

            self.request_count += 1

            if df is None or len(df) == 0:
                print(f"    无数据返回")
                return None

            # 筛选上午数据 (09:30-11:30)
            df['time'] = pd.to_datetime(df['datetime']).dt.time
            df['date'] = pd.to_datetime(df['datetime']).dt.strftime('%Y%m%d')

            # 只保留指定日期的数据
            df = df[df['date'] == trade_date].copy()

            # 筛选上午交易时间
            morning_df = df[
                ((df['time'] >= pd.to_datetime('09:30:00').time()) &
                 (df['time'] <= pd.to_datetime('11:30:00').time()))
            ].copy()

            if len(morning_df) == 0:
                print(f"    无上午交易数据")
                return None

            # 添加前收盘价（从当日数据或前一天数据计算）
            if 'pre_close' not in morning_df.columns:
                # 使用前一天的收盘价作为 pre_close
                first_close = morning_df['close'].iloc[0]
                first_pct_chg = morning_df['pct_chg'].iloc[0]
                if first_pct_chg != 0:
                    morning_df['pre_close'] = first_close / (1 + first_pct_chg / 100)
                else:
                    morning_df['pre_close'] = morning_df['open'].iloc[0]

            print(f"    成功获取 {len(morning_df)} 条记录")

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
        trade_date: str,
        freq: str = "5",
        delay: float = 0.5
    ) -> Dict[str, pd.DataFrame]:
        """
        批量下载分钟数据

        Args:
            ts_codes: 股票代码列表
            trade_date: 交易日期
            freq: 分钟频率
            delay: 请求间隔（避免过快请求）

        Returns:
            Dict[股票代码, DataFrame]
        """
        results = {}

        print(f"\n使用 akshare (curl) 下载 {len(ts_codes)} 只股票 {trade_date} 的 {freq}分钟数据...")

        for i, code in enumerate(ts_codes):
            print(f"\n[{i+1}/{len(ts_codes)}] {code}")

            df = self.download_minute_data(code, trade_date, freq)
            if df is not None and len(df) > 0:
                results[code] = df

            # 添加延迟，避免请求过快
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


def extract_akshare_morning_features(df: pd.DataFrame) -> Optional[Dict]:
    """
    从 akshare 分钟数据中提取上午特征
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
        "data_source": "akshare_minute",
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
    if "vol" in df.columns and "amount" in df.columns:
        total_vol = df["vol"].sum()
        if total_vol > 0:
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


def test_akshare():
    """测试 akshare 分钟数据获取"""
    print("="*80)
    print("akshare 分钟数据测试 (Curl 方案)")
    print("="*80)

    manager = AkshareMinuteManager()

    # 测试股票
    test_codes = ["000001.SZ", "000002.SZ", "600519.SH"]

    # 使用历史日期测试
    test_date = "20241224"

    print(f"\n下载 {test_date} 上午数据...")

    results = manager.download_batch(test_codes, test_date, freq="5", delay=1.0)

    print(f"\n\n结果汇总:")
    for code, df in results.items():
        print(f"\n{code}: {len(df)} 条记录")
        print(df[['datetime', 'open', 'high', 'low', 'close', 'vol']].head())

        # 提取特征
        features = extract_akshare_morning_features(df)
        if features:
            print(f"\n  提取的特征:")
            for k, v in list(features.items())[:10]:
                print(f"    {k}: {v}")

    # 缓存统计
    stats = manager.get_cache_stats()
    print(f"\n\n缓存统计: {stats}")

    return results


if __name__ == "__main__":
    test_akshare()

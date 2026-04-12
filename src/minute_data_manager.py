"""
分钟数据管理器
下载、缓存和管理 Tushare 分钟级数据
避免高频调用，本地缓存已下载数据
"""

import tushare as ts
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Tuple
import json
import pickle
import time

TUSHARE_TOKEN = "fd6cf8fc8404cf6f93ca6091c1e603d9bc3a65f5a536c77dbb882e60"
ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()


class MinuteDataCache:
    """分钟数据缓存管理器"""

    def __init__(self, cache_dir: str = "data/minute_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.cache_dir / "metadata.json"
        self.metadata = self._load_metadata()

    def _load_metadata(self) -> Dict:
        """加载缓存元数据"""
        if self.metadata_file.exists():
            with open(self.metadata_file, 'r') as f:
                return json.load(f)
        return {}

    def _save_metadata(self):
        """保存缓存元数据"""
        with open(self.metadata_file, 'w') as f:
            json.dump(self.metadata, f, indent=2)

    def _get_cache_key(self, ts_code: str, trade_date: str, freq: str) -> str:
        """生成缓存键"""
        return f"{ts_code}_{trade_date}_{freq}"

    def _get_cache_path(self, cache_key: str) -> Path:
        """获取缓存文件路径"""
        return self.cache_dir / f"{cache_key}.pkl"

    def get(self, ts_code: str, trade_date: str, freq: str = "5min") -> Optional[pd.DataFrame]:
        """从缓存获取数据"""
        cache_key = self._get_cache_key(ts_code, trade_date, freq)
        cache_path = self._get_cache_path(cache_key)

        if cache_path.exists() and cache_key in self.metadata:
            with open(cache_path, 'rb') as f:
                return pickle.load(f)
        return None

    def set(self, ts_code: str, trade_date: str, freq: str, df: pd.DataFrame):
        """保存数据到缓存"""
        cache_key = self._get_cache_key(ts_code, trade_date, freq)
        cache_path = self._get_cache_path(cache_key)

        with open(cache_path, 'wb') as f:
            pickle.dump(df, f)

        self.metadata[cache_key] = {
            "ts_code": ts_code,
            "trade_date": trade_date,
            "freq": freq,
            "cached_at": datetime.now().isoformat(),
            "rows": len(df)
        }
        self._save_metadata()

    def get_cache_stats(self) -> Dict:
        """获取缓存统计"""
        total_files = len(list(self.cache_dir.glob("*.pkl")))
        total_size = sum(f.stat().st_size for f in self.cache_dir.glob("*.pkl"))

        return {
            "total_files": total_files,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "cache_keys": list(self.metadata.keys())
        }


class MinuteDataManager:
    """分钟数据管理器"""

    def __init__(self, cache_dir: str = "data/minute_cache"):
        self.cache = MinuteDataCache(cache_dir)
        self.request_count = 0
        self.last_request_time = 0
        self.min_interval = 35  # Tushare Pro 分钟数据限速：每分钟2次

    def _throttle(self):
        """请求限速"""
        current_time = time.time()
        elapsed = current_time - self.last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_request_time = time.time()

    def download_minute_data(
        self,
        ts_code: str,
        trade_date: str,
        freq: str = "5min",
        start_time: str = "09:30:00",
        end_time: str = "11:30:00",
        use_cache: bool = True
    ) -> Optional[pd.DataFrame]:
        """
        下载指定日期的分钟数据

        Args:
            ts_code: 股票代码
            trade_date: 交易日期 (YYYYMMDD)
            freq: 分钟频率 (1min, 5min, 15min, 30min, 60min)
            start_time: 开始时间
            end_time: 结束时间
            use_cache: 是否使用缓存
        """
        # 检查缓存
        if use_cache:
            cached_df = self.cache.get(ts_code, trade_date, freq)
            if cached_df is not None:
                # 从缓存中筛选时间范围
                cached_df['time'] = pd.to_datetime(cached_df['trade_time']).dt.time
                start_t = datetime.strptime(start_time, "%H:%M:%S").time()
                end_t = datetime.strptime(end_time, "%H:%M:%S").time()
                return cached_df[(cached_df['time'] >= start_t) & (cached_df['time'] <= end_t)].copy()

        # 限速
        self._throttle()

        try:
            # Tushare Pro 分钟数据接口
            start_dt = f"{trade_date} {start_time}"
            end_dt = f"{trade_date} {end_time}"

            df = pro.stk_mins(
                ts_code=ts_code,
                start_date=start_dt,
                end_date=end_dt,
                freq=freq
            )

            self.request_count += 1

            if df is None or len(df) == 0:
                print(f"  无分钟数据: {ts_code} {trade_date}")
                return None

            # 保存到缓存
            if use_cache:
                self.cache.set(ts_code, trade_date, freq, df)

            return df

        except Exception as e:
            print(f"  下载分钟数据失败 {ts_code} {trade_date}: {e}")
            return None

    def download_morning_data(
        self,
        ts_codes: List[str],
        trade_date: str,
        freq: str = "5min",
        progress_interval: int = 10
    ) -> Dict[str, pd.DataFrame]:
        """
        批量下载上午数据 (9:30-11:30)

        Returns:
            Dict[股票代码, DataFrame]
        """
        results = {}

        print(f"\n下载 {len(ts_codes)} 只股票 {trade_date} 上午 {freq} 数据...")

        for i, code in enumerate(ts_codes):
            if (i + 1) % progress_interval == 0 or i == 0:
                print(f"  进度: {i+1}/{len(ts_codes)}, API调用: {self.request_count}")

            df = self.download_minute_data(code, trade_date, freq)
            if df is not None and len(df) > 0:
                results[code] = df

        print(f"\n完成: 成功 {len(results)}/{len(ts_codes)}, 总API调用: {self.request_count}")

        return results

    def get_cache_stats(self) -> Dict:
        """获取缓存统计"""
        return self.cache.get_cache_stats()


class RealMorningFeatureExtractor:
    """基于真实分钟数据的上午特征提取器"""

    def __init__(self, data_manager: MinuteDataManager):
        self.data_manager = data_manager

    def extract_features(self, ts_code: str, trade_date: str, freq: str = "5min") -> Optional[Dict]:
        """
        从真实分钟数据中提取上午特征
        """
        df = self.data_manager.download_minute_data(ts_code, trade_date, freq)

        if df is None or len(df) < 3:
            return None

        # 确保数据按时间排序
        df = df.sort_values("trade_time").reset_index(drop=True)

        features = {"ts_code": ts_code, "trade_date": trade_date, "data_source": "real_minute"}

        # 1. 基础价格数据
        first_bar = df.iloc[0]
        last_bar = df.iloc[-1]

        open_price = first_bar["open"]
        close_price = last_bar["close"]
        high_price = df["high"].max()
        low_price = df["low"].min()

        # 获取前收盘价 (从日线数据或分钟数据)
        pre_close = first_bar.get("pre_close", open_price)

        # 2. 开盘特征
        features["morning_open"] = open_price
        features["morning_gap_pct"] = round((open_price - pre_close) / pre_close * 100, 4)

        # 3. 上午涨跌幅
        features["morning_return"] = round((close_price - pre_close) / pre_close * 100, 4)
        features["morning_change"] = round((close_price - open_price) / open_price * 100, 4)

        # 4. 上午振幅
        features["morning_max_up"] = round((high_price - open_price) / open_price * 100, 4)
        features["morning_max_down"] = round((low_price - open_price) / open_price * 100, 4)
        features["morning_range"] = round((high_price - low_price) / open_price * 100, 4)

        # 5. 波动率 (收盘价变化的标准差)
        if len(df) >= 3:
            df['bar_return'] = df['close'].pct_change()
            features["morning_volatility"] = round(df['bar_return'].std() * 100, 4)
        else:
            features["morning_volatility"] = 0

        # 6. 成交量特征
        if "vol" in df.columns:
            total_vol = df["vol"].sum()
            features["morning_total_vol"] = int(total_vol)
            features["morning_avg_vol"] = round(total_vol / len(df), 2)

            # 成交量分布 (前半段 vs 后半段)
            mid_idx = len(df) // 2
            first_half_vol = df.iloc[:mid_idx]["vol"].sum()
            second_half_vol = df.iloc[mid_idx:]["vol"].sum()
            features["vol_first_half"] = int(first_half_vol)
            features["vol_second_half"] = int(second_half_vol)
            features["vol_distribution"] = round(second_half_vol / (first_half_vol + 1e-10), 4)

        # 7. 价格位置特征
        if high_price != low_price:
            features["close_position"] = round((close_price - low_price) / (high_price - low_price), 4)
        else:
            features["close_position"] = 0.5

        # 8. VWAP (成交量加权均价)
        if "vol" in df.columns and "amount" in df.columns:
            vwap = df["amount"].sum() / (df["vol"].sum() + 1e-10)
            features["vwap"] = round(vwap, 4)
            features["vwap_deviation"] = round((close_price - vwap) / vwap * 100, 4)

        # 9. 趋势特征 (分段分析)
        n_bars = len(df)
        if n_bars >= 6:
            # 开盘30分钟 vs 收盘30分钟
            first_30_close = df.iloc[min(5, n_bars//2 - 1)]["close"]
            last_30_close = df.iloc[-1]["close"]
            last_30_open = df.iloc[max(n_bars//2, 0)]["open"]

            features["first_30_return"] = round((first_30_close - open_price) / open_price * 100, 4)
            features["last_30_return"] = round((last_30_close - last_30_open) / last_30_open * 100, 4)
            features["trend_consistency"] = 1 if features["first_30_return"] * features["last_30_return"] > 0 else -1

        # 10. 极值点时间
        high_idx = df["high"].idxmax()
        low_idx = df["low"].idxmin()
        features["high_time_position"] = round(high_idx / n_bars, 4)
        features["low_time_position"] = round(low_idx / n_bars, 4)

        # 11. K线形态特征
        # 上影线/下影线比例
        features["upper_shadow_ratio"] = round((high_price - df["close"].max()) / (high_price - low_price + 1e-10), 4)
        features["lower_shadow_ratio"] = round((df["close"].min() - low_price) / (high_price - low_price + 1e-10), 4)

        features["n_bars"] = n_bars

        return features

    def extract_batch(
        self,
        ts_codes: List[str],
        trade_date: str,
        freq: str = "5min"
    ) -> pd.DataFrame:
        """批量提取特征"""
        all_features = []

        print(f"\n提取 {len(ts_codes)} 只股票的真实分钟特征...")

        for i, code in enumerate(ts_codes):
            if (i + 1) % 10 == 0:
                print(f"  进度: {i+1}/{len(ts_codes)}")

            features = self.extract_features(code, trade_date, freq)
            if features:
                all_features.append(features)

        if not all_features:
            return pd.DataFrame()

        df = pd.DataFrame(all_features)
        print(f"\n成功提取 {len(df)} 只股票的特征")

        return df


def test_minute_data():
    """测试分钟数据下载"""
    print("="*80)
    print("分钟数据下载测试")
    print("="*80)

    manager = MinuteDataManager()

    # 测试股票
    test_codes = ["000001.SZ", "000002.SZ", "600519.SH"]
    test_date = "20251224"

    # 下载上午数据
    results = manager.download_morning_data(test_codes, test_date, freq="5min")

    print(f"\n下载结果:")
    for code, df in results.items():
        print(f"\n{code}: {len(df)} 条记录")
        print(df[['trade_time', 'open', 'high', 'low', 'close', 'vol']].head())

    # 提取特征
    extractor = RealMorningFeatureExtractor(manager)

    print(f"\n特征提取:")
    for code in test_codes:
        features = extractor.extract_features(code, test_date)
        if features:
            print(f"\n{code}:")
            key_features = {k: v for k, v in features.items() if k not in ['ts_code', 'trade_date', 'data_source']}
            for k, v in list(key_features.items())[:10]:
                print(f"  {k}: {v}")

    # 缓存统计
    stats = manager.get_cache_stats()
    print(f"\n缓存统计:")
    print(f"  文件数: {stats['total_files']}")
    print(f"  总大小: {stats['total_size_mb']} MB")


if __name__ == "__main__":
    test_minute_data()

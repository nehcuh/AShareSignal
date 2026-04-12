"""
使用 pytdx 获取通达信分钟数据
无需 API Key，免费获取股票分钟级数据

参考资料: https://github.com/LisonEvf/pytdx2
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional, Dict
import pickle

from pytdx.hq import TdxHq_API
from pytdx.params import TDXParams


class PytdxMinuteDataManager:
    """pytdx 分钟数据管理器"""

    def __init__(self, cache_dir: str = "data/pytdx_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.api = None
        self.best_ip = None

    def _get_api(self) -> TdxHq_API:
        """获取通达信 API 连接"""
        if self.api is None:
            self.api = TdxHq_API()
            # 自动选择最佳服务器
            if self.best_ip is None:
                print("正在选择最快的服务器...")
                from pytdx.exhq import TdxExHq_API
                # 使用默认服务器
                self.best_ip = '119.147.212.81'  # 深圳电信

            # 尝试多个服务器
            servers = [
                ('119.147.212.81', 7709),   # 深圳电信
                ('218.75.126.146', 7709),   # 上海电信
                ('221.194.181.101', 7709),  # 北京联通
                ('119.147.171.77', 7709),   # 深圳电信2
                ('60.191.116.100', 7709),   # 杭州电信
                ('14.215.128.18', 7709),    # 广州电信
            ]

            connected = False
            for ip, port in servers:
                try:
                    if self.api.connect(ip, port):
                        self.best_ip = ip
                        print(f"  已连接到服务器: {ip}:{port}")
                        connected = True
                        break
                except Exception as e:
                    continue

            if not connected:
                print("  警告: 无法连接到任何服务器")

        return self.api

    def _ts_code_to_tdx(self, ts_code: str) -> tuple:
        """
        将 Tushare 代码格式转换为通达信格式
        返回: (market, code)
        market: 0=深圳, 1=上海
        """
        code, suffix = ts_code.split('.')
        if suffix == 'SZ':
            return 0, code
        elif suffix == 'SH':
            return 1, code
        else:
            raise ValueError(f"未知的代码格式: {ts_code}")

    def _get_cache_path(self, ts_code: str, trade_date: str) -> Path:
        """获取缓存路径"""
        return self.cache_dir / f"{ts_code}_{trade_date}.pkl"

    def download_minute_data(
        self,
        ts_code: str,
        trade_date: str,
        freq: int = 5,  # 5分钟
        use_cache: bool = True
    ) -> Optional[pd.DataFrame]:
        """
        下载指定日期的分钟数据

        Args:
            ts_code: 股票代码 (如 "000001.SZ")
            trade_date: 交易日期 (YYYYMMDD)
            freq: 分钟频率 (1, 5, 15, 30, 60)
            use_cache: 是否使用缓存
        """
        # 检查缓存
        cache_path = self._get_cache_path(ts_code, trade_date)
        if use_cache and cache_path.exists():
            with open(cache_path, 'rb') as f:
                return pickle.load(f)

        try:
            api = self._get_api()
            market, code = self._ts_code_to_tdx(ts_code)

            # 映射频率
            freq_map = {1: 8, 5: 0, 15: 1, 30: 2, 60: 3}
            tdx_freq = freq_map.get(freq, 0)

            # 获取分钟数据 (通达信最多返回 800 条)
            data = api.get_security_bars(
                category=tdx_freq,
                market=market,
                code=code,
                start=0,
                count=800
            )

            if data is None or len(data) == 0:
                return None

            # 转换为 DataFrame
            df = api.to_df(data)

            # 筛选指定日期
            df['date'] = pd.to_datetime(df['datetime']).dt.strftime('%Y%m%d')
            df = df[df['date'] == trade_date].copy()

            if len(df) == 0:
                return None

            # 标准化列名
            df = df.rename(columns={
                'open': 'open',
                'high': 'high',
                'low': 'low',
                'close': 'close',
                'vol': 'vol',
                'amount': 'amount',
                'datetime': 'trade_time'
            })

            # 添加时间列
            df['time'] = pd.to_datetime(df['trade_time']).dt.time

            # 获取前收盘价计算跳空
            # 从前一天的最后一条数据获取
            all_data = api.get_security_bars(
                category=tdx_freq,
                market=market,
                code=code,
                start=0,
                count=1000
            )
            all_df = api.to_df(all_data)

            # 找到前一天的收盘价
            all_df['date'] = pd.to_datetime(all_df['datetime']).dt.strftime('%Y%m%d')
            prev_date = (datetime.strptime(trade_date, '%Y%m%d') - timedelta(days=1)).strftime('%Y%m%d')
            prev_data = all_df[all_df['date'] <= trade_date]

            if len(prev_data) > 0:
                # 找到 trade_date 之前的最后一条
                prev_close_idx = prev_data[prev_data['date'] < trade_date].index
                if len(prev_close_idx) > 0:
                    pre_close = prev_data.loc[prev_close_idx[-1], 'close']
                    df['pre_close'] = pre_close
                else:
                    df['pre_close'] = df['open'].iloc[0]
            else:
                df['pre_close'] = df['open'].iloc[0]

            # 只保留上午数据 (9:30-11:30)
            df = df[(df['time'] >= pd.to_datetime('09:30:00').time()) &
                    (df['time'] <= pd.to_datetime('11:30:00').time())]

            if len(df) == 0:
                return None

            # 保存缓存
            if use_cache:
                with open(cache_path, 'wb') as f:
                    pickle.dump(df, f)

            return df

        except Exception as e:
            print(f"  下载失败 {ts_code}: {e}")
            return None

    def download_morning_batch(
        self,
        ts_codes: List[str],
        trade_date: str,
        freq: int = 5
    ) -> Dict[str, pd.DataFrame]:
        """批量下载上午数据"""
        results = {}

        print(f"\n使用 pytdx 下载 {len(ts_codes)} 只股票 {trade_date} 的 {freq}min 数据...")

        for i, code in enumerate(ts_codes):
            if (i + 1) % 10 == 0 or i == 0:
                print(f"  进度: {i+1}/{len(ts_codes)}")

            df = self.download_minute_data(code, trade_date, freq)
            if df is not None and len(df) > 0:
                results[code] = df

        print(f"\n完成: 成功下载 {len(results)}/{len(ts_codes)} 只股票")

        # 关闭连接
        if self.api:
            self.api.disconnect()
            self.api = None

        return results

    def get_cache_stats(self) -> Dict:
        """获取缓存统计"""
        files = list(self.cache_dir.glob("*.pkl"))
        total_size = sum(f.stat().st_size for f in files)
        return {
            "total_files": len(files),
            "total_size_mb": round(total_size / (1024 * 1024), 2)
        }


def extract_pytdx_morning_features(df: pd.DataFrame) -> Dict:
    """从 pytdx 分钟数据中提取上午特征"""
    if df is None or len(df) < 3:
        return None

    df = df.sort_values("trade_time").reset_index(drop=True)

    first_bar = df.iloc[0]
    last_bar = df.iloc[-1]

    open_price = first_bar["open"]
    close_price = last_bar["close"]
    high_price = df["high"].max()
    low_price = df["low"].min()
    pre_close = first_bar.get("pre_close", open_price)

    features = {
        "data_source": "pytdx_real_minute",
        "morning_open": open_price,
        "morning_pre_close": pre_close,
        "morning_gap_pct": round((open_price - pre_close) / pre_close * 100, 4),
        "morning_return": round((close_price - pre_close) / pre_close * 100, 4),
        "morning_change": round((close_price - open_price) / open_price * 100, 4),
        "morning_max_up": round((high_price - open_price) / open_price * 100, 4),
        "morning_max_down": round((low_price - open_price) / open_price * 100, 4),
        "morning_range": round((high_price - low_price) / open_price * 100, 4),
        "morning_close": close_price,
        "morning_high": high_price,
        "morning_low": low_price,
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

    # 价格位置
    if high_price != low_price:
        features["close_position"] = round((close_price - low_price) / (high_price - low_price), 4)
    else:
        features["close_position"] = 0.5

    # VWAP
    if "vol" in df.columns and "amount" in df.columns:
        vwap = df["amount"].sum() / (df["vol"].sum() + 1e-10)
        features["vwap"] = round(vwap, 4)
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

    return features


def test_pytdx():
    """测试 pytdx 数据获取"""
    print("="*80)
    print("pytdx 分钟数据测试")
    print("="*80)

    manager = PytdxMinuteDataManager()

    # 测试股票
    test_codes = ["000001.SZ", "000002.SZ", "600519.SH"]
    test_date = "20251224"

    print(f"\n下载 {test_date} 上午数据...")

    for code in test_codes:
        print(f"\n{code}:")
        df = manager.download_minute_data(code, test_date, freq=5)

        if df is not None:
            print(f"  成功! {len(df)} 条记录")
            print(df[['trade_time', 'open', 'high', 'low', 'close', 'vol', 'pre_close']].head())

            # 提取特征
            features = extract_pytdx_morning_features(df)
            print(f"\n  特征:")
            for k, v in list(features.items())[:8]:
                print(f"    {k}: {v}")
        else:
            print(f"  无数据")

    # 缓存统计
    stats = manager.get_cache_stats()
    print(f"\n缓存统计: {stats}")


if __name__ == "__main__":
    test_pytdx()

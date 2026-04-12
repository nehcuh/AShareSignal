"""
pytdx 分钟数据获取模块
使用本地安装的 pytdx 获取通达信分钟数据

优势：
- 可获取历史分钟数据（不只是最近1个月）
- 无API限制
- 数据来自通达信服务器，质量可靠
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, time, timedelta
from typing import List, Optional, Dict, Tuple
import pickle

from pytdx.hq import TdxHq_API

# 可用的通达信服务器
WORKING_SERVERS = [
    ('110.41.147.114', 7709),  # 深圳双线主站1
    ('110.41.2.72', 7709),      # 深圳双线主站2
    ('110.41.4.4', 7709),       # 深圳双线主站3
    ('124.70.176.52', 7709),    # 上海双线主站1
    ('123.60.186.45', 7709),    # 上海双线主站3
]

# 周期映射
PERIOD_MAP = {
    '1': 8,    # 1分钟
    '5': 0,    # 5分钟
    '15': 1,   # 15分钟
    '30': 2,   # 30分钟
    '60': 3,   # 60分钟
}


class PytdxMinuteManager:
    """pytdx 分钟数据管理器"""

    def __init__(self, cache_dir: str = "data/pytdx_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.api = None
        self.server = None
        self.request_count = 0

    def connect(self) -> bool:
        """连接到通达信服务器"""
        # 如果已有连接，先断开
        if self.api:
            try:
                self.api.disconnect()
            except:
                pass

        self.api = TdxHq_API()

        for ip, port in WORKING_SERVERS:
            try:
                if self.api.connect(ip, port, time_out=10):
                    self.server = (ip, port)
                    return True
            except:
                continue

        return False

    def disconnect(self):
        """断开连接"""
        if self.api:
            self.api.disconnect()
            self.api = None

    def _get_cache_path(self, ts_code: str, trade_date: str, freq: str) -> Path:
        """获取缓存路径"""
        code_clean = ts_code.replace('.', '_')
        return self.cache_dir / f"{code_clean}_{trade_date}_{freq}min.pkl"

    def _ts_code_to_pytdx(self, ts_code: str) -> Tuple[int, str]:
        """
        转换股票代码格式
        返回: (market, code)
        market: 0=深圳, 1=上海
        """
        code = ts_code.split('.')[0]
        if '.SZ' in ts_code:
            return 0, code
        elif '.SH' in ts_code:
            return 1, code
        return 0, code

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

        # 连接服务器
        if not self.connect():
            print(f"  无法连接到通达信服务器")
            return None

        try:
            market, code = self._ts_code_to_pytdx(ts_code)
            period = PERIOD_MAP.get(freq, 0)

            print(f"  从 pytdx 获取 {ts_code} {trade_date} {freq}分钟数据...")

            # 获取数据（获取较多数据以确保覆盖目标日期）
            data = self.api.get_security_bars(period, market, code, 0, 800)

            self.request_count += 1

            if not data:
                print(f"    无数据返回")
                return None

            df = self.api.to_df(data)

            # 解析日期时间
            df['datetime'] = pd.to_datetime(df['datetime'])
            df['date'] = df['datetime'].dt.strftime('%Y%m%d')
            df['time'] = df['datetime'].dt.time

            # 筛选指定日期
            df = df[df['date'] == trade_date].copy()

            if len(df) == 0:
                print(f"    无 {trade_date} 的数据")
                return None

            # 筛选上午交易时间
            morning_df = df[
                (df['time'] >= time(9, 30)) &
                (df['time'] <= time(11, 30))
            ].copy()

            if len(morning_df) == 0:
                print(f"    无上午交易数据")
                return None

            # 计算前收盘价（用第一根K线的open近似）
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
        trade_date: str,
        freq: str = "5",
        delay: float = 0.1
    ) -> Dict[str, pd.DataFrame]:
        """
        批量下载分钟数据
        """
        import time

        results = {}

        print(f"\n使用 pytdx 下载 {len(ts_codes)} 只股票 {trade_date} 的 {freq}分钟数据...")

        for i, code in enumerate(ts_codes):
            print(f"\n[{i+1}/{len(ts_codes)}] {code}")

            df = self.download_minute_data(code, trade_date, freq)
            if df is not None and len(df) > 0:
                results[code] = df

            if delay > 0 and i < len(ts_codes) - 1:
                time.sleep(delay)

        print(f"\n完成: 成功下载 {len(results)}/{len(ts_codes)} 只股票")
        print(f"总请求次数: {self.request_count}")

        return results

    def __del__(self):
        """析构时断开连接"""
        self.disconnect()


def test_pytdx_minute():
    """测试 pytdx 分钟数据获取"""
    print("="*80)
    print("pytdx 分钟数据测试")
    print("="*80)

    manager = PytdxMinuteManager()

    # 测试股票
    test_codes = ["000001.SZ", "000002.SZ", "600519.SH"]

    # 使用今天日期测试
    today = datetime.now().strftime('%Y%m%d')
    print(f"\n下载 {today} 上午数据...")

    results = manager.download_batch(test_codes, today, freq="5", delay=0.2)

    print(f"\n\n结果汇总:")
    for code, df in results.items():
        print(f"\n{code}: {len(df)} 条记录")
        print(df[['datetime', 'open', 'high', 'low', 'close', 'vol']].head())

    manager.disconnect()

    return results


if __name__ == "__main__":
    test_pytdx_minute()

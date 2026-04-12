"""
Pytdx2 分钟数据适配器
使用 pytdx2 项目的服务器和方法获取通达信分钟数据

基于: https://github.com/LisonEvf/pytdx2
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional, Dict
import sys
import pickle
import socket
import struct

# pytdx2 服务器列表
MAIN_HOSTS = [
    ("通达信深圳双线主站1", "110.41.147.114", 7709),
    ("通达信深圳双线主站2", "110.41.2.72", 7709),
    ("通达信深圳双线主站3", "110.41.4.4", 7709),
    ("通达信深圳双线主站4", "47.113.94.204", 7709),
    ("通达信深圳双线主站5", "8.129.174.169", 7709),
    ("通达信深圳双线主站6", "110.41.154.219", 7709),
    ("通达信上海双线主站1", "124.70.176.52", 7709),
    ("通达信上海双线主站2", "47.100.236.28", 7709),
    ("通达信上海双线主站3", "123.60.186.45", 7709),
    ("通达信上海双线主站4", "123.60.164.122", 7709),
    ("通达信北京双线主站1", "121.36.54.217", 7709),
    ("通达信北京双线主站2", "121.36.81.195", 7709),
    ("通达信广州双线主站1", "124.71.85.110", 7709),
]

# 市场代码
MARKET_SZ = 0  # 深圳
MARKET_SH = 1  # 上海

# 周期代码
PERIOD_1MIN = 7
PERIOD_5MIN = 0
PERIOD_15MIN = 1
PERIOD_30MIN = 2
PERIOD_60MIN = 3
PERIOD_DAILY = 4


class Pytdx2MinuteClient:
    """通达信分钟数据客户端 (简化版)"""

    def __init__(self):
        self.socket = None
        self.connected = False
        self.best_host = None

    def connect(self, ip: str = None, port: int = 7709) -> bool:
        """连接到通达信服务器"""
        if ip is None:
            # 自动选择最佳服务器
            ip, port = self._find_best_server()

        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10)
            self.socket.connect((ip, port))
            self.connected = True
            self.best_host = (ip, port)

            # 发送登录请求
            if self._login():
                print(f"  已连接到 {ip}:{port}")
                return True
            else:
                self.disconnect()
                return False

        except Exception as e:
            print(f"  连接失败 {ip}:{port}: {e}")
            return False

    def _find_best_server(self) -> tuple:
        """找到响应最快的服务器"""
        print("  测试服务器响应速度...")

        best_time = float('inf')
        best_server = MAIN_HOSTS[0][1:]

        for name, ip, port in MAIN_HOSTS[:5]:  # 只测试前5个
            try:
                start = datetime.now()
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3)
                sock.connect((ip, port))
                sock.close()
                elapsed = (datetime.now() - start).total_seconds()

                if elapsed < best_time:
                    best_time = elapsed
                    best_server = (ip, port)
                    print(f"    {name}: {elapsed:.3f}s")

            except:
                continue

        return best_server

    def _login(self) -> bool:
        """登录服务器"""
        # 简化的登录请求
        try:
            # 发送心跳/登录包
            heartbeat = b'\x00' * 10
            self.socket.send(heartbeat)
            response = self.socket.recv(1024)
            return len(response) > 0
        except:
            return False

    def disconnect(self):
        """断开连接"""
        if self.socket:
            self.socket.close()
            self.socket = None
        self.connected = False

    def get_minute_kline(
        self,
        market: int,
        code: str,
        period: int = PERIOD_5MIN,
        count: int = 800
    ) -> Optional[pd.DataFrame]:
        """
        获取分钟K线数据

        Args:
            market: 0=深圳, 1=上海
            code: 股票代码 (如 '000001')
            period: 周期 (0=5分钟, 7=1分钟)
            count: 获取条数
        """
        if not self.connected:
            print("  未连接服务器")
            return None

        try:
            # 构建请求包 (简化版)
            # 通达信协议: cmd + market + code + period + start + count
            cmd = 0x10c  # 获取K线数据命令

            # 编码代码
            code_bytes = code.encode('utf-8')
            code_padded = code_bytes + b'\x00' * (6 - len(code_bytes))

            # 构建请求
            request = struct.pack('<H', cmd)  # 命令
            request += struct.pack('<B', market)  # 市场
            request += code_padded  # 代码
            request += struct.pack('<H', period)  # 周期
            request += struct.pack('<H', 0)  # 起始位置
            request += struct.pack('<H', count)  # 数量

            self.socket.send(request)
            response = self.socket.recv(65536)

            if len(response) < 20:
                return None

            # 解析响应 (简化版)
            # 实际解析需要根据通达信协议实现
            # 这里返回模拟数据
            return self._parse_kline_response(response, market, code)

        except Exception as e:
            print(f"  获取数据失败: {e}")
            return None

    def _parse_kline_response(self, data: bytes, market: int, code: str) -> pd.DataFrame:
        """解析K线响应数据"""
        # 简化的解析 - 实际需要根据通达信二进制协议解析
        # 这里我们返回一个空 DataFrame 作为占位
        return pd.DataFrame()


class Pytdx2MinuteManager:
    """Pytdx2 分钟数据管理器 - 使用原始的 pytdx 库但用 pytdx2 的服务器"""

    def __init__(self, cache_dir: str = "data/pytdx2_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # 尝试使用原始的 pytdx
        try:
            from pytdx.hq import TdxHq_API
            self.api_class = TdxHq_API
            self.has_pytdx = True
        except ImportError:
            self.has_pytdx = False
            print("警告: pytdx 未安装")

    def _get_cache_path(self, ts_code: str, trade_date: str) -> Path:
        """获取缓存路径"""
        return self.cache_dir / f"{ts_code}_{trade_date}.pkl"

    def download_minute_data(
        self,
        ts_code: str,
        trade_date: str,
        freq: int = 5,
        use_cache: bool = True
    ) -> Optional[pd.DataFrame]:
        """下载分钟数据"""

        # 检查缓存
        cache_path = self._get_cache_path(ts_code, trade_date)
        if use_cache and cache_path.exists():
            with open(cache_path, 'rb') as f:
                return pickle.load(f)

        if not self.has_pytdx:
            return None

        # 解析代码
        if '.SZ' in ts_code:
            market = 0
            code = ts_code.replace('.SZ', '')
        elif '.SH' in ts_code:
            market = 1
            code = ts_code.replace('.SH', '')
        else:
            return None

        # 映射周期
        freq_map = {1: 8, 5: 0, 15: 1, 30: 2, 60: 3}
        tdx_freq = freq_map.get(freq, 0)

        # 使用 pytdx2 的服务器列表
        api = self.api_class()

        for name, ip, port in MAIN_HOSTS:
            try:
                if api.connect(ip, port):
                    print(f"  连接到 {name} ({ip}:{port})")

                    # 获取数据
                    data = api.get_security_bars(
                        category=tdx_freq,
                        market=market,
                        code=code,
                        start=0,
                        count=800
                    )

                    api.disconnect()

                    if data and len(data) > 0:
                        df = api.to_df(data)

                        # 筛选指定日期
                        df['date'] = pd.to_datetime(df['datetime']).dt.strftime('%Y%m%d')
                        df = df[df['date'] == trade_date].copy()

                        if len(df) > 0:
                            # 保存缓存
                            if use_cache:
                                with open(cache_path, 'wb') as f:
                                    pickle.dump(df, f)
                            return df

                    break  # 成功连接但无数据，不再尝试其他服务器

            except Exception as e:
                print(f"  {name} 失败: {e}")
                continue

        return None

    def download_batch(
        self,
        ts_codes: List[str],
        trade_date: str,
        freq: int = 5
    ) -> Dict[str, pd.DataFrame]:
        """批量下载"""
        results = {}

        print(f"使用 pytdx2 服务器列表下载 {len(ts_codes)} 只股票...")

        for i, code in enumerate(ts_codes):
            print(f"[{i+1}/{len(ts_codes)}] {code}...")
            df = self.download_minute_data(code, trade_date, freq)
            if df is not None:
                results[code] = df
                print(f"  ✓ {len(df)} 条")
            else:
                print(f"  ✗ 无数据")

        return results


def test_pytdx2():
    """测试 pytdx2 适配器"""
    print("="*80)
    print("Pytdx2 分钟数据测试")
    print("="*80)

    manager = Pytdx2MinuteManager()

    # 测试股票
    test_codes = ["000001.SZ", "000002.SZ", "600519.SH"]
    test_date = "20251224"

    print(f"\n下载 {test_date} 上午数据...")
    print(f"使用 pytdx2 服务器列表: {[h[0] for h in MAIN_HOSTS[:3]]}")

    results = manager.download_batch(test_codes, test_date, freq=5)

    print(f"\n结果:")
    for code, df in results.items():
        print(f"\n{code}: {len(df)} 条记录")
        if len(df) > 0:
            print(df[['datetime', 'open', 'high', 'low', 'close', 'vol']].head())

    return results


if __name__ == "__main__":
    test_pytdx2()

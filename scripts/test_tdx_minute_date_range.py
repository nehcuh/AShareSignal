#!/usr/bin/env python3
from pytdx.hq import TdxHq_API
import pandas as pd

# 通达信服务器配置
TDX_HOST = '110.41.147.114'
TDX_PORT = 7709

def get_earliest_minute_date():
    api = TdxHq_API()
    if not api.connect(TDX_HOST, TDX_PORT):
        print("❌ 无法连接通达信服务器")
        return None
    
    try:
        # 测试用股票：000001.SZ 平安银行（深市）
        market = 0
        code = '000001'
        
        # 拉取最大数量的5分钟K线（每次最多拉800条，多轮拉取）
        all_kline = []
        offset = 0
        while True:
            kline = api.get_security_bars(0, market, code, offset, 800)
            if not kline:
                break
            all_kline.extend(kline)
            offset += 800
            # 最多拉10000条，避免无限循环
            if offset > 10000:
                break
        
        if not all_kline:
            print("❌ 无法获取K线数据")
            return None
        
        df = pd.DataFrame(all_kline)
        df['datetime'] = pd.to_datetime(df['datetime'])
        df['date'] = df['datetime'].dt.date
        
        earliest_date = df['date'].min()
        latest_date = df['date'].max()
        
        print(f"✅ 当前通达信5分钟行情时间范围: {earliest_date} 至 {latest_date}")
        print(f"📊 共获取到 {len(df)} 条5分钟K线数据")
        
        # 检查2026-03-01是否有数据
        target_date = pd.to_datetime('2026-03-01').date()
        has_20260301 = len(df[df['date'] == target_date]) > 0
        print(f"\n🔍 2026-03-01是否有分钟数据: {'✅ 有' if has_20260301 else '❌ 没有'}")
        
        # 统计可获取数据的最早3个月范围
        date_range = pd.date_range(start=earliest_date, end=latest_date, freq='D')
        print(f"\n📅 可获取分钟数据的总天数: {len(date_range)} 天")
        print(f"🗓️  往前可追溯时长: {(latest_date - earliest_date).days} 天")
        
        return earliest_date
        
    finally:
        api.disconnect()

if __name__ == "__main__":
    get_earliest_minute_date()
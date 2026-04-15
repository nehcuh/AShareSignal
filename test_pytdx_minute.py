#!/usr/bin/env python3
"""
Pytdx分钟行情获取测试脚本
验证本地修改版pytdx 1.72r2的分钟级K线获取能力
"""
from pytdx.hq import TdxHq_API
import pandas as pd
from datetime import datetime

def get_available_server():
    """获取可用的通达信行情服务器"""
    api = TdxHq_API(heartbeat=True)
    # 常用的通达信服务器列表
    servers = [
        ("119.147.212.138", 7709),
        ("115.238.56.198", 7709),
        ("114.80.63.27", 7709),
        ("180.153.18.17", 7709),
        ("124.160.88.183", 7709),
        ("218.75.39.18", 7709),
        ("123.129.245.203", 7709),
        ("221.194.181.6", 7709)
    ]
    for server in servers:
        try:
            if api.connect(server[0], server[1], time_out=3):
                print(f"✅ 已连接到服务器: {server[0]}:{server[1]}")
                return api
        except Exception as e:
            continue
    print("❌ 没有可用的通达信服务器，请检查网络或更换服务器列表")
    return None

def test_5min_kline_20260414(api):
    """测试获取2026-04-14的5分钟K线数据，查找下午13:00开盘价"""
    print("\n" + "="*50)
    print("测试项1: 获取2026-04-14的5分钟K线数据")
    
    # 测试标的：平安银行（000001.SZ），市场代码0代表深市
    code = "000001"
    market = 0
    # 5分钟K线category=0，获取最近100根K线（覆盖全天48根）
    data = api.get_security_bars(category=0, market=market, code=code, start=0, count=100)
    if not data:
        print("❌ 获取5分钟K线失败")
        return False
    
    df = pd.DataFrame(data)
    df['datetime'] = pd.to_datetime(df['datetime'])
    # 筛选2026-04-14的数据
    df_0414 = df[df['datetime'].dt.date == pd.to_datetime('2026-04-14').date()]
    print(f"✅ 获取到2026-04-14的5分钟K线数量: {len(df_0414)}根")
    
    if len(df_0414) == 0:
        print("❌ 2026-04-14无5分钟K线数据")
        return False
    
    # 查找13:00的K线
    df_1300 = df_0414[df_0414['datetime'].dt.time == pd.to_datetime('13:00:00').time()]
    if len(df_1300) > 0:
        open_price = df_1300.iloc[0]['open']
        print(f"✅ 已获取到2026-04-14下午13:00开盘价: {open_price}")
        print(f"📊 13:00 K线数据: open={open_price}, high={df_1300.iloc[0]['high']}, low={df_1300.iloc[0]['low']}, close={df_1300.iloc[0]['close']}, vol={df_1300.iloc[0]['vol']}")
    else:
        print("⚠️  未找到2026-04-14 13:00的5分钟K线，可用时间段:")
        print(df_0414['datetime'].dt.strftime('%H:%M').unique())
    
    # 输出样本数据
    print("\n📋 5分钟K线样本数据（前5根）:")
    print(df_0414[['datetime', 'open', 'high', 'low', 'close', 'vol']].head().to_string(index=False))
    return True

def test_realtime_minute_kline(api):
    """测试获取2026-04-15的实时1分钟/5分钟行情数据"""
    print("\n" + "="*50)
    print("测试项2: 获取2026-04-15的实时分钟K线数据")
    
    code = "000001"
    market = 0
    
    # 测试1分钟K线
    print("\n🔍 测试1分钟K线:")
    data_1min = api.get_security_bars(category=8, market=market, code=code, start=0, count=50)
    if data_1min:
        df_1min = pd.DataFrame(data_1min)
        df_1min['datetime'] = pd.to_datetime(df_1min['datetime'])
        df_0415_1min = df_1min[df_1min['datetime'].dt.date == pd.to_datetime('2026-04-15').date()]
        print(f"✅ 获取到2026-04-15的1分钟K线数量: {len(df_0415_1min)}根")
        if len(df_0415_1min) > 0:
            latest = df_0415_1min.iloc[-1]
            print(f"⏰ 最新1分钟K线时间: {latest['datetime'].strftime('%H:%M:%S')}, 最新价: {latest['close']}")
    else:
        print("❌ 获取1分钟K线失败")
    
    # 测试5分钟K线
    print("\n🔍 测试5分钟K线:")
    data_5min = api.get_security_bars(category=0, market=market, code=code, start=0, count=50)
    if data_5min:
        df_5min = pd.DataFrame(data_5min)
        df_5min['datetime'] = pd.to_datetime(df_5min['datetime'])
        df_0415_5min = df_5min[df_5min['datetime'].dt.date == pd.to_datetime('2026-04-15').date()]
        print(f"✅ 获取到2026-04-15的5分钟K线数量: {len(df_0415_5min)}根")
        if len(df_0415_5min) > 0:
            latest = df_0415_5min.iloc[-1]
            print(f"⏰ 最新5分钟K线时间: {latest['datetime'].strftime('%H:%M:%S')}, 最新价: {latest['close']}")
    else:
        print("❌ 获取5分钟K线失败")
    
    return True

if __name__ == "__main__":
    print("Pytdx分钟行情获取测试脚本 v1.0")
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    api = get_available_server()
    if not api:
        exit(1)
    
    try:
        # 测试5分钟历史数据
        test_5min_kline_20260414(api)
        # 测试实时分钟数据
        test_realtime_minute_kline(api)
    finally:
        api.disconnect()
    
    print("\n" + "="*50)
    print("测试完成！")

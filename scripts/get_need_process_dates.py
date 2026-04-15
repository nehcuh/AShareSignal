#!/usr/bin/env python3
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tushare as ts
from datetime import datetime
import pandas as pd

# 从环境变量加载tushare token
ts.set_token(os.getenv('TUSHARE_TOKEN'))
pro = ts.pro_api()

def get_trading_dates(start_date, end_date):
    """获取指定日期范围内的交易日列表"""
    df = pro.trade_cal(exchange='SSE', start_date=start_date, end_date=end_date, is_open='1')
    trading_dates = df['cal_date'].tolist()
    trading_dates.sort()
    return trading_dates

if __name__ == "__main__":
    # 日期范围：2026-02-01 至 2026-03-25
    start_date = '20260201'
    end_date = '20260325'
    
    trading_dates = get_trading_dates(start_date, end_date)
    
    # 排除已经跑过的日期（20260326及之后）
    existing_dates = [
        '20260326', '20260327', '20260330', '20260331',
        '20260401', '20260402', '20260403', '20260407',
        '20260408', '20260409', '20260410', '20260413',
        '20260414'
    ]
    
    need_process = [d for d in trading_dates if d not in existing_dates]
    
    print(f"✅ 2026-02-01 至 2026-03-25 期间共有 {len(trading_dates)} 个交易日")
    print(f"🔍 需要处理的新日期共 {len(need_process)} 个:")
    for date in need_process:
        print(f"  - {date}")
    
    # 保存需要处理的日期到文件
    with open('need_process_dates.txt', 'w') as f:
        for date in need_process:
            f.write(f"{date}\n")
    
    print(f"\n💾 需要处理的日期已保存到: need_process_dates.txt")
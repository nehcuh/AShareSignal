#!/usr/bin/env python
import os
import sys
import pandas as pd
import tushare as ts
from datetime import datetime

# 配置
START_DATE = '20260326'
END_DATE = datetime.now().strftime('%Y%m%d')
TOP_N = 5
OUTPUT_DIR = 'output/historical_filter'
SUMMARY_FILE = f'{OUTPUT_DIR}/all_dates_result.csv'

def load_tushare_token():
    secrets_path = os.path.expanduser('~/.config/zsh/secrets.zsh')
    with open(secrets_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('export TUSHARE_TOKEN='):
                return line.split('=', 1)[1].strip().strip('"\'')
    sys.exit(1)

def get_trade_dates(start, end):
    """获取指定区间的交易日列表"""
    pro = ts.pro_api(load_tushare_token())
    cal = pro.trade_cal(exchange='SSE', start_date=start, end_date=end, is_open='1')
    return sorted(cal['cal_date'].tolist())

def run_filter(date):
    """运行单日筛选"""
    print(f"\n🚀 正在处理日期: {date}")
    cmd = f'cd {os.path.dirname(os.path.dirname(os.path.abspath(__file__)))} && uv run scripts/signal_filter.py --date {date} --top {TOP_N}'
    exit_code = os.system(cmd)
    if exit_code != 0:
        print(f"❌ {date} 筛选失败，跳过")
        return False
    # 读取结果
    result_path = f'output/screening_{date}_final_top{TOP_N}.csv'
    if not os.path.exists(result_path):
        print(f"⚠️  {date} 结果文件不存在，跳过")
        return False
    df = pd.read_csv(result_path)
    df['筛选日期'] = date
    return df

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    print(f"📅 获取从{START_DATE}到{END_DATE}的交易日列表...")
    trade_dates = get_trade_dates(START_DATE, END_DATE)
    print(f"✅ 共{len(trade_dates)}个交易日需要处理: {','.join(trade_dates)}")
    
    all_results = []
    for date in trade_dates:
        df = run_filter(date)
        if df is not False:
            all_results.append(df)
    
    # 合并所有结果
    if not all_results:
        print("❌ 无任何有效结果")
        sys.exit(1)
    total_df = pd.concat(all_results, ignore_index=True)
    total_df.to_csv(SUMMARY_FILE, index=False, encoding='utf-8-sig')
    print(f"\n✅ 所有日期结果已汇总到: {SUMMARY_FILE}")
    print(f"📊 共筛选出{len(total_df)}条记录")
    return total_df

if __name__ == '__main__':
    main()

#!/usr/bin/env python
import os
import sys
import pandas as pd
import tushare as ts
from datetime import datetime

# 配置
CUTOFF_DATE = '20260331'  # 4月1日之前的股票池
END_ANALYSIS_DATE = '20260414'
SUMMARY_FILE = 'output/historical_filter/all_dates_result.csv'
OUTPUT_REPORT = 'output/historical_filter/april_before_pool_return.csv'

def load_tushare_token():
    secrets_path = os.path.expanduser('~/.config/zsh/secrets.zsh')
    with open(secrets_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('export TUSHARE_TOKEN='):
                return line.split('=', 1)[1].strip().strip('"\'')
    sys.exit(1)

def calculate_stock_return(ts_code, select_date, end_date):
    """计算单只股票从筛选日到结束日的收益情况"""
    pro = ts.pro_api(load_tushare_token())
    # 获取筛选日到结束日的行情
    df = pro.daily(ts_code=ts_code, start_date=select_date, end_date=end_date).sort_values('trade_date')
    if len(df) == 0:
        return None
    # 筛选日收盘价（如果筛选日当天停牌，取下一个交易日）
    entry_price = df.iloc[0]['close']
    # 最新收盘价
    latest_price = df.iloc[-1]['close']
    # 期间最大涨幅
    max_high = df['high'].max()
    # 计算收益
    return_rate = round((latest_price - entry_price)/entry_price * 100, 2)
    max_return = round((max_high - entry_price)/entry_price * 100, 2)
    # 是否盈利
    is_profit = return_rate > 0
    return {
        '代码': ts_code,
        '筛选日期': select_date,
        '入场价格': round(entry_price,2),
        '最新价格': round(latest_price,2),
        '期间最高价格': round(max_high,2),
        '持有至今收益(%)': return_rate,
        '期间最高收益(%)': max_return,
        '是否盈利': is_profit
    }

def main():
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    pro = ts.pro_api(load_tushare_token())
    
    # 1. 读取汇总结果
    if not os.path.exists(SUMMARY_FILE):
        print("❌ 汇总结果文件不存在，请先运行batch_filter.py")
        sys.exit(1)
    total_df = pd.read_csv(SUMMARY_FILE)
    
    # 2. 筛选4月1日之前的股票池
    pool_df = total_df[total_df['筛选日期'] <= int(CUTOFF_DATE)].copy()
    # 去重（同一只股票可能多次入选）
    pool_df = pool_df.drop_duplicates(subset=['代码'], keep='first')
    print(f"✅ 4月1日之前筛选出的股票池共{len(pool_df)}只标的")
    
    # 3. 计算每只股票的收益
    print("⏳ 正在计算所有标的收益情况...")
    returns = []
    for _, row in pool_df.iterrows():
        print(f"处理中: {row['代码']} {row['名称']}...")
        res = calculate_stock_return(row['代码'], str(row['筛选日期']), END_ANALYSIS_DATE)
        if res:
            # 合并基础信息
            res['名称'] = row['名称']
            res['入选时综合得分'] = row['综合总分']
            returns.append(res)
    
    # 4. 统计结果
    return_df = pd.DataFrame(returns)
    return_df.to_csv(OUTPUT_REPORT, index=False, encoding='utf-8-sig')
    
    # 5. 输出统计报告
    avg_return = round(return_df['持有至今收益(%)'].mean(),2)
    avg_max_return = round(return_df['期间最高收益(%)'].mean(),2)
    win_rate = round(return_df['是否盈利'].mean()*100,2)
    top_stock = return_df.sort_values('期间最高收益(%)', ascending=False).iloc[0]
    worst_stock = return_df.sort_values('持有至今收益(%)').iloc[0]
    
    print("\n" + "="*80)
    print("📈 4月1日前筛选股票池收益统计报告（截至2026年4月14日）")
    print("="*80)
    print(f"📊 股票池总数量: {len(return_df)}只")
    print(f"💰 平均持有至今收益率: {avg_return}%")
    print(f"🚀 平均最高收益率: {avg_max_return}%")
    print(f"✅ 胜率: {win_rate}%")
    print(f"🏆 最高收益标的: {top_stock['名称']}({top_stock['代码']}) 最高收益{top_stock['期间最高收益(%)']}%")
    print(f"⚠️  最差收益标的: {worst_stock['名称']}({worst_stock['代码']}) 持有收益{worst_stock['持有至今收益(%)']}%")
    print("="*80)
    print(f"💾 详细收益数据已保存到: {OUTPUT_REPORT}")
    print("\n📋 Top5收益标的:")
    print(return_df.sort_values('持有至今收益(%)', ascending=False).head(5)[['代码','名称','持有至今收益(%)','期间最高收益(%)']].to_string(index=False))

if __name__ == '__main__':
    main()

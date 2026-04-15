#!/usr/bin/env python
import os
import sys
import pandas as pd
import tushare as ts
from datetime import datetime

# 配置
END_DATE = datetime.now().strftime('%Y%m%d')
ALL_RESULTS_FILE = 'output/historical_filter/all_dates_result.csv'
OUTPUT_REPORT = 'output/historical_filter/daily_portfolio_return.csv'

def load_tushare_token():
    secrets_path = os.path.expanduser('~/.config/zsh/secrets.zsh')
    with open(secrets_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('export TUSHARE_TOKEN='):
                return line.split('=', 1)[1].strip().strip('"\'')
    sys.exit(1)

def get_portfolio_return(portfolio_df, select_date):
    """计算单个日期股票池的平均收益"""
    pro = ts.pro_api(load_tushare_token())
    returns = []
    for _, row in portfolio_df.iterrows():
        try:
            # 获取行情
            df = pro.daily(ts_code=row['代码'], start_date=str(select_date), end_date=END_DATE).sort_values('trade_date')
            if len(df) == 0:
                continue
            entry_price = df.iloc[0]['close']
            latest_price = df.iloc[-1]['close']
            max_high = df['high'].max()
            hold_return = round((latest_price - entry_price)/entry_price * 100, 2)
            max_return = round((max_high - entry_price)/entry_price * 100, 2)
            returns.append({
                'code': row['代码'],
                'name': row['名称'],
                'hold_return': hold_return,
                'max_return': max_return,
                'is_profit': hold_return > 0
            })
        except:
            continue
    if not returns:
        return None
    ret_df = pd.DataFrame(returns)
    best = ret_df.sort_values('hold_return', ascending=False).iloc[0]
    worst = ret_df.sort_values('hold_return').iloc[0]
    best_name = str(best['name']) if pd.notna(best['name']) else best['code']
    worst_name = str(worst['name']) if pd.notna(worst['name']) else worst['code']
    return {
        '筛选日期': select_date,
        '股票数量': len(ret_df),
        '平均持有收益(%)': round(ret_df['hold_return'].mean(), 2),
        '平均最高收益(%)': round(ret_df['max_return'].mean(), 2),
        '胜率(%)': round(ret_df['is_profit'].mean()*100, 2),
        '最佳标的': f"{best_name}({best['code']})",
        '最佳标的收益(%)': best['hold_return'],
        '最差标的': f"{worst_name}({worst['code']})",
        '最差标的收益(%)': worst['hold_return']
    }

def main():
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if not os.path.exists(ALL_RESULTS_FILE):
        print("❌ 汇总结果不存在，请先运行batch_filter.py")
        sys.exit(1)
    
    all_df = pd.read_csv(ALL_RESULTS_FILE)
    # 按日期分组
    date_groups = all_df.groupby('筛选日期')
    print(f"✅ 共{len(date_groups)}个交易日的股票池，正在计算每日收益...")

    daily_returns = []
    for date, portfolio in date_groups:
        print(f"⏳ 计算日期{date}的组合收益...")
        res = get_portfolio_return(portfolio, date)
        if res:
            daily_returns.append(res)
    
    # 输出结果
    result_df = pd.DataFrame(daily_returns).sort_values('筛选日期', ascending=True)
    result_df.to_csv(OUTPUT_REPORT, index=False, encoding='utf-8-sig')

    print("\n" + "="*120)
    print(f"📅 每日股票池收益统计（截至{datetime.now().strftime('%Y-%m-%d')}）")
    print("="*120)
    print(result_df[['筛选日期','股票数量','平均持有收益(%)','平均最高收益(%)','胜率(%)','最佳标的','最佳标的收益(%)']].to_string(index=False))
    print("="*120)
    print(f"💾 详细数据已保存到: {OUTPUT_REPORT}")
    print(f"\n📊 整体平均日组合收益: {round(result_df['平均持有收益(%)'].mean(),2)}%")
    print(f"📈 正收益天数占比: {round((result_df['平均持有收益(%)']>0).mean()*100,2)}%")

if __name__ == '__main__':
    main()

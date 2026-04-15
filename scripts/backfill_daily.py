"""
用 tushare 日线数据粗筛 03-26 候选，再用 pytdx 分钟数据精确打分
"""
import os, sys, requests, pandas as pd, numpy as np
from pathlib import Path
import argparse
from datetime import datetime

# 确保 output 目录存在
Path("output").mkdir(exist_ok=True)

def tushare_api(token, api_name, params):
    url = 'https://api.tushare.pro'
    payload = {'api_name': api_name, 'token': token, 'params': params, 'fields': ''}
    r = requests.post(url, json=payload, timeout=60)
    data = r.json()
    if data.get('code') == 0:
        return data['data']
    print(f"  Error: {data.get('msg')}")
    return None

def is_main(code):
    c = code.split('.')[0]
    if c.startswith('688') or c.startswith('300') or c.startswith('301') or c.startswith('8') or c.startswith('430'):
        return False
    return c[:3] in ['000','001','002','003','600','601','603','605']

def is_st(name):
    n = str(name).upper()
    return 'ST' in n or '退' in n

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', type=str, default=datetime.today().strftime('%Y%m%d'), help='交易日日期，格式YYYYMMDD，默认今天')
    args = parser.parse_args()
    trade_date = args.date
    date_short = f"{trade_date[4:6]}-{trade_date[6:]}"

    token = os.environ.get('TUSHARE_TOKEN', '')
    if not token:
        print("请设置 TUSHARE_TOKEN")
        return

    # 1. 股票列表
    print("获取股票列表...")
    sr = tushare_api(token, 'stock_basic', {'exchange': '', 'list_status': 'L', 'fields': 'ts_code,name'})
    stocks = pd.DataFrame(sr['items'], columns=sr['fields'])
    stocks = stocks[stocks['ts_code'].apply(is_main) & ~stocks['name'].apply(is_st)]
    print(f"  主板非ST: {len(stocks)} 只")

    # 2. 日线
    print(f"获取 {date_short} 日线...")
    dr = tushare_api(token, 'daily', {'trade_date': trade_date, 'fields': 'ts_code,trade_date,open,high,low,close,pre_close,pct_chg,vol,amount'})
    daily = pd.DataFrame(dr['items'], columns=dr['fields'])
    for col in ['open','high','low','close','pre_close','pct_chg','vol','amount']:
        daily[col] = pd.to_numeric(daily[col], errors='coerce')
    daily = daily[daily['ts_code'].apply(is_main)]
    daily = daily.merge(stocks[['ts_code','name']], on='ts_code', how='left')

    # 3. 换手率
    print("获取换手率...")
    br = tushare_api(token, 'daily_basic', {'trade_date': trade_date, 'fields': 'ts_code,turnover_rate,volume_ratio,total_mv'})
    if br and br.get('items'):
        basic = pd.DataFrame(br['items'], columns=br['fields'])
        for c in ['turnover_rate','volume_ratio','total_mv']:
            if c in basic.columns:
                basic[c] = pd.to_numeric(basic[c], errors='coerce')
        daily = daily.merge(basic[['ts_code','turnover_rate','volume_ratio','total_mv']], on='ts_code', how='left')
    daily['turnover_rate'] = daily['turnover_rate'].fillna(0)
    daily['volume_ratio'] = daily.get('volume_ratio', pd.Series(1, index=daily.index)).fillna(1)
    daily['total_mv'] = daily.get('total_mv', pd.Series(0, index=daily.index)).fillna(0)
    print(f"  共 {len(daily)} 只有日线数据")

    # 4. 日线粗筛评分
    df = daily.copy()
    df['morning_gap_pct'] = ((df['open'] - df['pre_close']) / df['pre_close'] * 100).round(4)
    df['morning_return'] = df['pct_chg']
    df['morning_max_down'] = ((df['low'] - df['open']) / df['open'] * 100).round(4)
    df['morning_max_up'] = ((df['high'] - df['open']) / df['open'] * 100).round(4)
    df['close_position'] = np.where(df['high'] != df['low'],
        ((df['close'] - df['low']) / (df['high'] - df['low'])).round(4), 0.5)
    df['amplitude'] = ((df['high'] - df['low']) / df['pre_close'] * 100).round(4)
    df['turnover'] = df['turnover_rate']

    df['score'] = 50
    df['signals'] = ''

    m = (df['morning_max_down'] < -1.5) & (df['close_position'] > 0.6)
    df.loc[m, 'score'] += 25; df.loc[m, 'signals'] += '深跌反弹|'
    m = (df['morning_gap_pct'] < -1) & (df['morning_return'] > 0)
    df.loc[m, 'score'] += 20; df.loc[m, 'signals'] += '低开高走|'
    m = (df['turnover'] > 3) & (df['morning_return'] > 0)
    df.loc[m, 'score'] += 15; df.loc[m, 'signals'] += '量价齐升|'
    m = (df['morning_return'] > 0) & (df['morning_return'] < 4)
    df.loc[m, 'score'] += 10
    m = (df['morning_gap_pct'] > 1.5) & (df['morning_return'] < 0)
    df.loc[m, 'score'] -= 30; df.loc[m, 'signals'] += '⚠️高开低走|'
    m = df['morning_return'] > 6
    df.loc[m, 'score'] -= 20; df.loc[m, 'signals'] += '⚠️涨幅过大|'
    m = df['morning_return'] < -2
    df.loc[m, 'score'] -= 15; df.loc[m, 'signals'] += '⚠️弱势|'
    m = df['turnover'] > 15
    df.loc[m & (df['morning_return'] < 3), 'score'] -= 10
    m = df['turnover'] < 0.3
    df.loc[m, 'score'] -= 10
    m = df['amplitude'] > 8
    df.loc[m, 'score'] -= 5; df.loc[m, 'signals'] += '⚠️波动剧烈|'

    def get_rating(s):
        if s >= 70: return 'A'
        elif s >= 60: return 'B'
        elif s >= 45: return 'C'
        else: return 'D'

    df['rating'] = df['score'].apply(get_rating)
    df['signals'] = df['signals'].str.rstrip('|')
    result = df.sort_values('score', ascending=False)

    # 5. 输出
    rc = result['rating'].value_counts()
    print(f"\n评级分布: A={rc.get('A',0)} B={rc.get('B',0)} C={rc.get('C',0)} D={rc.get('D',0)}")

    print(f"\n日线粗筛 Top 20:")
    print(f"{'#':<3} {'代码':<12} {'名称':<10} {'收盘':>7} {'涨跌%':>7} {'换手%':>5} {'得分':>4} {'信号'}")
    print("-"*80)
    for i, (_, r) in enumerate(result.head(20).iterrows(), 1):
        nm = str(r.get('name',''))[:8]
        sig = str(r.get('signals',''))[:35]
        print(f"{i:<3} {r['ts_code']:<12} {nm:<10} {r['close']:>7.2f} {r['pct_chg']:>+6.2f}% {r['turnover_rate']:>4.1f} {r['score']:>4} {sig}")

    # 保存
    output_path = f'output/screening_{trade_date}_daily_approx.csv'
    result.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"\n日线结果已保存: {output_path}")

    # A+B 级候选列表（需要分钟数据精确重算）
    candidates = result[result['rating'].isin(['A','B'])]['ts_code'].tolist()
    print(f"\nA+B级候选({len(candidates)}只):")
    for c in candidates:
        row = result[result['ts_code']==c].iloc[0]
        print(f"  {c} {row.get('name','')} score={row['score']} {row.get('signals','')}")

if __name__ == '__main__':
    main()

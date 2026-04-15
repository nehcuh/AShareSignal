"""
回填 2026-03-26 的选股结果
使用 tushare 日线数据，复用 screen_mainboard_today.py 的评分逻辑
"""

import os
import sys
import requests
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime

# 加载 tushare token
sys.path.append(str(Path(__file__).parent.parent / "src"))

def tushare_api(token, api_name, params):
    url = 'https://api.tushare.pro'
    payload = {'api_name': api_name, 'token': token, 'params': params, 'fields': ''}
    r = requests.post(url, json=payload, timeout=60)
    data = r.json()
    if data.get('code') == 0:
        return data['data']
    print(f"  API Error [{api_name}]: {data.get('msg')}")
    return None


def get_stock_list(token):
    """获取所有主板非ST股票列表"""
    print("获取股票列表...")
    result = tushare_api(token, 'stock_basic', {
        'exchange': '',
        'list_status': 'L',
        'fields': 'ts_code,symbol,name,area,industry,market,list_date'
    })
    if not result or not result.get('items'):
        print("获取股票列表失败")
        return pd.DataFrame()

    df = pd.DataFrame(result['items'], columns=result['fields'])

    # 筛选主板
    def is_main_board(ts_code):
        code = ts_code.split('.')[0]
        if code.startswith('688'): return False  # 科创板
        if code.startswith('300') or code.startswith('301'): return False  # 创业板
        if code.startswith('8') or code.startswith('430'): return False  # 北交所
        if (code.startswith('000') or code.startswith('001') or
            code.startswith('002') or code.startswith('003') or
            code.startswith('600') or code.startswith('601') or
            code.startswith('603') or code.startswith('605')):
            return True
        return False

    def is_st(name):
        if not name: return False
        n = str(name).upper()
        return 'ST' in n or '*ST' in n or '退' in n

    df = df[df['ts_code'].apply(is_main_board)]
    df = df[~df['name'].apply(is_st)]
    print(f"  主板非ST: {len(df)} 只")
    return df


def get_daily_batch(token, trade_date, ts_codes):
    """批量获取日线数据（tushare 每次5000只）"""
    all_data = []
    batch_size = 100

    for i in range(0, len(ts_codes), batch_size):
        batch = ts_codes[i:i+batch_size]
        codes_str = ','.join(batch)
        result = tushare_api(token, 'daily', {
            'ts_code': codes_str,
            'trade_date': trade_date,
        })
        if result and result.get('items'):
            all_data.extend(result['items'])
        if i % 500 == 0 and i > 0:
            print(f"  已处理 {i}/{len(ts_codes)}...")

    if not all_data:
        return pd.DataFrame()

    return pd.DataFrame(all_data)


def calculate_features_and_score(df):
    """计算特征并评分（复用 screen_mainboard_today.py 逻辑）"""

    # 类型转换
    for col in ['open', 'high', 'low', 'close', 'pre_close', 'pct_chg', 'vol', 'amount']:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    # 计算换手率（vol 是手，需要总股本；但 tushare daily 没有直接给换手率）
    # 换手率 = 成交量(手)*100 / 流通股本(股)
    # 或者用 turnover_rate 字段
    # tushare daily 接口有 vol 但没有 turnover，需要用 daily_basic
    # 但我们先简化：用振幅和涨跌幅来打分

    # close_position: (close - low) / (high - low)
    df['close_position'] = np.where(
        df['high'] != df['low'],
        ((df['close'] - df['low']) / (df['high'] - df['low'])).round(4),
        0.5
    )

    # morning features (用日线近似)
    df['morning_gap_pct'] = ((df['open'] - df['pre_close']) / df['pre_close'] * 100).round(4)
    df['morning_return'] = df['pct_chg']  # 日涨跌幅
    df['morning_max_down'] = ((df['low'] - df['open']) / df['open'] * 100).round(4)
    df['morning_max_up'] = ((df['high'] - df['open']) / df['open'] * 100).round(4)
    df['amplitude'] = ((df['high'] - df['low']) / df['pre_close'] * 100).round(4)

    # 日成交量(手) -> 亿元近似换手率 (粗略: vol * close * 100 / 1e8)
    # 更准确：单独获取 daily_basic 的 turnover_rate
    df['turnover'] = 0  # 先占位，后面补

    return df


def apply_screening(df):
    """应用评分策略"""
    df = df.copy()
    df['score'] = 50
    df['signals'] = ''

    # 规则1: 深跌反弹
    mask1 = (df['morning_max_down'] < -1.5) & (df['close_position'] > 0.6)
    df.loc[mask1, 'score'] += 25
    df.loc[mask1, 'signals'] += '深跌反弹|'

    # 规则2: 低开高走
    mask2 = (df['morning_gap_pct'] < -1) & (df['morning_return'] > 0)
    df.loc[mask2, 'score'] += 20
    df.loc[mask2, 'signals'] += '低开高走|'

    # 规则3: 量价齐升（换手率>3%且上涨）- 暂用成交量判断
    # 由于没有换手率，用 vol > 前日的 1.5 倍 + 上涨 作为代替
    # 先跳过，后面补 turnover 后重新打分

    # 规则4: 温和上涨
    mask4 = (df['morning_return'] > 0) & (df['morning_return'] < 4)
    df.loc[mask4, 'score'] += 10

    # 规则5: 高开低走
    mask5 = (df['morning_gap_pct'] > 1.5) & (df['morning_return'] < 0)
    df.loc[mask5, 'score'] -= 30
    df.loc[mask5, 'signals'] += '⚠️高开低走|'

    # 规则6: 涨幅过大
    mask6 = df['morning_return'] > 6
    df.loc[mask6, 'score'] -= 20
    df.loc[mask6, 'signals'] += '⚠️涨幅过大|'

    # 规则7: 上午弱势
    mask7 = df['morning_return'] < -2
    df.loc[mask7, 'score'] -= 15
    df.loc[mask7, 'signals'] += '⚠️上午弱势|'

    # 规则8/9: 换手率 - 需要实际数据
    # 规则10: 振幅过大
    mask10 = df['amplitude'] > 8
    df.loc[mask10, 'score'] -= 5
    df.loc[mask10, 'signals'] += '⚠️波动剧烈|'

    # 评级
    def get_rating(score):
        if score >= 70: return 'A-强烈推荐'
        elif score >= 60: return 'B-推荐关注'
        elif score >= 45: return 'C-中性观察'
        else: return 'D-暂不关注'

    df['rating'] = df['score'].apply(get_rating)
    df['signals'] = df['signals'].str.rstrip('|')

    return df.sort_values('score', ascending=False)


def get_daily_basic(token, trade_date, ts_codes):
    """获取换手率等基本面数据"""
    all_data = []
    batch_size = 100

    for i in range(0, len(ts_codes), batch_size):
        batch = ts_codes[i:i+batch_size]
        codes_str = ','.join(batch)
        result = tushare_api(token, 'daily_basic', {
            'ts_code': codes_str,
            'trade_date': trade_date,
            'fields': 'ts_code,trade_date,turnover_rate,volume_ratio,pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,total_mv,circ_mv'
        })
        if result and result.get('items'):
            all_data.extend(result['items'])
        if i % 500 == 0 and i > 0:
            print(f"  daily_basic 已处理 {i}/{len(ts_codes)}...")

    if not all_data:
        return pd.DataFrame()

    df = pd.DataFrame(all_data)
    return df


def main():
    token = os.environ.get('TUSHARE_TOKEN', '')
    if not token:
        print("请设置 TUSHARE_TOKEN 环境变量")
        return

    trade_date = '20260326'

    # 1. 获取股票列表
    stock_list = get_stock_list(token)
    if stock_list.empty:
        return

    ts_codes = stock_list['ts_code'].tolist()

    # 2. 获取日线数据
    print(f"\n获取 {trade_date} 日线数据...")
    daily_df = get_daily_batch(token, trade_date, ts_codes)
    if daily_df.empty:
        print("获取日线数据失败")
        return

    fields = ['ts_code', 'trade_date', 'open', 'high', 'low', 'close',
              'pre_close', 'change', 'pct_chg', 'vol', 'amount']
    daily_df.columns = fields[:len(daily_df.columns)]
    print(f"  获取到 {len(daily_df)} 只股票的日线数据")

    # 3. 获取换手率等数据
    print(f"\n获取 {trade_date} 换手率数据...")
    basic_df = get_daily_basic(token, trade_date, ts_codes)
    print(f"  获取到 {len(basic_df)} 只股票的基本面数据")

    # 4. 合并
    if not basic_df.empty and 'turnover_rate' in basic_df.columns:
        basic_df['turnover_rate'] = pd.to_numeric(basic_df['turnover_rate'], errors='coerce')
        basic_df['volume_ratio'] = pd.to_numeric(basic_df.get('volume_ratio', 0), errors='coerce')
        basic_df['total_mv'] = pd.to_numeric(basic_df.get('total_mv', 0), errors='coerce')
        daily_df = daily_df.merge(
            basic_df[['ts_code', 'turnover_rate', 'volume_ratio', 'total_mv']],
            on='ts_code', how='left'
        )
        daily_df['turnover_rate'] = daily_df['turnover_rate'].fillna(0)
        daily_df['volume_ratio'] = daily_df['volume_ratio'].fillna(1)
        daily_df['total_mv'] = daily_df['total_mv'].fillna(0)
    else:
        daily_df['turnover_rate'] = 0
        daily_df['volume_ratio'] = 1
        daily_df['total_mv'] = 0

    # 5. 计算特征
    daily_df = calculate_features_and_score(daily_df)

    # 用真实换手率替换
    daily_df['turnover'] = daily_df['turnover_rate']

    # 6. 应用完整评分策略（包含换手率规则）
    df = daily_df.copy()
    df['score'] = 50
    df['signals'] = ''

    # 规则1: 深跌反弹
    mask1 = (df['morning_max_down'] < -1.5) & (df['close_position'] > 0.6)
    df.loc[mask1, 'score'] += 25
    df.loc[mask1, 'signals'] += '深跌反弹|'

    # 规则2: 低开高走
    mask2 = (df['morning_gap_pct'] < -1) & (df['morning_return'] > 0)
    df.loc[mask2, 'score'] += 20
    df.loc[mask2, 'signals'] += '低开高走|'

    # 规则3: 量价齐升
    mask3 = (df['turnover'] > 3) & (df['morning_return'] > 0)
    df.loc[mask3, 'score'] += 15
    df.loc[mask3, 'signals'] += '量价齐升|'

    # 规则4: 温和上涨
    mask4 = (df['morning_return'] > 0) & (df['morning_return'] < 4)
    df.loc[mask4, 'score'] += 10

    # 规则5: 高开低走
    mask5 = (df['morning_gap_pct'] > 1.5) & (df['morning_return'] < 0)
    df.loc[mask5, 'score'] -= 30
    df.loc[mask5, 'signals'] += '⚠️高开低走|'

    # 规则6: 涨幅过大
    mask6 = df['morning_return'] > 6
    df.loc[mask6, 'score'] -= 20
    df.loc[mask6, 'signals'] += '⚠️涨幅过大|'

    # 规则7: 弱势
    mask7 = df['morning_return'] < -2
    df.loc[mask7, 'score'] -= 15
    df.loc[mask7, 'signals'] += '⚠️上午弱势|'

    # 规则8: 高换手率
    mask8 = df['turnover'] > 15
    df.loc[mask8 & (df['morning_return'] < 3), 'score'] -= 10

    # 规则9: 低换手率
    mask9 = df['turnover'] < 0.3
    df.loc[mask9, 'score'] -= 10

    # 规则10: 振幅过大
    mask10 = df['amplitude'] > 8
    df.loc[mask10, 'score'] -= 5
    df.loc[mask10, 'signals'] += '⚠️波动剧烈|'

    def get_rating(score):
        if score >= 70: return 'A-强烈推荐'
        elif score >= 60: return 'B-推荐关注'
        elif score >= 45: return 'C-中性观察'
        else: return 'D-暂不关注'

    df['rating'] = df['score'].apply(get_rating)
    df['signals'] = df['signals'].str.rstrip('|')

    # 合并股票名称
    df = df.merge(stock_list[['ts_code', 'name']], on='ts_code', how='left')

    result = df.sort_values('score', ascending=False)

    # 7. 输出结果
    print("\n" + "="*90)
    print(f"2026-03-26 选股结果回填 (共 {len(result)} 只)")
    print("="*90)

    # 评级统计
    rating_counts = result['rating'].value_counts()
    print("\n【评级分布】")
    for r in ['A-强烈推荐', 'B-推荐关注', 'C-中性观察', 'D-暂不关注']:
        print(f"  {r}: {rating_counts.get(r, 0)} 只")

    # Top 20
    print(f"\n{'排名':<4} {'代码':<12} {'名称':<10} {'收盘':>8} {'涨跌%':>8} {'换手%':>6} {'得分':>5} {'评级':<12} {'信号'}")
    print("-"*90)
    for i, (_, row) in enumerate(result.head(20).iterrows(), 1):
        name = str(row.get('name', ''))[:8]
        signals = str(row.get('signals', ''))[:30]
        print(f"{i:<4} {row['ts_code']:<12} {name:<10} {float(row['close']):>8.2f} "
              f"{float(row['pct_chg']):>+7.2f}% {float(row['turnover']):>5.2f} "
              f"{row['score']:>5} {row['rating']:<12} {signals}")

    # 保存 CSV
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"screening_mainboard_{trade_date}_backfill.csv"

    save_cols = ['ts_code', 'name', 'close', 'pct_chg', 'turnover', 'total_mv',
                 'morning_gap_pct', 'morning_return', 'morning_max_down',
                 'morning_max_up', 'close_position', 'amplitude', 'volume_ratio',
                 'score', 'rating', 'signals']
    result[save_cols].to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"\n结果已保存: {output_file}")


if __name__ == '__main__':
    main()

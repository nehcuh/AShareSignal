"""
今日股票筛选工具 - 增强版
基于策略筛选符合条件的股票，只选主板，剔除ST
使用 akshare 获取实时数据
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import sys
import time
import akshare as ak

sys.path.append(str(Path(__file__).parent))


def is_main_board(ts_code: str) -> bool:
    """
    判断是否为主板股票
    主板：000XXX、002XXX、001XXX（深圳），600XXX、601XXX、603XXX、605XXX（上海）
    排除：688XXX（科创板）、300XXX、301XXX（创业板）、8XXXXX、430XXX（北交所）
    """
    code = ts_code.split('.')[0]

    # 科创板
    if code.startswith('688'):
        return False

    # 创业板
    if code.startswith('300') or code.startswith('301'):
        return False

    # 北交所
    if code.startswith('8') or code.startswith('430'):
        return False

    # 主板代码
    # 深圳主板：000, 001, 002, 003
    # 上海主板：600, 601, 603, 605
    if (code.startswith('000') or code.startswith('001') or
        code.startswith('002') or code.startswith('003') or
        code.startswith('600') or code.startswith('601') or
        code.startswith('603') or code.startswith('605')):
        return True

    return False


def is_st_stock(name: str) -> bool:
    """判断是否为ST股票"""
    if not name:
        return False
    name = str(name).upper()
    return 'ST' in name or '*ST' in name or '退' in name


def get_main_board_spot() -> pd.DataFrame:
    """
    获取主板实时行情数据
    """
    print("获取实时行情数据...")

    all_stocks = []

    try:
        # 获取上海A股实时行情
        print("  获取上海A股...")
        sh_spot = ak.stock_sh_a_spot_em()
        for _, row in sh_spot.iterrows():
            code = str(row['代码'])
            ts_code = f"{code}.SH"
            if is_main_board(ts_code) and not is_st_stock(row['名称']):
                all_stocks.append({
                    'ts_code': ts_code,
                    'code': code,
                    'name': row['名称'],
                    'price': row['最新价'],
                    'change_pct': row['涨跌幅'],
                    'change': row['涨跌额'],
                    'open': row['今开'],
                    'high': row['最高'],
                    'low': row['最低'],
                    'pre_close': row['昨收'],
                    'volume': row['成交量'],
                    'turnover': row['换手率'],
                    'amplitude': row['振幅'],
                    'amount': row['成交额'],
                    'exchange': 'SH'
                })

        # 获取深圳A股实时行情
        print("  获取深圳A股...")
        sz_spot = ak.stock_sz_a_spot_em()
        for _, row in sz_spot.iterrows():
            code = str(row['代码'])
            ts_code = f"{code}.SZ"
            if is_main_board(ts_code) and not is_st_stock(row['名称']):
                all_stocks.append({
                    'ts_code': ts_code,
                    'code': code,
                    'name': row['名称'],
                    'price': row['最新价'],
                    'change_pct': row['涨跌幅'],
                    'change': row['涨跌额'],
                    'open': row['今开'],
                    'high': row['最高'],
                    'low': row['最低'],
                    'pre_close': row['昨收'],
                    'volume': row['成交量'],
                    'turnover': row['换手率'],
                    'amplitude': row['振幅'],
                    'amount': row['成交额'],
                    'exchange': 'SZ'
                })

    except Exception as e:
        print(f"获取行情失败: {e}")

    df = pd.DataFrame(all_stocks)
    print(f"\n获取到 {len(df)} 只主板非ST股票")

    return df


def calculate_morning_features(spot_df: pd.DataFrame, trade_time: str = "morning") -> pd.DataFrame:
    """
    根据实时行情数据计算上午特征

    当无法获取分钟数据时，使用实时行情的以下指标代替：
    - 开盘价相对昨收的跳空幅度 -> morning_gap_pct
    - 当前价相对昨收的涨幅 -> morning_return
    - 最高价相对开盘价的涨幅 -> morning_max_up
    - 最低价相对开盘价的跌幅 -> morning_max_down
    - 当前价在高低点区间位置 -> close_position
    """
    df = spot_df.copy()

    # 计算特征
    df['morning_gap_pct'] = ((df['open'] - df['pre_close']) / df['pre_close'] * 100).round(4)
    df['morning_return'] = ((df['price'] - df['pre_close']) / df['pre_close'] * 100).round(4)
    df['morning_change'] = ((df['price'] - df['open']) / df['open'] * 100).round(4)

    # 估算最大上涨/下跌（基于最高价/最低价）
    df['morning_max_up'] = ((df['high'] - df['open']) / df['open'] * 100).round(4)
    df['morning_max_down'] = ((df['low'] - df['open']) / df['open'] * 100).round(4)
    df['morning_range'] = ((df['high'] - df['low']) / df['open'] * 100).round(4)

    # 当前价格在高低点区间的位置
    def calc_position(row):
        if row['high'] != row['low']:
            return (row['price'] - row['low']) / (row['high'] - row['low'])
        return 0.5

    df['close_position'] = df.apply(calc_position, axis=1).round(4)

    return df


def apply_screening_strategy(features_df: pd.DataFrame) -> pd.DataFrame:
    """
    应用筛选策略

    策略规则：
    1. 深跌反弹信号（morning_max_down < -2 且 close_position > 0.6）- 强势反弹
    2. 低开高走（morning_gap_pct < -1.5 且 morning_return > 0）- 逆转信号
    3. 量价齐升（换手率放大 且 morning_return > 0）- 资金关注
    4. 温和上涨（0 < morning_return < 4）- 稳健走势
    5. 避免高开低走（morning_gap_pct > 2 且 morning_return < 0）- 诱多陷阱
    6. 避免涨幅过大（morning_return > 6）- 追高风险
    7. 避免上午弱势（morning_return < -2）- 弱势信号
    8. 换手率适中（0.5% < turnover < 15%）- 流动性考虑
    """
    df = features_df.copy()

    # 初始化得分
    df['score'] = 50
    df['signals'] = ''

    # 规则1: 深跌反弹信号（强势）
    mask1 = (df['morning_max_down'] < -1.5) & (df['close_position'] > 0.6)
    df.loc[mask1, 'score'] += 25
    df.loc[mask1, 'signals'] += '深跌反弹|'

    # 规则2: 低开高走（强势）
    mask2 = (df['morning_gap_pct'] < -1) & (df['morning_return'] > 0)
    df.loc[mask2, 'score'] += 20
    df.loc[mask2, 'signals'] += '低开高走|'

    # 规则3: 量价齐升（换手率>3%且上涨）
    mask3 = (df['turnover'] > 3) & (df['morning_return'] > 0)
    df.loc[mask3, 'score'] += 15
    df.loc[mask3, 'signals'] += '量价齐升|'

    # 规则4: 温和上涨（避免涨停追高）
    mask4 = (df['morning_return'] > 0) & (df['morning_return'] < 4)
    df.loc[mask4, 'score'] += 10

    # 规则5: 负分规则 - 高开低走（风险信号）
    mask5 = (df['morning_gap_pct'] > 1.5) & (df['morning_return'] < 0)
    df.loc[mask5, 'score'] -= 30
    df.loc[mask5, 'signals'] += '⚠️高开低走|'

    # 规则6: 上午涨幅过大（追高风险）
    mask6 = df['morning_return'] > 6
    df.loc[mask6, 'score'] -= 20
    df.loc[mask6, 'signals'] += '⚠️涨幅过大|'

    # 规则7: 上午下跌
    mask7 = df['morning_return'] < -2
    df.loc[mask7, 'score'] -= 15
    df.loc[mask7, 'signals'] += '⚠️上午弱势|'

    # 规则8: 高换手率（风险信号，如果不是强势上涨）
    mask8 = df['turnover'] > 15
    df.loc[mask8 & (df['morning_return'] < 3), 'score'] -= 10

    # 规则9: 低换手率（流动性差）
    mask9 = df['turnover'] < 0.3
    df.loc[mask9, 'score'] -= 10

    # 规则10: 振幅过大（波动剧烈）
    mask10 = df['amplitude'] > 8
    df.loc[mask10, 'score'] -= 5
    df.loc[mask10, 'signals'] += '⚠️波动剧烈|'

    # 计算评级
    def get_rating(score):
        if score >= 70:
            return 'A-强烈推荐'
        elif score >= 60:
            return 'B-推荐关注'
        elif score >= 45:
            return 'C-中性观察'
        else:
            return 'D-暂不关注'

    df['rating'] = df['score'].apply(get_rating)

    # 清理signals末尾的|
    df['signals'] = df['signals'].str.rstrip('|')

    return df.sort_values('score', ascending=False)


def screen_today_main_board() -> pd.DataFrame:
    """
    筛选今日主板股票
    """
    trade_date = datetime.now().strftime('%Y%m%d')
    trade_time = datetime.now().strftime('%H:%M')

    print("="*80)
    print(f"今日主板股票筛选")
    print(f"日期: {trade_date}  时间: {trade_time}")
    print("="*80)
    print("\n【筛选条件】")
    print("- 仅主板股票（剔除科创板、创业板、北交所）")
    print("- 剔除ST股票")
    print("- 基于实时行情特征筛选")
    print()

    # 1. 获取主板实时行情
    spot_df = get_main_board_spot()
    if spot_df.empty:
        print("获取行情数据失败")
        return pd.DataFrame()

    # 2. 计算特征
    features_df = calculate_morning_features(spot_df)

    # 3. 应用策略
    result_df = apply_screening_strategy(features_df)

    # 4. 输出结果
    print("\n" + "="*80)
    print("筛选结果")
    print("="*80)

    # 按评级分组统计
    rating_counts = result_df['rating'].value_counts()
    print("\n【评级分布】")
    for rating in ['A-强烈推荐', 'B-推荐关注', 'C-中性观察', 'D-暂不关注']:
        count = rating_counts.get(rating, 0)
        print(f"  {rating}: {count} 只")

    # 推荐股票（A、B级）
    recommended = result_df[result_df['rating'].str.startswith(('A', 'B'))]

    if len(recommended) > 0:
        print(f"\n【推荐关注股票】({len(recommended)} 只)")
        print("-"*80)

        for idx, row in recommended.head(20).iterrows():
            signals_str = f" [{row['signals']}]" if row['signals'] else ""
            print(f"\n  {row['ts_code']} {row['name']}")
            print(f"    现价: {row['price']:.2f}  涨跌: {row['change_pct']:+.2f}%")
            print(f"    开盘跳空: {row['morning_gap_pct']:+.2f}%  最高涨幅: {row['morning_max_up']:+.2f}%")
            print(f"    换手率: {row['turnover']:.2f}%  得分: {row['score']}  评级: {row['rating']}{signals_str}")
    else:
        print("\n【暂无推荐股票】")

    # 风险股票（D级且有警示信号）
    risky = result_df[result_df['rating'].str.startswith('D')]
    risky_with_signals = risky[risky['signals'].str.contains('⚠️', na=False)]

    if len(risky_with_signals) > 0:
        print(f"\n\n【风险警示股票】(共{len(risky_with_signals)}只)")
        print("-"*80)
        for idx, row in risky_with_signals.head(10).iterrows():
            print(f"  {row['ts_code']} {row['name']}: 现价{row['price']:.2f} 涨跌{row['change_pct']:+.2f}% - {row['signals']}")

    # 统计信息
    print("\n\n【市场统计】")
    print(f"  主板非ST股票总数: {len(result_df)}")
    print(f"  平均涨跌: {result_df['change_pct'].mean():.2f}%")
    print(f"  上涨家数: {(result_df['change_pct'] > 0).sum()}")
    print(f"  下跌家数: {(result_df['change_pct'] < 0).sum()}")

    # 保存结果
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)

    output_file = output_dir / f"screening_mainboard_{trade_date}.csv"

    # 选择要保存的列
    save_cols = [
        'ts_code', 'code', 'name', 'price', 'change_pct', 'turnover',
        'morning_gap_pct', 'morning_return', 'morning_max_down',
        'close_position', 'score', 'rating', 'signals'
    ]
    result_df[save_cols].to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"\n完整结果已保存: {output_file}")

    return result_df


def print_top_picks(result_df: pd.DataFrame, n: int = 10):
    """打印精选股票"""
    if result_df.empty:
        return

    print("\n" + "="*80)
    print(f"Top {n} 精选股票")
    print("="*80)

    top = result_df.head(n)

    print(f"\n{'排名':<4} {'代码':<12} {'名称':<10} {'现价':>8} {'涨跌%':>8} {'得分':>6} {'评级':<12} {'关键信号'}")
    print("-"*80)

    for i, (_, row) in enumerate(top.iterrows(), 1):
        signals = row['signals'][:20] if row['signals'] else '-'
        print(f"{i:<4} {row['ts_code']:<12} {row['name']:<10} {row['price']:>8.2f} "
              f"{row['change_pct']:>8.2f} {row['score']:>6} {row['rating']:<12} {signals}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='今日主板股票筛选工具')
    parser.add_argument('--top', type=int, default=20, help='显示前N只股票')

    args = parser.parse_args()

    # 执行筛选
    result = screen_today_main_board()

    if not result.empty:
        # 打印精选
        print_top_picks(result, args.top)

        # 按评级分组输出
        print("\n\n按评级分组:")
        for rating in ['A-强烈推荐', 'B-推荐关注']:
            group = result[result['rating'] == rating]
            if len(group) > 0:
                print(f"\n{rating} ({len(group)}只):")
                for _, row in group.head(10).iterrows():
                    print(f"  {row['ts_code']} {row['name']} - 得分{row['score']} - {row['signals']}")

"""
今日股票筛选工具
基于策略筛选符合条件的股票，只选主板，剔除ST
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import sys
import pickle
import akshare as ak

sys.path.append(str(Path(__file__).parent))

from sina_minute import SinaMinuteManager, extract_sina_morning_features


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
    name = name.upper()
    return 'ST' in name or '*ST' in name or '退' in name


def get_all_main_board_stocks() -> pd.DataFrame:
    """
    获取所有A股列表，并筛选出主板股票
    """
    print("获取A股列表...")

    # 使用akshare获取股票列表
    try:
        # 获取上海A股
        sh_df = ak.stock_sh_a_spot_em()
        sh_df['exchange'] = 'SH'
        sh_df['ts_code'] = sh_df['代码'].astype(str) + '.SH'

        # 获取深圳A股
        sz_df = ak.stock_sz_a_spot_em()
        sz_df['exchange'] = 'SZ'
        sz_df['ts_code'] = sz_df['代码'].astype(str) + '.SZ'

        # 合并
        all_df = pd.concat([sh_df, sz_df], ignore_index=True)

        # 筛选主板
        all_df['is_main_board'] = all_df['ts_code'].apply(is_main_board)
        all_df['is_st'] = all_df['名称'].apply(is_st_stock)

        main_board = all_df[
            (all_df['is_main_board'] == True) &
            (all_df['is_st'] == False)
        ].copy()

        print(f"总计A股: {len(all_df)} 只")
        print(f"主板股票: {len(main_board)} 只")
        print(f"剔除ST: {all_df['is_st'].sum()} 只")

        return main_board[['ts_code', '代码', '名称', 'exchange', '最新价', '涨跌幅', '换手率']]

    except Exception as e:
        print(f"获取股票列表失败: {e}")
        return pd.DataFrame()


def apply_screening_strategy(features_df: pd.DataFrame) -> pd.DataFrame:
    """
    应用筛选策略

    策略规则：
    1. 上午深跌反弹信号（morning_max_down < -2 且 close_position > 0.6）
    2. 低开高走（morning_gap_pct < -1.5 且 morning_return > 0）
    3. 量价齐升（vol_distribution > 1.2 且 morning_return > 0）
    4. 避免高开低走（morning_gap_pct > 2 且 morning_return < 0）
    5. 上午涨幅适中（0 < morning_return < 5，避免涨停追高风险）
    6. 换手率适中（1% < 换手率 < 15%，避免流动性问题）
    """
    df = features_df.copy()

    # 初始化得分
    df['score'] = 50
    df['signals'] = ''

    # 规则1: 深跌反弹信号（强势）
    mask1 = (df['morning_max_down'] < -2) & (df['close_position'] > 0.6)
    df.loc[mask1, 'score'] += 25
    df.loc[mask1, 'signals'] += '深跌反弹|'

    # 规则2: 低开高走（强势）
    mask2 = (df['morning_gap_pct'] < -1.5) & (df['morning_return'] > 0)
    df.loc[mask2, 'score'] += 20
    df.loc[mask2, 'signals'] += '低开高走|'

    # 规则3: 量价齐升
    mask3 = (df.get('vol_distribution', 0) > 1.2) & (df['morning_return'] > 0)
    df.loc[mask3, 'score'] += 15
    df.loc[mask3, 'signals'] += '量价齐升|'

    # 规则4: 温和上涨（避免涨停追高）
    mask4 = (df['morning_return'] > 0) & (df['morning_return'] < 5)
    df.loc[mask4, 'score'] += 10

    # 规则5: 负分规则 - 高开低走（风险信号）
    mask5 = (df['morning_gap_pct'] > 2) & (df['morning_return'] < 0)
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
    if '换手率' in df.columns:
        mask8 = df['换手率'] > 15
        df.loc[mask8 & (df['morning_return'] < 3), 'score'] -= 10

    # 规则9: 低换手率（流动性差）
    if '换手率' in df.columns:
        mask9 = df['换手率'] < 0.5
        df.loc[mask9, 'score'] -= 10

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


def screen_today_stocks(
    max_stocks: int = 100,
    trade_date: str = None
) -> pd.DataFrame:
    """
    筛选今日股票

    Args:
        max_stocks: 最多分析的股票数量
        trade_date: 交易日期 (YYYYMMDD)，None则使用今天
    """
    if trade_date is None:
        trade_date = datetime.now().strftime('%Y%m%d')

    print("="*80)
    print(f"今日股票筛选 - {trade_date}")
    print("="*80)
    print("\n【筛选条件】")
    print("- 仅主板股票（剔除科创板、创业板、北交所）")
    print("- 剔除ST股票")
    print("- 基于上午分钟数据特征筛选")
    print()

    # 1. 获取主板股票列表
    stocks_df = get_all_main_board_stocks()
    if stocks_df.empty:
        print("获取股票列表失败")
        return pd.DataFrame()

    # 限制数量（用于测试或快速筛选）
    if max_stocks and len(stocks_df) > max_stocks:
        print(f"\n为加快处理，随机选取 {max_stocks} 只股票进行分析")
        stocks_df = stocks_df.sample(n=max_stocks, random_state=42).reset_index(drop=True)

    ts_codes = stocks_df['ts_code'].tolist()
    print(f"\n开始分析 {len(ts_codes)} 只主板股票...")

    # 2. 获取上午分钟数据
    manager = SinaMinuteManager()
    all_features = []

    for i, ts_code in enumerate(ts_codes):
        if (i + 1) % 20 == 0:
            print(f"  进度: {i+1}/{len(ts_codes)}")

        # 获取分钟数据（优先从缓存）
        df = manager.download_minute_data(ts_code, trade_date, freq="5", use_cache=True)

        if df is not None and len(df) > 0:
            features = extract_sina_morning_features(df)
            if features:
                # 合并股票基本信息
                stock_info = stocks_df[stocks_df['ts_code'] == ts_code].iloc[0]
                features['name'] = stock_info['名称']
                features['latest_price'] = stock_info['最新价']
                features['change_pct'] = stock_info['涨跌幅']
                features['turnover'] = stock_info['换手率']
                all_features.append(features)

    if not all_features:
        print("\n未能获取任何股票的分钟数据")
        print("可能原因：")
        print("  1. 今日非交易日")
        print("  2. 交易时间尚未结束（需要11:30后才有完整上午数据）")
        print("  3. 网络连接问题")
        return pd.DataFrame()

    print(f"\n成功获取 {len(all_features)} 只股票的上午数据")

    # 3. 创建DataFrame并应用策略
    features_df = pd.DataFrame(all_features)
    result_df = apply_screening_strategy(features_df)

    # 4. 输出结果
    print("\n" + "="*80)
    print("筛选结果")
    print("="*80)

    # 按评级分组统计
    rating_counts = result_df['rating'].value_counts()
    print("\n【评级分布】")
    for rating, count in rating_counts.items():
        print(f"  {rating}: {count} 只")

    # 推荐股票（A、B级）
    recommended = result_df[result_df['rating'].str.startswith(('A', 'B'))]

    if len(recommended) > 0:
        print(f"\n【推荐关注股票】({len(recommended)} 只)")
        print("-"*80)

        display_cols = [
            'ts_code', 'name', 'morning_return', 'morning_gap_pct',
            'morning_max_down', 'close_position', 'score', 'rating', 'signals'
        ]

        for idx, row in recommended.head(20).iterrows():
            print(f"\n  代码: {row['ts_code']} ({row['name']})")
            print(f"  上午涨幅: {row['morning_return']:+.2f}%  开盘跳空: {row['morning_gap_pct']:+.2f}%")
            print(f"  最大跌幅: {row['morning_max_down']:+.2f}%  收盘位置: {row['close_position']:.2f}")
            print(f"  得分: {row['score']}  评级: {row['rating']}")
            if row['signals']:
                print(f"  信号: {row['signals']}")
    else:
        print("\n【暂无推荐股票】")

    # 风险股票
    risky = result_df[result_df['rating'].str.startswith('D')]
    if len(risky) > 0:
        print(f"\n\n【风险警示股票】(得分较低，共{len(risky)}只)")
        print("-"*80)
        for idx, row in risky.head(10).iterrows():
            if row['signals'] and '⚠️' in str(row['signals']):
                print(f"  {row['ts_code']} ({row['name']}): {row['signals']}")

    # 保存结果
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)

    output_file = output_dir / f"screening_{trade_date}.csv"
    result_df.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"\n\n完整结果已保存: {output_file}")

    return result_df


def quick_screen_from_cache(trade_date: str = None) -> pd.DataFrame:
    """
    从缓存数据中快速筛选（不下载新数据）
    """
    if trade_date is None:
        trade_date = datetime.now().strftime('%Y%m%d')

    cache_dir = Path("data/sina_minute_cache")

    if not cache_dir.exists():
        print("缓存目录不存在")
        return pd.DataFrame()

    # 查找缓存文件
    cache_files = list(cache_dir.glob(f"*_{trade_date}.pkl"))

    if not cache_files:
        print(f"未找到 {trade_date} 的缓存数据")
        # 尝试找最近的日期
        all_files = list(cache_dir.glob("*.pkl"))
        if all_files:
            dates = sorted(set(f.stem.split('_')[-1] for f in all_files), reverse=True)
            print(f"可用日期: {', '.join(dates[:5])}")
        return pd.DataFrame()

    print(f"找到 {len(cache_files)} 只股票的缓存数据")

    all_features = []

    for cache_file in cache_files:
        try:
            with open(cache_file, 'rb') as f:
                df = pickle.load(f)

            features = extract_sina_morning_features(df)
            if features:
                # 从文件名解析ts_code
                parts = cache_file.stem.split('_')
                code = parts[0]
                exchange = parts[1]
                features['ts_code'] = f"{code}.{exchange}"
                all_features.append(features)
        except Exception as e:
            continue

    if not all_features:
        print("无法从缓存提取特征")
        return pd.DataFrame()

    features_df = pd.DataFrame(all_features)
    result_df = apply_screening_strategy(features_df)

    return result_df


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='今日股票筛选工具')
    parser.add_argument('--date', type=str, help='指定日期 (YYYYMMDD)')
    parser.add_argument('--max', type=int, default=100, help='最大分析股票数')
    parser.add_argument('--cache-only', action='store_true', help='仅使用缓存数据')

    args = parser.parse_args()

    if args.cache_only:
        result = quick_screen_from_cache(args.date)
    else:
        result = screen_today_stocks(
            max_stocks=args.max,
            trade_date=args.date
        )

    if not result.empty:
        print("\n\nTop 10 股票:")
        print(result[['ts_code', 'morning_return', 'score', 'rating']].head(10).to_string())

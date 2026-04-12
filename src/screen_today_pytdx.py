"""
今日主板股票筛选 - Pytdx分钟数据版
使用 pytdx 获取今日上午分钟行情进行筛选
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import sys
import tushare as ts

sys.path.append(str(Path(__file__).parent))

from pytdx_minute import PytdxMinuteManager

# Tushare token (用于获取股票列表)
TUSHARE_TOKEN = "fd6cf8fc8404cf6f93ca6091c1e603d9bc3a65f5a536c77dbb882e60"
ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()


def is_main_board(ts_code: str) -> bool:
    """判断是否为主板股票"""
    code = ts_code.split('.')[0]

    if code.startswith('688'):
        return False
    if code.startswith('300') or code.startswith('301'):
        return False
    if code.startswith('8') or code.startswith('430'):
        return False

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


def get_main_board_stock_list() -> pd.DataFrame:
    """获取主板股票列表"""
    print("获取主板股票列表...")

    try:
        all_stocks = pro.stock_basic(exchange='', list_status='L')
        all_stocks['ts_code'] = all_stocks['ts_code'].astype(str)

        all_stocks['is_main_board'] = all_stocks['ts_code'].apply(is_main_board)
        all_stocks['is_st'] = all_stocks['name'].apply(is_st_stock)

        main_board = all_stocks[
            (all_stocks['is_main_board'] == True) &
            (all_stocks['is_st'] == False)
        ].copy()

        print(f"主板非ST股票: {len(main_board)} 只")
        return main_board[['ts_code', 'name', 'industry']]

    except Exception as e:
        print(f"获取股票列表失败: {e}")
        return pd.DataFrame()


def code_to_pytdx(ts_code: str) -> tuple:
    """将ts_code转换为pytdx格式"""
    code, exchange = ts_code.split('.')
    market = 0 if exchange == 'SZ' else 1
    return market, code


def extract_morning_features(minute_df: pd.DataFrame, today_str: str = None) -> Optional[Dict]:
    """从分钟数据提取上午特征 (9:30-11:30)"""
    if minute_df is None or len(minute_df) < 10:
        return None

    df = minute_df.copy()

    if 'datetime' not in df.columns:
        return None

    if today_str is None:
        today_str = datetime.now().strftime('%Y-%m-%d')

    # 从datetime提取时间
    df['dt'] = pd.to_datetime(df['datetime'])
    df['time_str'] = df['dt'].dt.strftime('%H:%M')
    df['date'] = df['dt'].dt.strftime('%Y-%m-%d')

    # 获取昨收价（从昨天最后一条数据）
    yesterday_df = df[df['date'] != today_str]
    if len(yesterday_df) > 0:
        pre_close = yesterday_df.iloc[-1]['close']
    else:
        # 如果没有昨天数据，用今天开盘价的估算
        today_df = df[df['date'] == today_str]
        pre_close = today_df.iloc[0]['open'] if len(today_df) > 0 else df.iloc[0]['open']

    # 过滤今日上午数据 (9:30-11:30)
    today_df = df[df['date'] == today_str].copy()
    morning_mask = (today_df['time_str'] >= '09:30') & (today_df['time_str'] <= '11:30')
    morning_df = today_df[morning_mask].copy()

    if len(morning_df) < 5:
        return None

    morning_df = morning_df.sort_values('dt')

    open_price = morning_df.iloc[0]['open']
    high = morning_df['high'].max()
    low = morning_df['low'].min()
    close = morning_df.iloc[-1]['close']

    # 计算相对昨收的涨跌幅
    morning_gap_pct = ((open_price - pre_close) / pre_close * 100) if pre_close > 0 else 0
    morning_return = ((close - pre_close) / pre_close * 100) if pre_close > 0 else 0

    # 计算相对开盘价的盘中波动（用于判断深跌反弹）
    morning_max_up = ((high - open_price) / open_price * 100) if open_price > 0 else 0
    morning_max_down = ((low - open_price) / open_price * 100) if open_price > 0 else 0

    if high != low:
        close_position = (close - low) / (high - low)
    else:
        close_position = 0.5

    total_vol = morning_df['vol'].sum() if 'vol' in morning_df.columns else morning_df['volume'].sum()
    amplitude = ((high - low) / pre_close * 100) if pre_close > 0 else 0

    return {
        'morning_gap_pct': round(morning_gap_pct, 4),
        'morning_return': round(morning_return, 4),
        'morning_max_up': round(morning_max_up, 4),
        'morning_max_down': round(morning_max_down, 4),
        'close_position': round(close_position, 4),
        'morning_high': high,
        'morning_low': low,
        'morning_close': close,
        'pre_close': pre_close,
        'open_price': open_price,
        'morning_vol': total_vol,
        'amplitude': round(amplitude, 4),
    }


def apply_screening_strategy(features_df: pd.DataFrame) -> pd.DataFrame:
    """应用筛选策略"""
    df = features_df.copy()

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
    mask3 = (df['morning_return'] > 0) & (df['morning_vol'] > df['morning_vol'].median())
    df.loc[mask3, 'score'] += 15
    df.loc[mask3, 'signals'] += '量价齐升|'

    # 规则4: 温和上涨
    mask4 = (df['morning_return'] > 0) & (df['morning_return'] < 5)
    df.loc[mask4, 'score'] += 10

    # 规则5: 高开低走
    mask5 = (df['morning_gap_pct'] > 1.5) & (df['morning_return'] < 0)
    df.loc[mask5, 'score'] -= 30
    df.loc[mask5, 'signals'] += '⚠️高开低走|'

    # 规则6: 涨幅过大
    mask6 = df['morning_return'] > 6
    df.loc[mask6, 'score'] -= 20
    df.loc[mask6, 'signals'] += '⚠️涨幅过大|'

    # 规则7: 上午下跌
    mask7 = df['morning_return'] < -2
    df.loc[mask7, 'score'] -= 15
    df.loc[mask7, 'signals'] += '⚠️上午弱势|'

    # 规则8: 振幅过大
    mask8 = df['amplitude'] > 8
    df.loc[mask8, 'score'] -= 5
    df.loc[mask8, 'signals'] += '⚠️波动剧烈|'

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
    df['signals'] = df['signals'].str.rstrip('|')

    return df.sort_values('score', ascending=False)


def screen_today_with_pytdx(max_stocks: int = 200):
    """使用pytdx分钟数据筛选今日股票"""
    today = datetime.now().strftime('%Y%m%d')

    print("="*80)
    print(f"今日主板股票筛选 - Pytdx分钟数据版")
    print(f"日期: {today}")
    print("="*80)
    print()

    stocks_df = get_main_board_stock_list()
    if stocks_df.empty:
        print("获取股票列表失败")
        return pd.DataFrame()

    if max_stocks and len(stocks_df) > max_stocks:
        print(f"为加快处理，选取前 {max_stocks} 只股票")
        stocks_df = stocks_df.head(max_stocks).reset_index(drop=True)

    print("\n连接通达信服务器...")
    manager = PytdxMinuteManager()
    if not manager.connect():
        print("连接通达信服务器失败")
        return pd.DataFrame()
    print("连接成功")

    all_features = []

    print(f"\n获取 {len(stocks_df)} 只股票的分钟数据...")
    for i, row in stocks_df.iterrows():
        ts_code = row['ts_code']
        name = row['name']

        if (i + 1) % 50 == 0:
            print(f"  进度: {i+1}/{len(stocks_df)}")

        try:
            market, code = code_to_pytdx(ts_code)

            minute_data = manager.api.get_security_bars(
                category=0,
                market=market,
                code=code,
                start=0,
                count=48
            )

            if minute_data:
                df = manager.api.to_df(minute_data)

                today_str = datetime.now().strftime('%Y-%m-%d')
                df['date'] = pd.to_datetime(df['datetime']).dt.strftime('%Y-%m-%d')
                today_df = df[df['date'] == today_str]

                if len(today_df) >= 5:
                    # 传入完整df（含昨天数据）以便计算昨收价
                    features = extract_morning_features(df, today_str)
                    if features:
                        features['ts_code'] = ts_code
                        features['name'] = name
                        all_features.append(features)

        except Exception as e:
            continue

    manager.disconnect()

    if not all_features:
        print("\n未能获取今日分钟数据")
        print("可能原因：")
        print("  1. 今日非交易日")
        print("  2. 交易时间尚未开始")
        print("  3. pytdx连接问题")
        return pd.DataFrame()

    print(f"\n成功获取 {len(all_features)} 只股票的上午数据")

    features_df = pd.DataFrame(all_features)
    result_df = apply_screening_strategy(features_df)

    print("\n" + "="*80)
    print("筛选结果")
    print("="*80)

    rating_counts = result_df['rating'].value_counts()
    print("\n【评级分布】")
    for rating in ['A-强烈推荐', 'B-推荐关注', 'C-中性观察', 'D-暂不关注']:
        count = rating_counts.get(rating, 0)
        print(f"  {rating}: {count} 只")

    recommended = result_df[result_df['rating'].str.startswith(('A', 'B'))]

    if len(recommended) > 0:
        print(f"\n【推荐关注股票】({len(recommended)} 只)")
        print("-"*80)

        for idx, row in recommended.head(20).iterrows():
            signals_str = f" [{row['signals']}]" if row['signals'] else ""
            print(f"\n  {row['ts_code']} {row['name']}")
            print(f"    上午涨幅: {row['morning_return']:+.2f}%  开盘跳空: {row['morning_gap_pct']:+.2f}%")
            print(f"    最大下探: {row['morning_max_down']:+.2f}%  收盘位置: {row['close_position']:.2f}")
            print(f"    得分: {row['score']}  评级: {row['rating']}{signals_str}")
    else:
        print("\n【暂无推荐股票】")

    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)

    output_file = output_dir / f"screening_pytdx_{today}.csv"
    result_df.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"\n完整结果已保存: {output_file}")

    return result_df


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='今日股票筛选 - Pytdx分钟数据版')
    parser.add_argument('--max', type=int, default=300, help='最大分析股票数')

    args = parser.parse_args()

    result = screen_today_with_pytdx(max_stocks=args.max)

    if not result.empty:
        print("\n\nTop 20 精选股票:")
        print(result[['ts_code', 'name', 'morning_return', 'score', 'rating']].head(20).to_string())

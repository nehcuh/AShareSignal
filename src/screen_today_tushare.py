"""
今日主板股票筛选 - Tushare版本
获取今日行情数据并进行策略筛选
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import sys
import tushare as ts

# Tushare token
TUSHARE_TOKEN = "fd6cf8fc8404cf6f93ca6091c1e603d9bc3a65f5a536c77dbb882e60"
ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()


def is_main_board(ts_code: str) -> bool:
    """判断是否为主板股票"""
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


def get_today_spot() -> pd.DataFrame:
    """获取今日实时行情（使用Tushare pro.daily或pro.query）"""
    print("获取今日行情数据...")

    today = datetime.now().strftime('%Y%m%d')

    try:
        # 获取所有A股实时行情
        print("  从Tushare获取股票列表...")
        all_stocks = pro.stock_basic(exchange='', list_status='L')
        all_stocks['ts_code'] = all_stocks['ts_code'].astype(str)

        # 筛选主板
        all_stocks['is_main_board'] = all_stocks['ts_code'].apply(is_main_board)
        all_stocks['is_st'] = all_stocks['name'].apply(is_st_stock)

        main_board = all_stocks[
            (all_stocks['is_main_board'] == True) &
            (all_stocks['is_st'] == False)
        ].copy()

        print(f"主板股票: {len(main_board)} 只")

        # 获取今日行情数据
        print(f"  获取 {today} 行情数据...")

        # 获取日线数据
        daily_df = pro.daily(trade_date=today)

        if daily_df is None or len(daily_df) == 0:
            # 可能没有今日数据，尝试昨日
            print(f"今日 {today} 无数据，尝试获取最近交易日...")
            cal = pro.trade_cal(exchange='SSE', start_date=today, end_date=today)
            if cal is not None and len(cal) > 0:
                if cal.iloc[0]['is_open'] == 0:
                    print("今日非交易日")
                    return pd.DataFrame()

            # 尝试获取昨日数据作为参考
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
            daily_df = pro.daily(trade_date=yesterday)
            print(f"使用昨日数据: {yesterday}")

        if daily_df is None or len(daily_df) == 0:
            print("无法获取行情数据")
            return pd.DataFrame()

        # 合并数据
        daily_df['ts_code'] = daily_df['ts_code'].astype(str)
        merged = main_board[['ts_code', 'name']].merge(
            daily_df, on='ts_code', how='inner'
        )

        print(f"获取到 {len(merged)} 只主板股票行情")

        return merged

    except Exception as e:
        print(f"获取行情失败: {e}")
        import traceback
        traceback.print_exc()
        return pd.DataFrame()


def get_limit_up_stocks(trade_date: str) -> List[str]:
    """获取涨停股票列表"""
    try:
        limit_df = pro.limit_list(trade_date=trade_date)
        if limit_df is not None and len(limit_df) > 0:
            # 只取涨停的（剔除跌停）
            limit_up = limit_df[limit_df['limit'] == 'U']['ts_code'].tolist()
            return limit_up
    except Exception as e:
        print(f"获取涨停列表失败: {e}")
    return []


def calculate_features(df: pd.DataFrame) -> pd.DataFrame:
    """计算特征"""
    result = df.copy()

    # 当日涨跌幅就是 morning_return（全天数据）
    result['morning_return'] = result['pct_chg']

    # 计算开盘跳空幅度 (假设用(open - pre_close) / pre_close)
    # 注意：日线数据中没有 pre_close，用 open 和 close 估算
    result['morning_gap_pct'] = ((result['open'] - result['pre_close']) / result['pre_close'] * 100).round(4)

    # 估算最大下跌（基于最低价相对开盘价）
    result['morning_max_down'] = ((result['low'] - result['open']) / result['open'] * 100).round(4)
    result['morning_max_up'] = ((result['high'] - result['open']) / result['open'] * 100).round(4)

    # 估算收盘位置（在高低点区间中的位置）
    def calc_position(row):
        if row['high'] != row['low']:
            return (row['close'] - row['low']) / (row['high'] - row['low'])
        return 0.5

    result['close_position'] = result.apply(calc_position, axis=1).round(4)

    # 振幅
    result['amplitude'] = ((result['high'] - result['low']) / result['open'] * 100).round(4)

    return result


def apply_screening_strategy(features_df: pd.DataFrame) -> pd.DataFrame:
    """应用筛选策略"""
    df = features_df.copy()

    # 初始化得分
    df['score'] = 50
    df['signals'] = ''

    # 规则1: 深跌反弹信号（强势）- 日内有较深回调但最终收高
    mask1 = (df['morning_max_down'] < -2) & (df['close_position'] > 0.6)
    df.loc[mask1, 'score'] += 25
    df.loc[mask1, 'signals'] += '深跌反弹|'

    # 规则2: 低开高走（强势）- 开盘跳空低开但全天收涨
    mask2 = (df['morning_gap_pct'] < -1) & (df['morning_return'] > 0)
    df.loc[mask2, 'score'] += 20
    df.loc[mask2, 'signals'] += '低开高走|'

    # 规则3: 量价齐升（成交额放大且上涨）
    # 用换手率和涨幅判断
    mask3 = (df.get('turnover_rate', 0) > 3) & (df['morning_return'] > 0)
    df.loc[mask3, 'score'] += 15
    df.loc[mask3, 'signals'] += '量价齐升|'

    # 规则4: 温和上涨（避免涨停追高）
    mask4 = (df['morning_return'] > 0) & (df['morning_return'] < 6)
    df.loc[mask4, 'score'] += 10

    # 规则5: 负分规则 - 高开低走（风险信号）
    mask5 = (df['morning_gap_pct'] > 1.5) & (df['morning_return'] < 0)
    df.loc[mask5, 'score'] -= 30
    df.loc[mask5, 'signals'] += '⚠️高开低走|'

    # 规则6: 涨幅过大（追高风险）
    mask6 = df['morning_return'] > 9
    df.loc[mask6, 'score'] -= 20
    df.loc[mask6, 'signals'] += '⚠️涨幅过大|'

    # 规则7: 下跌
    mask7 = df['morning_return'] < -2
    df.loc[mask7, 'score'] -= 15
    df.loc[mask7, 'signals'] += '⚠️弱势|'

    # 规则8: 高换手率（风险信号，如果不是强势上涨）
    if 'turnover_rate' in df.columns:
        mask8 = df['turnover_rate'] > 15
        df.loc[mask8 & (df['morning_return'] < 3), 'score'] -= 10

    # 规则9: 低换手率（流动性差）
    if 'turnover_rate' in df.columns:
        mask9 = df['turnover_rate'] < 0.3
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


def screen_today_mainboard():
    """今日主板筛选主函数"""
    today = datetime.now().strftime('%Y%m%d')

    print("="*80)
    print(f"今日主板股票筛选 - Tushare版")
    print(f"日期: {today}")
    print("="*80)
    print()

    # 获取行情数据
    spot_df = get_today_spot()
    if spot_df.empty:
        print("获取行情数据失败")
        return pd.DataFrame()

    # 计算特征
    features_df = calculate_features(spot_df)

    # 应用策略
    result_df = apply_screening_strategy(features_df)

    # 输出结果
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

        display_cols = ['ts_code', 'name', 'close', 'pct_chg', 'score', 'rating', 'signals']
        for idx, row in recommended.head(20).iterrows():
            signals_str = f" [{row['signals']}]" if row['signals'] else ""
            print(f"\n  {row['ts_code']} {row['name']}")
            print(f"    现价: {row['close']:.2f}  涨跌: {row['pct_chg']:+.2f}%")
            print(f"    开盘跳空: {row['morning_gap_pct']:+.2f}%  最大下探: {row['morning_max_down']:+.2f}%")
            print(f"    收盘位置: {row['close_position']:.2f}  得分: {row['score']}  评级: {row['rating']}{signals_str}")
    else:
        print("\n【暂无推荐股票】")

    # 统计信息
    print("\n\n【市场统计】")
    print(f"  主板非ST股票总数: {len(result_df)}")
    print(f"  平均涨跌: {result_df['pct_chg'].mean():.2f}%")
    print(f"  上涨家数: {(result_df['pct_chg'] > 0).sum()}")
    print(f"  下跌家数: {(result_df['pct_chg'] < 0).sum()}")

    # 保存结果
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)

    output_file = output_dir / f"screening_mainboard_{today}.csv"

    # 选择要保存的列
    save_cols = [
        'ts_code', 'name', 'close', 'pct_chg', 'open', 'high', 'low',
        'morning_gap_pct', 'morning_return', 'morning_max_down',
        'close_position', 'score', 'rating', 'signals'
    ]
    available_cols = [c for c in save_cols if c in result_df.columns]
    result_df[available_cols].to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"\n完整结果已保存: {output_file}")

    return result_df


if __name__ == "__main__":
    result = screen_today_mainboard()

    if not result.empty:
        print("\n\nTop 20 精选股票:")
        print(result[['ts_code', 'name', 'pct_chg', 'score', 'rating']].head(20).to_string())

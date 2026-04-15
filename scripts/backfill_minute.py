"""
用 pytdx 分钟数据对日线粗筛候选精确重算
复现 screen_mainboard_today.py 的盘中快照评分逻辑
"""
import os, sys, pandas as pd, numpy as np, argparse
from datetime import time, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from pytdx_minute import PytdxMinuteManager

def simulate_morning_snapshot(minute_df, pre_close, snapshot_time=time(11,30)):
    """
    用分钟数据模拟盘中快照
    截取到 snapshot_time 为止的行情，计算 morning features
    """
    df = minute_df[minute_df['time'] <= snapshot_time].copy()
    if len(df) == 0:
        return None
    
    # 盘中实时价 = 最后一根K线的收盘价
    price = float(df.iloc[-1]['close'])
    
    # 开盘价 = 第一根K线的开盘价
    open_price = float(df.iloc[0]['open'])
    
    # 盘中最高/最低
    high = float(df['high'].max())
    low = float(df['low'].min())
    
    # 计算特征
    morning_gap_pct = (open_price - pre_close) / pre_close * 100
    morning_return = (price - pre_close) / pre_close * 100
    morning_max_down = (low - open_price) / open_price * 100
    morning_max_up = (high - open_price) / open_price * 100
    
    if high != low:
        close_position = (price - low) / (high - low)
    else:
        close_position = 0.5
    
    amplitude = (high - low) / pre_close * 100
    
    # 换手率用日线数据（分钟数据无法直接计算）
    # 成交量
    total_vol = float(df['vol'].sum())  # 手
    
    return {
        'price': round(price, 2),
        'open': round(open_price, 2),
        'high': round(high, 2),
        'low': round(low, 2),
        'pre_close': round(pre_close, 2),
        'morning_gap_pct': round(morning_gap_pct, 4),
        'morning_return': round(morning_return, 4),
        'morning_max_down': round(morning_max_down, 4),
        'morning_max_up': round(morning_max_up, 4),
        'close_position': round(close_position, 4),
        'amplitude': round(amplitude, 4),
        'vol': total_vol,
    }


def apply_screening(features, turnover=0):
    """应用评分策略"""
    score = 50
    signals = []
    
    # 规则1: 深跌反弹
    if features['morning_max_down'] < -1.5 and features['close_position'] > 0.6:
        score += 25
        signals.append('深跌反弹')
    
    # 规则2: 低开高走
    if features['morning_gap_pct'] < -1 and features['morning_return'] > 0:
        score += 20
        signals.append('低开高走')
    
    # 规则3: 量价齐升
    if turnover > 3 and features['morning_return'] > 0:
        score += 15
        signals.append('量价齐升')
    
    # 规则4: 温和上涨
    if 0 < features['morning_return'] < 4:
        score += 10
    
    # 规则5: 高开低走
    if features['morning_gap_pct'] > 1.5 and features['morning_return'] < 0:
        score -= 30
        signals.append('⚠️高开低走')
    
    # 规则6: 涨幅过大
    if features['morning_return'] > 6:
        score -= 20
        signals.append('⚠️涨幅过大')
    
    # 规则7: 弱势
    if features['morning_return'] < -2:
        score -= 15
        signals.append('⚠️弱势')
    
    # 规则8: 高换手率
    if turnover > 15 and features['morning_return'] < 3:
        score -= 10
    
    # 规则9: 低换手率
    if turnover < 0.3:
        score -= 10
    
    # 规则10: 振幅过大
    if features['amplitude'] > 8:
        score -= 5
        signals.append('⚠️波动剧烈')
    
    def get_rating(s):
        if s >= 70: return 'A'
        elif s >= 60: return 'B'
        elif s >= 45: return 'C'
        else: return 'D'
    
    return score, get_rating(score), '|'.join(signals)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', type=str, default=datetime.today().strftime('%Y%m%d'), help='交易日日期，格式YYYYMMDD，默认今天')
    args = parser.parse_args()
    trade_date = args.date

    # 读取日线粗筛结果
    daily_path = f'output/screening_{trade_date}_daily_approx.csv'
    daily_df = pd.read_csv(daily_path)
    
    # 取日线 Top 50 候选
    candidates = daily_df.head(50)
    
    # 初始化 pytdx
    mgr = PytdxMinuteManager()
    
    # 还需要前收盘价 —— 用日线 pre_close
    # 也需要日线换手率
    
    results = []
    
    print(f"对 {len(candidates)} 只候选股进行分钟级精确重算...")
    print(f"{'代码':<12} {'名称':<10} {'日分':>4} {'精分':>4} {'日评级':>4} {'精评级':>4} {'信号(精确)'}")
    print("-"*80)
    
    for _, row in candidates.iterrows():
        ts_code = row['ts_code']
        name = str(row.get('name', ''))[:8]
        pre_close = row['pre_close']
        turnover = row.get('turnover_rate', 0)
        daily_score = row['score']
        daily_rating = row['rating']
        
        # 获取分钟数据
        minute_df = mgr.download_minute_data(ts_code, trade_date, freq='5', use_cache=True)
        
        if minute_df is None or len(minute_df) == 0:
            print(f"{ts_code:<12} {name:<10} {daily_score:>4} ---- 分钟数据缺失")
            continue
        
        # 模拟上午收盘快照
        features = simulate_morning_snapshot(minute_df, pre_close, snapshot_time=time(11,30))
        if features is None:
            continue
        
        score, rating, signals = apply_screening(features, turnover)
        
        diff = score - daily_score
        diff_str = f"{'+' if diff > 0 else ''}{diff}" if diff != 0 else "="
        
        print(f"{ts_code:<12} {name:<10} {daily_score:>4} -> {score:>4} {daily_rating:>4} -> {rating:>4} {diff_str:>3} {signals}")
        
        results.append({
            'ts_code': ts_code,
            'name': name,
            'pre_close': pre_close,
            'daily_score': daily_score,
            'minute_score': score,
            'daily_rating': daily_rating,
            'minute_rating': rating,
            'signals': signals,
            **features,
            'turnover': turnover,
        })
    
    mgr.disconnect()
    
    # 保存结果
    if results:
        result_df = pd.DataFrame(results)
        result_df = result_df.sort_values('minute_score', ascending=False)
        output_path = f'output/screening_{trade_date}_minute_precise.csv'
        result_df.to_csv(output_path, index=False, encoding='utf-8-sig')
        
        print(f"\n\n{'='*80}")
        print("分钟级精确评分 Top 20:")
        print(f"{'#':<3} {'代码':<12} {'名称':<10} {'精分':>4} {'评级':>3} {'涨跌%':>7} {'换手%':>5} {'信号'}")
        print("-"*70)
        for i, (_, r) in enumerate(result_df.head(20).iterrows(), 1):
            print(f"{i:<3} {r['ts_code']:<12} {r['name']:<10} {r['minute_score']:>4} {r['minute_rating']:>3} {r['morning_return']:>+6.2f}% {r['turnover']:>4.1f} {r['signals']}")
        
        print(f"\n精确结果已保存: {output_path}")

if __name__ == '__main__':
    main()

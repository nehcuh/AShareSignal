"""
Signal-2: 拉 Top20 精确评分股票 03-26→04-14 的实际表现
计算：区间涨幅、最大涨幅、最大回撤、波动率
"""
import os, requests, pandas as pd, numpy as np
from pathlib import Path

def tushare_api(token, api_name, params):
    url = 'https://api.tushare.pro'
    payload = {'api_name': api_name, 'token': token, 'params': params, 'fields': ''}
    r = requests.post(url, json=payload, timeout=60)
    data = r.json()
    if data.get('code') == 0:
        return data['data']
    print(f"  Error: {data.get('msg')}")
    return None

def main():
    token = os.environ.get('TUSHARE_TOKEN', '')
    
    # 读取分钟级精确结果
    precise = pd.read_csv('output/screening_20260326_minute_precise.csv')
    precise = precise.sort_values('minute_score', ascending=False)
    
    # 取精确评分 Top 20
    top20 = precise.head(20)
    ts_codes = top20['ts_code'].tolist()
    
    print(f"获取 {len(ts_codes)} 只股票 03-26→04-14 日线数据...")
    
    all_daily = []
    for code in ts_codes:
        result = tushare_api(token, 'daily', {
            'ts_code': code,
            'start_date': '20260326',
            'end_date': '20260414',
        })
        if result and result.get('items'):
            df = pd.DataFrame(result['items'], columns=result['fields'])
            for col in ['open','high','low','close','pre_close','pct_chg','vol','amount']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            all_daily.append(df)
    
    print(f"获取到 {len(all_daily)} 只股票数据")
    
    # 计算每只股票的表现
    performance = []
    for code in ts_codes:
        stock_daily = [df for df in all_daily if df['ts_code'].iloc[0] == code]
        if not stock_daily:
            continue
        df = stock_daily[0].sort_values('trade_date')
        
        if len(df) == 0:
            continue
        
        # 基准价格：03-26 收盘
        base_row = df[df['trade_date'] == '20260326']
        if len(base_row) == 0:
            base_close = float(df.iloc[0]['close'])
            base_date = df.iloc[0]['trade_date']
        else:
            base_close = float(base_row.iloc[0]['close'])
            base_date = '20260326'
        
        # 03-26 盘中快照价（精确）
        minute_row = top20[top20['ts_code'] == code]
        snapshot_price = float(minute_row.iloc[0]['price']) if len(minute_row) > 0 else base_close
        
        # 区间最高/最低
        max_close = float(df['close'].max())
        min_close = float(df['close'].min())
        max_date = df.loc[df['close'].idxmax(), 'trade_date']
        min_date = df.loc[df['close'].idxmin(), 'trade_date']
        
        # 最后一天收盘
        end_close = float(df.iloc[-1]['close'])
        end_date = df.iloc[-1]['trade_date']
        
        # 涨跌幅
        total_return = (end_close - base_close) / base_close * 100
        
        # 最大涨幅（从03-26收盘到区间最高点）
        max_gain = (max_close - base_close) / base_close * 100
        
        # 最大回撤（从区间最高点到最低点）
        max_drawdown = (min_close - max_close) / max_close * 100
        
        # 从快照价计算的收益
        snapshot_return = (end_close - snapshot_price) / snapshot_price * 100
        
        # 日收益率波动率
        daily_returns = df['pct_chg'].values
        volatility = np.std(daily_returns) if len(daily_returns) > 1 else 0
        
        # 上涨天数/总天数
        up_days = (df['pct_chg'] > 0).sum()
        total_days = len(df)
        up_ratio = up_days / total_days if total_days > 0 else 0
        
        # 连续下跌最大天数
        pct_list = df['pct_chg'].values
        max_consec_down = 0
        current_down = 0
        for p in pct_list:
            if p < 0:
                current_down += 1
                max_consec_down = max(max_consec_down, current_down)
            else:
                current_down = 0
        
        name = str(minute_row.iloc[0]['name']) if len(minute_row) > 0 else ''
        score = int(minute_row.iloc[0]['minute_score']) if len(minute_row) > 0 else 0
        signals = str(minute_row.iloc[0]['signals']) if len(minute_row) > 0 else ''
        turnover = float(minute_row.iloc[0]['turnover']) if len(minute_row) > 0 else 0
        
        performance.append({
            'ts_code': code,
            'name': name,
            'minute_score': score,
            'signals': signals,
            'base_close': base_close,
            'snapshot_price': snapshot_price,
            'end_close': end_close,
            'end_date': end_date,
            'total_return': round(total_return, 2),
            'snapshot_return': round(snapshot_return, 2),
            'max_gain': round(max_gain, 2),
            'max_drawdown': round(max_drawdown, 2),
            'max_date': max_date,
            'min_date': min_date,
            'volatility': round(volatility, 2),
            'up_ratio': round(up_ratio, 3),
            'up_days': f"{up_days}/{total_days}",
            'max_consec_down': max_consec_down,
            'turnover_0326': turnover,
        })
    
    perf_df = pd.DataFrame(performance)
    perf_df = perf_df.sort_values('total_return', ascending=False)
    
    # 输出
    print(f"\n{'='*100}")
    print(f"Top20 股票 03-26→{perf_df.iloc[0]['end_date']} 实际表现")
    print(f"{'='*100}")
    
    print(f"\n{'#':<3} {'代码':<12} {'名称':<8} {'评分':>4} {'03-26收':>8} {'最新收':>8} {'区间涨%':>8} {'最大涨%':>8} {'最大回撤%':>9} {'胜率':>5} {'波动':>5} {'信号'}")
    print("-"*110)
    
    for i, (_, r) in enumerate(perf_df.iterrows(), 1):
        sig = str(r['signals'])[:25]
        print(f"{i:<3} {r['ts_code']:<12} {r['name']:<8} {r['minute_score']:>4} "
              f"{r['base_close']:>8.2f} {r['end_close']:>8.2f} {r['total_return']:>+7.1f}% "
              f"{r['max_gain']:>+7.1f}% {r['max_drawdown']:>+8.1f}% "
              f"{r['up_ratio']:>4.1%} {r['volatility']:>4.1f} {sig}")
    
    # 分赢家/输家
    median_ret = perf_df['total_return'].median()
    winners = perf_df[perf_df['total_return'] > 0]
    losers = perf_df[perf_df['total_return'] <= 0]
    
    print(f"\n{'='*60}")
    print(f"赢家 ({len(winners)} 只, 区间涨>0%):")
    for _, r in winners.iterrows():
        print(f"  {r['ts_code']} {r['name']} {r['total_return']:>+6.1f}% score={r['minute_score']} {r['signals']}")
    
    print(f"\n输家 ({len(losers)} 只, 区间涨≤0%):")
    for _, r in losers.iterrows():
        print(f"  {r['ts_code']} {r['name']} {r['total_return']:>+6.1f}% score={r['minute_score']} {r['signals']}")
    
    # 统计对比
    if len(winners) > 0 and len(losers) > 0:
        print(f"\n{'='*60}")
        print("赢家 vs 输家 特征对比:")
        for metric, col in [('平均评分', 'minute_score'), ('平均换手率', 'turnover_0326'),
                            ('平均最大涨幅', 'max_gain'), ('平均最大回撤', 'max_drawdown'),
                            ('平均波动率', 'volatility'), ('平均胜率', 'up_ratio')]:
            w = winners[col].mean()
            l = losers[col].mean()
            print(f"  {metric}: 赢家={w:.2f} 输家={l:.2f} 差异={w-l:+.2f}")
    
    # 保存
    perf_df.to_csv('output/signal2_performance_0326_0414.csv', index=False, encoding='utf-8-sig')
    print(f"\n结果已保存: output/signal2_performance_0326_0414.csv")

if __name__ == '__main__':
    main()

"""
Signal-3: 赢家 vs 输家深度因子对比
维度：行业板块、近5日趋势背景、量价结构、市值、盘中形态特征
"""
import os, requests, pandas as pd, numpy as np
from pathlib import Path
from datetime import datetime

def tushare_api(token, api_name, params):
    url = 'https://api.tushare.pro'
    payload = {'api_name': api_name, 'token': token, 'params': params, 'fields': ''}
    r = requests.post(url, json=payload, timeout=60)
    data = r.json()
    if data.get('code') == 0:
        return data['data']
    print(f"  Error [{api_name}]: {data.get('msg')}")
    return None

def main():
    token = os.environ.get('TUSHARE_TOKEN', '')
    
    # 读取 signal2 结果
    perf = pd.read_csv('output/signal2_performance_0326_0414.csv')
    ts_codes = perf['ts_code'].tolist()
    
    # 分类赢家/输家
    perf['group'] = perf['total_return'].apply(lambda x: 'winner' if x > 0 else 'loser')
    
    print(f"分析 {len(ts_codes)} 只股票的多维特征...")
    
    # ===== 1. 行业信息 =====
    print("\n[1] 获取行业分类...")
    industry_result = tushare_api(token, 'stock_basic', {
        'exchange': '', 'list_status': 'L',
        'fields': 'ts_code,name,industry,market,list_date'
    })
    if industry_result and industry_result.get('items'):
        industry_df = pd.DataFrame(industry_result['items'], columns=industry_result['fields'])
        perf = perf.merge(industry_df[['ts_code','industry','list_date']], on='ts_code', how='left')
    
    # ===== 2. 近5日走势背景（03-19到03-25） =====
    print("[2] 获取近5日走势背景...")
    all_bg = []
    for code in ts_codes:
        result = tushare_api(token, 'daily', {
            'ts_code': code,
            'start_date': '20260319',
            'end_date': '20260325',
        })
        if result and result.get('items'):
            df = pd.DataFrame(result['items'], columns=result['fields'])
            for col in ['open','high','low','close','pre_close','pct_chg','vol','amount']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            if len(df) > 0:
                df = df.sort_values('trade_date')
                # 近5日累计涨跌幅
                cum_ret = (df.iloc[-1]['close'] / df.iloc[0]['pre_close'] - 1) * 100
                # 近5日最大跌幅（连跌最深）
                max_down = df['pct_chg'].min()
                # 近5日平均换手（用成交额/市值近似）
                avg_vol = df['vol'].mean()
                # 03-25 收盘价
                last_close = float(df.iloc[-1]['close'])
                # 连跌天数
                consec_down = 0
                max_cd = 0
                for _, r in df.iterrows():
                    if r['pct_chg'] < 0:
                        consec_down += 1
                        max_cd = max(max_cd, consec_down)
                    else:
                        consec_down = 0
                
                # 波动率
                ret_std = df['pct_chg'].std()
                
                # 量能趋势：后3天均量 / 前2天均量
                if len(df) >= 3:
                    vol_trend = df.iloc[-3:]['vol'].mean() / max(df.iloc[:2]['vol'].mean(), 1)
                else:
                    vol_trend = 1.0
                
                all_bg.append({
                    'ts_code': code,
                    'bg_5d_return': round(cum_ret, 2),
                    'bg_5d_max_down': round(max_down, 2),
                    'bg_5d_avg_vol': round(avg_vol, 0),
                    'bg_prev_close': last_close,
                    'bg_consec_down': max_cd,
                    'bg_volatility': round(ret_std, 2),
                    'bg_vol_trend': round(vol_trend, 2),
                })
    
    if all_bg:
        bg_df = pd.DataFrame(all_bg)
        perf = perf.merge(bg_df, on='ts_code', how='left')
    
    # ===== 3. 03-26 当日详细特征（从精确评分数据） =====
    print("[3] 获取03-26当日详细特征...")
    precise = pd.read_csv('output/screening_20260326_minute_precise.csv')
    
    # 额外计算：盘中趋势方向（上午下半段 vs 上半段）
    # 从精确数据中已有 morning_return, morning_max_down, close_position, amplitude
    
    # ===== 4. 03-26 基本面（市值、PE、量比） =====
    print("[4] 获取03-26基本面...")
    basic_result = tushare_api(token, 'daily_basic', {
        'trade_date': '20260326',
        'fields': 'ts_code,turnover_rate,volume_ratio,pe,pe_ttm,pb,total_mv,circ_mv'
    })
    if basic_result and basic_result.get('items'):
        basic_df = pd.DataFrame(basic_result['items'], columns=basic_result['fields'])
        for col in ['turnover_rate','volume_ratio','pe','pe_ttm','pb','total_mv','circ_mv']:
            if col in basic_df.columns:
                basic_df[col] = pd.to_numeric(basic_df[col], errors='coerce')
        # 只保留需要的列，避免重名冲突
        basic_df = basic_df.rename(columns={
            'turnover_rate': 'd_turnover',
            'volume_ratio': 'd_volume_ratio',
        })
        perf = perf.merge(basic_df[['ts_code','d_volume_ratio','pe_ttm','pb','total_mv','circ_mv']], 
                          on='ts_code', how='left')
    
    # ===== 5. 03-26 分钟级形态特征 =====
    print("[5] 计算分钟级形态特征...")
    sys_path = Path(__file__).parent.parent / "src"
    import sys
    sys.path.insert(0, str(sys_path))
    from pytdx_minute import PytdxMinuteManager
    from datetime import time
    
    mgr = PytdxMinuteManager()
    
    minute_features = []
    for code in ts_codes:
        minute_df = mgr.download_minute_data(code, '20260326', freq='5', use_cache=True)
        if minute_df is None or len(minute_df) == 0:
            continue
        
        # 分上下半场
        first_half = minute_df[minute_df['time'] <= time(10, 30)]
        second_half = minute_df[(minute_df['time'] > time(10, 30)) & (minute_df['time'] <= time(11, 30))]
        
        if len(first_half) == 0 or len(second_half) == 0:
            continue
        
        fh_close = float(first_half.iloc[-1]['close'])
        sh_close = float(second_half.iloc[-1]['close'])
        open_price = float(minute_df.iloc[0]['open'])
        
        # 上半场涨跌
        fh_return = (fh_close - open_price) / open_price * 100
        # 下半场涨跌
        sh_return = (sh_close - fh_close) / fh_close * 100
        # 下半场 vs 上半场量比
        fh_vol = float(first_half['vol'].sum())
        sh_vol = float(second_half['vol'].sum())
        vol_ratio_intraday = sh_vol / max(fh_vol, 1)
        
        # 最大拉升发生在哪个时段
        all_returns = []
        for _, r in minute_df.iterrows():
            bar_return = (float(r['close']) - float(r['open'])) / float(r['open']) * 100
            all_returns.append(bar_return)
        
        # 盘中加速：最后一小时 vs 第一小时
        first_hour = minute_df[minute_df['time'] <= time(10, 30)]
        last_hour = minute_df[minute_df['time'] >= time(10, 30)]
        
        fh_range = (float(first_hour['high'].max()) - float(first_hour['low'].min())) / float(first_hour.iloc[0]['open']) * 100
        lh_range = (float(last_hour['high'].max()) - float(last_hour['low'].min())) / float(last_hour.iloc[0]['open']) * 100
        
        minute_features.append({
            'ts_code': code,
            'mf_fh_return': round(fh_return, 2),
            'mf_sh_return': round(sh_return, 2),
            'mf_vol_ratio_intra': round(vol_ratio_intraday, 2),
            'mf_fh_range': round(fh_range, 2),
            'mf_lh_range': round(lh_range, 2),
            'mf_acceleration': round(lh_range - fh_range, 2),  # 下半场振幅 - 上半场振幅
            'mf_max_bar': round(max(all_returns), 2),
            'mf_min_bar': round(min(all_returns), 2),
            'mf_trend': 'up' if sh_return > fh_return else ('down' if sh_return < fh_return else 'flat'),
        })
    
    mgr.disconnect()
    
    if minute_features:
        mf_df = pd.DataFrame(minute_features)
        perf = perf.merge(mf_df, on='ts_code', how='left')
    
    # ===== 输出完整分析 =====
    print(f"\n{'='*120}")
    print("Signal-3: 赢家 vs 输家 多维因子对比")
    print(f"{'='*120}")
    
    winners = perf[perf['group'] == 'winner']
    losers = perf[perf['group'] == 'loser']
    
    # 行业分布
    print("\n【行业分布】")
    print(f"  赢家行业: {winners['industry'].value_counts().to_dict()}")
    print(f"  输家行业: {losers['industry'].value_counts().to_dict()}")
    
    # 数值因子对比
    numeric_cols = {
        'minute_score': '评分',
        'turnover_0326': '换手率%',
        'd_volume_ratio': '量比',
        'total_mv': '总市值(万)',
        'pe_ttm': 'PE(TTM)',
        'pb': 'PB',
        'bg_5d_return': '近5日涨%',
        'bg_5d_max_down': '近5日最大单日跌%',
        'bg_consec_down': '近5日最大连跌天数',
        'bg_volatility': '近5日波动率',
        'bg_vol_trend': '近5日量能趋势',
        'mf_fh_return': '上半场涨%',
        'mf_sh_return': '下半场涨%',
        'mf_vol_ratio_intra': '下半场/上半场量比',
        'mf_acceleration': '盘面加速(下半场振幅-上半场)',
        'mf_max_bar': '最大单5分钟涨幅%',
        'mf_min_bar': '最大单5分钟跌幅%',
    }
    
    print(f"\n{'因子':<20} {'赢家均值':>10} {'输家均值':>10} {'差异':>10} {'区分力'}")
    print("-"*65)
    
    discriminating_factors = []
    for col, label in numeric_cols.items():
        if col not in perf.columns:
            continue
        w_mean = winners[col].mean()
        l_mean = losers[col].mean()
        diff = w_mean - l_mean
        
        # 计算区分力（标准化差异）
        overall_std = perf[col].std()
        if overall_std > 0 and not np.isnan(overall_std):
            discriminancy = abs(diff) / overall_std
        else:
            discriminancy = 0
        
        stars = ''
        if discriminancy > 0.5:
            stars = '★★★'
        elif discriminancy > 0.3:
            stars = '★★'
        elif discriminancy > 0.15:
            stars = '★'
        else:
            stars = '·'
        
        if discriminancy > 0.15:
            discriminating_factors.append((col, label, diff, discriminancy))
        
        print(f"  {label:<18} {w_mean:>10.2f} {l_mean:>10.2f} {diff:>+10.2f} {stars}")
    
    # 按区分力排序
    print(f"\n{'='*65}")
    print("高区分力因子排序（★越多区分力越强）:")
    discriminating_factors.sort(key=lambda x: abs(x[3]), reverse=True)
    for col, label, diff, disc in discriminating_factors:
        direction = '正向→赢家' if diff > 0 else '负向→输家'
        print(f"  {label:<18} 差异={diff:+.2f} 区分度={disc:.2f} {direction}")
    
    # 个股明细
    print(f"\n{'='*120}")
    print("个股明细:")
    print(f"{'代码':<12} {'名称':<8} {'组':>5} {'涨%':>7} {'行业':<8} {'市值(亿)':>8} {'5日涨%':>7} {'量比':>5} {'上半场%':>7} {'下半场%':>7} {'加速':>6}")
    print("-"*100)
    for _, r in perf.sort_values('total_return', ascending=False).iterrows():
        mv = r.get('total_mv', 0) / 10000 if pd.notna(r.get('total_mv')) else 0
        print(f"{r['ts_code']:<12} {r.get('name',''):<8} {r['group']:>5} {r['total_return']:>+6.1f}% "
              f"{r.get('industry',''):<8} {mv:>7.0f} "
              f"{r.get('bg_5d_return',0):>+6.1f}% "
              f"{r.get('d_volume_ratio',0):>4.1f} "
              f"{r.get('mf_fh_return',0):>+6.1f}% "
              f"{r.get('mf_sh_return',0):>+6.1f}% "
              f"{r.get('mf_acceleration',0):>+5.1f}")
    
    # 保存
    perf.to_csv('output/signal3_factor_comparison.csv', index=False, encoding='utf-8-sig')
    print(f"\n结果已保存: output/signal3_factor_comparison.csv")

if __name__ == '__main__':
    main()

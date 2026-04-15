#!/usr/bin/env python3
import os
import pandas as pd
from pytdx.hq import TdxHq_API

# 通达信服务器配置
TDX_HOST = '110.41.147.114'
TDX_PORT = 7709

def code_to_market(code):
    if code.startswith(('60', '68', '90')):
        return 1
    else:
        return 0

def get_t_afternoon_feature(code, select_date):
    """获取T日下午的量价特征（我们是T日中午选股，下午开盘买入）"""
    api = TdxHq_API()
    if not api.connect(TDX_HOST, TDX_PORT):
        return None
    
    try:
        market = code_to_market(code)
        # 获取T日的分钟K线
        min_kline = api.get_security_bars(0, market, code, 0, 500)
        if not min_kline:
            return None
        
        min_df = pd.DataFrame(min_kline)
        min_df['datetime'] = pd.to_datetime(min_df['datetime'])
        min_df['date'] = min_df['datetime'].dt.strftime('%Y%m%d')
        min_df['hour'] = min_df['datetime'].dt.hour
        min_df['minute'] = min_df['datetime'].dt.minute
        
        # 筛选T日的数据
        t_day_min = min_df[min_df['date'] == select_date]
        if len(t_day_min) < 240: # 全天4小时交易，不足说明数据缺失
            return None
        
        # 上午收盘价格（我们的买入基准价）
        am_close = t_day_min[(t_day_min['hour'] == 11) & (t_day_min['minute'] == 30)].iloc[0]['close']
        # 下午开盘价
        pm_open = t_day_min[(t_day_min['hour'] == 13) & (t_day_min['minute'] == 0)].iloc[0]['open']
        # 下午收盘价
        pm_close = t_day_min.iloc[-1]['close']
        # 下午最高价/最低价
        pm_high = t_day_min[t_day_min['hour'] >= 13]['high'].max()
        pm_low = t_day_min[t_day_min['hour'] >= 13]['low'].min()
        # 下午成交量/上午成交量比值
        am_vol = t_day_min[t_day_min['hour'] < 12]['vol'].sum()
        pm_vol = t_day_min[t_day_min['hour'] >= 13]['vol'].sum()
        pm_am_vol_ratio = round(pm_vol / am_vol, 2)
        
        # 计算下午收益
        pm_gain = round((pm_close - pm_open) / pm_open * 100, 2)
        pm_max_drawdown = round((pm_open - pm_low) / pm_open * 100, 2)
        pm_max_gain = round((pm_high - pm_open) / pm_open * 100, 2)
        
        # 获取后续3个交易日的整体收益
        daily_kline = api.get_security_bars(9, market, code, 0, 10)
        daily_df = pd.DataFrame(daily_kline)
        daily_df['datetime'] = pd.to_datetime(daily_df['datetime'])
        daily_df['date'] = daily_df['datetime'].dt.strftime('%Y%m%d')
        t_idx = daily_df[daily_df['date'] == select_date].index[0]
        hold_df = daily_df.iloc[t_idx:t_idx+4]
        final_close = hold_df.iloc[-1]['close']
        total_return = round((final_close - pm_open) / pm_open * 100, 2)
        is_loss = 1 if total_return < 0 else 0
        
        return {
            'code': code,
            'select_date': select_date,
            'pm_am_vol_ratio': pm_am_vol_ratio,
            'pm_gain': pm_gain,
            'pm_max_drawdown': pm_max_drawdown,
            'pm_max_gain': pm_max_gain,
            'total_return': total_return,
            'is_loss': is_loss
        }
    finally:
        api.disconnect()

def main():
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    # 读取所有历史选股结果
    from glob import glob
    files = sorted(glob('output/screening_*_final_top5.csv'))
    all_stocks = []
    
    for f in files:
        date = os.path.basename(f).split('_')[1]
        df = pd.read_csv(f)
        for _, row in df.iterrows():
            all_stocks.append({
                'code': row['代码'],
                'name': row['名称'] if pd.notna(row['名称']) else row['代码'],
                'select_date': date
            })
    
    print(f"✅ 共加载历史选股样本{len(all_stocks)}个，开始提取T日下午特征...")
    
    all_features = []
    for stock in all_stocks:
        print(f"⏳ 处理{stock['code']} {stock['name']} {stock['select_date']}...")
        feat = get_t_afternoon_feature(stock['code'], stock['select_date'])
        if feat:
            feat['name'] = stock['name']
            all_features.append(feat)
    
    feat_df = pd.DataFrame(all_features)
    feat_df.to_csv('output/historical_filter/afternoon_features.csv', index=False, encoding='utf-8-sig')
    
    # 统计亏损vs盈利样本的下午特征差异
    loss_df = feat_df[feat_df['is_loss'] == 1]
    profit_df = feat_df[feat_df['is_loss'] == 0]
    
    print("\n" + "="*80)
    print("📊 T日下午特征对后续盈亏的影响统计")
    print("="*80)
    print(f"总样本数：{len(feat_df)}，亏损样本数：{len(loss_df)}，盈利样本数：{len(profit_df)}")
    print(f"\n特征对比（亏损组均值 vs 盈利组均值）：")
    compare_cols = ['pm_am_vol_ratio', 'pm_gain', 'pm_max_drawdown', 'pm_max_gain']
    for col in compare_cols:
        loss_mean = round(loss_df[col].mean(), 2) if not pd.isna(loss_df[col].mean()) else '无数据'
        profit_mean = round(profit_df[col].mean(), 2) if not pd.isna(profit_df[col].mean()) else '无数据'
        diff = round(loss_mean - profit_mean, 2) if isinstance(loss_mean, float) and isinstance(profit_mean, float) else '-'
        print(f"{col}: {loss_mean} vs {profit_mean}，差异：{diff}")
    
    # 统计阈值胜率
    print(f"\n🎯 关键阈值胜率统计：")
    # 下午量比<0.6（我们的入场因子正向条件，看是不是下午符合的胜率更高）
    good_vol = feat_df[feat_df['pm_am_vol_ratio'] < 0.6]
    if len(good_vol) > 0:
        win_rate = round(len(good_vol[good_vol['is_loss'] == 0])/len(good_vol)*100,2)
        avg_return = round(good_vol['total_return'].mean(),2)
        print(f"T日下午/上午量比 < 0.6：样本数{len(good_vol)}，胜率{win_rate}%，平均收益{avg_return}%")
    
    # 下午跌幅>2%
    bad_gain = feat_df[feat_df['pm_gain'] < -2]
    if len(bad_gain) > 0:
        win_rate = round(len(bad_gain[bad_gain['is_loss'] == 0])/len(bad_gain)*100,2)
        avg_return = round(bad_gain['total_return'].mean(),2)
        print(f"T日下午跌幅 > 2%：样本数{len(bad_gain)}，胜率{win_rate}%，平均收益{avg_return}%")
    
    # 下午最大回撤>3%
    bad_drawdown = feat_df[feat_df['pm_max_drawdown'] > 3]
    if len(bad_drawdown) > 0:
        win_rate = round(len(bad_drawdown[bad_drawdown['is_loss'] == 0])/len(bad_drawdown)*100,2)
        avg_return = round(bad_drawdown['total_return'].mean(),2)
        print(f"T日下午最大回撤 > 3%：样本数{len(bad_drawdown)}，胜率{win_rate}%，平均收益{avg_return}%")

if __name__ == "__main__":
    main()
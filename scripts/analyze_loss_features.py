#!/usr/bin/env python3
import os
import glob
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

def get_stock_detail_data(code, select_date, hold_days=5):
    """获取股票从入选日起最多5个交易日的分钟/日线特征"""
    api = TdxHq_API()
    if not api.connect(TDX_HOST, TDX_PORT):
        return None
    
    try:
        market = code_to_market(code)
        # 获取日K线
        daily_kline = api.get_security_bars(9, market, code, 0, 30)
        if not daily_kline:
            return None
        daily_df = pd.DataFrame(daily_kline)
        daily_df['datetime'] = pd.to_datetime(daily_df['datetime'])
        daily_df['date'] = daily_df['datetime'].dt.strftime('%Y%m%d')
        
        # 找到入选日的位置
        select_idx = daily_df[daily_df['date'] == select_date].index
        if len(select_idx) == 0:
            return None
        select_idx = select_idx[0]
        
        # 取入选日及之后最多5个交易日
        hold_df = daily_df.iloc[select_idx:select_idx+hold_days].copy()
        if len(hold_df) < 1:
            return None
        
        # 计算特征
        select_price = hold_df.iloc[0]['close']
        max_price = hold_df['high'].max()
        min_price = hold_df['low'].min()
        hold_return = round((hold_df.iloc[-1]['close'] - select_price) / select_price * 100, 2)
        max_return = round((max_price - select_price) / select_price * 100, 2)
        max_drawdown = round((select_price - min_price) / select_price * 100, 2)
        
        # 首日特征
        first_day = hold_df.iloc[0]
        first_day_gain = round((first_day['close'] - first_day['open']) / first_day['open'] * 100, 2)
        first_day_vol_ratio = round(first_day['vol'] / daily_df.iloc[select_idx-5:select_idx]['vol'].mean(), 2)
        
        # 次日特征
        next_day_gain = None
        next_day_vol_ratio = None
        next_day_am_gain = None
        if len(hold_df) >= 2:
            next_day = hold_df.iloc[1]
            next_day_gain = round((next_day['close'] - first_day['close']) / first_day['close'] * 100, 2)
            next_day_vol_ratio = round(next_day['vol'] / first_day['vol'], 2)
            
            # 获取次日上午涨幅（需要分钟数据）
            min_kline = api.get_security_bars(0, market, code, 0, 1000)
            if min_kline:
                min_df = pd.DataFrame(min_kline)
                min_df['datetime'] = pd.to_datetime(min_df['datetime'])
                min_df['date'] = min_df['datetime'].dt.strftime('%Y%m%d')
                min_df['hour'] = min_df['datetime'].dt.hour
                next_day_min = min_df[min_df['date'] == hold_df.iloc[1]['date']]
                if len(next_day_min) > 0:
                    am_min = next_day_min[next_day_min['hour'] < 11]
                    if len(am_min) > 0:
                        am_open = am_min.iloc[0]['open']
                        am_close = am_min.iloc[-1]['close']
                        next_day_am_gain = round((am_close - am_open) / am_open * 100, 2)
        
        return {
            'code': code,
            'select_date': select_date,
            'hold_return': hold_return,
            'max_return': max_return,
            'max_drawdown': max_drawdown,
            'is_loss': 1 if hold_return < 0 else 0,
            'first_day_gain': first_day_gain,
            'first_day_vol_ratio': first_day_vol_ratio,
            'next_day_gain': next_day_gain,
            'next_day_vol_ratio': next_day_vol_ratio,
            'next_day_am_gain': next_day_am_gain
        }
    finally:
        api.disconnect()

def main():
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    # 读取所有历史选股结果
    files = sorted(glob.glob('output/screening_*_final_top5.csv'))
    all_stocks = []
    
    for f in files:
        date = os.path.basename(f).split('_')[1]
        df = pd.read_csv(f)
        for _, row in df.iterrows():
            all_stocks.append({
                'code': row['代码'],
                'name': row['名称'] if pd.notna(row['名称']) else row['代码'],
                'select_date': date,
                'score': row['综合总分']
            })
    
    print(f"✅ 共加载历史选股样本{len(all_stocks)}个，开始提取特征...")
    
    all_features = []
    loss_count = 0
    for stock in all_stocks:
        print(f"⏳ 处理{stock['code']} {stock['name']} {stock['select_date']}...")
        feat = get_stock_detail_data(stock['code'], stock['select_date'])
        if feat:
            feat['name'] = stock['name']
            feat['score'] = stock['score']
            all_features.append(feat)
            if feat['is_loss']:
                loss_count += 1
    
    # 转成DataFrame
    feat_df = pd.DataFrame(all_features)
    feat_df.to_csv('output/historical_filter/all_stock_features.csv', index=False, encoding='utf-8-sig')
    
    # 统计亏损样本 vs 盈利样本的特征差异
    loss_df = feat_df[feat_df['is_loss'] == 1]
    profit_df = feat_df[feat_df['is_loss'] == 0]
    
    print("\n" + "="*80)
    print("📊 亏损vs盈利样本特征对比统计")
    print("="*80)
    print(f"总样本数：{len(feat_df)}，亏损样本数：{len(loss_df)}，盈利样本数：{len(profit_df)}，胜率：{round(len(profit_df)/len(feat_df)*100,2)}%")
    print(f"平均持有收益：{round(feat_df['hold_return'].mean(),2)}%，平均最大收益：{round(feat_df['max_return'].mean(),2)}%")
    print(f"\n特征对比（亏损组均值 vs 盈利组均值）：")
    compare_cols = ['max_drawdown', 'first_day_gain', 'first_day_vol_ratio', 'next_day_gain', 'next_day_vol_ratio', 'next_day_am_gain']
    for col in compare_cols:
        loss_mean = round(loss_df[col].mean(), 2) if not pd.isna(loss_df[col].mean()) else '无数据'
        profit_mean = round(profit_df[col].mean(), 2) if not pd.isna(profit_df[col].mean()) else '无数据'
        diff = round(loss_mean - profit_mean, 2) if isinstance(loss_mean, float) and isinstance(profit_mean, float) else '-'
        print(f"{col}: {loss_mean} vs {profit_mean}，差异：{diff}")
    
    # 统计阈值的胜率
    print(f"\n🎯 关键阈值胜率统计：")
    # 次日上午涨幅< -1%的胜率
    bad_am_gain = feat_df[feat_df['next_day_am_gain'] < -1]
    if len(bad_am_gain) > 0:
        bad_am_win_rate = round(len(bad_am_gain[bad_am_gain['is_loss'] == 0])/len(bad_am_gain)*100,2)
        print(f"次日上午涨幅 < -1%：样本数{len(bad_am_gain)}，胜率{bad_am_win_rate}%")
    # 次日量比>1.5的胜率
    bad_vol_ratio = feat_df[feat_df['next_day_vol_ratio'] > 1.5]
    if len(bad_vol_ratio) > 0:
        bad_vol_win_rate = round(len(bad_vol_ratio[bad_vol_ratio['is_loss'] == 0])/len(bad_vol_ratio)*100,2)
        print(f"次日量比 > 1.5：样本数{len(bad_vol_ratio)}，胜率{bad_vol_win_rate}%")
    # 首日涨幅< -2%的胜率
    bad_first_gain = feat_df[feat_df['first_day_gain'] < -2]
    if len(bad_first_gain) > 0:
        bad_first_win_rate = round(len(bad_first_gain[bad_first_gain['is_loss'] == 0])/len(bad_first_gain)*100,2)
        print(f"入选日涨幅 < -2%：样本数{len(bad_first_gain)}，胜率{bad_first_win_rate}%")

if __name__ == "__main__":
    main()
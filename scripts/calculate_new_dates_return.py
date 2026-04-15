#!/usr/bin/env python3
import os
import glob
import pandas as pd
from datetime import datetime
from pytdx.hq import TdxHq_API

# 通达信服务器配置
TDX_HOST = '110.41.147.114'
TDX_PORT = 7709

# 统计截止日期
END_DATE = '20260414'

def code_to_market(code):
    """将股票代码转换为通达信市场代码：0=深市，1=沪市"""
    if code.startswith(('60', '68', '90')):
        return 1
    elif code.startswith(('00', '30', '20')):
        return 0
    else:
        return 0  # 默认深市

def get_stock_return(code, select_date):
    """获取单个股票从筛选日到截止日的持有收益和最高收益"""
    api = TdxHq_API()
    if not api.connect(TDX_HOST, TDX_PORT):
        print(f"❌ 无法连接通达信服务器")
        return None
    
    try:
        market = code_to_market(code)
        # 获取日K线数据
        kline = api.get_security_bars(9, market, code, 0, 500)
        if not kline:
            return None
        
        df = pd.DataFrame(kline)
        df['datetime'] = pd.to_datetime(df['datetime'])
        df['date'] = df['datetime'].dt.strftime('%Y%m%d')
        
        # 筛选日收盘价
        select_day_data = df[df['date'] == select_date]
        if select_day_data.empty:
            return None
        select_price = select_day_data.iloc[0]['close']
        
        # 截止日收盘价
        end_day_data = df[df['date'] == END_DATE]
        if end_day_data.empty:
            end_day_data = df[df['date'] <= END_DATE].tail(1)
            if end_day_data.empty:
                return None
        end_price = end_day_data.iloc[0]['close']
        
        # 期间最高价
        period_data = df[(df['date'] >= select_date) & (df['date'] <= END_DATE)]
        max_price = period_data['high'].max()
        
        hold_return = round((end_price - select_price) / select_price * 100, 2)
        max_return = round((max_price - select_price) / select_price * 100, 2)
        is_profit = 1 if hold_return > 0 else 0
        
        return {
            'code': code,
            'hold_return': hold_return,
            'max_return': max_return,
            'is_profit': is_profit
        }
    finally:
        api.disconnect()

def get_portfolio_return(date):
    """获取指定日期TOP5股票的组合收益"""
    file_path = f'output/screening_{date}_final_top5.csv'
    if not os.path.exists(file_path):
        print(f"❌ 找不到{date}的筛选结果")
        return None
    
    df = pd.read_csv(file_path)
    if len(df) < 5:
        print(f"⚠️ {date}的筛选结果不足5只")
        return None
    
    returns = []
    for _, row in df.iterrows():
        code = row['代码']
        ret = get_stock_return(code, date)
        if ret:
            ret['name'] = row['名称'] if pd.notna(row['名称']) else code
            returns.append(ret)
    
    if not returns:
        return None
    
    ret_df = pd.DataFrame(returns)
    best = ret_df.sort_values('hold_return', ascending=False).iloc[0]
    worst = ret_df.sort_values('hold_return').iloc[0]
    best_name = str(best['name']) if pd.notna(best['name']) else best['code']
    worst_name = str(worst['name']) if pd.notna(worst['name']) else worst['code']
    
    return {
        '筛选日期': date,
        '股票数量': len(ret_df),
        '平均持有收益(%)': round(ret_df['hold_return'].mean(), 2),
        '平均最高收益(%)': round(ret_df['max_return'].mean(), 2),
        '胜率(%)': round(ret_df['is_profit'].mean()*100, 2),
        '最佳标的': f"{best_name}({best['code']})",
        '最佳标的收益(%)': best['hold_return'],
        '最差标的': f"{worst_name}({worst['code']})",
        '最差标的收益(%)': worst['hold_return']
    }

def main():
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    # 查找所有已有的筛选结果文件
    files = glob.glob('output/screening_*_final_top5.csv')
    # 提取日期
    dates = sorted([os.path.basename(f).split('_')[1] for f in files])
    # 筛选出本次新成功的7个日期（20260320-20260325）
    new_dates = [d for d in dates if d >= '20260320' and d <= '20260325']
    
    print(f"✅ 共找到{len(new_dates)}个新处理完成的日期: {new_dates}")
    
    all_results = []
    for date in new_dates:
        print(f"⏳ 计算日期{date}的组合收益...")
        res = get_portfolio_return(date)
        if res:
            all_results.append(res)
    
    if not all_results:
        print("❌ 没有可统计的数据")
        return
    
    result_df = pd.DataFrame(all_results)
    
    # 输出表格
    print("\n" + "="*120)
    print("📅 新完成日期TOP5股票池收益统计（截至2026-04-14）")
    print("="*120)
    print(result_df.to_string(index=False))
    print("="*120)
    
    # 整体统计
    avg_daily_return = round(result_df['平均持有收益(%)'].mean(), 2)
    positive_days = len(result_df[result_df['平均持有收益(%)'] > 0])
    positive_rate = round(positive_days / len(result_df) * 100, 2)
    print(f"\n📊 整体平均日组合收益: {avg_daily_return}%")
    print(f"📈 正收益天数占比: {positive_rate}%")
    print(f"🏆 最高单日收益: {result_df['平均持有收益(%)'].max()}% ({result_df.loc[result_df['平均持有收益(%)'].idxmax(), '筛选日期']})")
    print(f"⚠️ 最低单日收益: {result_df['平均持有收益(%)'].min()}% ({result_df.loc[result_df['平均持有收益(%)'].idxmin(), '筛选日期']})")
    
    # 合并到历史统计文件
    history_file = 'output/historical_filter/daily_portfolio_return.csv'
    if os.path.exists(history_file):
        history_df = pd.read_csv(history_file)
        merged_df = pd.concat([history_df, result_df]).drop_duplicates(subset=['筛选日期']).sort_values('筛选日期')
        merged_df.to_csv(history_file, index=False, encoding='utf-8-sig')
        print(f"\n💾 已合并到历史统计文件: {history_file}")

if __name__ == "__main__":
    main()
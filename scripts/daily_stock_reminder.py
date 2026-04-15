import akshare as ak
import pandas as pd
from datetime import datetime

# 跟踪文件路径
TRACKING_FILE = "/Users/huchen/Projects/AShareSignal/output/stock_tracking_20260414.csv"
TODAY = datetime.now().strftime("%Y-%m-%d")

def update_stock_data():
    df = pd.read_csv(TRACKING_FILE)
    today_col = f"{TODAY}最新价"
    today_pct_col = f"{TODAY}涨跌幅(%)"
    
    # 如果今天的列不存在，添加
    if today_col not in df.columns:
        df[today_col] = None
        df[today_pct_col] = None
    
    for i, row in df.iterrows():
        code = row['代码']
        # 转换为akshare格式
        ak_code = code.replace('.SZ', '').replace('.SH', '')
        if code.endswith('.SZ'):
            ak_code = 'sz' + ak_code
        else:
            ak_code = 'sh' + ak_code
        
        try:
            # 获取今日行情
            df_daily = ak.stock_zh_a_daily(symbol=ak_code, start_date=TODAY.replace('-', ''), end_date=TODAY.replace('-', ''))
            if not df_daily.empty:
                latest_price = round(df_daily.iloc[0]['close'], 2)
                entry_price = row['参考入场价(2026-04-14)']
                prev_close = df_daily.iloc[0]['open'] if len(df_daily) > 0 else entry_price
                
                # 计算涨跌幅
                daily_pct = round((latest_price - prev_close) / prev_close * 100, 2)
                total_pct = round((latest_price - entry_price) / entry_price * 100, 2)
                
                # 更新数据
                df.at[i, today_col] = latest_price
                df.at[i, today_pct_col] = daily_pct
                df.at[i, '累计涨跌幅(%)'] = total_pct
        except Exception as e:
            print(f"获取{row['名称']}数据失败: {e}")
            continue
    
    # 保存更新
    df.to_csv(TRACKING_FILE, index=False, encoding='utf-8-sig')
    return df

def generate_notification(df):
    msg = f"📊 4月14日选股跟踪每日提醒 ({TODAY})\n\n"
    msg += "| 名称   | 入场价 | 最新价 | 当日涨跌幅 | 累计涨跌幅 | 评分 |\n"
    msg += "|:-----|-----:|-----:|-------:|-------:|-----:|\n"
    
    for _, row in df.iterrows():
        daily_pct = row[f"{TODAY}涨跌幅(%)"] if f"{TODAY}涨跌幅(%)" in row else "-"
        total_pct = row['累计涨跌幅(%)'] if not pd.isna(row['累计涨跌幅(%)']) else "-"
        latest_price = row[f"{TODAY}最新价"] if f"{TODAY}最新价" in row else "-"
        
        # 涨跌样式
        if isinstance(daily_pct, float):
            daily_pct_str = f"🔴 {daily_pct}%" if daily_pct > 0 else f"🟢 {daily_pct}%" if daily_pct < 0 else f"⚪ {daily_pct}%"
        else:
            daily_pct_str = daily_pct
        
        if isinstance(total_pct, float):
            total_pct_str = f"🔴 {total_pct}%" if total_pct > 0 else f"🟢 {total_pct}%" if total_pct < 0 else f"⚪ {total_pct}%"
        else:
            total_pct_str = total_pct
        
        msg += f"| {row['名称']} | {row['参考入场价(2026-04-14)']} | {latest_price} | {daily_pct_str} | {total_pct_str} | {row['选股评分']} |\n"
    
    msg += f"\n💡 完整跟踪数据已保存到: {TRACKING_FILE}"
    return msg

if __name__ == "__main__":
    df = update_stock_data()
    notification = generate_notification(df)
    print(notification)

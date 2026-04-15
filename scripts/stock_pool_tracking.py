import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import os
from pytdx.hq import TdxHq_API

# 总跟踪表路径
TRACKING_FILE = "/Users/huchen/Projects/AShareSignal/output/stock_pool_tracking_total.xlsx"

def get_am_pm_open_price(code, date_str):
    """获取指定日期下午开盘价（13:00开盘价）作为入场价"""
    api = TdxHq_API()
    # 连接通达信行情服务器
    if api.connect('119.147.212.181', 7709):
        # 转换代码：0=深市，1=沪市
        market = 0 if code.endswith('.SZ') else 1
        code_num = code.replace('.SZ', '').replace('.SH', '')
        
        # 获取当日5分钟K线
        end_datetime = datetime.strptime(date_str, "%Y-%m-%d")
        start_datetime = end_datetime - timedelta(days=1)
        
        data = api.get_security_bars(0, market, code_num, 0, 48)  # 48根5分钟线覆盖全天交易
        api.disconnect()
        
        if data:
            df = pd.DataFrame(data)
            df['datetime'] = pd.to_datetime(df['datetime'])
            # 筛选下午13:00的K线
            pm_open = df[df['datetime'].dt.hour == 13].iloc[0]['open'] if len(df[df['datetime'].dt.hour == 13]) > 0 else None
            return round(pm_open, 2) if pm_open else None
    return None

def init_total_tracking():
    """初始化总跟踪表"""
    if os.path.exists(TRACKING_FILE):
        return pd.ExcelFile(TRACKING_FILE)
    
    # 创建新的总表
    with pd.ExcelWriter(TRACKING_FILE, engine='openpyxl') as writer:
        # 创建说明sheet
        df_desc = pd.DataFrame({
            "说明": [
                "A股股票池总跟踪表",
                "每个Sheet对应选股日期（格式YYYYMMDD）",
                "每行对应选股当日选出的股票",
                "列：T日（选股日收盘价/入场价）、T+1日、T+2日... 对应各日收盘价",
                "累计涨跌幅自动计算相对于T日入场价的收益率"
            ]
        })
        df_desc.to_excel(writer, sheet_name="说明", index=False)
    return pd.ExcelFile(TRACKING_FILE)

def add_stock_pool(date_str, stocks):
    """
    添加新的股票池到总表
    date_str: 选股日期，格式YYYY-MM-DD
    stocks: 股票列表，格式[{"code": "xxx", "name": "xxx", "entry_price": float, "score": int}]
    """
    xls = init_total_tracking()
    sheet_name = date_str.replace('-', '')
    
    # 如果该日期sheet已存在，读取现有数据
    if sheet_name in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet_name)
    else:
        # 创建新的sheet
        df = pd.DataFrame(stocks)
        # 重命名列
        df = df.rename(columns={
            "entry_price": "T日(入场价)",
            "code": "股票代码",
            "name": "股票名称",
            "score": "选股评分"
        })
        # 添加累计涨跌幅列
        df["累计涨跌幅(%)"] = None
    
    # 获取当前日期，更新最新的价格数据
    today = datetime.now()
    t_date = datetime.strptime(date_str, "%Y-%m-%d")
    days_diff = (today - t_date).days
    
    for i in range(1, days_diff + 1):
        col_name = f"T+{i}日"
        if col_name not in df.columns:
            df[col_name] = None
    
    # 更新价格数据
    for i, row in df.iterrows():
        code = row['股票代码']
        # 转换为akshare格式
        ak_code = code.replace('.SZ', '').replace('.SH', '')
        if code.endswith('.SZ'):
            ak_code = 'sz' + ak_code
        else:
            ak_code = 'sh' + ak_code
        
        try:
            # 获取从选股日到今天的所有日线数据
            start_date = t_date.strftime("%Y%m%d")
            end_date = today.strftime("%Y%m%d")
            df_daily = ak.stock_zh_a_daily(symbol=ak_code, start_date=start_date, end_date=end_date)
            df_daily = df_daily.sort_values('date')
            
            if not df_daily.empty:
                # 更新T日价格（如果为空）
                if pd.isna(row['T日(入场价)']):
                    # 用下午开盘价作为入场价
                    pm_open = get_am_pm_open_price(code, date_str)
                    df.at[i, 'T日(入场价)'] = pm_open if pm_open else round(df_daily.iloc[0]['close'], 2)
                
                # 更新T+N日价格
                for day_idx in range(1, min(len(df_daily), days_diff + 1)):
                    col_name = f"T+{day_idx}日"
                    if day_idx < len(df_daily):
                        df.at[i, col_name] = round(df_daily.iloc[day_idx]['close'], 2)
                
                # 计算累计涨跌幅
                entry_price = df.at[i, 'T日(入场价)']
                latest_price = df_daily.iloc[-1]['close']
                df.at[i, '累计涨跌幅(%)'] = round((latest_price - entry_price) / entry_price * 100, 2)
        
        except Exception as e:
            print(f"更新{row['股票名称']}数据失败: {e}")
            continue
    
    # 保存到总表
    with pd.ExcelWriter(TRACKING_FILE, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
    
    return df

def generate_daily_notification(date_str="2026-04-14"):
    """生成每日提醒消息"""
    xls = init_total_tracking()
    sheet_name = date_str.replace('-', '')
    
    if sheet_name not in xls.sheet_names:
        return f"❌ 未找到{date_str}的股票池数据"
    
    df = pd.read_excel(xls, sheet_name=sheet_name)
    today = datetime.now().strftime("%Y-%m-%d")
    t_date = datetime.strptime(date_str, "%Y-%m-%d")
    days_diff = (datetime.now() - t_date).days
    
    msg = f"📊 A股股票池每日跟踪提醒 ({today})\n"
    msg += f"📅 选股日期：{date_str} | 已跟踪 {days_diff} 天\n\n"
    
    # 动态生成表格列
    headers = ["名称", "入场价"]
    for i in range(1, days_diff + 1):
        headers.append(f"T+{i}价")
    headers.append("累计收益率")
    headers.append("评分")
    
    msg += "|" + "|".join(headers) + "|\n"
    msg += "|" + "|".join([":----" for _ in headers]) + "|\n"
    
    for _, row in df.iterrows():
        values = [
            row['股票名称'],
            str(row['T日(入场价)'])
        ]
        for i in range(1, days_diff + 1):
            col_name = f"T+{i}日"
            values.append(str(row.get(col_name, "-")) if not pd.isna(row.get(col_name, None)) else "-")
        
        # 累计收益率样式
        total_pct = row['累计涨跌幅(%)']
        if not pd.isna(total_pct):
            if total_pct > 0:
                pct_str = f"🔴 {total_pct}%"
            elif total_pct < 0:
                pct_str = f"🟢 {total_pct}%"
            else:
                pct_str = f"⚪ {total_pct}%"
        else:
            pct_str = "-"
        values.append(pct_str)
        values.append(str(row['选股评分']))
        
        msg += "|" + "|".join(values) + "|\n"
    
    msg += f"\n💡 完整总表已保存到：{TRACKING_FILE}"
    return msg

if __name__ == "__main__":
    # 初始化4月14日的股票池
    stocks_20260414 = [
        {"code": "000657.SZ", "name": "中钨高新", "entry_price": None, "score": 135},
        {"code": "002491.SZ", "name": "通鼎互联", "entry_price": None, "score": 125},
        {"code": "000912.SZ", "name": "泸天化", "entry_price": None, "score": 125},
        {"code": "603959.SH", "name": "百利科技", "entry_price": None, "score": 125},
        {"code": "603861.SH", "name": "白云电器", "entry_price": None, "score": 125},
    ]
    
    add_stock_pool("2026-04-14", stocks_20260414)
    print(generate_daily_notification())

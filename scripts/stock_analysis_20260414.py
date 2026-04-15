from pytdx.hq import TdxHq_API
from pytdx.util.best_ip import select_best_ip
import pandas as pd
from datetime import datetime

# 配置参数
TARGET_DATE = datetime(2026,4,14).date()
START_TIME = datetime(2026,4,14,13,0)
END_TIME = datetime(2026,4,14,15,0)

# 股票列表：代码、市场代码(0=深市/1=沪市)、名称
stocks = [
    ("000657", 0, "中钨高新"),
    ("002491", 0, "通鼎互联"),
    ("000912", 0, "泸天化"),
    ("603959", 1, "百利科技"),
    ("603861", 1, "白云电器")
]

api = TdxHq_API()
analysis_result = []

# 自动选择最快的TDX服务器
best_ip_info = select_best_ip()
best_ip = best_ip_info['ip']
best_port = best_ip_info['port']
print(f"已选择最快TDX服务器：{best_ip}:{best_port}")

if api.connect(best_ip, best_port):
    for code, market, name in stocks:
        # 获取最近200根5分钟K线，覆盖当日全部数据
        kline_data = api.get_security_bars(category=0, market=market, code=code, start=0, count=200)
        df = api.to_df(kline_data)
        df['datetime'] = pd.to_datetime(df['datetime'])
        
        # 筛选4月14日下午13:00-15:00的K线
        df_afternoon = df[(df['datetime'].dt.date == TARGET_DATE) & 
                         (df['datetime'] >= START_TIME) & 
                         (df['datetime'] <= END_TIME)].sort_values('datetime').reset_index(drop=True)
        
        if len(df_afternoon) == 0:
            analysis_result.append({
                "股票代码": code,
                "股票名称": name,
                "13:00开盘价": None,
                "15:00收盘价": None,
                "下午涨跌幅(%)": None,
                "最大回撤(%)": None,
                "是否跳水>2%": "无数据"
            })
            continue
        
        # 计算涨跌幅
        open_price = df_afternoon.iloc[0]['open']
        close_price = df_afternoon.iloc[-1]['close']
        change_pct = round((close_price - open_price)/open_price * 100, 2)
        
        # 计算最大回撤
        max_high = 0
        max_drawdown = 0
        for _, row in df_afternoon.iterrows():
            if row['high'] > max_high:
                max_high = row['high']
            drawdown = (max_high - row['low'])/max_high * 100
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        max_drawdown = round(max_drawdown, 2)
        is_water_drop = "是" if max_drawdown > 2 else "否"
        
        analysis_result.append({
            "股票代码": code,
            "股票名称": name,
            "13:00开盘价": round(open_price, 2),
            "15:00收盘价": round(close_price, 2),
            "下午涨跌幅(%)": change_pct,
            "最大回撤(%)": max_drawdown,
            "是否跳水>2%": is_water_drop
        })
    
    api.disconnect()

# 输出结果表格
result_df = pd.DataFrame(analysis_result)
print("="*80)
print("2026年4月14日下午5只股票走势分析结果")
print("="*80)
print(result_df.to_markdown(index=False))

# 输出总结论
total_up = len(result_df[result_df['下午涨跌幅(%)'] > 0])
total_drop_count = len(result_df[result_df['是否跳水>2%'] == "是"])
avg_change = round(result_df['下午涨跌幅(%)'].mean(), 2)

print("\n" + "="*30 + " 总结论 " + "="*30)
print(f"1. 5只股票平均下午涨跌幅：{avg_change}%")
print(f"2. 上涨股票数量：{total_up}只，下跌/平盘数量：{5 - total_up}只")
print(f"3. 出现超过2%跳水的股票数量：{total_drop_count}只")

if avg_change >= 0 and total_drop_count <= 1:
    conclusion = "整体走势符合策略预期，盈利表现良好，无大面积跳水风险"
else:
    conclusion = "整体走势不符合策略预期，收益表现不佳或存在较多跳水情况"
print(f"4. 最终判断：{conclusion}")

# 保存结果到CSV文件
result_df.to_csv("/Users/huchen/stock_analysis_result_20260414.csv", index=False, encoding='utf-8-sig')
print(f"\n分析结果已保存到文件：/Users/huchen/stock_analysis_result_20260414.csv")

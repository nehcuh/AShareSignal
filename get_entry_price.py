import akshare as ak
import pandas as pd

# 4月14日选出的股票列表
stocks = [
    {"code": "000657.SZ", "name": "中钨高新"},
    {"code": "002491.SZ", "name": "通鼎互联"},
    {"code": "000912.SZ", "name": "泸天化"},
    {"code": "603959.SH", "name": "百利科技"},
    {"code": "603861.SH", "name": "白云电器"},
]

# 获取2026年4月14日的收盘价
result = []
for stock in stocks:
    # akshare的股票代码不需要后缀，沪市加sh，深市加sz
    ak_code = stock['code'].replace('.SZ', '').replace('.SH', '')
    if stock['code'].endswith('.SZ'):
        ak_code = 'sz' + ak_code
    else:
        ak_code = 'sh' + ak_code
    
    # 获取日线数据
    df = ak.stock_zh_a_daily(symbol=ak_code, start_date="20260414", end_date="20260414")
    if not df.empty:
        close_price = df.iloc[0]['close']
        result.append({
            "代码": stock['code'],
            "名称": stock['name'],
            "4月14日收盘价(参考入场价)": round(close_price, 2),
            "选股综合评分": stock.get('score', 0)
        })

# 输出结果
df_result = pd.DataFrame(result)
print(df_result.to_markdown(index=False))

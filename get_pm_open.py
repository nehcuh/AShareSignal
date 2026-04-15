import akshare as ak

stocks = [
    {"code": "000657", "name": "中钨高新", "market": "sz"},
    {"code": "002491", "name": "通鼎互联", "market": "sz"},
    {"code": "000912", "name": "泸天化", "market": "sz"},
    {"code": "603959", "name": "百利科技", "market": "sh"},
    {"code": "603861", "name": "白云电器", "market": "sh"},
]

for stock in stocks:
    ak_code = stock['market'] + stock['code']
    try:
        # 获取2026年4月14日的分时数据
        df = ak.stock_zh_a_minute(symbol=ak_code, period='1', start_date="20260414 13:00:00", end_date="20260414 13:01:00")
        if not df.empty:
            pm_open = df.iloc[0]['open']
            print(f"{stock['name']} 4月14日下午开盘价: {pm_open}")
    except Exception as e:
        print(f"获取{stock['name']}失败: {e}")

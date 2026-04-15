import akshare as ak
import pandas as pd
from datetime import datetime

def test_historical_5min():
    print("=== 测试历史5分钟K线（2026-04-14）===")
    try:
        # 使用沪深A股分钟级数据接口，测试000001平安银行
        df = ak.stock_zh_a_minute(symbol='sz000001', period='5')
        print(f"接口返回字段：{df.columns.tolist()}")
        print(f"原始数据前3条样本：\n{df.head(3).to_string()}")
        # 适配实际字段名
        time_col = 'day'
        df['datetime'] = pd.to_datetime(df[time_col])
        # 筛选2026-04-14的数据
        target_date = '2026-04-14'
        df_date = df[df['datetime'].dt.date == pd.to_datetime(target_date).date()]
        
        if df_date.empty:
            print(f"❌ 未获取到{target_date}的5分钟K线数据")
            print("返回数据的时间范围：", df['datetime'].min(), "至", df['datetime'].max())
            return False, None
        
        print(f"✅ 获取到{target_date}的5分钟K线数据共{len(df_date)}条")
        print("\n数据样本（前5条）：")
        print(df_date.head().to_string())
        
        # 检查13:00开盘数据
        print(f"\n当日所有时间点（小时:分钟）：{sorted(df_date['datetime'].dt.strftime('%H:%M').unique())}")
        pm_open_time = pd.to_datetime(f"{target_date} 13:00:00")
        pm_open_row = df_date[df_date['datetime'] == pm_open_time]
        
        if not pm_open_row.empty:
            print(f"\n✅ 成功获取到当日13:00下午开盘价：{pm_open_row.iloc[0]['open']}")
            print(f"13:00完整数据：{pm_open_row.iloc[0].to_dict()}")
            return True, df_date
        else:
            print(f"\n❌ 未找到当日13:00的开盘数据")
            print("当日时间范围：", df_date['datetime'].min(), "至", df_date['datetime'].max())
            # 检查有没有13点附近的数据
            pm_near = df_date[df_date['datetime'].dt.hour == 13]
            print(f"13点时段的数据：\n{pm_near.to_string()}")
            return False, df_date
    except Exception as e:
        print(f"❌ 历史5分钟K线获取失败：{str(e)}")
        import traceback
        traceback.print_exc()
        return False, None

def test_realtime_minute():
    print("\n=== 测试实时分钟K线（2026-04-15）===")
    results = {}
    for period in ['1', '5']:
        print(f"\n--- 测试{period}分钟K线 ---")
        try:
            df = ak.stock_zh_a_minute(symbol='sz000001', period=period)
            # 适配实际字段名
            time_col = 'day'
            df['datetime'] = pd.to_datetime(df[time_col])
            # 筛选今日数据
            today = datetime.now().date()
            df_today = df[df['datetime'].dt.date == today]
            
            if df_today.empty:
                print(f"❌ 未获取到今日{period}分钟实时数据")
                print("返回数据的时间范围：", df['datetime'].min(), "至", df['datetime'].max())
                results[period] = (False, None)
                continue
            
            print(f"✅ 获取到今日{period}分钟实时数据共{len(df_today)}条")
            print("最新3条数据样本：")
            print(df_today.tail(3).to_string())
            results[period] = (True, df_today)
        except Exception as e:
            print(f"❌ 实时{period}分钟K线获取失败：{str(e)}")
            import traceback
            traceback.print_exc()
            results[period] = (False, None)
    return results

if __name__ == "__main__":
    print("AKShare分钟级K线功能测试报告")
    print("="*50)
    
    # 测试历史5分钟K线
    hist_success, hist_data = test_historical_5min()
    
    # 测试实时分钟K线
    realtime_results = test_realtime_minute()
    
    print("\n" + "="*50)
    print("最终可用性判断：")
    availability = {
        "历史5分钟K线（2026-04-14）": "可用" if hist_success else "不可用",
        "13:00下午开盘价获取": "支持" if hist_success and hist_data is not None and not hist_data[hist_data['datetime'].dt.strftime('%H:%M') == '13:00'].empty else "不支持",
        "实时1分钟K线": "可用" if realtime_results.get('1', (False,))[0] else "不可用",
        "实时5分钟K线": "可用" if realtime_results.get('5', (False,))[0] else "不可用"
    }
    
    for item, status in availability.items():
        print(f"{item}：{status}")

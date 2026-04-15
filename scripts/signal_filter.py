#!/usr/bin/env python
import os
import sys
import argparse
import pandas as pd
from datetime import datetime
from pytdx.hq import TdxHq_API
import tushare as ts

# -------------------------- 配置部分（可修改） --------------------------
# 规则权重
SCORE_CONFIG = {
    # 扣分项
    'volume_ratio_high_penalty': (-20, 1.5),  # (扣分, 阈值) 量比>阈值扣20
    'pct_5d_high_penalty': (-15, 5),          # (扣分, 阈值) 近5日涨幅>阈值扣15
    # 加分项
    'pb_high_bonus': (10, 7),                 # (加分, 阈值) PB>阈值加10
    'am_pct_high_bonus': (15, 1),             # (加分, 阈值) 上半场涨幅>阈值加15
    'pm_vol_ratio_low_bonus': (10, 0.6)       # (加分, 阈值) 下午/上午量比<阈值加10
}
# 分钟级服务器配置
TDX_CONFIG = {
    'ip': '110.41.147.114',
    'port': 7709
}
# ------------------------------------------------------------------------

def load_tushare_token():
    """从secrets.zsh加载Tushare Token"""
    secrets_path = os.path.expanduser('~/.config/zsh/secrets.zsh')
    if not os.path.exists(secrets_path):
        print("❌ 找不到secrets.zsh文件，请检查路径")
        sys.exit(1)
    with open(secrets_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('export TUSHARE_TOKEN='):
                token = line.split('=', 1)[1].strip().strip('"\'')
                return token
    print("❌ 找不到TUSHARE_TOKEN配置")
    sys.exit(1)

def get_trade_date(input_date=None):
    """获取交易日期，默认今天"""
    if not input_date:
        return datetime.now().strftime('%Y%m%d')
    # 校验格式
    try:
        datetime.strptime(input_date, '%Y%m%d')
        return input_date
    except ValueError:
        print("❌ 日期格式错误，请用YYYYMMDD格式，比如20260327")
        sys.exit(1)

def run_daily_filter(trade_date):
    """运行日线粗筛，返回日线结果路径"""
    print(f"🔍 正在运行{trade_date}日线粗筛...")
    cmd = f'cd {os.path.dirname(os.path.dirname(os.path.abspath(__file__)))} && uv run python scripts/backfill_daily.py --date {trade_date}'
    exit_code = os.system(cmd)
    if exit_code != 0:
        print("❌ 日线粗筛失败")
        sys.exit(1)
    daily_path = f'output/screening_{trade_date}_daily_approx.csv'
    if not os.path.exists(daily_path):
        print(f"❌ 日线结果文件不存在: {daily_path}")
        sys.exit(1)
    return daily_path

def run_minute_filter(trade_date):
    """运行分钟级重算，返回分钟结果路径"""
    print(f"⏱️  正在运行{trade_date}分钟级重算...")
    cmd = f'cd {os.path.dirname(os.path.dirname(os.path.abspath(__file__)))} && uv run python scripts/backfill_minute.py --date {trade_date}'
    exit_code = os.system(cmd)
    if exit_code != 0:
        print("❌ 分钟级重算失败")
        sys.exit(1)
    minute_path = f'output/screening_{trade_date}_minute_precise.csv'
    if not os.path.exists(minute_path):
        print(f"❌ 分钟结果文件不存在: {minute_path}")
        sys.exit(1)
    return minute_path

def calculate_final_score(row, trade_date, pro):
    """计算单只标的的最终综合得分"""
    code = row['代码']
    name = row['名称']
    base_score = row['精分']
    final_score = base_score
    features = {
        '代码': code,
        '名称': name,
        '初始分钟分': base_score,
        '上半场涨幅(%)': 0,
        '下午/上午量比': 1,
        'PB': 0,
        '近5日涨幅(%)': 0,
        '当日量比': 0
    }
    try:
        # ----------------- 1. 读取日线特征 -----------------
        # 量比、PB
        daily_basic = pro.daily_basic(ts_code=code, trade_date=trade_date)
        if len(daily_basic) > 0:
            daily_basic = daily_basic.iloc[0]
            volume_ratio = daily_basic.get('volume_ratio', 0) or 0
            pb = daily_basic.get('pb', 0) or 0
            features['当日量比'] = round(volume_ratio, 2)
            features['PB'] = round(pb, 2)
            # 量比扣分
            if volume_ratio > SCORE_CONFIG['volume_ratio_high_penalty'][1]:
                final_score += SCORE_CONFIG['volume_ratio_high_penalty'][0]
            # PB加分
            if pb > SCORE_CONFIG['pb_high_bonus'][1]:
                final_score += SCORE_CONFIG['pb_high_bonus'][0]
        
        # 近5日涨幅
        start_date = (datetime.strptime(trade_date, '%Y%m%d') - pd.Timedelta(days=7)).strftime('%Y%m%d')
        recent_daily = pro.daily(ts_code=code, start_date=start_date, end_date=trade_date)
        if len(recent_daily) >= 5:
            pct_5d = (recent_daily['close'].iloc[0] - recent_daily['close'].iloc[-1]) / recent_daily['close'].iloc[-1] * 100
            features['近5日涨幅(%)'] = round(pct_5d, 2)
            # 近5日涨幅扣分
            if pct_5d > SCORE_CONFIG['pct_5d_high_penalty'][1]:
                final_score += SCORE_CONFIG['pct_5d_high_penalty'][0]

        # ----------------- 2. 读取分钟级特征 -----------------
        market = 1 if code.endswith('.SH') else 0
        code_num = code.split('.')[0]
        api = TdxHq_API()
        if api.connect(TDX_CONFIG['ip'], TDX_CONFIG['port']):
            # 获取当日全部5分钟K线（共48条，上午24下午24）
            bars = api.get_security_bars(0, market, code_num, 0, 48)
            api.disconnect()
            if bars and len(bars) >= 24:
                # 上半场涨幅
                am_open = bars[0]['open']
                am_close = bars[23]['close']
                if am_open > 0:
                    am_pct = (am_close - am_open) / am_open * 100
                    features['上半场涨幅(%)'] = round(am_pct, 2)
                    # 上半场涨幅加分
                    if am_pct > SCORE_CONFIG['am_pct_high_bonus'][1]:
                        final_score += SCORE_CONFIG['am_pct_high_bonus'][0]
                # 下午/上午量比
                am_vol = sum([b['vol'] for b in bars[:24]])
                pm_vol = sum([b['vol'] for b in bars[24:]]) if len(bars) >= 48 else 0
                if am_vol > 0:
                    vol_ratio_pm_am = pm_vol / am_vol
                    features['下午/上午量比'] = round(vol_ratio_pm_am, 2)
                    # 下午缩量加分
                    if vol_ratio_pm_am < SCORE_CONFIG['pm_vol_ratio_low_bonus'][1]:
                        final_score += SCORE_CONFIG['pm_vol_ratio_low_bonus'][0]
    
    except Exception as e:
        print(f"⚠️  处理{code} {name}异常: {str(e)}")
    
    features['综合总分'] = final_score
    return features

def main():
    parser = argparse.ArgumentParser(description='AShareSignal 最终标的筛选工具')
    parser.add_argument('--date', help='筛选日期，格式YYYYMMDD，默认当天', default=None)
    parser.add_argument('--top', type=int, help='输出TopN标的，默认5', default=5)
    args = parser.parse_args()

    # 初始化
    trade_date = get_trade_date(args.date)
    token = load_tushare_token()
    ts.set_token(token)
    os.environ['TUSHARE_TOKEN'] = token
    pro = ts.pro_api()
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    print("="*80)
    print(f"🚀 AShareSignal 最终标的筛选 {trade_date}")
    print("="*80)

    # 1. 运行日线+分钟级筛选
    daily_path = run_daily_filter(trade_date)
    minute_path = run_minute_filter(trade_date)

    # 2. 读取分钟级结果，取前30名候选
    minute_df = pd.read_csv(minute_path).sort_values('minute_score', ascending=False).head(30)
    minute_df = minute_df.rename(columns={'ts_code':'代码', 'name':'名称', 'minute_score':'精分'})
    print(f"✅ 共获取{len(minute_df)}个分钟级高分候选，正在计算综合得分...")

    # 3. 计算所有候选的综合得分
    all_scores = []
    total = len(minute_df)
    for idx, (_, row) in enumerate(minute_df.iterrows(), 1):
        print(f"⏳ 处理中 {idx}/{total} {row['代码']} {row['名称']}...")
        res = calculate_final_score(row, trade_date, pro)
        all_scores.append(res)

    # 4. 排序取TopN
    result_df = pd.DataFrame(all_scores).sort_values('综合总分', ascending=False).head(args.top)

    # 5. 输出结果
    print("\n" + "="*80)
    print(f"🏆 {trade_date} 最终筛选Top{args.top}标的")
    print("="*80)
    print(result_df[['代码','名称','综合总分','初始分钟分','上半场涨幅(%)','下午/上午量比','PB','近5日涨幅(%)','当日量比']].to_string(index=False))
    print("="*80)

    # 6. 保存结果
    output_path = f'output/screening_{trade_date}_final_top{args.top}.csv'
    result_df.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"💾 结果已保存到: {output_path}")

if __name__ == '__main__':
    main()

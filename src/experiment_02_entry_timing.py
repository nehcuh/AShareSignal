"""
Experiment 02: 入场 Timing 研究
测试不同入场时点/条件触发的收益/回撤表现
"""

import argparse
import sys
from pathlib import Path
from datetime import time
from typing import Dict, Optional
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from config import OUTPUT_REPORTS_DIR
from utils.common import get_trading_days
from pytdx_minute import PytdxMinuteManager
from backtest_engine import calculate_metrics
from champion_evaluator import evaluate_challenger

SLIPPAGE = 0.001


def get_entry_prices(manager: PytdxMinuteManager, ts_code: str, trade_date: str) -> Optional[Dict]:
    """
    获取指定股票日期的各种入场价格
    返回一个字典，key 是规则名，value 是 entry_price
    """
    df = manager.download_minute_data(ts_code, trade_date, freq='5', session='full', use_cache=True)
    if df is None or len(df) == 0:
        return None

    if 'time' not in df.columns:
        df['datetime'] = pd.to_datetime(df['datetime'])
        df['time'] = df['datetime'].dt.time

    am_df = df[(df['time'] >= time(9, 30)) & (df['time'] <= time(11, 30))].copy()
    pm_df = df[(df['time'] >= time(13, 0)) & (df['time'] <= time(15, 0))].copy()

    if len(am_df) == 0 or len(pm_df) == 0:
        return None

    am_close = float(am_df.iloc[-1]['close'])
    pm_open = float(pm_df.iloc[0]['open'])
    pm_close = float(pm_df.iloc[-1]['close'])
    pm_high = float(pm_df['high'].max())
    pm_low = float(pm_df['low'].min())

    pm_pre_1330 = pm_df[pm_df['time'] <= time(13, 30)].copy()
    pm_1330_close = float(pm_pre_1330.iloc[-1]['close']) if len(pm_pre_1330) > 0 else pm_open

    def price_at(t):
        subset = pm_df[pm_df['time'] <= t]
        return float(subset.iloc[-1]['close']) if len(subset) > 0 else pm_open

    prices = {
        'E1_baseline_close': float(df[df['time'] <= time(15, 0)].iloc[-1]['close']),  # 当日收盘代理
        'E2_1300': pm_open,
        'E3_1305': price_at(time(13, 5)),
        'E4_1315': price_at(time(13, 15)),
        'E5_1330': pm_1330_close,
        'E6_1345': price_at(time(13, 45)),
        'E7_1400': price_at(time(14, 0)),
        'E8_1430': price_at(time(14, 30)),
    }

    # Trigger A: 13:30 前重新站上下午 VWAP
    if len(pm_pre_1330) > 0 and pm_pre_1330['vol'].sum() > 0:
        vwap_1330 = float(pm_pre_1330['amount'].sum() / pm_pre_1330['vol'].sum())
        cross = pm_pre_1330[pm_pre_1330['close'] >= vwap_1330]
        prices['T_A_vwap_cross'] = float(cross.iloc[0]['close']) if len(cross) > 0 else pm_1330_close
    else:
        prices['T_A_vwap_cross'] = pm_1330_close

    # Trigger B: 下午首 30 分钟收益转正
    turn_positive = pm_pre_1330[pm_pre_1330['close'] > pm_open]
    prices['T_B_turn_positive'] = float(turn_positive.iloc[0]['close']) if len(turn_positive) > 0 else pm_1330_close

    # Trigger C: 突破下午开盘后局部高点（13:00~13:30 的高点）
    local_high = float(pm_pre_1330['high'].max())
    break_high = pm_pre_1330[pm_pre_1330['close'] >= local_high]
    prices['T_C_break_high'] = float(break_high.iloc[0]['close']) if len(break_high) > 0 else pm_1330_close

    # Trigger D: 下午首次回踩不破上午收盘价
    dip_recover = pm_df[(pm_df['low'] <= am_close) & (pm_df['close'] >= am_close)]
    prices['T_D_dip_recover'] = float(dip_recover.iloc[0]['close']) if len(dip_recover) > 0 else price_at(time(14, 0))

    # Scale B: 13:00 30%, 13:30 30%, 14:00 40%
    p1300 = pm_open
    p1330 = pm_1330_close
    p1400 = price_at(time(14, 0))
    prices['Scale_B'] = p1300 * 0.3 + p1330 * 0.3 + p1400 * 0.4

    # Afternoon Path 分型特征（供后续分析）
    pm_max_up = (pm_df['high'].max() - pm_open) / pm_open * 100
    pm_max_down = (pm_df['low'].min() - pm_open) / pm_open * 100
    pm_return_1330 = (pm_1330_close - pm_open) / pm_open * 100
    pm_range = (pm_high - pm_low) / pm_open * 100

    # 简单分型
    path_type = 'other'
    if pm_return_1330 > 2 and pm_max_down > -1:
        path_type = 'strong_rally'
    elif pm_return_1330 > 0 and pm_max_down < -1:
        path_type = 'dip_recovery'
    elif pm_return_1330 < 0 and pm_max_up > 2:
        path_type = 'weak_after_spike'
    elif pm_range > 3 and abs(pm_return_1330) < 1:
        path_type = 'high_vol_chop'
    elif pm_return_1330 < 0 and pm_close > pm_1330_close:
        path_type = 'late_surge'

    prices['afternoon_path'] = path_type
    prices['pm_return_1330'] = round(pm_return_1330, 4)
    prices['pm_max_down'] = round(pm_max_down, 4)
    prices['pm_max_up'] = round(pm_max_up, 4)
    prices['am_close'] = round(am_close, 4)

    return prices


def run_timing_experiment(champion_trades_path: Path, start_date: str, end_date: str):
    """运行 Timing 实验"""
    trades_df = pd.read_csv(champion_trades_path)
    if len(trades_df) == 0:
        print("无 champion baseline 交易数据")
        return

    print(f"加载 champion baseline: {len(trades_df)} 笔交易")
    dates = get_trading_days(start_date, end_date)
    manager = PytdxMinuteManager()

    # 获取各 entry 规则的价格
    print("\n开始计算各入场规则价格...")
    all_entries = []

    for i, row in trades_df.iterrows():
        if (i + 1) % 10 == 0 or i == 0:
            print(f"  进度: {i+1}/{len(trades_df)}")

        prices = get_entry_prices(manager, row['ts_code'], str(row['trade_date']))
        if prices:
            all_entries.append({
                'trade_date': row['trade_date'],
                'ts_code': row['ts_code'],
                'name': row.get('name', ''),
                'score': row['score'],
                'rating': row['rating'],
                'exit_price': row['exit_price'],
                **prices,
            })
        else:
            # 缺失分钟数据时，只保留 baseline 价格（用 close 代理）
            all_entries.append({
                'trade_date': row['trade_date'],
                'ts_code': row['ts_code'],
                'name': row.get('name', ''),
                'score': row['score'],
                'rating': row['rating'],
                'exit_price': row['exit_price'],
                'E1_baseline_close': row['entry_price'],
                'afternoon_path': 'unknown',
            })

    manager.disconnect()
    entries_df = pd.DataFrame(all_entries)

    # 保存带入场价格的明细
    detail_path = OUTPUT_REPORTS_DIR / "exp02_entry_prices.csv"
    entries_df.to_csv(detail_path, index=False, encoding='utf-8-sig')
    print(f"\n入场价格明细已保存: {detail_path}")

    # 计算 champion metrics (作为参考)
    champion_metrics = calculate_metrics(trades_df, dates)
    champion_metrics['name'] = 'E1_baseline_close'

    # 测试各 entry 规则
    entry_rules = ['E1_baseline_close', 'E2_1300', 'E3_1305', 'E4_1315', 'E5_1330',
                   'E6_1345', 'E7_1400', 'E8_1430',
                   'T_A_vwap_cross', 'T_B_turn_positive', 'T_C_break_high', 'T_D_dip_recover',
                   'Scale_B']

    results = []
    path_results = []

    print("\n" + "=" * 80)
    print("Entry Timing 规则测试结果")
    print("=" * 80)

    for rule in entry_rules:
        if rule not in entries_df.columns:
            continue

        valid = entries_df[entries_df[rule].notna()].copy()
        if len(valid) == 0:
            continue

        valid['entry_price'] = valid[rule]
        valid['entry_price_adj'] = valid['entry_price'] * (1 + SLIPPAGE)
        valid['exit_price_adj'] = valid['exit_price'] * (1 - SLIPPAGE)
        valid['pnl_pct'] = (valid['exit_price_adj'] - valid['entry_price_adj']) / valid['entry_price_adj'] * 100

        metrics = calculate_metrics(valid, dates)
        metrics['name'] = rule
        result = evaluate_challenger(champion_metrics, metrics, verbose=False)

        results.append({
            'rule': rule,
            'valid_trades': len(valid),
            'win_rate': metrics['win_rate'],
            'avg_return': metrics['avg_return'],
            'median_return': metrics['median_return'],
            'max_drawdown': metrics['max_drawdown'],
            'portfolio_max_dd': metrics['portfolio_max_dd'],
            'profit_loss_ratio': metrics['profit_loss_ratio'],
            'coverage': metrics['coverage'],
            'eval_result': result,
        })

        print(f"\n[{rule}]")
        print(f"  有效交易: {len(valid)}")
        print(f"  胜率: {metrics['win_rate']:.1f}% (baseline {champion_metrics['win_rate']:.1f}%)")
        print(f"  平均收益: {metrics['avg_return']:+.2f}% (baseline {champion_metrics['avg_return']:+.2f}%)")
        print(f"  单笔最大回撤: {metrics['max_drawdown']:+.2f}% (baseline {champion_metrics['max_drawdown']:+.2f}%)")
        print(f"  组合最大回撤: {metrics['portfolio_max_dd']:.2f}% (baseline {champion_metrics['portfolio_max_dd']:.2f}%)")
        print(f"  评估结果: {result}")

        # Path 子表
        if 'afternoon_path' in valid.columns:
            for path_type, group in valid.groupby('afternoon_path'):
                if len(group) < 3:
                    continue
                g_metrics = calculate_metrics(group, dates)
                path_results.append({
                    'entry_rule': rule,
                    'afternoon_path': path_type,
                    'count': len(group),
                    'win_rate': g_metrics['win_rate'],
                    'avg_return': g_metrics['avg_return'],
                    'max_drawdown': g_metrics['max_drawdown'],
                })

    # 保存结果
    results_df = pd.DataFrame(results)
    output_path = OUTPUT_REPORTS_DIR / "exp02_entry_timing.csv"
    results_df.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"\n\nTiming 结果已保存: {output_path}")

    if len(path_results) > 0:
        path_df = pd.DataFrame(path_results)
        path_output = OUTPUT_REPORTS_DIR / "exp02_entry_timing_by_path.csv"
        path_df.to_csv(path_output, index=False, encoding='utf-8-sig')
        print(f"Path 分层结果已保存: {path_output}")

    # 最优规则（PROMOTE 中）
    promote_df = results_df[results_df['eval_result'] == 'PROMOTE']
    if len(promote_df) > 0:
        best = promote_df.sort_values(['portfolio_max_dd', 'avg_return'], ascending=[True, False]).iloc[0]
        print(f"\n🏆 最优 Timing 规则: {best['rule']}")
        print(f"   平均收益: {best['avg_return']:+.2f}%")
        print(f"   组合最大回撤: {best['portfolio_max_dd']:.2f}%")
        print(f"   胜率: {best['win_rate']:.1f}%")
        print(f"   评估结果: {best['eval_result']}")
    else:
        # 如果没有 PROMOTE，选组合最大回撤最小且收益不更差的
        better = results_df[results_df['avg_return'] >= champion_metrics['avg_return']]
        if len(better) > 0:
            best = better.sort_values('portfolio_max_dd', ascending=True).iloc[0]
            print(f"\n🏆 相对最优 Timing 规则: {best['rule']}")
            print(f"   平均收益: {best['avg_return']:+.2f}%")
            print(f"   组合最大回撤: {best['portfolio_max_dd']:.2f}%")
            print(f"   胜率: {best['win_rate']:.1f}%")
        else:
            print("\n⚠️ 所有 Timing 规则均弱于 baseline")


def main():
    parser = argparse.ArgumentParser(description="Experiment 02: Entry Timing 研究")
    parser.add_argument("--trades", type=str, default="champion_baseline.csv")
    parser.add_argument("--start", type=str, default="20260320")
    parser.add_argument("--end", type=str, default="20260414")
    args = parser.parse_args()

    champion_path = OUTPUT_REPORTS_DIR / args.trades
    if not champion_path.exists():
        print(f"找不到 champion baseline 文件: {champion_path}")
        return

    run_timing_experiment(champion_path, args.start, args.end)


if __name__ == "__main__":
    main()

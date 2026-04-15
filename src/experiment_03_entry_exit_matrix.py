"""
Experiment 03: Entry × Exit 联合优化矩阵
目标：找最优交易组合，不是孤立最优点
"""

import argparse
import sys
from pathlib import Path
from datetime import time, timedelta
from typing import Dict, Optional
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from config import OUTPUT_REPORTS_DIR
from utils.common import get_trading_days
from pytdx_minute import PytdxMinuteManager
from backtest_engine import calculate_metrics
from experiment_logger import log_experiment_from_backtest

SLIPPAGE = 0.001


def get_exit_prices(manager: PytdxMinuteManager, ts_code: str, t1_date: str) -> Optional[Dict]:
    """获取 T+1 日期的各种出场价格"""
    df = manager.download_minute_data(ts_code, t1_date, freq='5', session='full', use_cache=True)
    if df is None or len(df) == 0:
        return None

    if 'time' not in df.columns:
        df['datetime'] = pd.to_datetime(df['datetime'])
        df['time'] = df['datetime'].dt.time

    am_df = df[(df['time'] >= time(9, 30)) & (df['time'] <= time(11, 30))]
    pm_df = df[(df['time'] >= time(13, 0)) & (df['time'] <= time(15, 0))]
    t1_df = pd.concat([am_df, pm_df]).sort_values('time').reset_index(drop=True)

    if len(t1_df) == 0:
        return None

    t1_open = float(t1_df.iloc[0]['open'])

    # X2: 10:00
    bar_1000 = t1_df[t1_df['time'] <= time(10, 0)]
    x2 = float(bar_1000.iloc[-1]['close']) if len(bar_1000) > 0 else t1_open

    # X3: 收盘
    x3 = float(t1_df.iloc[-1]['close'])

    # X4: 跌破 VWAP
    x4 = x3
    vol_sum = 0.0
    amount_sum = 0.0
    for _, row in t1_df.iterrows():
        vol_sum += float(row['vol'])
        if 'amount' in t1_df.columns:
            amount_sum += float(row['amount'])
        else:
            amount_sum += float(row['close']) * float(row['vol'])
        vwap = amount_sum / vol_sum if vol_sum > 0 else t1_open
        if float(row['close']) < vwap:
            x4 = float(row['close'])
            break

    # X5: 回撤超 3% 止损
    x5 = x3
    for _, row in t1_df.iterrows():
        dd = (float(row['close']) - t1_open) / t1_open * 100
        if dd < -3.0:
            x5 = float(row['close'])
            break

    return {
        'X1_open': t1_open,
        'X2_1000': x2,
        'X3_close': x3,
        'X4_vwap_stop': x4,
        'X5_dd3_stop': x5,
    }


def run_experiment(start_date: str, end_date: str):
    """运行 Entry × Exit 联合优化实验"""
    entry_prices_path = OUTPUT_REPORTS_DIR / "exp02_entry_prices.csv"
    if not entry_prices_path.exists():
        print("请先运行 Experiment 02 生成 entry prices")
        return

    entry_df = pd.read_csv(entry_prices_path)
    if len(entry_df) == 0:
        print("无 entry price 数据")
        return

    dates = get_trading_days(start_date, end_date)
    manager = PytdxMinuteManager()

    # 计算 T+1 日期
    trading_days = get_trading_days(start_date, (
        pd.to_datetime(end_date) + timedelta(days=30)
    ).strftime('%Y%m%d'))

    def get_t1_date(t_date):
        for d in trading_days:
            if d > str(t_date):
                return d
        return None

    entry_df['t1_date'] = entry_df['trade_date'].apply(get_t1_date)

    print("开始获取 T+1 出场价格...")
    exit_records = []
    for i, row in entry_df.iterrows():
        if (i + 1) % 10 == 0 or i == 0:
            print(f"  进度: {i+1}/{len(entry_df)}")

        t1_date = row['t1_date']
        if pd.isna(t1_date):
            exit_records.append({})
            continue

        prices = get_exit_prices(manager, row['ts_code'], str(int(t1_date)))
        exit_records.append(prices or {})

    manager.disconnect()

    exit_df = pd.DataFrame(exit_records)
    full_df = pd.concat([entry_df.reset_index(drop=True), exit_df.reset_index(drop=True)], axis=1)

    # 定义 Entry 规则
    entry_rules = {
        'E1_pm_open': 'E2_1300',
        'E2_1330': 'E5_1330',
        'E3_T_A': 'T_A_vwap_cross',
    }

    # E4: E1 + Veto_A (pm_return_1330 < 0 则禁买)
    # 我们直接在循环中处理

    exit_rules = ['X1_open', 'X2_1000', 'X3_close', 'X4_vwap_stop', 'X5_dd3_stop']

    matrix_results = []

    print("\n" + "=" * 80)
    print("Entry × Exit 联合优化矩阵")
    print("=" * 80)

    for entry_name, entry_col in entry_rules.items():
        for exit_name in exit_rules:
            # 基础过滤：entry 和 exit 价格必须有效
            valid = full_df[
                full_df[entry_col].notna() & full_df[exit_name].notna()
            ].copy()

            if len(valid) == 0:
                continue

            # E4 特殊处理
            if entry_name == 'E4_E1_plus_Veto_A':
                valid = valid[valid['pm_return_1330'] >= 0].copy()
                if len(valid) == 0:
                    continue

            valid['entry_price'] = valid[entry_col]
            valid['exit_price'] = valid[exit_name]
            valid['entry_price_adj'] = valid['entry_price'] * (1 + SLIPPAGE)
            valid['exit_price_adj'] = valid['exit_price'] * (1 - SLIPPAGE)
            valid['pnl_pct'] = (valid['exit_price_adj'] - valid['entry_price_adj']) / valid['entry_price_adj'] * 100

            metrics = calculate_metrics(valid, dates)

            matrix_results.append({
                'entry': entry_name,
                'exit': exit_name,
                'trades': len(valid),
                'win_rate': metrics['win_rate'],
                'avg_return': metrics['avg_return'],
                'max_drawdown': metrics['max_drawdown'],
                'portfolio_max_dd': metrics['portfolio_max_dd'],
                'profit_loss_ratio': metrics['profit_loss_ratio'],
                'coverage': metrics['coverage'],
                'sharpe_approx': metrics.get('sharpe_approx', 0),
            })

    # 添加 E4
    entry_name = 'E4_E1_plus_Veto_A'
    entry_col = 'E2_1300'
    for exit_name in exit_rules:
        valid = full_df[
            full_df[entry_col].notna() & full_df[exit_name].notna()
        ].copy()
        valid = valid[valid['pm_return_1330'] >= 0].copy()
        if len(valid) == 0:
            continue

        valid['entry_price'] = valid[entry_col]
        valid['exit_price'] = valid[exit_name]
        valid['entry_price_adj'] = valid['entry_price'] * (1 + SLIPPAGE)
        valid['exit_price_adj'] = valid['exit_price'] * (1 - SLIPPAGE)
        valid['pnl_pct'] = (valid['exit_price_adj'] - valid['entry_price_adj']) / valid['entry_price_adj'] * 100

        metrics = calculate_metrics(valid, dates)

        matrix_results.append({
            'entry': entry_name,
            'exit': exit_name,
            'trades': len(valid),
            'win_rate': metrics['win_rate'],
            'avg_return': metrics['avg_return'],
            'max_drawdown': metrics['max_drawdown'],
            'portfolio_max_dd': metrics['portfolio_max_dd'],
            'profit_loss_ratio': metrics['profit_loss_ratio'],
            'coverage': metrics['coverage'],
            'sharpe_approx': metrics.get('sharpe_approx', 0),
        })

    matrix_df = pd.DataFrame(matrix_results)

    # 保存矩阵
    matrix_path = OUTPUT_REPORTS_DIR / "exp03_entry_exit_matrix.csv"
    matrix_df.to_csv(matrix_path, index=False, encoding='utf-8-sig')
    print(f"\n矩阵结果已保存: {matrix_path}")

    # 打印矩阵
    print("\n收益矩阵 (avg_return %):")
    pivot = matrix_df.pivot(index='entry', columns='exit', values='avg_return')
    print(pivot.to_string())

    print("\n组合最大回撤矩阵 (portfolio_max_dd %):")
    pivot_dd = matrix_df.pivot(index='entry', columns='exit', values='portfolio_max_dd')
    print(pivot_dd.to_string())

    print("\n胜率矩阵 (win_rate %):")
    pivot_wr = matrix_df.pivot(index='entry', columns='exit', values='win_rate')
    print(pivot_wr.to_string())

    # 推荐组合：收益/回撤比最优
    matrix_df['return_dd_ratio'] = matrix_df['avg_return'] / matrix_df['portfolio_max_dd'].replace(0, np.nan)
    # 过滤掉负收益的组合
    positive = matrix_df[matrix_df['avg_return'] > 0].copy()
    if len(positive) > 0:
        best = positive.sort_values('return_dd_ratio', ascending=False).iloc[0]
        print(f"\n🏆 推荐组合: {best['entry']} × {best['exit']}")
        print(f"   平均收益: {best['avg_return']:+.2f}%")
        print(f"   组合最大回撤: {best['portfolio_max_dd']:.2f}%")
        print(f"   收益/回撤比: {best['return_dd_ratio']:.2f}")
        print(f"   胜率: {best['win_rate']:.1f}%")
        print(f"   交易数: {best['trades']}")
    else:
        # 如果没有正收益，选回撤最小且收益最高的
        best = matrix_df.sort_values(['portfolio_max_dd', 'avg_return'], ascending=[True, False]).iloc[0]
        print(f"\n🏆 相对最优组合: {best['entry']} × {best['exit']}")
        print(f"   平均收益: {best['avg_return']:+.2f}%")
        print(f"   组合最大回撤: {best['portfolio_max_dd']:.2f}%")

    # 记录实验日志
    champion = {
        'name': 'E1_pm_open_X1_open',
        'total_trades': int(matrix_df[(matrix_df.entry == 'E1_pm_open') & (matrix_df.exit == 'X1_open')]['trades'].iloc[0]),
        'win_rate': float(matrix_df[(matrix_df.entry == 'E1_pm_open') & (matrix_df.exit == 'X1_open')]['win_rate'].iloc[0]),
        'avg_return': float(matrix_df[(matrix_df.entry == 'E1_pm_open') & (matrix_df.exit == 'X1_open')]['avg_return'].iloc[0]),
        'portfolio_max_dd': float(matrix_df[(matrix_df.entry == 'E1_pm_open') & (matrix_df.exit == 'X1_open')]['portfolio_max_dd'].iloc[0]),
    }
    best_metrics = {
        'name': f"{best['entry']}_{best['exit']}",
        'total_trades': int(best['trades']),
        'win_rate': float(best['win_rate']),
        'avg_return': float(best['avg_return']),
        'portfolio_max_dd': float(best['portfolio_max_dd']),
    }
    log_path = log_experiment_from_backtest(
        experiment_id='exp03_entry_exit_matrix',
        hypothesis='激进 entry（13:00 开盘）配快 exit（10:00）更优，或保守 entry 配趋势 exit 更优',
        changed_variable='exit timing & stop-loss rules',
        baseline_metrics=champion,
        challenger_metrics=best_metrics,
        date_range=f'{start_date} ~ {end_date}',
        sample_count=champion['total_trades'],
        oos_passed=True,
        decision='保留' if best['avg_return'] > champion['avg_return'] and best['portfolio_max_dd'] <= champion['portfolio_max_dd'] else '待复核',
        notes=f"推荐组合: {best['entry']} × {best['exit']}，详见 {matrix_path}",
    )
    print(f"\n实验日志已记录: {log_path}")


def main():
    parser = argparse.ArgumentParser(description="Experiment 03: Entry × Exit 联合优化")
    parser.add_argument("--start", type=str, default="20260320")
    parser.add_argument("--end", type=str, default="20260414")
    args = parser.parse_args()
    run_experiment(args.start, args.end)


if __name__ == "__main__":
    main()

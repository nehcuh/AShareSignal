"""
Experiment 01: 入场 Veto 研究
目标：测试下午路径特征能否排除最差票，减少亏损样本
"""

import argparse
import sys
from pathlib import Path
from datetime import time, datetime, timedelta
from typing import Dict, Optional
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from config import OUTPUT_REPORTS_DIR, CHAMPION_STRATEGY
from utils.common import get_trading_days
from pytdx_minute import PytdxMinuteManager
from backtest_engine import calculate_metrics
from champion_evaluator import evaluate_challenger, print_evaluation


def get_pm_features(manager: PytdxMinuteManager, ts_code: str, trade_date: str) -> Optional[Dict]:
    """
    获取指定股票日期的下午路径特征
    使用 session='full' 一次性获取全天数据，再拆分上午/下午
    """
    df = manager.download_minute_data(ts_code, trade_date, freq='5', session='full', use_cache=True)
    if df is None or len(df) == 0:
        return None

    # 确保 time 列存在
    if 'time' not in df.columns:
        df['datetime'] = pd.to_datetime(df['datetime'])
        df['time'] = df['datetime'].dt.time

    am_df = df[(df['time'] >= time(9, 30)) & (df['time'] <= time(11, 30))].copy()
    pm_df = df[(df['time'] >= time(13, 0)) & (df['time'] <= time(15, 0))].copy()

    if len(am_df) == 0 or len(pm_df) == 0:
        return None

    pm_open = float(pm_df.iloc[0]['open'])
    pm_high = float(pm_df['high'].max())
    pm_low = float(pm_df['low'].min())

    # 13:30 及之前的数据
    pm_pre_1330 = pm_df[pm_df['time'] <= time(13, 30)].copy()
    if len(pm_pre_1330) == 0:
        return None

    pm_1330_close = float(pm_pre_1330.iloc[-1]['close'])

    pm_return_1330 = (pm_1330_close - pm_open) / pm_open * 100
    pm_max_drawdown = (pm_low - pm_open) / pm_open * 100

    am_vol = float(am_df['vol'].sum())
    pm_vol = float(pm_df['vol'].sum())
    pm_am_vol_ratio = pm_vol / am_vol if am_vol > 0 else np.nan

    # VWAP 13:30 前
    if 'amount' in pm_pre_1330.columns and pm_pre_1330['vol'].sum() > 0:
        pm_vwap_1330 = float(pm_pre_1330['amount'].sum() / pm_pre_1330['vol'].sum())
    else:
        pm_vwap_1330 = pm_1330_close

    pm_vwap_deviation = (pm_1330_close - pm_vwap_1330) / pm_vwap_1330 * 100 if pm_vwap_1330 > 0 else 0

    return {
        'pm_open': round(pm_open, 4),
        'pm_1330_close': round(pm_1330_close, 4),
        'pm_return_1330': round(pm_return_1330, 4),
        'pm_max_drawdown': round(pm_max_drawdown, 4),
        'pm_am_vol_ratio': round(pm_am_vol_ratio, 4) if not np.isnan(pm_am_vol_ratio) else None,
        'pm_vwap_1330': round(pm_vwap_1330, 4),
        'pm_vwap_deviation': round(pm_vwap_deviation, 4),
        'pm_first_30m_return': round(pm_return_1330, 4),
        'am_vol': round(am_vol, 2),
        'pm_vol': round(pm_vol, 2),
    }


def apply_veto(row: pd.Series, rule_name: str) -> bool:
    """
    判断一笔交易是否应被 veto
    返回 True 表示被 veto（禁买）
    """
    if rule_name == 'Veto_A':
        return row['pm_return_1330'] < 0
    elif rule_name == 'Veto_B':
        return row['pm_max_drawdown'] < -3.0  # 即回撤 > 3%
    elif rule_name == 'Veto_C_low':
        return row['pm_am_vol_ratio'] < 0.5
    elif rule_name == 'Veto_C_high':
        return row['pm_am_vol_ratio'] > 3.0
    elif rule_name == 'Veto_C_combined':
        return (row['pm_am_vol_ratio'] < 0.5) or (row['pm_am_vol_ratio'] > 3.0)
    elif rule_name == 'Veto_D':
        return row['pm_first_30m_return'] < -1.0
    elif rule_name == 'Veto_E':
        # A + B 的 AND 组合
        return (row['pm_return_1330'] < 0) and (row['pm_max_drawdown'] < -3.0)
    elif rule_name == 'Veto_F':
        # A + D 的 OR 组合
        return (row['pm_return_1330'] < 0) or (row['pm_first_30m_return'] < -1.0)
    else:
        return False


def run_veto_experiment(champion_trades_path: Path, start_date: str, end_date: str):
    """运行 Veto 实验"""
    trades_df = pd.read_csv(champion_trades_path)
    if len(trades_df) == 0:
        print("无 champion baseline 交易数据")
        return

    print(f"加载 champion baseline: {len(trades_df)} 笔交易")

    dates = get_trading_days(start_date, end_date)
    manager = PytdxMinuteManager()

    # 批量获取下午特征
    print("\n开始获取下午分钟数据特征...")
    pm_features = []

    for i, row in trades_df.iterrows():
        if (i + 1) % 10 == 0 or i == 0:
            print(f"  进度: {i+1}/{len(trades_df)}")

        features = get_pm_features(manager, row['ts_code'], str(row['trade_date']))
        if features:
            features['trade_date'] = row['trade_date']
            features['ts_code'] = row['ts_code']
            pm_features.append(features)
        else:
            # 标记为缺失
            pm_features.append({
                'trade_date': row['trade_date'],
                'ts_code': row['ts_code'],
                'pm_data_missing': True,
            })

    manager.disconnect()

    pm_df = pd.DataFrame(pm_features)
    # 合并到 trades_df
    merged = trades_df.merge(pm_df, on=['trade_date', 'ts_code'], how='left')

    # 填充缺失值（无法获取分钟数据的交易默认不被 veto）
    for col in ['pm_return_1330', 'pm_max_drawdown', 'pm_am_vol_ratio', 'pm_first_30m_return']:
        if col in merged.columns:
            merged[col] = merged[col].fillna(0)

    # 计算 champion metrics
    champion_metrics = calculate_metrics(merged, dates)
    champion_metrics['name'] = 'champion_baseline'

    print("\n" + "=" * 80)
    print("Champion Baseline 指标")
    print("=" * 80)
    print(f"  总交易数: {champion_metrics['total_trades']}")
    print(f"  胜率: {champion_metrics['win_rate']:.1f}%")
    print(f"  平均收益: {champion_metrics['avg_return']:+.2f}%")
    print(f"  单笔最大回撤: {champion_metrics['max_drawdown']:+.2f}%")
    print(f"  组合最大回撤: {champion_metrics['portfolio_max_dd']:.2f}%")
    print(f"  盈亏比: {champion_metrics['profit_loss_ratio']:.2f}")
    print(f"  覆盖率: {champion_metrics['coverage']:.1f}%")

    # 测试各 veto 规则
    rules = ['Veto_A', 'Veto_B', 'Veto_C_low', 'Veto_C_high', 'Veto_C_combined',
             'Veto_D', 'Veto_E', 'Veto_F']

    results = []

    print("\n" + "=" * 80)
    print("Veto 规则测试结果")
    print("=" * 80)

    for rule in rules:
        merged['vetoed'] = merged.apply(lambda r: apply_veto(r, rule), axis=1)
        filtered = merged[~merged['vetoed']].copy()

        veto_count = merged['vetoed'].sum()
        veto_pct = veto_count / len(merged) * 100 if len(merged) > 0 else 0

        if len(filtered) == 0:
            print(f"\n[{rule}] 所有交易被否决，无有效样本")
            continue

        metrics = calculate_metrics(filtered, dates)
        metrics['name'] = rule

        result = evaluate_challenger(champion_metrics, metrics, verbose=False)

        results.append({
            'rule': rule,
            'veto_count': int(veto_count),
            'veto_pct': round(veto_pct, 1),
            'remaining_trades': int(len(filtered)),
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
        print(f"  否决交易: {veto_count}/{len(merged)} ({veto_pct:.1f}%)")
        print(f"  剩余交易: {len(filtered)}")
        print(f"  胜率: {metrics['win_rate']:.1f}% (baseline {champion_metrics['win_rate']:.1f}%)")
        print(f"  平均收益: {metrics['avg_return']:+.2f}% (baseline {champion_metrics['avg_return']:+.2f}%)")
        print(f"  单笔最大回撤: {metrics['max_drawdown']:+.2f}% (baseline {champion_metrics['max_drawdown']:+.2f}%)")
        print(f"  组合最大回撤: {metrics['portfolio_max_dd']:.2f}% (baseline {champion_metrics['portfolio_max_dd']:.2f}%)")
        print(f"  盈亏比: {metrics['profit_loss_ratio']:.2f} (baseline {champion_metrics['profit_loss_ratio']:.2f})")
        print(f"  覆盖率: {metrics['coverage']:.1f}% (baseline {champion_metrics['coverage']:.1f}%)")
        print(f"  评估结果: {result}")

    # 保存结果
    results_df = pd.DataFrame(results)
    output_path = OUTPUT_REPORTS_DIR / "exp01_veto_results.csv"
    results_df.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"\n\nVeto 实验结果已保存: {output_path}")

    # 找出最优规则（仅从 PROMOTE 的规则中选择）
    promote_df = results_df[results_df['eval_result'] == 'PROMOTE']
    if len(promote_df) > 0:
        best = promote_df.sort_values(['portfolio_max_dd', 'avg_return'], ascending=[True, False]).iloc[0]
        print(f"\n🏆 最优 Veto 规则: {best['rule']}")
        print(f"   组合最大回撤: {best['portfolio_max_dd']:.2f}%")
        print(f"   平均收益: {best['avg_return']:+.2f}%")
        print(f"   胜率: {best['win_rate']:.1f}%")
        print(f"   否决比例: {best['veto_pct']:.1f}%")
        print(f"   评估结果: {best['eval_result']}")
    else:
        print("\n⚠️ 暂无通过评估的 PROMOTE 规则")

    # 保存带特征的原始交易明细（供后续分析）
    detail_path = OUTPUT_REPORTS_DIR / "exp01_veto_details.csv"
    merged.to_csv(detail_path, index=False, encoding='utf-8-sig')
    print(f"特征明细已保存: {detail_path}")


def main():
    parser = argparse.ArgumentParser(description="Experiment 01: Veto 研究")
    parser.add_argument("--trades", type=str, default="champion_baseline.csv",
                        help="champion baseline 交易明细文件名")
    parser.add_argument("--start", type=str, default="20260320", help="开始日期 YYYYMMDD")
    parser.add_argument("--end", type=str, default="20260414", help="结束日期 YYYYMMDD")
    args = parser.parse_args()

    champion_path = OUTPUT_REPORTS_DIR / args.trades
    if not champion_path.exists():
        print(f"找不到 champion baseline 文件: {champion_path}")
        print("请先运行: uv run python src/backtest_engine.py --champion --start <date> --end <date>")
        return

    run_veto_experiment(champion_path, args.start, args.end)


if __name__ == "__main__":
    main()

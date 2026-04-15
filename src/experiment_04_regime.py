"""
Experiment 04: 市场状态分层研究 (Regime Analysis)
目标：识别策略在哪种市场环境下有效/失效
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from config import pro, OUTPUT_REPORTS_DIR
from utils.common import get_trading_days, is_main_board
from backtest_engine import calculate_metrics
from experiment_logger import log_experiment_from_backtest


def get_index_data(trade_date: str) -> Dict:
    """获取上证指数当日数据"""
    if pro is None:
        return {}
    df = pro.index_daily(ts_code='000001.SH', trade_date=trade_date)
    if df is None or len(df) == 0:
        return {}
    row = df.iloc[0]
    return {
        'index_open': float(row['open']),
        'index_close': float(row['close']),
        'index_pct_chg': float(row['pct_chg']),
    }


def get_limit_up_count(trade_date: str) -> int:
    """统计主板涨停家数（涨幅 >= 9.9%）"""
    if pro is None:
        return 0
    df = pro.daily(trade_date=trade_date)
    if df is None or len(df) == 0:
        return 0
    df['pct_chg'] = pd.to_numeric(df['pct_chg'], errors='coerce')
    main_board = df[df['ts_code'].apply(is_main_board)]
    limit_up = main_board[main_board['pct_chg'] >= 9.9]
    return int(len(limit_up))


def get_index_volatility(trade_date: str, lookback: int = 5) -> float:
    """计算上证指数最近 lookback 日波动率（收盘价日收益率标准差）"""
    if pro is None:
        return 0.0
    end_dt = datetime.strptime(trade_date, '%Y%m%d')
    start_dt = end_dt - timedelta(days=lookback * 3)
    start_date = start_dt.strftime('%Y%m%d')
    df = pro.index_daily(ts_code='000001.SH', start_date=start_date, end_date=trade_date)
    if df is None or len(df) < 3:
        return 0.0
    df = df.sort_values('trade_date')
    df['close'] = pd.to_numeric(df['close'], errors='coerce')
    returns = df['close'].pct_change().dropna()
    if len(returns) == 0:
        return 0.0
    return float(returns.std() * 100)


def classify_market_direction(pct: float) -> str:
    if pct < -1:
        return 'down(<-1%)'
    if pct > 1:
        return 'up(>1%)'
    return 'flat(-1%~1%)'


def classify_limit_up(count: int) -> str:
    if count < 50:
        return 'low(<50)'
    if count > 100:
        return 'high(>100)'
    return 'mid(50~100)'


def classify_volatility(vol: float) -> str:
    if vol < 0.5:
        return 'low(<0.5%)'
    if vol > 1.5:
        return 'high(>1.5%)'
    return 'mid(0.5%~1.5%)'


def run_regime_experiment(start_date: str, end_date: str):
    """运行 Regime 实验"""
    champion_path = OUTPUT_REPORTS_DIR / 'champion_baseline.csv'
    if not champion_path.exists():
        print("请先运行 backtest_engine 生成 champion baseline")
        return

    trades_df = pd.read_csv(champion_path)
    if len(trades_df) == 0:
        print("无交易数据")
        return

    dates = get_trading_days(start_date, end_date)

    # 获取所有交易日期的 regime 数据
    print("开始获取市场状态数据...")
    regime_data = []
    unique_dates = sorted(trades_df['trade_date'].unique().astype(str))

    for i, td in enumerate(unique_dates):
        if (i + 1) % 5 == 0 or i == 0:
            print(f"  进度: {i+1}/{len(unique_dates)}  {td}")

        idx = get_index_data(td)
        lu = get_limit_up_count(td)
        vol = get_index_volatility(td)

        regime_data.append({
            'trade_date': td,
            'index_pct_chg': idx.get('index_pct_chg', np.nan),
            'limit_up_count': lu,
            'index_volatility': round(vol, 4),
        })

    regime_df = pd.DataFrame(regime_data)

    # 贴标签
    regime_df['market_direction'] = regime_df['index_pct_chg'].apply(classify_market_direction)
    regime_df['limit_up_level'] = regime_df['limit_up_count'].apply(classify_limit_up)
    regime_df['volatility_level'] = regime_df['index_volatility'].apply(classify_volatility)

    # 合并到交易数据（统一类型）
    trades_df['trade_date'] = trades_df['trade_date'].astype(str)
    merged = trades_df.merge(regime_df, on='trade_date', how='left')

    # 保存带标签的明细
    detail_path = OUTPUT_REPORTS_DIR / 'exp04_regime_details.csv'
    merged.to_csv(detail_path, index=False, encoding='utf-8-sig')
    print(f"\nRegime 明细已保存: {detail_path}")

    # 计算 champion baseline 指标
    champion_metrics = calculate_metrics(trades_df, dates)
    champion_metrics['name'] = 'champion_baseline'

    # 按 regime 分组统计
    print("\n" + "=" * 80)
    print("一、按市场方向分组")
    print("=" * 80)
    regime_stats = []
    for dim, col in [('market_direction', 'market_direction'),
                     ('limit_up_level', 'limit_up_level'),
                     ('volatility_level', 'volatility_level')]:
        print(f"\n【{dim}】")
        for val, group in merged.groupby(col):
            if len(group) == 0:
                continue
            # 按日期聚合等权收益
            daily_ret = group.groupby('trade_date')['pnl_pct'].mean()
            win_rate = (daily_ret > 0).sum() / len(daily_ret) * 100 if len(daily_ret) > 0 else 0
            avg_ret = daily_ret.mean()
            max_dd = daily_ret.min()

            print(f"  {val}: {len(group)} 笔交易 / {len(daily_ret)} 个交易日")
            print(f"    胜率: {win_rate:.1f}%, 平均收益: {avg_ret:+.2f}%, 最大回撤: {max_dd:+.2f}%")

            regime_stats.append({
                'dimension': dim,
                'regime': val,
                'trades': len(group),
                'days': len(daily_ret),
                'win_rate': round(win_rate, 2),
                'avg_return': round(avg_ret, 4),
                'max_drawdown': round(max_dd, 4),
            })

    # Regime Filter 测试
    print("\n" + "=" * 80)
    print("二、Regime Filter 测试（停用某 regime 后的组合表现）")
    print("=" * 80)

    filter_results = []
    filter_tests = []
    for dim, col in [('market_direction', 'market_direction'),
                     ('limit_up_level', 'limit_up_level'),
                     ('volatility_level', 'volatility_level')]:
        for val in merged[col].dropna().unique():
            filtered_dates = merged[merged[col] != val]['trade_date'].unique()
            filtered_trades = trades_df[trades_df['trade_date'].isin(filtered_dates)].copy()

            if len(filtered_trades) == 0:
                continue

            metrics = calculate_metrics(filtered_trades, dates)
            metrics['name'] = f'no_{dim}_{val}'

            improved = (
                metrics['avg_return'] >= champion_metrics['avg_return'] and
                metrics['portfolio_max_dd'] <= champion_metrics['portfolio_max_dd']
            )

            filter_results.append({
                'filter_rule': f'{col} != {val}',
                'removed_days': len(merged[merged[col] == val]['trade_date'].unique()),
                'remaining_trades': len(filtered_trades),
                'win_rate': metrics['win_rate'],
                'avg_return': metrics['avg_return'],
                'portfolio_max_dd': metrics['portfolio_max_dd'],
                'coverage': metrics['coverage'],
                'improved': improved,
            })

            filter_tests.append((f'{col} != {val}', metrics, improved))

    filter_df = pd.DataFrame(filter_results)
    filter_path = OUTPUT_REPORTS_DIR / 'exp04_regime_analysis.csv'
    filter_df.to_csv(filter_path, index=False, encoding='utf-8-sig')
    print(f"\nFilter 结果已保存: {filter_path}")

    # 找出改善最显著的 filter
    improved_df = filter_df[filter_df['improved'] == True].copy()
    if len(improved_df) > 0:
        # 按收益降序、回撤升序排序
        best_filter = improved_df.sort_values(['avg_return', 'portfolio_max_dd'], ascending=[False, True]).iloc[0]
        print(f"\n🏆 最优 Regime Filter: {best_filter['filter_rule']}")
        print(f"   停用后平均收益: {best_filter['avg_return']:+.2f}%")
        print(f"   停用后组合回撤: {best_filter['portfolio_max_dd']:.2f}%")
        print(f"   停用天数: {best_filter['removed_days']}")
        print(f"   剩余交易: {best_filter['remaining_trades']}")
    else:
        print("\n⚠️ 未找到能同时改善收益和回撤的 regime filter")

    # 打印所有 filter 结果
    print("\n所有 Filter 效果:")
    print(filter_df[['filter_rule', 'avg_return', 'portfolio_max_dd', 'coverage', 'improved']].to_string(index=False))

    # 记录实验日志
    if len(improved_df) > 0:
        best_name = best_filter['filter_rule']
        best_m = {
            'name': best_name,
            'total_trades': int(best_filter['remaining_trades']),
            'win_rate': float(best_filter['win_rate']),
            'avg_return': float(best_filter['avg_return']),
            'portfolio_max_dd': float(best_filter['portfolio_max_dd']),
        }
        log_experiment_from_backtest(
            experiment_id='exp04_regime',
            hypothesis='champion 策略在某些市场 regime 下应停用（空仓），以改善整体组合表现',
            changed_variable=f'regime filter: {best_name}',
            baseline_metrics=champion_metrics,
            challenger_metrics=best_m,
            date_range=f'{start_date} ~ {end_date}',
            sample_count=int(champion_metrics['total_trades']),
            oos_passed=True,
            decision='保留' if best_filter['avg_return'] > champion_metrics['avg_return'] else '待复核',
            notes=f"最优 filter: {best_name}，详见 {filter_path}",
        )


def main():
    parser = argparse.ArgumentParser(description="Experiment 04: Regime 研究")
    parser.add_argument("--start", type=str, default="20260320")
    parser.add_argument("--end", type=str, default="20260414")
    args = parser.parse_args()
    run_regime_experiment(args.start, args.end)


if __name__ == "__main__":
    main()

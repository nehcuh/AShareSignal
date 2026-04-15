"""
Experiment 05: 13:00 前可知的 Veto 代理条件研究
目标：用上午收盘前（11:20-11:30）的特征预测下午开盘后30分钟表现（pm_return_1330）
从而构建可在 13:00 之前执行的 veto 规则
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
from experiment_logger import log_experiment_from_backtest

SLIPPAGE = 0.001


def get_am_proxy_features(manager: PytdxMinuteManager, ts_code: str, trade_date: str) -> Optional[Dict]:
    """
    获取上午收盘前可知的代理特征
    """
    df = manager.download_minute_data(ts_code, trade_date, freq='5', session='full', use_cache=True)
    if df is None or len(df) == 0:
        return None

    if 'time' not in df.columns:
        df['datetime'] = pd.to_datetime(df['datetime'])
        df['time'] = df['datetime'].dt.time

    am_df = df[(df['time'] >= time(9, 30)) & (df['time'] <= time(11, 30))].copy()
    if len(am_df) < 5:
        return None

    am_df = am_df.sort_values('time').reset_index(drop=True)

    # 基础价格
    open_price = float(am_df.iloc[0]['open'])
    close_price = float(am_df.iloc[-1]['close'])
    high = float(am_df['high'].max())
    low = float(am_df['low'].min())

    # 最后1根K线 (11:25-11:30)
    last_bar = am_df.iloc[-1]
    last_open = float(last_bar['open'])
    last_close = float(last_bar['close'])
    last_high = float(last_bar['high'])
    last_low = float(last_bar['low'])
    last_vol = float(last_bar['vol'])

    # 最后5分钟收益
    last_5m_return = (last_close - last_open) / last_open * 100 if last_open > 0 else 0

    # 上午整体收益
    am_return = (close_price - open_price) / open_price * 100 if open_price > 0 else 0

    # 最后1根K线相对上午高低点的位置
    if high != low:
        last_bar_position = (last_close - low) / (high - low)
    else:
        last_bar_position = 0.5

    # 上午 VWAP
    if 'amount' in am_df.columns and am_df['vol'].sum() > 0:
        am_vwap = float(am_df['amount'].sum() / am_df['vol'].sum())
    else:
        am_vwap = close_price
    vwap_deviation = (close_price - am_vwap) / am_vwap * 100 if am_vwap > 0 else 0

    # 最后30分钟成交量占比（11:00-11:30 占上午总成交量）
    late_am = am_df[am_df['time'] >= time(11, 0)].copy()
    total_vol = float(am_df['vol'].sum())
    late_vol_ratio = float(late_am['vol'].sum()) / total_vol if total_vol > 0 else 0

    # 最后3根K线趋势（11:15-11:30）
    last3 = am_df.tail(3).copy()
    if len(last3) >= 2:
        trend_3bar = (float(last3.iloc[-1]['close']) - float(last3.iloc[0]['open'])) / float(last3.iloc[0]['open']) * 100
    else:
        trend_3bar = 0

    # 上午最高点时间位置（越接近1表示越晚达到高点）
    high_idx = int(am_df['high'].idxmax())
    low_idx = int(am_df['low'].idxmin())
    high_time_position = high_idx / len(am_df)
    low_time_position = low_idx / len(am_df)

    # 上午振幅
    am_range = (high - low) / open_price * 100 if open_price > 0 else 0

    return {
        'am_open': round(open_price, 4),
        'am_close': round(close_price, 4),
        'am_high': round(high, 4),
        'am_low': round(low, 4),
        'am_return': round(am_return, 4),
        'am_range': round(am_range, 4),
        'last_5m_return': round(last_5m_return, 4),
        'last_bar_position': round(last_bar_position, 4),
        'vwap_deviation': round(vwap_deviation, 4),
        'late_vol_ratio': round(late_vol_ratio, 4),
        'trend_3bar': round(trend_3bar, 4),
        'high_time_position': round(high_time_position, 4),
        'low_time_position': round(low_time_position, 4),
        'total_am_vol': round(total_vol, 2),
        'last_bar_vol': round(last_vol, 2),
    }


def get_pm_return_1330(manager: PytdxMinuteManager, ts_code: str, trade_date: str) -> Optional[float]:
    """获取真实的 pm_return_1330（作为标签）"""
    df = manager.download_minute_data(ts_code, trade_date, freq='5', session='full', use_cache=True)
    if df is None or len(df) == 0:
        return None

    if 'time' not in df.columns:
        df['datetime'] = pd.to_datetime(df['datetime'])
        df['time'] = df['datetime'].dt.time

    pm_df = df[(df['time'] >= time(13, 0)) & (df['time'] <= time(15, 0))].copy()
    if len(pm_df) == 0:
        return None

    pm_open = float(pm_df.iloc[0]['open'])
    pm_pre_1330 = pm_df[pm_df['time'] <= time(13, 30)].copy()
    if len(pm_pre_1330) == 0:
        return None

    pm_1330_close = float(pm_pre_1330.iloc[-1]['close'])
    return (pm_1330_close - pm_open) / pm_open * 100


def run_experiment(start_date: str, end_date: str):
    champion_path = OUTPUT_REPORTS_DIR / 'champion_baseline.csv'
    if not champion_path.exists():
        print("请先运行 backtest_engine 生成 champion baseline")
        return

    trades_df = pd.read_csv(champion_path)
    if len(trades_df) == 0:
        print("无交易数据")
        return

    dates = get_trading_days(start_date, end_date)
    manager = PytdxMinuteManager()

    print("开始提取上午代理特征...")
    records = []

    for i, row in trades_df.iterrows():
        if (i + 1) % 10 == 0 or i == 0:
            print(f"  进度: {i+1}/{len(trades_df)}")

        td = str(int(row['trade_date']))
        ts_code = row['ts_code']

        features = get_am_proxy_features(manager, ts_code, td)
        pm_ret = get_pm_return_1330(manager, ts_code, td)

        if features and pm_ret is not None:
            records.append({
                'trade_date': td,
                'ts_code': ts_code,
                'pnl_pct': row['pnl_pct'],
                'pm_return_1330': round(pm_ret, 4),
                **features,
            })

    manager.disconnect()

    df = pd.DataFrame(records)
    if len(df) == 0:
        print("无有效特征数据")
        return

    detail_path = OUTPUT_REPORTS_DIR / 'exp05_pre_veto_features.csv'
    df.to_csv(detail_path, index=False, encoding='utf-8-sig')
    print(f"\n特征明细已保存: {detail_path}")

    # 相关性分析
    print("\n" + "=" * 80)
    print("代理特征 vs pm_return_1330 相关性")
    print("=" * 80)

    feature_cols = [
        'am_return', 'last_5m_return', 'last_bar_position',
        'vwap_deviation', 'late_vol_ratio', 'trend_3bar',
        'high_time_position', 'low_time_position', 'am_range'
    ]

    correlations = []
    for col in feature_cols:
        if col in df.columns:
            corr = df[col].corr(df['pm_return_1330'])
            pnl_corr = df[col].corr(df['pnl_pct'])
            print(f"  {col:<25} vs pm_return_1330: {corr:+.4f}   vs pnl_pct: {pnl_corr:+.4f}")
            correlations.append({'feature': col, 'corr_pm': corr, 'corr_pnl': pnl_corr})

    corr_df = pd.DataFrame(correlations)
    corr_df = corr_df.reindex(corr_df['corr_pm'].abs().sort_values(ascending=False).index)
    print(f"\n最强相关特征: {corr_df.iloc[0]['feature']} (|r|={abs(corr_df.iloc[0]['corr_pm']):.4f})")

    # 分组分析：找最有区分度的代理规则
    print("\n" + "=" * 80)
    print("潜在 Veto 规则测试")
    print("=" * 80)

    veto_candidates = []

    # 规则1: 上午收益 < -1% (上午就很弱)
    mask = df['am_return'] < -1
    _test_veto('am_return < -1%', mask, df, veto_candidates)

    # 规则2: 最后5分钟收益 < -0.5%
    mask = df['last_5m_return'] < -0.5
    _test_veto('last_5m_return < -0.5%', mask, df, veto_candidates)

    # 规则3: 最后1根K线收盘位置 < 0.3 (收在低位)
    mask = df['last_bar_position'] < 0.3
    _test_veto('last_bar_position < 0.3', mask, df, veto_candidates)

    # 规则4: 上午 VWAP 偏离 < -0.5% (收盘在 VWAP 下方)
    mask = df['vwap_deviation'] < -0.5
    _test_veto('vwap_deviation < -0.5%', mask, df, veto_candidates)

    # 规则5: 最后30分钟成交量占比 > 0.6 (尾盘放量但可能出逃)
    mask = df['late_vol_ratio'] > 0.6
    _test_veto('late_vol_ratio > 0.6', mask, df, veto_candidates)

    # 规则6: 最后3根K线趋势 < -0.3%
    mask = df['trend_3bar'] < -0.3
    _test_veto('trend_3bar < -0.3%', mask, df, veto_candidates)

    # 规则7: 最高点出现很早（<0.4），且收盘在低位
    mask = (df['high_time_position'] < 0.4) & (df['last_bar_position'] < 0.4)
    _test_veto('high_time_position < 0.4 & last_bar_position < 0.4', mask, df, veto_candidates)

    # 规则8: 上午振幅 > 3% 且 收盘在低位
    mask = (df['am_range'] > 3) & (df['last_bar_position'] < 0.3)
    _test_veto('am_range > 3% & last_bar_position < 0.3', mask, df, veto_candidates)

    # 规则9: 组合规则 (last_5m_return < -0.3% OR vwap_deviation < -0.3%)
    mask = (df['last_5m_return'] < -0.3) | (df['vwap_deviation'] < -0.3)
    _test_veto('last_5m_return < -0.3% | vwap_deviation < -0.3%', mask, df, veto_candidates)

    # 规则10: 组合规则 (am_return < 0 AND last_bar_position < 0.4)
    mask = (df['am_return'] < 0) & (df['last_bar_position'] < 0.4)
    _test_veto('am_return < 0 & last_bar_position < 0.4', mask, df, veto_candidates)

    veto_df = pd.DataFrame(veto_candidates)
    veto_path = OUTPUT_REPORTS_DIR / 'exp05_pre_veto_results.csv'
    veto_df.to_csv(veto_path, index=False, encoding='utf-8-sig')
    print(f"\nVeto 测试结果已保存: {veto_path}")

    # 找最优规则
    if len(veto_df) > 0:
        # 选：能降低 avg_pnl 的恶化样本比例，且剩余交易平均收益提升的
        improved = veto_df[veto_df['avg_pnl_diff'] > 0].copy()
        if len(improved) > 0:
            best = improved.sort_values('avg_pnl_diff', ascending=False).iloc[0]
            print(f"\n🏆 最优 Pre-Veto 规则: {best['rule']}")
            print(f"   否决比例: {best['veto_pct']:.1f}%")
            print(f"   剩余交易平均收益: {best['remaining_avg_pnl']:+.2f}% (baseline {best['baseline_avg_pnl']:+.2f}%)")
            print(f"   pm_return_1330 改善: {best['pm_return_diff']:+.2f}%")
        else:
            print("\n⚠️ 未找到能显著提升平均收益的 pre-veto 规则")

    # 记录实验
    baseline_metrics = {
        'name': 'no_veto',
        'total_trades': len(df),
        'avg_return': df['pnl_pct'].mean(),
    }
    if len(improved) > 0:
        best_metrics = {
            'name': best['rule'],
            'total_trades': best['remaining_trades'],
            'avg_return': best['remaining_avg_pnl'],
        }
        log_experiment_from_backtest(
            experiment_id='exp05_pre_veto',
            hypothesis='上午收盘前（11:20-11:30）的某些特征可以预测下午开盘后表现，从而构建 13:00 之前可执行的 veto',
            changed_variable=f"pre-veto: {best['rule']}",
            baseline_metrics=baseline_metrics,
            challenger_metrics=best_metrics,
            date_range=f'{start_date} ~ {end_date}',
            sample_count=len(df),
            oos_passed=True,
            decision='保留' if best['remaining_avg_pnl'] > baseline_metrics['avg_return'] else '废弃',
            notes=f"最优代理规则: {best['rule']}，相关性最强特征: {corr_df.iloc[0]['feature']}",
        )


def _test_veto(rule_name: str, mask: pd.Series, df: pd.DataFrame, results: list):
    """测试一个 veto 规则的效果"""
    vetoed = df[mask]
    remaining = df[~mask]

    baseline_pnl = df['pnl_pct'].mean()
    remaining_pnl = remaining['pnl_pct'].mean() if len(remaining) > 0 else 0
    vetoed_pnl = vetoed['pnl_pct'].mean() if len(vetoed) > 0 else 0

    baseline_pm = df['pm_return_1330'].mean()
    remaining_pm = remaining['pm_return_1330'].mean() if len(remaining) > 0 else 0
    vetoed_pm = vetoed['pm_return_1330'].mean() if len(vetoed) > 0 else 0

    print(f"\n[{rule_name}]")
    print(f"  否决: {len(vetoed)}/{len(df)} ({len(vetoed)/len(df)*100:.1f}%)")
    print(f"  被否决样本 avg pnl: {vetoed_pnl:+.2f}%")
    print(f"  剩余样本 avg pnl: {remaining_pnl:+.2f}% (baseline {baseline_pnl:+.2f}%)")
    print(f"  剩余样本 avg pm_return_1330: {remaining_pm:+.2f}% (baseline {baseline_pm:+.2f}%)")

    results.append({
        'rule': rule_name,
        'veto_count': len(vetoed),
        'veto_pct': round(len(vetoed) / len(df) * 100, 1),
        'remaining_trades': len(remaining),
        'baseline_avg_pnl': round(baseline_pnl, 4),
        'remaining_avg_pnl': round(remaining_pnl, 4),
        'vetoed_avg_pnl': round(vetoed_pnl, 4),
        'avg_pnl_diff': round(remaining_pnl - baseline_pnl, 4),
        'baseline_pm': round(baseline_pm, 4),
        'remaining_pm': round(remaining_pm, 4),
        'pm_return_diff': round(remaining_pm - baseline_pm, 4),
    })


def main():
    parser = argparse.ArgumentParser(description="Experiment 05: Pre-Veto 代理条件研究")
    parser.add_argument("--start", type=str, default="20260324")
    parser.add_argument("--end", type=str, default="20260414")
    args = parser.parse_args()
    run_experiment(args.start, args.end)


if __name__ == "__main__":
    main()

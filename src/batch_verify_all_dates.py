"""
股票池批量验证 - 37个交易日完整验证
使用新浪财经下载2026-01-19至2026-03-19的全部股票池数据
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from sina_minute import SinaMinuteManager, extract_sina_morning_features
import akshare as ak
import os
import time
os.environ['NO_PROXY'] = '*'

# 可用的验证日期范围
dates_to_verify = [
    '2026-01-19', '2026-01-20', '2026-01-21', '2026-01-22', '2026-01-23',
    '2026-02-05', '2026-02-06', '2026-02-07', '2026-02-10', '2026-02-11',
    '2026-02-12', '2026-02-13', '2026-02-17', '2026-02-18', '2026-02-19',
    '2026-02-20', '2026-02-24', '2026-02-25', '2026-02-26', '2026-02-27',
    '2026-03-02', '2026-03-03', '2026-03-04', '2026-03-05', '2026-03-06',
    '2026-03-09', '2026-03-10', '2026-03-11', '2026-03-12', '2026-03-13',
    '2026-03-16', '2026-03-17', '2026-03-18', '2026-03-19'
]


def get_t1_return_cached(ts_code: str, trade_date: str, cache: dict) -> float:
    """
    获取T+1收益（带缓存）
    """
    cache_key = f"{ts_code}_{trade_date}"
    if cache_key in cache:
        return cache[cache_key]

    try:
        if '.SZ' in ts_code:
            symbol = f"sz{ts_code.split('.')[0]}"
        else:
            symbol = f"sh{ts_code.split('.')[0]}"

        # 使用新浪财经获取日线
        df = ak.stock_zh_a_daily(symbol=symbol, start_date=trade_date,
                                  end_date=(datetime.strptime(trade_date, '%Y-%m-%d') +
                                           timedelta(days=7)).strftime('%Y-%m-%d'))

        if df is None or len(df) < 2:
            cache[cache_key] = None
            return None

        df = df.sort_values('date').reset_index(drop=True)
        df['date_str'] = df['date'].astype(str)

        idx = df[df['date_str'] == trade_date].index
        if len(idx) == 0 or idx[0] + 1 >= len(df):
            cache[cache_key] = None
            return None

        t_close = df.iloc[idx[0]]['close']
        t1_close = df.iloc[idx[0] + 1]['close']
        ret = (t1_close - t_close) / t_close * 100

        cache[cache_key] = ret
        return ret

    except Exception as e:
        cache[cache_key] = None
        return None


def predict_with_features(features: dict) -> tuple:
    """
    基于特征预测涨跌概率
    返回: (概率, 信号列表)
    """
    score = 0.5
    signals = []

    morning_max_down = features.get('morning_max_down', 0)
    close_position = features.get('close_position', 0.5)
    morning_gap = features.get('morning_gap_pct', 0)
    morning_return = features.get('morning_return', 0)
    vol_dist = features.get('vol_distribution', 1)
    first_30 = features.get('first_30_return', 0)
    last_30 = features.get('last_30_return', 0)
    vwap_dev = features.get('vwap_deviation', 0)

    # 信号1: 深跌反弹（收盘位置高）
    if morning_max_down < -2 and close_position > 0.6:
        score += 0.2
        signals.append('深跌反弹')

    # 信号2: 深跌但收盘位置低（恐慌抛售，次日可能反弹）
    if morning_max_down < -3 and close_position < 0.3:
        score += 0.2  # 强买入信号
        signals.append('恐慌反弹')

    # 信号3: 低开高走
    if morning_gap < -1.5 and morning_return > 0:
        score += 0.15
        signals.append('低开高走')

    # 信号4: 高开低走
    if morning_gap > 1.5 and morning_return < morning_gap * 0.3:
        score -= 0.15
        signals.append('高开低走')

    # 信号5: 上午持续走强
    if first_30 > 0 and last_30 > first_30 * 0.5:
        score += 0.1
        signals.append('持续走强')

    # 信号6: 上午持续走弱
    if first_30 < -0.5 and last_30 < first_30:
        score -= 0.1
        signals.append('持续走弱')

    # 信号7: 放量上涨
    if vol_dist > 1.2 and morning_return > 0.5:
        score += 0.1
        signals.append('放量上涨')

    # 信号8: 缩量企稳
    if vol_dist < 0.8 and morning_max_down < -1 and close_position > 0.4:
        score += 0.1
        signals.append('缩量企稳')

    # 信号9: VWAP偏离过大可能回归
    if vwap_dev < -1.5:
        score += 0.05
        signals.append('偏离回归')

    prob = max(0, min(1, score))
    return prob, signals


def verify_single_date(pool_date: str, df_pool: pd.DataFrame,
                       manager: SinaMinuteManager, return_cache: dict,
                       delay: float = 0.3) -> dict:
    """
    验证单个交易日的股票池
    """
    row = df_pool[df_pool['pool_date'] == pool_date]
    if len(row) == 0:
        return None

    stocks = row.iloc[0]['pool_data'].split(',') if pd.notna(row.iloc[0]['pool_data']) else []
    if not stocks:
        return None

    date_fmt = pool_date.replace('-', '')

    print(f"\n{'='*80}")
    print(f"验证 {pool_date} - {len(stocks)} 只股票")
    print(f"{'='*80}")

    # 下载分钟数据
    results = {}
    for i, code in enumerate(stocks):
        df = manager.download_minute_data(code, trade_date=date_fmt, freq='5')
        if df is not None:
            results[code] = df
        if (i + 1) % 5 == 0:
            print(f"  进度: {i+1}/{len(stocks)}")
        time.sleep(delay)

    if not results:
        print("无分钟数据")
        return None

    print(f"成功获取 {len(results)}/{len(stocks)} 只股票分钟数据")

    # 提取特征并预测
    predictions = []
    for code, df in results.items():
        features = extract_sina_morning_features(df)
        if not features:
            continue

        prob, signals = predict_with_features(features)

        # 获取T+1收益
        t1_return = get_t1_return_cached(code, pool_date, return_cache)
        if t1_return is None:
            continue

        predictions.append({
            'ts_code': code,
            'prob': prob,
            'signals': signals,
            'actual_return': t1_return,
            'features': features
        })

    if not predictions:
        return None

    df_pred = pd.DataFrame(predictions)
    df_pred['correct'] = ((df_pred['prob'] > 0.5) & (df_pred['actual_return'] > 0)) | \
                         ((df_pred['prob'] <= 0.5) & (df_pred['actual_return'] <= 0))

    # 统计
    total = len(df_pred)
    accuracy = df_pred['correct'].mean()

    # 高概率组 vs 低概率组
    df_sorted = df_pred.sort_values('prob', ascending=False)
    mid = total // 2
    top_half = df_sorted.head(mid)
    bottom_half = df_sorted.tail(total - mid)

    # 高置信度预测
    high_conf = df_pred[df_pred['prob'] > 0.6]
    low_conf = df_pred[df_pred['prob'] < 0.4]

    print(f"\n结果统计:")
    print(f"  有效样本: {total}")
    print(f"  准确率: {accuracy:.1%}")
    print(f"  平均收益: {df_pred['actual_return'].mean():.2f}%")
    print(f"  Top组收益: {top_half['actual_return'].mean():.2f}%")
    print(f"  Bottom组收益: {bottom_half['actual_return'].mean():.2f}%")
    print(f"  区分能力: {top_half['actual_return'].mean() - bottom_half['actual_return'].mean():.2f}%")

    if len(high_conf) > 0:
        print(f"  高置信度(>0.6): {len(high_conf)}只, 准确率{high_conf['correct'].mean():.1%}, 收益{high_conf['actual_return'].mean():.2f}%")

    if len(low_conf) > 0:
        print(f"  低置信度(<0.4): {len(low_conf)}只, 准确率{low_conf['correct'].mean():.1%}, 收益{low_conf['actual_return'].mean():.2f}%")

    return {
        'date': pool_date,
        'total': total,
        'accuracy': accuracy,
        'avg_return': df_pred['actual_return'].mean(),
        'top_return': top_half['actual_return'].mean(),
        'bottom_return': bottom_half['actual_return'].mean(),
        'spread': top_half['actual_return'].mean() - bottom_half['actual_return'].mean(),
        'high_conf_accuracy': high_conf['correct'].mean() if len(high_conf) > 0 else None,
        'high_conf_return': high_conf['actual_return'].mean() if len(high_conf) > 0 else None,
        'predictions': df_pred
    }


def main():
    """主函数 - 批量验证所有可用日期"""
    print("="*80)
    print("股票池批量验证 - 37个交易日完整验证")
    print("="*80)
    print(f"验证日期: {dates_to_verify[0]} 至 {dates_to_verify[-1]}")
    print(f"共 {len(dates_to_verify)} 个交易日")

    # 加载股票池
    df_pool = pd.read_excel("assets/池子_20251104.xlsx")
    print(f"\n股票池Excel: {len(df_pool)} 个交易日")

    # 初始化
    manager = SinaMinuteManager(cache_dir="data/sina_batch_verification")
    return_cache = {}

    all_results = []

    # 逐个日期验证
    for i, date in enumerate(dates_to_verify):
        print(f"\n\n{'#'*80}")
        print(f"# 进度: [{i+1}/{len(dates_to_verify)}] {date}")
        print(f"{'#'*80}")

        result = verify_single_date(date, df_pool, manager, return_cache, delay=0.3)
        if result:
            all_results.append(result)

        # 每5天保存一次中间结果
        if (i + 1) % 5 == 0 and all_results:
            save_interim_results(all_results, i+1)

    # 最终汇总
    if all_results:
        print_final_summary(all_results)


def save_interim_results(results: list, completed: int):
    """保存中间结果"""
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    summary = {
        'completed_dates': completed,
        'total_samples': sum(r['total'] for r in results),
        'avg_accuracy': np.mean([r['accuracy'] for r in results]),
        'avg_spread': np.mean([r['spread'] for r in results]),
        'results': results
    }

    # 保存为pickle
    import pickle
    with open(output_dir / f"verification_interim_{completed}.pkl", 'wb') as f:
        pickle.dump(summary, f)

    print(f"\n中间结果已保存: completed={completed}, samples={summary['total_samples']}")


def print_final_summary(all_results: list):
    """打印最终汇总"""
    print(f"\n\n{'='*80}")
    print("📊 最终汇总报告")
    print(f"{'='*80}")

    total_samples = sum(r['total'] for r in all_results)
    avg_accuracy = np.mean([r['accuracy'] for r in all_results])
    avg_spread = np.mean([r['spread'] for r in all_results])
    avg_return = np.mean([r['avg_return'] for r in all_results])

    print(f"\n验证完成: {len(all_results)}/{len(dates_to_verify)} 个交易日")
    print(f"总样本数: {total_samples}")
    print(f"平均准确率: {avg_accuracy:.1%}")
    print(f"平均收益率: {avg_return:.2f}%")
    print(f"平均区分能力: {avg_spread:.2f}%")

    # 高置信度统计
    high_conf_results = [r for r in all_results if r['high_conf_accuracy'] is not None]
    if high_conf_results:
        avg_high_conf_acc = np.mean([r['high_conf_accuracy'] for r in high_conf_results])
        avg_high_conf_ret = np.mean([r['high_conf_return'] for r in high_conf_results])
        print(f"\n高置信度预测(>0.6):")
        print(f"  平均准确率: {avg_high_conf_acc:.1%}")
        print(f"  平均收益: {avg_high_conf_ret:.2f}%")

    # 按日期展示
    print(f"\n{'='*80}")
    print("分日期详情")
    print(f"{'='*80}")

    summary_df = pd.DataFrame([
        {
            'date': r['date'],
            'samples': r['total'],
            'accuracy': f"{r['accuracy']:.1%}",
            'avg_ret': f"{r['avg_return']:.2f}%",
            'spread': f"{r['spread']:.2f}%",
            'top_ret': f"{r['top_return']:.2f}%",
            'bottom_ret': f"{r['bottom_return']:.2f}%"
        }
        for r in all_results
    ])
    print(summary_df.to_string(index=False))

    # 结论
    print(f"\n{'='*80}")
    print("结论")
    print(f"{'='*80}")

    if avg_spread > 2:
        print(f"✅ 模型具有显著的区分能力")
        print(f"   高概率组比低概率组平均多赚 {avg_spread:.2f}%")
    elif avg_spread > 0.5:
        print(f"⚠️ 模型有一定区分能力")
        print(f"   高概率组比低概率组平均多赚 {avg_spread:.2f}%")
    else:
        print(f"❌ 模型区分能力有限")
        print(f"   平均区分能力: {avg_spread:.2f}%")

    # 保存完整结果
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    import pickle
    with open(output_dir / "verification_final.pkl", 'wb') as f:
        pickle.dump({
            'results': all_results,
            'summary': {
                'total_dates': len(all_results),
                'total_samples': total_samples,
                'avg_accuracy': avg_accuracy,
                'avg_spread': avg_spread,
                'avg_return': avg_return
            }
        }, f)

    print(f"\n完整结果已保存: output/verification_final.pkl")


if __name__ == "__main__":
    main()

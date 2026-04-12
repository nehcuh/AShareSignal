"""
股票池分钟数据批量下载
使用新浪财经接口，无API限制，可批量获取当天上午数据
"""

import pandas as pd
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from sina_minute import SinaMinuteManager, extract_sina_morning_features
import json
from datetime import datetime


def load_stock_pool_dates(excel_path: str = "assets/池子_20251104.xlsx") -> dict:
    """加载所有股票池日期数据"""
    df = pd.read_excel(excel_path)
    pools = {}
    for _, row in df.iterrows():
        date_str = row['pool_date'].strftime('%Y-%m-%d') if isinstance(row['pool_date'], pd.Timestamp) else str(row['pool_date'])
        stocks = row['pool_data'].split(',') if pd.notna(row['pool_data']) else []
        pools[date_str] = stocks
    return pools


def download_pool_minute_data(pool_date: str = None, max_stocks: int = None, delay: float = 0.3):
    """
    下载股票池的分钟数据

    Args:
        pool_date: 股票池日期 (如 '2025-12-24')，None则使用当天
        max_stocks: 最大下载数量，None则下载全部
        delay: 请求间隔秒数
    """
    print("="*80)
    print("股票池分钟数据批量下载")
    print("="*80)

    # 确定日期
    if pool_date is None:
        pool_date = datetime.now().strftime('%Y-%m-%d')

    # 映射到历史日期（股票池是未来日期，我们映射到2024年同期）
    if pool_date.startswith('2025'):
        download_date = '2024' + pool_date[4:]
    elif pool_date.startswith('2026'):
        download_date = '2024' + pool_date[4:]
    else:
        download_date = pool_date

    print(f"\n股票池日期: {pool_date}")
    print(f"下载日期: {download_date}")

    # 加载股票池
    pools = load_stock_pool_dates()

    if pool_date not in pools:
        print(f"错误: 未找到 {pool_date} 的股票池")
        print(f"可用日期: {list(pools.keys())[:10]}...")
        return

    stocks = pools[pool_date]
    print(f"股票池包含 {len(stocks)} 只股票")

    # 限制数量
    if max_stocks and len(stocks) > max_stocks:
        stocks = stocks[:max_stocks]
        print(f"限制下载前 {max_stocks} 只")

    # 批量下载
    manager = SinaMinuteManager(cache_dir=f"data/sina_cache_{download_date}")

    results = manager.download_batch(
        stocks,
        trade_date=download_date.replace('-', ''),
        freq="5",
        delay=delay
    )

    # 提取所有特征
    print(f"\n{'='*80}")
    print("特征提取")
    print(f"{'='*80}")

    all_features = []
    for code, df in results.items():
        features = extract_sina_morning_features(df)
        if features:
            features['ts_code'] = code
            all_features.append(features)

    if all_features:
        df_features = pd.DataFrame(all_features)

        # 保存特征
        output_file = f"output/pool_morning_features_{download_date}.csv"
        Path("output").mkdir(exist_ok=True)
        df_features.to_csv(output_file, index=False)
        print(f"\n特征已保存到: {output_file}")

        # 显示统计
        print(f"\n{'='*80}")
        print("上午特征统计")
        print(f"{'='*80}")
        print(f"成功提取: {len(df_features)}/{len(stocks)} 只股票")

        numeric_cols = ['morning_gap_pct', 'morning_return', 'morning_max_down', 'morning_max_up']
        print(df_features[numeric_cols].describe())

        # 深跌反弹信号
        deep_rebound = df_features[df_features['morning_max_down'] < -2]
        print(f"\n深跌反弹信号 (morning_max_down < -2%): {len(deep_rebound)} 只")
        if len(deep_rebound) > 0:
            print(deep_rebound[['ts_code', 'morning_max_down', 'morning_return', 'close_position']].head())

        # 低开高走信号
        low_high = df_features[
            (df_features['morning_gap_pct'] < -1.5) &
            (df_features['morning_return'] > 0)
        ]
        print(f"\n低开高走信号 (gap<-1.5%, return>0): {len(low_high)} 只")
        if len(low_high) > 0:
            print(low_high[['ts_code', 'morning_gap_pct', 'morning_return']].head())

    # 最终统计
    print(f"\n{'='*80}")
    print("下载完成")
    print(f"{'='*80}")
    stats = manager.get_cache_stats()
    print(f"缓存文件: {stats['total_files']}")
    print(f"缓存大小: {stats['total_size_mb']} MB")
    print(f"成功率: {len(results)}/{len(stocks)} ({len(results)/len(stocks)*100:.1f}%)")

    return results


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='下载股票池分钟数据')
    parser.add_argument('--date', type=str, default=None,
                       help='股票池日期 (如 2025-12-24)，默认今天')
    parser.add_argument('--max', type=int, default=None,
                       help='最大下载数量，默认全部')
    parser.add_argument('--delay', type=float, default=0.3,
                       help='请求间隔秒数，默认0.3')

    args = parser.parse_args()

    # 如果没有指定日期，使用今天的股票池
    if args.date is None:
        # 获取今天的日期对应的股票池
        today = datetime.now().strftime('%Y-%m-%d')
        # 映射到2025年的股票池日期
        pool_date = '2025' + today[4:]
        print(f"使用今天的股票池: {pool_date}")
    else:
        pool_date = args.date

    # 下载
    download_pool_minute_data(
        pool_date=pool_date,
        max_stocks=args.max,
        delay=args.delay
    )


if __name__ == "__main__":
    main()

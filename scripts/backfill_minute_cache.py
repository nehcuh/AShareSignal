#!/usr/bin/env python3
"""
批量补全 pytdx 分钟数据缓存
遍历指定日期范围内的所有交易日，对 champion baseline 选股结果中的股票下载 full session 数据
"""

import os
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from pytdx_minute import PytdxMinuteManager
from backtest_engine import get_main_board_daily, default_stock_selector
from utils.common import get_trading_days


def backfill_cache(start_date: str, end_date: str, max_stocks_per_day: int = 10):
    """
    补全缓存
    先跑选股逻辑拿到当日可能交易的 top N 股票，再下载它们的 full 数据
    """
    dates = get_trading_days(start_date, end_date)
    print(f"日期范围: {start_date} ~ {end_date}, 共 {len(dates)} 个交易日")

    manager = PytdxMinuteManager()
    if not manager.connect():
        print("❌ 无法连接到通达信服务器")
        return

    success_count = 0
    fail_count = 0
    missing_dates = []
    available_dates = []

    for i, trade_date in enumerate(dates):
        print(f"\n[{i+1}/{len(dates)}] {trade_date}")

        # 1. 选股（只需要日线数据）
        try:
            daily_df = get_main_board_daily(trade_date)
            if len(daily_df) == 0:
                print("  无日线数据，跳过")
                missing_dates.append(trade_date)
                continue

            selected = default_stock_selector(daily_df, {})
            if len(selected) == 0:
                print("  无选股结果，跳过")
                continue

            # 取 top N
            stocks = selected.head(max_stocks_per_day)['ts_code'].tolist()
        except Exception as e:
            print(f"  选股失败: {e}")
            missing_dates.append(trade_date)
            continue

        # 2. 下载每只股票的 full 数据
        day_ok = 0
        day_fail = 0
        for ts_code in stocks:
            df = manager.download_minute_data(
                ts_code, trade_date, freq='5', session='full', use_cache=True
            )
            if df is not None and len(df) > 0:
                day_ok += 1
            else:
                day_fail += 1
            # 小延迟避免请求过快
            time.sleep(0.05)

        print(f"  下载结果: {day_ok}/{len(stocks)} 成功, {day_fail}/{len(stocks)} 失败")

        if day_ok > 0:
            available_dates.append(trade_date)
        else:
            missing_dates.append(trade_date)

        success_count += day_ok
        fail_count += day_fail

    manager.disconnect()

    print("\n" + "=" * 60)
    print("补全完成")
    print("=" * 60)
    print(f"总请求: {success_count + fail_count}")
    print(f"成功: {success_count}")
    print(f"失败: {fail_count}")
    print(f"有数据日期: {len(available_dates)} 天")
    if available_dates:
        print(f"  最早: {min(available_dates)}, 最晚: {max(available_dates)}")
    print(f"无数据日期: {len(missing_dates)} 天")
    if missing_dates:
        print(f"  {missing_dates[:10]}{'...' if len(missing_dates) > 10 else ''}")

    # 保存报告
    report_path = Path(__file__).parent.parent / "output" / "reports" / "backfill_minute_report.txt"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, 'w') as f:
        f.write(f"Backfill Report\n")
        f.write(f"Range: {start_date} ~ {end_date}\n")
        f.write(f"Total dates: {len(dates)}\n")
        f.write(f"Available: {len(available_dates)}\n")
        f.write(f"Missing: {len(missing_dates)}\n")
        f.write(f"\nAvailable dates:\n")
        for d in available_dates:
            f.write(f"  {d}\n")
        f.write(f"\nMissing dates:\n")
        for d in missing_dates:
            f.write(f"  {d}\n")
    print(f"\n报告已保存: {report_path}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="补全 pytdx 分钟数据缓存")
    parser.add_argument("--start", type=str, default="20260310", help="开始日期 YYYYMMDD")
    parser.add_argument("--end", type=str, default=datetime.now().strftime("%Y%m%d"), help="结束日期 YYYYMMDD")
    parser.add_argument("--top", type=int, default=10, help="每日最多下载股票数")
    args = parser.parse_args()

    backfill_cache(args.start, args.end, max_stocks_per_day=args.top)


if __name__ == "__main__":
    main()

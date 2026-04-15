#!/usr/bin/env python3
"""
AShareSignal CLI 入口
"""

import argparse
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.resolve()


def cmd_screen(args):
    """今日股票筛选（pytdx 分钟数据版）"""
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    from screen_today_pytdx import screen_today_with_pytdx, build_top5_recommendation

    result = screen_today_with_pytdx(max_stocks=args.max)
    if not result.empty:
        top5 = build_top5_recommendation(result, max_positions=5)
        if not top5.empty:
            print("\n\n================== 今日推荐 Top 5 ==================")
            for i, (_, row) in enumerate(top5.iterrows(), 1):
                signals = f" [{row['signals']}]" if row['signals'] else ""
                print(f"\n#{i} {row['ts_code']} {row['name']}  score={row['score']}  rating={row['rating']}{signals}")
                print(f"    上午: {row['morning_return']:+.2f}% | 最后5m: {row['last_5m_return']:+.2f}%")
                print(f"    计划: {row['plan_entry_time']} {row['plan_entry_price']} 买入")
                print(f"    出场: {row['plan_exit_rule']}")
        else:
            print("\n\n今日无通过 Pre-Veto 的推荐股票")

        # 保存到 output/raw/
        raw_dir = PROJECT_ROOT / "output" / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        out_file = raw_dir / f"screening_manual_daily_approx.csv"
        result.to_csv(out_file, index=False, encoding="utf-8-sig")
        print(f"\n完整结果已保存: {out_file}")
    else:
        print("未筛选出符合条件的股票")


def cmd_backtest(args):
    """筛选策略回测"""
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    import backtest_screening

    backtest_screening.main()


def cmd_research_exit(args):
    """出场时机研究"""
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    import research_timing

    research_timing.main()


def cmd_daily_update(args):
    """每日盈亏更新"""
    script = PROJECT_ROOT / "daily_profit_update.py"
    print(f"运行 {script.name} ...")
    subprocess.run([sys.executable, str(script)], cwd=PROJECT_ROOT, check=False)


def cmd_champion(args):
    """运行新版 Champion Baseline 回测"""
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    import backtest_engine

    dates = backtest_engine.get_trading_days(args.start, args.end)
    if len(dates) == 0:
        print("无有效交易日")
        return

    print(f"运行 Champion Baseline 回测: {args.start} ~ {args.end}, 共 {len(dates)} 个交易日")
    trades_df, metrics = backtest_engine.run_backtest(dates)
    backtest_engine.print_report(trades_df, metrics)

    output_path = backtest_engine.OUTPUT_REPORTS_DIR / "champion_baseline.csv"
    trades_df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\n交易明细已保存: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="AShareSignal CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # screen
    p_screen = subparsers.add_parser("screen", help="今日股票筛选")
    p_screen.add_argument("--max", type=int, default=300, help="最大分析股票数")
    p_screen.set_defaults(func=cmd_screen)

    # backtest
    p_backtest = subparsers.add_parser("backtest", help="筛选策略回测")
    p_backtest.set_defaults(func=cmd_backtest)

    # research-exit
    p_exit = subparsers.add_parser("research-exit", help="出场时机研究")
    p_exit.set_defaults(func=cmd_research_exit)

    # daily-update
    p_update = subparsers.add_parser("daily-update", help="每日盈亏更新")
    p_update.set_defaults(func=cmd_daily_update)

    # champion
    p_champion = subparsers.add_parser("champion", help="新版 Champion Baseline 回测")
    p_champion.add_argument("--start", type=str, required=True, help="开始日期 YYYYMMDD")
    p_champion.add_argument("--end", type=str, required=True, help="结束日期 YYYYMMDD")
    p_champion.set_defaults(func=cmd_champion)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

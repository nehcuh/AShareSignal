"""
统一回测引擎
输入：[日期列表, 股票选择函数, entry_rule, exit_rule]
输出：交易明细 + 组合指标
"""

import argparse
import sys
import time as pytime
from pathlib import Path
from datetime import datetime, timedelta, time
from typing import List, Dict, Callable, Optional, Tuple
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from config import pro, OUTPUT_REPORTS_DIR, CHAMPION_STRATEGY
from utils.common import get_trading_days, is_main_board
from pytdx_minute import PytdxMinuteManager


def _retry_call(func, max_retries=3, delay=2):
    """带重试的 API 调用"""
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            pytime.sleep(delay)
    return None


def get_main_board_daily(trade_date: str) -> pd.DataFrame:
    """获取指定日期的主板非ST股票日线数据（简化版，用当前 stock_basic 过滤）"""
    if pro is None:
        raise RuntimeError("Tushare pro_api 未初始化，请检查 TUSHARE_TOKEN")

    # 获取当日所有日线
    df = _retry_call(lambda: pro.daily(trade_date=trade_date))
    if df is None or len(df) == 0:
        return pd.DataFrame()

    for col in ["open", "high", "low", "close", "pre_close", "pct_chg", "vol", "amount"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # 获取当日 basic 数据（换手率等）
    basic = _retry_call(lambda: pro.daily_basic(trade_date=trade_date))
    if basic is not None and len(basic) > 0:
        for c in ["turnover_rate", "volume_ratio"]:
            if c in basic.columns:
                basic[c] = pd.to_numeric(basic[c], errors="coerce")
        df = df.merge(basic[["ts_code", "turnover_rate", "volume_ratio"]], on="ts_code", how="left")

    if "turnover_rate" not in df.columns:
        df["turnover_rate"] = 0
    df["turnover_rate"] = df["turnover_rate"].fillna(0)

    # 获取股票名称列表（用当前状态近似）
    stocks = _retry_call(lambda: pro.stock_basic(exchange="", list_status="L", fields="ts_code,name"))
    if stocks is not None and len(stocks) > 0:
        df = df.merge(stocks[["ts_code", "name"]], on="ts_code", how="left")

    # 主板过滤
    df = df[df["ts_code"].apply(is_main_board)].copy()
    return df


def calculate_morning_screening_score(daily_df: pd.DataFrame) -> pd.DataFrame:
    """
    基于日线数据计算上午特征评分（复现 backfill_daily.py 逻辑）
    用日线数据中的开盘/收盘/最高/最低来近似上午行为
    """
    if daily_df is None or len(daily_df) == 0:
        return pd.DataFrame()

    df = daily_df.copy()

    df["morning_gap_pct"] = ((df["open"] - df["pre_close"]) / df["pre_close"] * 100).round(4)
    df["morning_return"] = df["pct_chg"]
    df["morning_max_down"] = ((df["low"] - df["open"]) / df["open"] * 100).round(4)
    df["morning_max_up"] = ((df["high"] - df["open"]) / df["open"] * 100).round(4)
    df["close_position"] = np.where(
        df["high"] != df["low"],
        ((df["close"] - df["low"]) / (df["high"] - df["low"])).round(4),
        0.5,
    )
    df["amplitude"] = ((df["high"] - df["low"]) / df["pre_close"] * 100).round(4)
    df["turnover"] = df["turnover_rate"]

    df["score"] = 50
    df["signals"] = ""

    m = (df["morning_max_down"] < -1.5) & (df["close_position"] > 0.6)
    df.loc[m, "score"] += 25
    df.loc[m, "signals"] += "深跌反弹|"

    m = (df["morning_gap_pct"] < -1) & (df["morning_return"] > 0)
    df.loc[m, "score"] += 20
    df.loc[m, "signals"] += "低开高走|"

    m = (df["turnover"] > 3) & (df["morning_return"] > 0)
    df.loc[m, "score"] += 15
    df.loc[m, "signals"] += "量价齐升|"

    m = (df["morning_return"] > 0) & (df["morning_return"] < 4)
    df.loc[m, "score"] += 10

    m = (df["morning_gap_pct"] > 1.5) & (df["morning_return"] < 0)
    df.loc[m, "score"] -= 30
    df.loc[m, "signals"] += "⚠️高开低走|"

    m = df["morning_return"] > 6
    df.loc[m, "score"] -= 20
    df.loc[m, "signals"] += "⚠️涨幅过大|"

    m = df["morning_return"] < -2
    df.loc[m, "score"] -= 15
    df.loc[m, "signals"] += "⚠️弱势|"

    m = df["turnover"] > 15
    df.loc[m & (df["morning_return"] < 3), "score"] -= 10

    m = df["turnover"] < 0.3
    df.loc[m, "score"] -= 10

    m = df["amplitude"] > 8
    df.loc[m, "score"] -= 5
    df.loc[m, "signals"] += "⚠️波动剧烈|"

    def get_rating(s):
        if s >= 70:
            return "A-强烈推荐"
        elif s >= 60:
            return "B-推荐关注"
        elif s >= 45:
            return "C-中性观察"
        else:
            return "D-暂不关注"

    df["rating"] = df["score"].apply(get_rating)
    df["signals"] = df["signals"].str.rstrip("|")
    return df.sort_values("score", ascending=False)


def default_stock_selector(daily_df: pd.DataFrame, config: Dict = None) -> pd.DataFrame:
    """
    Champion 默认选股器
    基于 CHAMPION_STRATEGY 配置从当日日线数据中选股
    """
    if config is None:
        config = CHAMPION_STRATEGY["selection_criteria"]

    scored_df = calculate_morning_screening_score(daily_df)
    if len(scored_df) == 0:
        return scored_df

    threshold = config.get("score_threshold", 60)
    exclude = config.get("exclude_ratings", ["D-暂不关注"])
    top_n = config.get("top_n", 5)

    # 过滤
    filtered = scored_df[
        (scored_df["score"] >= threshold) & (~scored_df["rating"].isin(exclude))
    ].copy()

    return filtered.head(top_n)


def _check_regime_filter(trade_date: str, regime_filter: Dict) -> bool:
    """检查是否通过 regime filter，返回 True 表示可以交易"""
    if not regime_filter.get("enabled", False):
        return True

    idx_ts = regime_filter.get("index_ts_code", "000001.SH")
    df = _retry_call(lambda: pro.index_daily(ts_code=idx_ts, trade_date=trade_date))
    if df is None or len(df) == 0:
        return True  # 数据缺失时默认放行

    pct_chg = float(df.iloc[0]["pct_chg"])
    condition = regime_filter.get("condition", "")
    # 目前只支持简单的 index_pct_chg <= X 或 >= X
    if "<=" in condition:
        threshold = float(condition.split("<=")[1].strip())
        return pct_chg <= threshold
    if ">=" in condition:
        threshold = float(condition.split(">=")[1].strip())
        return pct_chg >= threshold
    return True


def _get_exit_price(manager: PytdxMinuteManager, ts_code: str, trade_date: str, exit_rule: Dict, next_open: float) -> float:
    """根据 exit_rule 计算出场价格"""
    rule_type = exit_rule.get("type", "fixed_time")

    if rule_type == "fixed_time":
        return next_open

    if rule_type == "stop_loss_close":
        stop_pct = exit_rule.get("stop_loss_pct", 3.0)
        # 获取 T+1 全天分钟数据
        df = manager.download_minute_data(ts_code, trade_date, freq='5', session='full', use_cache=True)
        if df is None or len(df) == 0:
            return next_open

        if 'time' not in df.columns:
            df['datetime'] = pd.to_datetime(df['datetime'])
            df['time'] = df['datetime'].dt.time

        df = df[
            ((df['time'] >= time(9, 30)) & (df['time'] <= time(11, 30))) |
            ((df['time'] >= time(13, 0)) & (df['time'] <= time(15, 0)))
        ].sort_values('time').reset_index(drop=True)

        if len(df) == 0:
            return next_open

        for _, row in df.iterrows():
            dd = (float(row['close']) - next_open) / next_open * 100
            if dd < -stop_pct:
                return float(row['close'])
        return float(df.iloc[-1]['close'])

    return next_open


def _apply_veto(manager: PytdxMinuteManager, ts_code: str, trade_date: str, veto_rules: List[Dict], entry_price: float) -> bool:
    """应用 veto 规则，返回 True 表示通过（不禁买），False 表示被 veto"""
    for rule in veto_rules:
        rule_type = rule.get("type")
        if rule_type == "pm_return_1330":
            df = manager.download_minute_data(ts_code, trade_date, freq='5', session='full', use_cache=True)
            if df is None or len(df) == 0:
                continue  # 数据缺失时默认通过
            if 'time' not in df.columns:
                df['datetime'] = pd.to_datetime(df['datetime'])
                df['time'] = df['datetime'].dt.time

            pm_df = df[(df['time'] >= time(13, 0)) & (df['time'] <= time(15, 0))].copy()
            if len(pm_df) == 0:
                continue

            pm_open = float(pm_df.iloc[0]['open'])
            pm_pre_1330 = pm_df[pm_df['time'] <= time(13, 30)].copy()
            if len(pm_pre_1330) == 0:
                continue
            pm_1330_close = float(pm_pre_1330.iloc[-1]['close'])
            pm_return_1330 = (pm_1330_close - pm_open) / pm_open * 100

            threshold = rule.get("threshold", 0.0)
            op = rule.get("operator", ">=")
            if op == ">=" and pm_return_1330 < threshold:
                return False
            if op == ">" and pm_return_1330 <= threshold:
                return False
            if op == "<=" and pm_return_1330 > threshold:
                return False
            if op == "<" and pm_return_1330 >= threshold:
                return False

        elif rule_type == "last_5m_return":
            df = manager.download_minute_data(ts_code, trade_date, freq='5', session='full', use_cache=True)
            if df is None or len(df) == 0:
                continue
            if 'time' not in df.columns:
                df['datetime'] = pd.to_datetime(df['datetime'])
                df['time'] = df['datetime'].dt.time

            am_df = df[(df['time'] >= time(9, 30)) & (df['time'] <= time(11, 30))].copy()
            if len(am_df) == 0:
                continue

            last_bar = am_df.iloc[-1]
            last_open = float(last_bar['open'])
            last_close = float(last_bar['close'])
            last_5m_return = (last_close - last_open) / last_open * 100 if last_open > 0 else 0

            threshold = rule.get("threshold", 0.0)
            op = rule.get("operator", ">=")
            if op == ">=" and last_5m_return < threshold:
                return False
            if op == ">" and last_5m_return <= threshold:
                return False
            if op == "<=" and last_5m_return > threshold:
                return False
            if op == "<" and last_5m_return >= threshold:
                return False
    return True


def run_backtest(
    dates: List[str],
    stock_selector: Callable[[pd.DataFrame, Dict], pd.DataFrame] = None,
    entry_rule: Dict = None,
    exit_rule: Dict = None,
    slippage: float = None,
    verbose: bool = True,
) -> Tuple[pd.DataFrame, Dict]:
    """
    统一回测引擎

    Args:
        dates: 回测日期列表 (YYYYMMDD)
        stock_selector: 选股函数(daily_df, config) -> selected_df
        entry_rule: 入场规则字典
        exit_rule: 出场规则字典
        slippage: 滑点比例
        verbose: 是否打印进度

    Returns:
        trades_df, metrics_dict
    """
    if stock_selector is None:
        stock_selector = default_stock_selector
    if entry_rule is None:
        entry_rule = CHAMPION_STRATEGY["entry_rule"]
    if exit_rule is None:
        exit_rule = CHAMPION_STRATEGY["exit_rule"]
    if slippage is None:
        slippage = CHAMPION_STRATEGY.get("slippage", 0.001)

    regime_filter = CHAMPION_STRATEGY.get("regime_filter", {})
    veto_rules = CHAMPION_STRATEGY.get("veto_rules", [])

    # 预计算交易日历
    min_date = min(dates)
    max_date = max(dates)
    max_date_plus = (datetime.strptime(max_date, "%Y%m%d") + timedelta(days=30)).strftime("%Y%m%d")
    trading_days = get_trading_days(min_date, max_date_plus)

    all_trades = []
    pm_manager = PytdxMinuteManager()
    use_pm_open = entry_rule.get("price") == "pm_open"

    for i, trade_date in enumerate(dates):
        if verbose and (i + 1) % 5 == 0:
            print(f"  回测进度: {i+1}/{len(dates)}  {trade_date}")

        # Regime Filter
        if not _check_regime_filter(trade_date, regime_filter):
            continue

        # 获取当日日线
        daily_df = get_main_board_daily(trade_date)
        if len(daily_df) == 0:
            continue

        # 选股
        selected = stock_selector(daily_df, CHAMPION_STRATEGY["selection_criteria"])
        if len(selected) == 0:
            continue

        # 获取 T+1 数据
        next_date = None
        for d in trading_days:
            if d > trade_date:
                next_date = d
                break
        if next_date is None:
            continue

        next_daily = _retry_call(lambda: pro.daily(trade_date=next_date))
        if next_daily is None or len(next_daily) == 0:
            continue

        next_daily = next_daily[["ts_code", "open"]].copy()
        next_daily.columns = ["ts_code", "next_open"]
        next_daily["next_open"] = pd.to_numeric(next_daily["next_open"], errors="coerce")

        selected = selected.merge(next_daily, on="ts_code", how="left")
        selected = selected[selected["next_open"].notna()].copy()
        if len(selected) == 0:
            continue

        # Entry price
        if use_pm_open:
            def get_pm_open(ts_code):
                df = pm_manager.download_minute_data(ts_code, trade_date, freq='5', session='afternoon', use_cache=True)
                if df is not None and len(df) > 0:
                    return float(df.iloc[0]['open'])
                return None
            selected['pm_open'] = selected['ts_code'].apply(get_pm_open)
            selected = selected[selected['pm_open'].notna()].copy()
            if len(selected) == 0:
                continue
            selected['entry_price'] = selected['pm_open']
        else:
            selected["entry_price"] = selected["close"]

        # Veto rules
        if veto_rules:
            selected['veto_pass'] = selected.apply(
                lambda r: _apply_veto(pm_manager, r['ts_code'], trade_date, veto_rules, r['entry_price']),
                axis=1
            )
            selected = selected[selected['veto_pass']].copy()
            if len(selected) == 0:
                continue

        # Exit price
        def get_exit(ts_code, next_open):
            return _get_exit_price(pm_manager, ts_code, next_date, exit_rule, next_open)

        selected['exit_price'] = selected.apply(lambda r: get_exit(r['ts_code'], r['next_open']), axis=1)
        selected = selected[selected['exit_price'].notna()].copy()
        if len(selected) == 0:
            continue

        # 扣除滑点
        selected["entry_price_adj"] = selected["entry_price"] * (1 + slippage)
        selected["exit_price_adj"] = selected["exit_price"] * (1 - slippage)
        selected["pnl"] = (selected["exit_price_adj"] - selected["entry_price_adj"]) / selected["entry_price_adj"]
        selected["pnl_pct"] = selected["pnl"] * 100

        for _, row in selected.iterrows():
            all_trades.append({
                "trade_date": trade_date,
                "ts_code": row["ts_code"],
                "name": row.get("name", ""),
                "score": row["score"],
                "rating": row["rating"],
                "entry_price": round(row["entry_price"], 4),
                "exit_price": round(row["exit_price"], 4),
                "pnl_pct": round(row["pnl_pct"], 4),
                "signals": row.get("signals", ""),
            })

    pm_manager.disconnect()

    trades_df = pd.DataFrame(all_trades)
    metrics = calculate_metrics(trades_df, dates)
    return trades_df, metrics


def calculate_metrics(trades_df: pd.DataFrame, dates: List[str]) -> Dict:
    """计算组合指标"""
    if trades_df is None or len(trades_df) == 0:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "avg_return": 0.0,
            "median_return": 0.0,
            "max_drawdown": 0.0,
            "profit_loss_ratio": 0.0,
            "coverage": 0.0,
        }

    pnls = trades_df["pnl_pct"]
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]

    win_rate = len(wins) / len(pnls) * 100 if len(pnls) > 0 else 0
    avg_return = pnls.mean()
    median_return = pnls.median()
    max_drawdown = pnls.min()
    profit_loss_ratio = abs(wins.mean() / losses.mean()) if len(losses) > 0 and losses.mean() != 0 else float("inf")

    # 覆盖率 = 有信号的天数 / 总交易日数
    trade_dates = set(trades_df["trade_date"].unique())
    coverage = len(trade_dates) / len(dates) * 100 if len(dates) > 0 else 0

    # 等权组合每日收益（用于计算夏普、累积收益等）
    daily_returns = trades_df.groupby("trade_date")["pnl_pct"].mean()
    cumulative = (1 + daily_returns / 100).cumprod()
    max_dd_series = (cumulative.cummax() - cumulative) / cumulative.cummax()
    portfolio_max_dd = max_dd_series.max() * 100 if len(max_dd_series) > 0 else 0
    portfolio_max_dd = abs(portfolio_max_dd)  # 确保回撤为正值

    return {
        "total_trades": len(pnls),
        "win_rate": round(win_rate, 2),
        "avg_return": round(avg_return, 4),
        "median_return": round(median_return, 4),
        "max_drawdown": round(max_drawdown, 4),
        "portfolio_max_dd": round(portfolio_max_dd, 4),
        "profit_loss_ratio": round(profit_loss_ratio, 4),
        "coverage": round(coverage, 2),
        "daily_std": round(daily_returns.std(), 4),
        "sharpe_approx": round(avg_return / daily_returns.std(), 4) if daily_returns.std() > 0 else 0,
    }


def print_report(trades_df: pd.DataFrame, metrics: Dict):
    """打印回测报告"""
    print("\n" + "=" * 80)
    print("Champion Baseline 回测报告")
    print("=" * 80)

    print(f"\n策略配置:")
    print(f"  股票池: {CHAMPION_STRATEGY['universe']}")
    print(f"  入选条件: score >= {CHAMPION_STRATEGY['selection_criteria']['score_threshold']}")
    print(f"  排除评级: {', '.join(CHAMPION_STRATEGY['selection_criteria']['exclude_ratings'])}")
    print(f"  每日持仓: 最多 Top {CHAMPION_STRATEGY['position_sizing']['max_positions_per_day']}")
    exit_desc = "T+1 开盘价"
    if CHAMPION_STRATEGY['exit_rule'].get('type') == 'stop_loss_close':
        exit_desc = f"T+1 回撤超 {CHAMPION_STRATEGY['exit_rule'].get('stop_loss_pct', 3)}% 止损，否则收盘卖"
    print(f"  入场: {CHAMPION_STRATEGY['entry_rule']['time']} (优先用 pytdx 真实下午开盘价，缺失则跳过)")
    print(f"  出场: {exit_desc}")
    print(f"  滑点: {CHAMPION_STRATEGY['slippage'] * 100}%")

    print(f"\n核心指标:")
    print(f"  总交易数: {metrics['total_trades']}")
    print(f"  胜率: {metrics['win_rate']:.1f}%")
    print(f"  平均收益: {metrics['avg_return']:+.2f}%")
    print(f"  中位数收益: {metrics['median_return']:+.2f}%")
    print(f"  单笔最大回撤: {metrics['max_drawdown']:+.2f}%")
    print(f"  组合最大回撤: {metrics['portfolio_max_dd']:.2f}%")
    print(f"  盈亏比: {metrics['profit_loss_ratio']:.2f}")
    print(f"  覆盖率: {metrics['coverage']:.1f}%")
    print(f"  日收益波动: {metrics['daily_std']:.2f}%")
    print(f"  夏普近似: {metrics['sharpe_approx']:.2f}")

    if len(trades_df) > 0:
        print(f"\n评级分布:")
        for rating, count in trades_df["rating"].value_counts().items():
            subset = trades_df[trades_df["rating"] == rating]
            avg_pnl = subset["pnl_pct"].mean()
            print(f"  {rating}: {count} 笔, 平均收益 {avg_pnl:+.2f}%")


def main():
    parser = argparse.ArgumentParser(description="AShareSignal 统一回测引擎")
    parser.add_argument("--start", type=str, required=True, help="开始日期 YYYYMMDD")
    parser.add_argument("--end", type=str, required=True, help="结束日期 YYYYMMDD")
    parser.add_argument("--output", type=str, default="champion_baseline.csv", help="输出文件名")
    parser.add_argument("--champion", action="store_true", help="运行 champion baseline")
    args = parser.parse_args()

    dates = get_trading_days(args.start, args.end)
    if len(dates) == 0:
        print("无有效交易日")
        return

    print(f"开始回测: {args.start} ~ {args.end}, 共 {len(dates)} 个交易日")
    trades_df, metrics = run_backtest(dates)

    print_report(trades_df, metrics)

    # 保存结果
    OUTPUT_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_REPORTS_DIR / args.output
    trades_df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\n交易明细已保存: {output_path}")


if __name__ == "__main__":
    main()

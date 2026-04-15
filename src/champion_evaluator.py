"""
Champion / Challenger 评估器
输入 challenger 的 metrics，自动与 champion 比较，输出升级建议
"""

from typing import Dict, Any


def evaluate_challenger(
    champion_metrics: Dict[str, Any],
    challenger_metrics: Dict[str, Any],
    verbose: bool = True,
) -> str:
    """
    评估 challenger 是否可以取代 champion

    升级门槛（必须同时满足）:
    1. OOS 收益不低于 champion
    2. 最大回撤不恶化
    3. 样本覆盖率 > 50%
    4. 加滑点后仍成立（challenger_metrics 需已包含滑点）

    Returns:
        "PROMOTE" | "REJECT" | "PENDING"
    """
    reasons = []

    # 1. OOS 收益比较（用平均收益作为代理）
    champ_return = champion_metrics.get("avg_return", 0)
    chall_return = challenger_metrics.get("avg_return", 0)
    if chall_return < champ_return:
        reasons.append(f"OOS 收益下降: {chall_return:+.2f}% < {champ_return:+.2f}%")

    # 2. 最大回撤不恶化（以组合最大回撤为主）
    champ_port_dd = champion_metrics.get("portfolio_max_dd", 999)
    chall_port_dd = challenger_metrics.get("portfolio_max_dd", 999)
    if chall_port_dd > champ_port_dd:
        reasons.append(f"组合最大回撤恶化: {chall_port_dd:.2f}% > {champ_port_dd:.2f}%")

    # 3. 覆盖率 > 50%
    champ_coverage = champion_metrics.get("coverage", 0)
    chall_coverage = challenger_metrics.get("coverage", 0)
    if chall_coverage <= 50:
        reasons.append(f"覆盖率不足: {chall_coverage:.1f}% <= 50%")

    # 4. 样本数检查（如果样本数太少，标记为 PENDING）
    champ_trades = champion_metrics.get("total_trades", 0)
    chall_trades = challenger_metrics.get("total_trades", 0)
    if chall_trades < max(30, champ_trades * 0.3):
        if verbose:
            print(f"⚠️ 样本数偏少: {chall_trades} 笔，建议更多数据")

    if len(reasons) == 0:
        if chall_trades < max(30, champ_trades * 0.3):
            return "PENDING"
        return "PROMOTE"
    else:
        return "REJECT"


def print_evaluation(
    champion_metrics: Dict[str, Any],
    challenger_metrics: Dict[str, Any],
    result: str,
):
    """打印评估结果"""
    print("\n" + "=" * 60)
    print("Champion vs Challenger 评估")
    print("=" * 60)

    print(f"\n{'指标':<20} {'Champion':>12} {'Challenger':>12}")
    print("-" * 50)

    keys = [
        ("总交易数", "total_trades", "{:>12.0f}"),
        ("胜率(%)", "win_rate", "{:>12.1f}"),
        ("平均收益(%)", "avg_return", "{:>+12.2f}"),
        ("中位数收益(%)", "median_return", "{:>+12.2f}"),
        ("单笔最大回撤(%)", "max_drawdown", "{:>+12.2f}"),
        ("组合最大回撤(%)", "portfolio_max_dd", "{:>12.2f}"),
        ("盈亏比", "profit_loss_ratio", "{:>12.2f}"),
        ("覆盖率(%)", "coverage", "{:>12.1f}"),
    ]

    for label, key, fmt in keys:
        c_val = champion_metrics.get(key, 0)
        ch_val = challenger_metrics.get(key, 0)
        print(f"{label:<20} {fmt.format(c_val)} {fmt.format(ch_val)}")

    print("\n" + "-" * 50)
    if result == "PROMOTE":
        print("✅ 评估结果: PROMOTE — 建议升级 challenger 为 champion")
    elif result == "REJECT":
        print("❌ 评估结果: REJECT — challenger 未达到升级门槛")
    else:
        print("⚠️ 评估结果: PENDING — 样本不足或结果模糊，需要更多数据")
    print("=" * 60)


if __name__ == "__main__":
    # 测试
    champion = {
        "total_trades": 80,
        "win_rate": 16.2,
        "avg_return": -1.30,
        "max_drawdown": -6.77,
        "portfolio_max_dd": 17.30,
        "profit_loss_ratio": 0.69,
        "coverage": 94.1,
    }

    # 一个更差的 challenger
    challenger_worse = {
        "total_trades": 75,
        "win_rate": 15.0,
        "avg_return": -2.00,
        "max_drawdown": -7.50,
        "portfolio_max_dd": 20.00,
        "profit_loss_ratio": 0.50,
        "coverage": 93.0,
    }

    res = evaluate_challenger(champion, challenger_worse)
    print_evaluation(champion, challenger_worse, res)

    # 一个更好的 challenger
    challenger_better = {
        "total_trades": 80,
        "win_rate": 20.0,
        "avg_return": -0.50,
        "max_drawdown": -5.00,
        "portfolio_max_dd": 10.00,
        "profit_loss_ratio": 1.20,
        "coverage": 94.1,
    }

    res = evaluate_challenger(champion, challenger_better)
    print_evaluation(champion, challenger_better, res)

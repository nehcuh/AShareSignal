"""
实验记录器
每个实验强制记录 8 个字段，自动追加到 wiki/experiments/ 下的 markdown 文件
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent
EXPERIMENTS_DIR = PROJECT_ROOT / "wiki" / "experiments"
EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)


class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


def log_experiment(
    experiment_id: str,
    hypothesis: str,
    changed_variable: str,
    baseline: str,
    date_range: str,
    sample_count: int,
    metrics: Dict[str, Any],
    oos_passed: bool,
    decision: str,
    notes: Optional[str] = None,
) -> Path:
    """
    记录一次实验结果到 wiki/experiments/{experiment_id}.md

    Args:
        experiment_id: 实验编号，如 "exp01_veto_a"
        hypothesis: 假设是什么
        changed_variable: 改了哪个唯一变量
        baseline: baseline 是什么
        date_range: 使用的数据区间
        sample_count: 样本数是多少
        metrics: 结果指标字典
        oos_passed: 是否通过 OOS
        decision: 最终决策（保留 / 废弃 / 待复核）
        notes: 额外备注

    Returns:
        生成的 markdown 文件路径
    """
    output_path = EXPERIMENTS_DIR / f"{experiment_id}.md"

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    content = f"""# {experiment_id}

> 记录时间: {now}

## 1. 假设

{hypothesis}

## 2. 唯一变量

{changed_variable}

## 3. Baseline

{baseline}

## 4. 数据区间

{date_range}

## 5. 样本数

{sample_count}

## 6. 结果指标

```json
{json.dumps(metrics, indent=2, ensure_ascii=False, cls=NumpyEncoder)}
```

## 7. OOS 验证

{'✅ 通过' if oos_passed else '❌ 未通过'}

## 8. 最终决策

**{decision}**

"""

    if notes:
        content += f"""## 备注

{notes}

"""

    content += "---\n\n"

    # 追加模式写入
    with open(output_path, "a", encoding="utf-8") as f:
        f.write(content)

    return output_path


def log_experiment_from_backtest(
    experiment_id: str,
    hypothesis: str,
    changed_variable: str,
    baseline_metrics: Dict[str, Any],
    challenger_metrics: Dict[str, Any],
    date_range: str,
    sample_count: int,
    oos_passed: bool,
    decision: str,
    notes: Optional[str] = None,
) -> Path:
    """
    便捷函数：同时记录 baseline 和 challenger 的指标
    """
    metrics = {
        "baseline": baseline_metrics,
        "challenger": challenger_metrics,
    }
    return log_experiment(
        experiment_id=experiment_id,
        hypothesis=hypothesis,
        changed_variable=changed_variable,
        baseline=baseline_metrics.get("name", "champion_baseline"),
        date_range=date_range,
        sample_count=sample_count,
        metrics=metrics,
        oos_passed=oos_passed,
        decision=decision,
        notes=notes,
    )


if __name__ == "__main__":
    # 简单测试
    path = log_experiment(
        experiment_id="exp01_veto_a_test",
        hypothesis="对 score>=60 的股票，若 13:30 仍低于下午开盘价则禁买，可降低最大回撤",
        changed_variable="entry veto 规则: pm_return_1330 < 0",
        baseline="champion_baseline (score>=60, T+1开盘卖出)",
        date_range="20260320 ~ 20260414",
        sample_count=80,
        metrics={"win_rate": 16.2, "avg_return": -1.30, "max_drawdown": -6.77},
        oos_passed=False,
        decision="废弃",
        notes="这是一个测试记录",
    )
    print(f"实验记录已保存: {path}")

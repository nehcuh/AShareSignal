#!/usr/bin/env python3
"""
每日自动筛选脚本
- 获取主板非ST股票列表
- 用 pytdx 分钟数据计算上午特征
- 应用 champion 评分策略 + Pre-Veto
- 输出 Top 5 推荐到 output/latest/
- 可扩展：发送通知到微信/钉钉/邮件
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# 确保能找到 src 模块
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from screen_today_pytdx import screen_today_with_pytdx, build_top5_recommendation


def send_notification(top5_df, date_str: str):
    """
    发送通知（当前只打印到控制台，后续可接入微信/钉钉/邮件）
    """
    if top5_df.empty:
        print(f"\n[{date_str}] 今日无推荐股票，不发送通知")
        return

    lines = [
        f"📊 AShareSignal 每日推荐 {date_str}",
        "=" * 50,
    ]

    for i, (_, row) in enumerate(top5_df.iterrows(), 1):
        lines.append(
            f"#{i} {row['ts_code']} {row['name']} | 得分:{row['score']} | 评级:{row['rating']}\n"
            f"   上午涨幅:{row['morning_return']:+.2f}% | 最后5m:{row['last_5m_return']:+.2f}%\n"
            f"   计划:13:00 pm_open 买入\n"
            f"   出场:T+1 回撤超3%止损，否则收盘卖出"
        )

    message = "\n\n".join(lines)
    print("\n" + message)

    # TODO: 接入企业微信/钉钉/邮件通知
    # webhook_url = os.environ.get("DINGTALK_WEBHOOK", "")
    # if webhook_url:
    #     requests.post(webhook_url, json={"msgtype": "text", "text": {"content": message}})


def main():
    today = datetime.now().strftime('%Y%m%d')
    print(f"\n{'='*60}")
    print(f"AShareSignal 每日自动筛选 - {today}")
    print(f"{'='*60}")

    # 1. 运行筛选
    result = screen_today_with_pytdx(max_stocks=300)

    if result.empty:
        print("\n今日未筛选出任何股票，流程结束")
        return

    # 2. 生成 Top 5
    top5 = build_top5_recommendation(result, max_positions=5)

    # 3. 发送通知
    send_notification(top5, today)

    # 4. 保存结果路径汇总
    latest_dir = Path(__file__).parent.parent / "output" / "latest"
    print(f"\n📁 结果文件:")
    print(f"   完整筛选: output/screening_pytdx_{today}.csv")
    if not top5.empty:
        print(f"   Top 5 推荐: output/latest/top5_{today}.csv")
    print(f"\n✅ {today} 每日筛选完成")


if __name__ == "__main__":
    main()

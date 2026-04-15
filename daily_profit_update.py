#!/usr/bin/env python3
import pandas as pd
from pytdx.hq import TdxHq_API
from pytdx.config.hosts import hq_hosts
from datetime import datetime
import random
import subprocess
import os

# Configuration
TRACKING_FILE = "/Users/huchen/Projects/AShareSignal/output/stock_tracking_20260414_updated.csv"
ENTRY_PRICE_COL = "参考入场价(2026-04-14)"
# 微信发送命令，根据实际环境调整，可替换为itchat/企业微信机器人/webhook等实现
WECHAT_SEND_WEBHOOK = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY"
USE_WEBHOOK = False  # 设为True使用企业微信机器人webhook，否则使用命令行工具

def send_wechat(message):
    """发送消息到微信"""
    try:
        if USE_WEBHOOK:
            import requests
            payload = {
                "msgtype": "text",
                "text": {
                    "content": message
                }
            }
            requests.post(WECHAT_SEND_WEBHOOK, json=payload, timeout=10)
        else:
            # 替换为实际的命令行微信发送指令，如wechaty-cli/itchat-runner等
            subprocess.run(
                ["wechat-cli", "send", "current", message],
                check=True,
                capture_output=True,
                text=True
            )
        return True
    except Exception as e:
        print(f"发送微信失败: {str(e)}")
        return False

if __name__ == "__main__":
    # 创建日志目录
    os.makedirs("/Users/huchen/Projects/AShareSignal/logs", exist_ok=True)
    
    # 读取跟踪数据
    df = pd.read_csv(TRACKING_FILE)
    today = datetime.now().strftime("%Y-%m-%d")
    
    # 初始化TDX API
    api = TdxHq_API()
    random.shuffle(hq_hosts)
    connected = False
    selected_host = None
    for host in hq_hosts[:10]:
        try:
            if api.connect(host[1], host[2], time_out=3):
                connected = True
                selected_host = host
                break
        except Exception as e:
            continue
    
    if not connected:
        send_wechat(f"【每日收益报表({today})】连接通达信服务器失败，无法更新收益数据")
        exit(1)
    
    # 获取最新价
    success_count = 0
    fail_count = 0
    stock_profit_list = []
    
    for idx, row in df.iterrows():
        code_full = row["代码"]
        name = row["名称"]
        entry_price = row[ENTRY_PRICE_COL]
        if pd.isna(entry_price) or entry_price <= 0:
            stock_profit_list.append(f"{code_full} {name}: 无有效入场价")
            continue
        
        code, market_suffix = code_full.split(".")
        market = 1 if market_suffix == "SH" else 0
        
        # 获取最新日K线收盘价
        daily_kline = api.get_security_bars(
            category=9, market=market, code=code, start=0, count=1
        )
        
        if daily_kline:
            latest_price = daily_kline[0]["close"]
            profit_pct = (latest_price / entry_price - 1) * 100
            df.at[idx, f"{today}最新价"] = round(latest_price, 2)
            df.at[idx, "累计涨跌幅(%)"] = round(profit_pct, 2)
            stock_profit_list.append(f"✅ {code_full} {name}: 最新价{latest_price:.2f}, 涨跌幅{profit_pct:.2f}%")
            success_count += 1
        else:
            fail_count += 1
            stock_profit_list.append(f"❌ {code_full} {name}: 获取最新价失败")
    
    api.disconnect()
    
    # 生成报表
    report = f"📊 A股选股池每日收益报表 ({today})\n"
    report += "="*40 + "\n"
    report += "\n".join(stock_profit_list)
    report += "\n" + "="*40 + "\n"
    report += f"统计: 共{len(df)}只股票, 成功{success_count}只, 失败{fail_count}只\n"
    report += f"数据源: 通达信服务器 {selected_host[1]}:{selected_host[2]}"
    
    # 保存更新后的数据
    df.to_csv(TRACKING_FILE, index=False, encoding="utf-8-sig")
    
    # 发送到微信
    if send_wechat(report):
        print(f"[{datetime.now()}] 报表已发送到微信")
    else:
        print(f"[{datetime.now()}] 报表发送失败，内容如下:\n{report}")
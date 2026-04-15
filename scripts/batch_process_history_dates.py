#!/usr/bin/env python3
import os
import subprocess
import time

def run_command(cmd):
    """运行shell命令并返回结果"""
    print(f"\n🚀 运行命令: {cmd}")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=600)
        if result.returncode == 0:
            print(f"✅ 命令执行成功")
            return True
        else:
            print(f"❌ 命令执行失败，错误信息: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print(f"⚠️ 命令执行超时")
        return False

def process_date(date):
    """处理单个日期的筛选流程"""
    print(f"\n\n{'='*80}")
    print(f"📅 开始处理日期: {date}")
    print(f"{'='*80}")
    
    # 1. 日线粗筛
    if not run_command(f"cd ~/Projects/AShareSignal && uv run scripts/backfill_daily.py --date={date}"):
        print(f"❌ {date} 日线粗筛失败，跳过该日期")
        return False
    
    # 2. 分钟级重算
    if not run_command(f"cd ~/Projects/AShareSignal && uv run scripts/backfill_minute.py --date={date}"):
        print(f"❌ {date} 分钟级重算失败，跳过该日期")
        return False
    
    # 3. 筛选top5
    if not run_command(f"cd ~/Projects/AShareSignal && uv run scripts/signal_filter.py --date={date} --top=5"):
        print(f"❌ {date} 筛选top5失败，跳过该日期")
        return False
    
    print(f"\n🎉 {date} 处理完成，结果已保存到 output/screening_{date}_final_top5.csv")
    return True

def main():
    # 读取需要处理的日期列表
    with open('need_process_dates.txt', 'r') as f:
        dates = [d.strip() for d in f.readlines() if d.strip()]
    
    print(f"✅ 共加载到 {len(dates)} 个需要处理的日期")
    
    success_count = 0
    fail_count = 0
    failed_dates = []
    
    for date in dates:
        if process_date(date):
            success_count += 1
        else:
            fail_count += 1
            failed_dates.append(date)
        
        # 间隔3秒，避免请求过于频繁
        time.sleep(3)
    
    # 统计结果
    print(f"\n\n{'='*80}")
    print(f"📊 全部处理完成，统计结果:")
    print(f"{'='*80}")
    print(f"总日期数: {len(dates)}")
    print(f"处理成功: {success_count}")
    print(f"处理失败: {fail_count}")
    if fail_count > 0:
        print(f"失败日期列表: {failed_dates}")
        # 保存失败日期到文件
        with open('failed_dates.txt', 'w') as f:
            for date in failed_dates:
                f.write(f"{date}\n")
        print(f"失败日期已保存到: failed_dates.txt")

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    main()
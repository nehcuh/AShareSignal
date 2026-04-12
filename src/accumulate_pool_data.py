"""
股票池分钟数据积累脚本
使用 Tushare 每天2次的配额，优先积累股票池中的股票
"""

import pandas as pd
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from predict_hybrid import HybridMinutePredictor
import tushare as ts

# 设置 Tushare token
ts.set_token("fd6cf8fc8404cf6f93ca6091c1e603d9bc3a65f5a536c77dbb882e60")
pro = ts.pro_api()

def load_stock_pool():
    """加载所有股票池中的唯一股票"""
    df = pd.read_excel("assets/池子_20251104.xlsx")

    all_stocks = set()
    for _, row in df.iterrows():
        if pd.notna(row['pool_data']):
            stocks = row['pool_data'].split(',')
            all_stocks.update(stocks)

    return sorted(list(all_stocks))

def check_cache(ts_code: str, trade_date: str) -> bool:
    """检查是否已有缓存"""
    cache_dir = Path("data/minute_cache")
    cache_file = cache_dir / f"{ts_code}_{trade_date}_5min.pkl"
    return cache_file.exists()

def load_stock_pool_for_date(pool_date: str = "2025-12-24") -> list:
    """加载特定日期的股票池"""
    df = pd.read_excel("assets/池子_20251104.xlsx")

    # 查找对应日期
    row = df[df['pool_date'] == pool_date]
    if len(row) == 0:
        print(f"未找到日期 {pool_date} 的股票池")
        return []

    stocks = row.iloc[0]['pool_data'].split(',') if pd.notna(row.iloc[0]['pool_data']) else []
    return stocks

def plan_downloads_for_date(target_date: str = "20241224", pool_date: str = "2025-12-24"):
    """
    规划特定日期股票池的下载

    Args:
        target_date: 要下载的历史日期 (YYYYMMDD)
        pool_date: Excel中的股票池日期 (如 2025-12-24)
    """
    print("="*80)
    print(f"股票池分钟数据积累计划 - {pool_date}")
    print("="*80)

    # 加载该日期的股票池
    pool_stocks = load_stock_pool_for_date(pool_date)
    if not pool_stocks:
        return

    print(f"\n股票池 {pool_date} 共有 {len(pool_stocks)} 只股票")
    print(f"示例: {pool_stocks[:10]}")

    # 检查缓存状态
    cached = []
    need_download = []

    for code in pool_stocks:
        if check_cache(code, target_date):
            cached.append(code)
        else:
            need_download.append(code)

    print(f"\n缓存状态 (日期: {target_date}):")
    print(f"  已有缓存: {len(cached)} 只")
    print(f"  需要下载: {len(need_download)} 只")

    # 计算需要的天数
    daily_quota = 2
    days_needed = (len(need_download) + daily_quota - 1) // daily_quota

    print(f"\n下载计划:")
    print(f"  每天配额: {daily_quota} 只")
    print(f"  需要天数: {days_needed} 天")

    # 生成今日下载命令
    if need_download:
        print(f"\n今日推荐下载命令:")
        today_stocks = need_download[:daily_quota]
        pool_str = ",".join(today_stocks)
        print(f"  uv run python src/predict_hybrid.py --mode download --date {target_date} --pool \"{pool_str}\"")

        # 保存完整下载列表到文件
        output_file = f"data/download_plan_{target_date}.txt"
        Path("data").mkdir(exist_ok=True)
        with open(output_file, "w") as f:
            f.write(f"# 股票池分钟数据下载计划\n")
            f.write(f"# 目标日期: {target_date}\n")
            f.write(f"# 股票池日期: {pool_date}\n")
            f.write(f"# 总共需要下载: {len(need_download)} 只股票\n")
            f.write(f"# 预计天数: {days_needed} 天\n\n")

            for i in range(0, len(need_download), daily_quota):
                batch = need_download[i:i+daily_quota]
                day_num = i // daily_quota + 1
                f.write(f"# Day {day_num}\n")
                f.write(f"uv run python src/predict_hybrid.py --mode download --date {target_date} --pool \"{','.join(batch)}\"\n\n")

        print(f"\n完整下载计划已保存到: {output_file}")

    return need_download

def download_today(target_date: str = "20241224"):
    """下载今天的2只股票"""
    need_download = plan_downloads(target_date)

    if len(need_download) < 2:
        print(f"\n✅ 所有股票池股票都已有缓存！")
        return

    today_stocks = need_download[:2]
    print(f"\n开始下载 {today_stocks}...")

    predictor = HybridMinutePredictor()

    for code in today_stocks:
        print(f"\n下载 {code} {target_date} 的分钟数据...")
        try:
            # 尝试下载
            result = predictor.minute_manager.minute_api.download_minute_data(
                code, target_date, freq="5"
            )
            if result is not None:
                print(f"  ✅ 成功: {len(result)} 条记录")
            else:
                print(f"  ❌ 失败: 无数据")
        except Exception as e:
            print(f"  ❌ 失败: {e}")

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "download":
        # 下载模式：下载今日的2只
        download_today()
    elif len(sys.argv) > 1 and sys.argv[1] == "plan":
        # 计划模式：指定日期
        target = sys.argv[2] if len(sys.argv) > 2 else "20241224"
        pool = sys.argv[3] if len(sys.argv) > 3 else "2025-12-24"
        plan_downloads_for_date(target, pool)
    else:
        # 默认：显示2025-12-24股票池的计划
        plan_downloads_for_date("20241224", "2025-12-24")

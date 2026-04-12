"""
分钟数据预测系统 - 使用缓存 + 批量处理方案
由于 Tushare 分钟数据权限限制（每天2次），本方案提供：
1. 使用已缓存的分钟数据
2. 逐步下载积累缓存
3. 混合使用真实分钟数据 + 日线模拟特征
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
import sys
sys.path.append(str(Path(__file__).parent))

from minute_data_manager import MinuteDataManager, RealMorningFeatureExtractor
from autoresearch import DataLoader, BacktestEngine

import tushare as ts
TUSHARE_TOKEN = "fd6cf8fc8404cf6f93ca6091c1e603d9bc3a65f5a536c77dbb882e60"
ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()


class HybridMinutePredictor:
    """混合预测器 - 有分钟数据用真实数据，没有则用日线模拟"""

    def __init__(self, cache_dir: str = "data/minute_cache"):
        self.minute_manager = MinuteDataManager(cache_dir)
        self.minute_extractor = RealMorningFeatureExtractor(self.minute_manager)
        self.data_loader = DataLoader()

    def get_morning_features(self, ts_code: str, trade_date: str, daily_df: pd.DataFrame) -> dict:
        """
        获取上午特征 - 优先使用真实分钟数据，否则用日线模拟
        """
        # 尝试获取真实分钟特征
        minute_features = self.minute_extractor.extract_features(ts_code, trade_date, "5min")

        if minute_features is not None:
            minute_features["minute_data_source"] = "real"
            return minute_features

        # 使用日线模拟
        return self._simulate_morning_from_daily(ts_code, trade_date, daily_df)

    def _simulate_morning_from_daily(self, ts_code: str, trade_date: str, daily_df: pd.DataFrame) -> dict:
        """从日线模拟上午特征"""
        day_data = daily_df[
            (daily_df["ts_code"] == ts_code) &
            (daily_df["trade_date"] == trade_date)
        ]

        if len(day_data) == 0:
            return None

        row = day_data.iloc[0]
        open_p = row["open"]
        close_p = row["close"]
        pre_close = row["pre_close"]
        high = row["high"]
        low = row["low"]

        # 模拟值
        return {
            "ts_code": ts_code,
            "trade_date": trade_date,
            "morning_open": open_p,
            "morning_gap_pct": round((open_p - pre_close) / pre_close * 100, 4),
            "morning_return": round((close_p - pre_close) / pre_close * 100, 4),
            "morning_change": round((close_p - open_p) / open_p * 100, 4),
            "morning_max_up": round((high - open_p) / open_p * 100, 4),
            "morning_max_down": round((low - open_p) / open_p * 100, 4),
            "morning_range": round((high - low) / open_p * 100, 4),
            "morning_volatility": 0,  # 无法从日线计算
            "morning_total_vol": row.get("vol", 0),
            "morning_avg_vol": 0,
            "close_position": 0.5,  # 默认中间位置
            "vol_distribution": 1.0,
            "minute_data_source": "simulated"
        }

    def predict(self, ts_code: str, trade_date: str, daily_df: pd.DataFrame) -> dict:
        """预测次日涨跌"""

        # 获取日线历史特征 (T-1及之前)
        hist_data = daily_df[
            (daily_df["ts_code"] == ts_code) &
            (daily_df["trade_date"] < trade_date)
        ].copy().sort_values("trade_date")

        if len(hist_data) < 20:
            return None

        # 日线特征
        close = hist_data["close"]
        pct_chg = hist_data["pct_chg"]

        daily_features = {}
        if len(close) >= 5:
            ma5 = close.tail(5).mean()
            daily_features["dist_to_ma5"] = round((close.iloc[-1] / ma5 - 1) * 100, 2)

        if len(pct_chg) >= 20:
            return_5 = pct_chg.tail(5).mean()
            return_20 = pct_chg.tail(20).mean()
            daily_features["trend_divergence"] = round(return_5 - return_20, 4)

            vol_5 = pct_chg.tail(5).std()
            vol_20 = pct_chg.tail(20).std()
            daily_features["vol_regime"] = round(vol_5 / (vol_20 + 1e-10), 4)

        if len(close) >= 7:
            delta = close.diff()
            gain = delta.where(delta > 0, 0).rolling(6).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(6).mean()
            rs = gain / loss.replace(0, np.inf)
            rsi = (100 - (100 / (1 + rs))).iloc[-1]
            daily_features["rsi_oversold"] = 1 if rsi < 30 else 0

        # 分钟特征
        minute_features = self.get_morning_features(ts_code, trade_date, daily_df)
        if minute_features is None:
            return None

        # 合并
        all_features = {**daily_features, **minute_features}

        # 计算概率
        score = 0.5

        # 分钟数据因子
        morning_max_down = minute_features.get("morning_max_down", 0)
        if morning_max_down < -2:
            score += 0.1
            close_pos = minute_features.get("close_position", 0.5)
            if close_pos > 0.6:
                score += 0.15

        morning_gap = minute_features.get("morning_gap_pct", 0)
        morning_return = minute_features.get("morning_return", 0)
        if morning_gap < -1.5 and morning_return > 0:
            score += 0.15
        if morning_gap > 2 and morning_return < 0:
            score -= 0.2

        vol_dist = minute_features.get("vol_distribution", 1)
        if vol_dist > 1.2 and morning_return > 0:
            score += 0.1

        # 日线因子
        if daily_features.get("rsi_oversold", 0) == 1:
            score += 0.1
        if daily_features.get("trend_divergence", 0) > 0:
            score += 0.05
        if daily_features.get("vol_regime", 1) > 1.2:
            score += 0.05

        prob = max(0, min(1, score))

        # 信号
        signals = []
        if morning_max_down < -2:
            signals.append("深跌反弹")
        if morning_gap < -1.5 and morning_return > 0:
            signals.append("低开高走")
        if morning_gap > 2 and morning_return < 0:
            signals.append("⚠️高开诱多")
        if daily_features.get("rsi_oversold", 0) == 1:
            signals.append("RSI超卖")

        data_quality = "高" if minute_features.get("minute_data_source") == "real" else "中"

        return {
            "ts_code": ts_code,
            "trade_date": trade_date,
            "probability": round(prob, 4),
            "confidence": "高" if prob > 0.6 else ("中" if prob > 0.45 else "低"),
            "recommendation": "推荐" if prob > 0.55 else ("谨慎" if prob > 0.4 else "避免"),
            "data_quality": data_quality,
            "signals": signals,
            "features": all_features
        }

    def predict_batch(self, ts_codes: list, trade_date: str, daily_df: pd.DataFrame) -> pd.DataFrame:
        """批量预测"""
        results = []

        print(f"\n预测 {len(ts_codes)} 只股票...")

        for i, code in enumerate(ts_codes):
            if (i + 1) % 10 == 0:
                print(f"  进度: {i+1}/{len(ts_codes)}")

            result = self.predict(code, trade_date, daily_df)
            if result:
                results.append(result)

        return pd.DataFrame(results)


def batch_download_minute_data(
    ts_codes: list,
    trade_date: str,
    cache_dir: str = "data/minute_cache"
):
    """
    批量下载分钟数据 - 渐进式积累缓存
    由于 Tushare 限制每天2次，建议每天运行一次积累数据
    """
    manager = MinuteDataManager(cache_dir)

    # 检查哪些还没缓存
    missing_codes = []
    for code in ts_codes:
        if manager.cache.get(code, trade_date, "5min") is None:
            missing_codes.append(code)

    if not missing_codes:
        print("所有股票已有缓存！")
        return

    print(f"需要下载 {len(missing_codes)} 只股票 (每天限2只)...")
    print(f"建议: 每天运行一次，约需 {len(missing_codes) / 2:.0f} 天完成全部缓存")

    # 下载前2只
    to_download = missing_codes[:2]
    for code in to_download:
        print(f"\n下载 {code}...")
        df = manager.download_minute_data(code, trade_date, "5min", use_cache=True)
        if df is not None:
            print(f"  ✓ 成功: {len(df)} 条记录")
        else:
            print(f"  ✗ 失败")

    stats = manager.get_cache_stats()
    print(f"\n当前缓存: {stats['total_files']} 只, {stats['total_size_mb']} MB")


def main():
    """主入口"""
    import argparse

    parser = argparse.ArgumentParser(description='分钟数据预测系统')
    parser.add_argument('--mode', type=str, default='predict', choices=['predict', 'download'],
                        help='模式: predict=预测, download=下载分钟数据')
    parser.add_argument('--date', type=str, required=True, help='交易日期 (YYYYMMDD)')
    parser.add_argument('--pool', type=str, help='股票池代码，逗号分隔')
    parser.add_argument('--file', type=str, help='股票池Excel文件')

    args = parser.parse_args()

    # 加载股票池
    if args.pool:
        ts_codes = args.pool.split(",")
    elif args.file:
        df = pd.read_excel(args.file)
        ts_codes = df.iloc[0]["pool_data"].split(",")
    else:
        # 默认测试股票
        ts_codes = ["000001.SZ", "000002.SZ", "600519.SH", "000858.SZ", "002594.SZ"]

    print("="*80)
    print(f"分钟数据预测系统 - {args.date}")
    print("="*80)

    if args.mode == 'download':
        # 下载模式 - 积累缓存
        batch_download_minute_data(ts_codes, args.date)

    else:
        # 预测模式
        predictor = HybridMinutePredictor()

        # 获取日线数据
        min_date = (datetime.strptime(args.date, "%Y%m%d") - timedelta(days=60)).strftime("%Y%m%d")
        max_date = (datetime.strptime(args.date, "%Y%m%d") + timedelta(days=1)).strftime("%Y%m%d")

        print(f"获取日线数据...")
        daily_df = predictor.data_loader.fetch_daily_data(ts_codes, min_date, max_date)
        predictor.data_loader.daily_data = daily_df

        # 预测
        results = predictor.predict_batch(ts_codes, args.date, daily_df)

        if len(results) > 0:
            print("\n" + "="*80)
            print("预测结果")
            print("="*80)

            print(f"\n{'代码':<12} {'概率':<8} {'置信度':<6} {'数据质量':<8} {'推荐':<6} {'信号'}")
            print("-" * 80)

            for _, row in results.sort_values('probability', ascending=False).iterrows():
                signals_str = ", ".join(row['signals']) if row['signals'] else "无"
                print(f"{row['ts_code']:<12} {row['probability']:<8.2f} {row['confidence']:<6} "
                      f"{row['data_quality']:<8} {row['recommendation']:<6} {signals_str}")

            # 高置信度推荐
            high_conf = results[results['probability'] > 0.6]
            if len(high_conf) > 0:
                print(f"\n🏆 高置信度推荐 ({len(high_conf)} 只):")
                for _, row in high_conf.iterrows():
                    print(f"  {row['ts_code']}: {row['probability']:.2f}")

            # 保存结果
            output_dir = Path("output")
            output_dir.mkdir(exist_ok=True)
            results.to_csv(output_dir / f"predictions_{args.date}.csv", index=False, encoding="utf-8-sig")
            print(f"\n结果已保存: output/predictions_{args.date}.csv")


if __name__ == "__main__":
    main()

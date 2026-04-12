"""
使用真实分钟数据的次日上涨预测系统
基于 Experiment 006 的优化模型 + 真实高频数据
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
import sys
import pickle
from typing import List, Dict, Optional
sys.path.append(str(Path(__file__).parent))

from minute_data_manager import MinuteDataManager, RealMorningFeatureExtractor
from autoresearch import DataLoader, BacktestEngine

import tushare as ts
TUSHARE_TOKEN = "fd6cf8fc8404cf6f93ca6091c1e603d9bc3a65f5a536c77dbb882e60"
ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()


class RealMinutePredictor:
    """基于真实分钟数据的预测器"""

    def __init__(self, cache_dir: str = "data/minute_cache"):
        self.minute_manager = MinuteDataManager(cache_dir)
        self.minute_extractor = RealMorningFeatureExtractor(self.minute_manager)
        self.data_loader = DataLoader()

    def get_daily_features(self, ts_code: str, trade_date: str, daily_df: pd.DataFrame) -> dict:
        """获取日线特征 (T-1及之前)"""
        stock_data = daily_df[
            (daily_df["ts_code"] == ts_code) &
            (daily_df["trade_date"] < trade_date)
        ].copy().sort_values("trade_date")

        if len(stock_data) < 20:
            return None

        close = stock_data["close"]
        pct_chg = stock_data["pct_chg"]

        features = {}

        # 趋势特征
        if len(close) >= 5:
            ma5 = close.tail(5).mean()
            features["dist_to_ma5"] = round((close.iloc[-1] / ma5 - 1) * 100, 2)

        if len(pct_chg) >= 20:
            return_5 = pct_chg.tail(5).mean()
            return_20 = pct_chg.tail(20).mean()
            features["trend_divergence"] = round(return_5 - return_20, 4)

            vol_5 = pct_chg.tail(5).std()
            vol_20 = pct_chg.tail(20).std()
            features["vol_regime"] = round(vol_5 / (vol_20 + 1e-10), 4)

        # RSI
        if len(close) >= 7:
            delta = close.diff()
            gain = delta.where(delta > 0, 0).rolling(6).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(6).mean()
            rs = gain / loss.replace(0, np.inf)
            rsi = (100 - (100 / (1 + rs))).iloc[-1]
            features["rsi_oversold"] = 1 if rsi < 30 else 0

        return features

    def predict_with_real_minute(
        self,
        ts_code: str,
        trade_date: str,
        daily_df: pd.DataFrame,
        freq: str = "5min"
    ) -> dict:
        """
        使用真实分钟数据预测次日涨跌
        """
        # 1. 获取日线特征 (T-1及之前)
        daily_features = self.get_daily_features(ts_code, trade_date, daily_df)
        if daily_features is None:
            return None

        # 2. 获取真实分钟特征 (T日上午)
        minute_features = self.minute_extractor.extract_features(ts_code, trade_date, freq)
        if minute_features is None:
            return None

        # 3. 合并特征
        all_features = {**daily_features, **minute_features}

        # 4. 计算预测概率 (基于 Experiment 006 的模型简化版)
        score = 0.5

        # 分钟数据正向因子
        morning_max_down = minute_features.get("morning_max_down", 0)
        if morning_max_down < -2:
            score += 0.1
            rebound_strength = minute_features.get("close_position", 0.5)
            if rebound_strength > 0.6:
                score += 0.15

        # 低开高走
        morning_gap = minute_features.get("morning_gap_pct", 0)
        morning_return = minute_features.get("morning_return", 0)
        if morning_gap < -1.5 and morning_return > 0:
            score += 0.15

        # 高开低走 (避免)
        if morning_gap > 2 and morning_return < 0:
            score -= 0.2

        # 成交量放大但价格上涨 (量价齐升)
        vol_distribution = minute_features.get("vol_distribution", 1)
        if vol_distribution > 1.2 and morning_return > 0:
            score += 0.1

        # 日线因子
        if daily_features.get("rsi_oversold", 0) == 1:
            score += 0.1

        if daily_features.get("trend_divergence", 0) > 0:
            score += 0.05

        if daily_features.get("vol_regime", 1) > 1.2:
            score += 0.05

        if daily_features.get("dist_to_ma5", 0) > 0:
            score += 0.05

        # 限制概率范围
        prob = max(0, min(1, score))

        # 生成信号
        signals = []
        if morning_max_down < -2:
            signals.append("深跌反弹")
        if morning_gap < -1.5 and morning_return > 0:
            signals.append("低开高走")
        if morning_gap > 2 and morning_return < 0:
            signals.append("⚠️高开诱多")
        if daily_features.get("rsi_oversold", 0) == 1:
            signals.append("RSI超卖")
        if vol_distribution > 1.2 and morning_return > 0:
            signals.append("量价齐升")

        return {
            "ts_code": ts_code,
            "trade_date": trade_date,
            "probability": round(prob, 4),
            "confidence": "高" if prob > 0.6 else ("中" if prob > 0.45 else "低"),
            "recommendation": "推荐" if prob > 0.55 else ("谨慎" if prob > 0.4 else "避免"),
            "signals": signals,
            "features": all_features
        }

    def predict_batch(
        self,
        ts_codes: List[str],
        trade_date: str,
        daily_df: pd.DataFrame,
        freq: str = "5min",
        resume: bool = True
    ) -> pd.DataFrame:
        """
        批量预测 (支持断点续传)
        """
        results = []
        cache_file = Path("data/prediction_progress.pkl")

        # 尝试恢复进度
        if resume and cache_file.exists():
            with open(cache_file, 'rb') as f:
                results = pickle.load(f)
            print(f"已恢复进度: {len(results)} 只股票已处理")

        processed_codes = {r["ts_code"] for r in results}
        remaining_codes = [c for c in ts_codes if c not in processed_codes]

        print(f"\n批量预测 {len(remaining_codes)} 只股票 (已处理 {len(results)} 只)...")
        print(f"预计时间: ~{len(remaining_codes) * 35 / 60:.1f} 分钟 (受API限速)")

        for i, code in enumerate(remaining_codes):
            print(f"\n[{i+1}/{len(remaining_codes)}] 处理 {code}...")

            result = self.predict_with_real_minute(code, trade_date, daily_df, freq)
            if result:
                results.append(result)
                print(f"  ✓ 概率: {result['probability']:.2f}, 推荐: {result['recommendation']}")
            else:
                print(f"  ✗ 无法预测")

            # 每10只保存一次进度
            if (i + 1) % 10 == 0:
                with open(cache_file, 'wb') as f:
                    pickle.dump(results, f)
                print(f"  进度已保存")

        # 最终保存
        if results:
            with open(cache_file, 'wb') as f:
                pickle.dump(results, f)

        return pd.DataFrame(results)


def analyze_real_minute_features(trade_date: str = "20251224", sample_size: int = 50):
    """
    分析真实分钟特征与次日涨跌的关系
    """
    print("="*80)
    print("真实分钟特征分析")
    print("="*80)

    predictor = RealMinutePredictor()

    # 加载股票池
    excel_path = Path(__file__).parent.parent / "assets" / "池子_20251104.xlsx"
    pool_df = predictor.data_loader.load_stock_pool(str(excel_path))

    # 获取样本
    all_stocks = list(set().union(*pool_df["stock_list"]))[:sample_size]

    print(f"\n分析 {len(all_stocks)} 只股票...")

    # 获取日线数据
    min_date = pool_df["pool_date"].min().strftime("%Y%m%d")
    max_date = (pool_df["pool_date"].max() + timedelta(days=30)).strftime("%Y%m%d")
    start_fetch = (datetime.strptime(min_date, "%Y%m%d") - timedelta(days=60)).strftime("%Y%m%d")

    print(f"获取日线数据...")
    daily_df = predictor.data_loader.fetch_daily_data(all_stocks, start_fetch, max_date)

    # 获取交易日历
    backtest = BacktestEngine(predictor.data_loader)
    trading_days = backtest.get_trading_days(min_date, max_date)

    # 找到下一个交易日
    next_date = None
    for d in trading_days:
        if d > trade_date:
            next_date = d
            break

    if next_date:
        print(f"匹配次日涨跌: {trade_date} -> {next_date}")
        next_data = daily_df[daily_df["trade_date"] == next_date]
    else:
        next_data = None

    # 批量预测
    results_df = predictor.predict_batch(all_stocks, trade_date, daily_df)

    if next_data is not None:
        # 匹配次日涨跌
        for idx, row in results_df.iterrows():
            ts_code = row["ts_code"]
            next_row = next_data[next_data["ts_code"] == ts_code]
            if len(next_row) > 0:
                results_df.at[idx, "next_pct_chg"] = next_row.iloc[0]["pct_chg"]
                results_df.at[idx, "next_up"] = 1 if next_row.iloc[0]["pct_chg"] > 0 else 0

        # 分析结果
        print("\n" + "="*80)
        print("预测效果分析")
        print("="*80)

        high_conf = results_df[results_df["probability"] > 0.6]
        if len(high_conf) > 0 and "next_up" in high_conf.columns:
            up_rate = high_conf["next_up"].mean() * 100
            avg_return = high_conf["next_pct_chg"].mean()
            print(f"\n高置信度(>0.6): {len(high_conf)} 只")
            print(f"  次日上涨率: {up_rate:.1f}%")
            print(f"  平均收益: {avg_return:+.2f}%")

    # 保存结果
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    results_df.to_csv(output_dir / f"real_minute_predictions_{trade_date}.csv", index=False, encoding="utf-8-sig")

    print(f"\n结果已保存: output/real_minute_predictions_{trade_date}.csv")

    return results_df


def main():
    """主入口"""
    import argparse

    parser = argparse.ArgumentParser(description='使用真实分钟数据预测次日涨跌')
    parser.add_argument('--date', type=str, required=True, help='交易日期 (YYYYMMDD)')
    parser.add_argument('--pool', type=str, help='股票池代码，逗号分隔')
    parser.add_argument('--file', type=str, help='股票池文件路径 (Excel)')
    parser.add_argument('--sample', type=int, default=50, help='分析样本数量')
    args = parser.parse_args()

    if args.pool:
        ts_codes = args.pool.split(",")
        print(f"预测 {len(ts_codes)} 只股票...")
        # TODO: 实现单日预测
    else:
        # 运行分析
        analyze_real_minute_features(args.date, args.sample)


if __name__ == "__main__":
    # 如果没有参数，运行测试
    import sys
    if len(sys.argv) == 1:
        print("运行测试模式...")
        analyze_real_minute_features("20251224", sample_size=20)
    else:
        main()

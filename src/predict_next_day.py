"""
次日上涨预测策略 - 可执行版本
基于 Experiment 006 优化模型

使用方法:
1. 准备当日中午筛选的股票池
2. 运行: uv run python src/predict_next_day.py --date 20251224 --pool "000001.SZ,000002.SZ"
3. 获取预测结果和高置信度推荐
"""

import tushare as ts
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
import argparse
import json

from config import pro


class NextDayPredictor:
    """次日上涨预测器"""

    def __init__(self):
        self.features = [
            "morning_max_down", "rebound_strength", "rsi_oversold",
            "gap_down_reversal", "gap_reversal_strength", "gap_up_trap",
            "trend_divergence", "vol_regime", "dist_to_ma5"
        ]

    def fetch_stock_data(self, ts_code: str, end_date: str, days: int = 30) -> pd.DataFrame:
        """获取股票历史数据"""
        start_date = (datetime.strptime(end_date, "%Y%m%d") - timedelta(days=days*2)).strftime("%Y%m%d")

        try:
            df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
            return df.sort_values("trade_date") if df is not None and len(df) > 0 else None
        except Exception as e:
            print(f"  获取 {ts_code} 数据失败: {e}")
            return None

    def extract_features(self, df: pd.DataFrame) -> dict:
        """提取预测特征"""
        if df is None or len(df) < 20:
            return None

        current = df.iloc[-1]
        hist = df.iloc[:-1] if len(df) > 1 else df

        features = {}

        # 基础价格
        close = current["close"]
        open_p = current["open"]
        high = current["high"]
        low = current["low"]
        pre_close = current["pre_close"]

        # 1. morning_max_down (日内最大跌幅)
        features["morning_max_down"] = round((low - open_p) / open_p * 100, 2)

        # 2. rebound_strength (反弹强度)
        if features["morning_max_down"] < -2:
            rebound_strength = (close - low) / (high - low + 1e-10)
            features["rebound_strength"] = round(rebound_strength, 4)
        else:
            features["rebound_strength"] = 0.5

        # 3. rsi_oversold (RSI超卖)
        close_hist = hist["close"]
        if len(close_hist) >= 7:
            delta = close_hist.diff()
            gain = delta.where(delta > 0, 0).rolling(6).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(6).mean()
            rs = gain / loss.replace(0, np.inf)
            rsi = (100 - (100 / (1 + rs))).iloc[-1]
            features["rsi_oversold"] = 1 if rsi < 30 else 0
        else:
            features["rsi_oversold"] = 0

        # 4. gap_down_reversal (低开反转)
        gap_pct = (open_p - pre_close) / pre_close * 100
        features["gap_down_reversal"] = 1 if (gap_pct < -1.5 and close > open_p) else 0

        # 5. gap_reversal_strength (反转强度)
        if features["gap_down_reversal"] == 1:
            features["gap_reversal_strength"] = round((close - open_p) / abs(gap_pct), 4)
        else:
            features["gap_reversal_strength"] = 0

        # 6. gap_up_trap (高开诱多)
        features["gap_up_trap"] = 1 if (gap_pct > 2 and close < open_p) else 0

        # 7. trend_divergence (趋势背离)
        pct_chg = hist["pct_chg"]
        if len(pct_chg) >= 20:
            return_5 = pct_chg.tail(5).mean()
            return_20 = pct_chg.tail(20).mean()
            features["trend_divergence"] = round(return_5 - return_20, 4)
        else:
            features["trend_divergence"] = 0

        # 8. vol_regime (波动率状态)
        if len(pct_chg) >= 20:
            vol_5 = pct_chg.tail(5).std()
            vol_20 = pct_chg.tail(20).std()
            features["vol_regime"] = round(vol_5 / (vol_20 + 1e-10), 4)
        else:
            features["vol_regime"] = 1.0

        # 9. dist_to_ma5 (偏离5日线)
        if len(close_hist) >= 5:
            ma5 = close_hist.tail(5).mean()
            features["dist_to_ma5"] = round((close / ma5 - 1) * 100, 2)
        else:
            features["dist_to_ma5"] = 0

        return features

    def predict(self, features: dict) -> dict:
        """
        预测次日涨跌概率
        基于 Experiment 006 发现的规律简化实现
        """
        score = 0.5  # 基础分

        # 正向因子
        if features.get("morning_max_down", 0) < -2:
            score += 0.1
            if features.get("rebound_strength", 0.5) > 0.6:
                score += 0.15

        if features.get("rsi_oversold", 0) == 1:
            score += 0.1

        if features.get("gap_down_reversal", 0) == 1:
            score += 0.15
            if features.get("gap_reversal_strength", 0) > 0.5:
                score += 0.1

        if features.get("trend_divergence", 0) > 0:
            score += 0.05

        if features.get("vol_regime", 1) > 1.2:
            score += 0.05

        if features.get("dist_to_ma5", 0) > 0:
            score += 0.05

        # 负向因子
        if features.get("gap_up_trap", 0) == 1:
            score -= 0.2

        if features.get("morning_max_down", 0) > 0:
            score -= 0.05

        # 限制在 0-1 范围
        prob = max(0, min(1, score))

        # 生成信号说明
        signals = []
        if features.get("morning_max_down", 0) < -2:
            signals.append("深跌反弹")
        if features.get("rsi_oversold", 0) == 1:
            signals.append("RSI超卖")
        if features.get("gap_down_reversal", 0) == 1:
            signals.append("低开高走")
        if features.get("gap_up_trap", 0) == 1:
            signals.append("⚠️高开诱多")

        return {
            "probability": round(prob, 4),
            "confidence": "高" if prob > 0.6 else ("中" if prob > 0.45 else "低"),
            "recommendation": "推荐" if prob > 0.55 else ("谨慎" if prob > 0.4 else "避免"),
            "signals": signals,
            "features": features
        }

    def predict_batch(self, ts_codes: list, trade_date: str) -> pd.DataFrame:
        """批量预测"""
        results = []

        print(f"\n预测 {len(ts_codes)} 只股票 {trade_date} 的次日涨跌...")

        for i, code in enumerate(ts_codes):
            if (i + 1) % 10 == 0:
                print(f"  进度: {i+1}/{len(ts_codes)}")

            df = self.fetch_stock_data(code, trade_date)
            features = self.extract_features(df)

            if features is None:
                continue

            prediction = self.predict(features)
            prediction["ts_code"] = code
            prediction["trade_date"] = trade_date

            results.append(prediction)

        return pd.DataFrame(results)


def print_recommendations(df: pd.DataFrame, top_n: int = 10):
    """打印推荐结果"""

    print("\n" + "="*80)
    print("次日上涨预测结果")
    print("="*80)

    print(f"\n总股票数: {len(df)}")
    print(f"高置信度(>0.6): {len(df[df['probability'] > 0.6])} 只")
    print(f"中置信度(0.45-0.6): {len(df[(df['probability'] >= 0.45) & (df['probability'] <= 0.6)])} 只")
    print(f"低置信度(<0.45): {len(df[df['probability'] < 0.45])} 只")

    # Top 推荐
    print(f"\n{'='*80}")
    print(f"🏆 Top {top_n} 推荐 (按置信度排序)")
    print(f"{'='*80}")

    top = df.nlargest(top_n, 'probability')

    print(f"\n{'排名':<4} {'代码':<12} {'概率':<8} {'置信度':<6} {'推荐':<6} {'信号'}")
    print("-" * 80)

    for idx, (_, row) in enumerate(top.iterrows(), 1):
        signals_str = ", ".join(row['signals']) if row['signals'] else "无"
        print(f"{idx:<4} {row['ts_code']:<12} {row['probability']:<8.2f} {row['confidence']:<6} {row['recommendation']:<6} {signals_str}")

    # 需要避免的
    print(f"\n{'='*80}")
    print("⚠️  需要避免的股票 (低置信度)")
    print(f"{'='*80}")

    avoid = df.nsmallest(min(5, len(df)), 'probability')
    for _, row in avoid.iterrows():
        signals_str = ", ".join(row['signals']) if row['signals'] else "无"
        print(f"  {row['ts_code']}: {row['probability']:.2f} - {signals_str}")


def main():
    parser = argparse.ArgumentParser(description='次日上涨预测')
    parser.add_argument('--date', type=str, help='交易日期 (YYYYMMDD)')
    parser.add_argument('--pool', type=str, help='股票池代码，逗号分隔')
    parser.add_argument('--file', type=str, help='股票池文件路径 (Excel)')
    parser.add_argument('--output', type=str, default='output/predictions.csv', help='输出文件')
    args = parser.parse_args()

    predictor = NextDayPredictor()

    # 确定交易日期
    if args.date:
        trade_date = args.date
    else:
        # 使用最近交易日
        today = datetime.now()
        trade_date = today.strftime("%Y%m%d")

    print(f"="*80)
    print(f"次日上涨预测 - {trade_date}")
    print(f"="*80)

    # 确定股票池
    if args.pool:
        ts_codes = args.pool.split(",")
    elif args.file:
        df = pd.read_excel(args.file)
        ts_codes = df.iloc[0]["pool_data"].split(",")
    else:
        # 使用示例数据
        print("未指定股票池，使用示例数据")
        ts_codes = ["000001.SZ", "000002.SZ", "000858.SZ", "002594.SZ", "300750.SZ"]

    print(f"\n股票池: {len(ts_codes)} 只")

    # 批量预测
    results_df = predictor.predict_batch(ts_codes, trade_date)

    if len(results_df) == 0:
        print("无有效预测结果")
        return

    # 打印推荐
    print_recommendations(results_df)

    # 保存结果
    output_path = Path(args.output)
    output_path.parent.mkdir(exist_ok=True)

    # 展开特征列
    feature_df = pd.json_normalize(results_df['features'])
    final_df = pd.concat([
        results_df[['ts_code', 'trade_date', 'probability', 'confidence', 'recommendation']],
        feature_df
    ], axis=1)

    final_df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\n结果已保存: {output_path}")


if __name__ == "__main__":
    main()

"""
深度特征工程实验
基于 Experiment 005 的发现，设计更精细的特征

关键发现:
1. morning_max_down 是最强特征 (corr 0.067)
2. return_mean_20 分组差异最大 (15.71%)
3. RSI 负相关 - 超卖股票反而更好
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
import sys
sys.path.append(str(Path(__file__).parent))

from autoresearch import AutoResearch, DataLoader, FeatureEngineer, BacktestEngine

import tushare as ts
from config import pro


class AdvancedFeatureEngineer(FeatureEngineer):
    """高级特征工程 - 基于研究发现优化"""

    def extract_all_features(self, ts_code: str, pool_date: str) -> dict:
        """提取增强特征集"""
        # 基础特征
        features = super().extract_all_features(ts_code, pool_date)
        if features is None:
            return None

        # 获取更多历史数据用于计算高级特征
        stock_data = self.daily_df[
            (self.daily_df["ts_code"] == ts_code) &
            (self.daily_df["trade_date"] <= pool_date)
        ].copy().sort_values("trade_date")

        if len(stock_data) < 30:
            return features

        # 扩展特征
        hist = stock_data.iloc[:-1] if len(stock_data) > 1 else stock_data

        # 1. 基于 morning_max_down 发现的反转信号
        current = stock_data.iloc[-1]
        morning_max_down = features.get("morning_max_down", 0)

        # 深跌反弹信号: 日内大跌但收盘收回
        if morning_max_down < -2:  # 跌幅超过2%
            rebound_strength = (current["close"] - current["low"]) / (current["high"] - current["low"] + 1e-10)
            features["deep_rebound"] = 1 if rebound_strength > 0.6 else 0
            features["rebound_strength"] = round(rebound_strength, 4)
        else:
            features["deep_rebound"] = 0
            features["rebound_strength"] = 0.5

        # 2. 基于 RSI 发现的超卖信号
        rsi = features.get("rsi_6", 50)
        features["rsi_oversold"] = 1 if rsi < 30 else 0
        features["rsi_overbought"] = 1 if rsi > 70 else 0

        # 3. 趋势强度特征 (基于 return_mean_20 发现)
        close = hist["close"]
        pct_chg = hist["pct_chg"]

        if len(pct_chg) >= 20:
            # 短期 vs 中期趋势背离
            return_5 = pct_chg.tail(5).mean()
            return_20 = pct_chg.tail(20).mean()
            features["trend_divergence"] = round(return_5 - return_20, 4)

            # 趋势加速/减速
            if len(pct_chg) >= 10:
                return_10 = pct_chg.tail(10).mean()
                features["trend_accel"] = round(return_5 - return_10, 4)

        # 4. 波动率 regime 特征
        if len(pct_chg) >= 20:
            vol_5 = pct_chg.tail(5).std()
            vol_20 = pct_chg.tail(20).std()
            features["vol_regime"] = round(vol_5 / (vol_20 + 1e-10), 4)
            features["vol_contraction"] = 1 if vol_5 < vol_20 * 0.8 else 0

        # 5. 开盘模式精细化
        gap_pct = features.get("morning_gap_pct", 0)

        # 大幅低开高走 (最强反转模式)
        if gap_pct < -1.5 and current["close"] > current["open"]:
            features["gap_down_reversal"] = 1
            features["gap_reversal_strength"] = round((current["close"] - current["open"]) / abs(gap_pct), 4)
        else:
            features["gap_down_reversal"] = 0
            features["gap_reversal_strength"] = 0

        # 大幅高开低走 (诱多陷阱)
        if gap_pct > 2 and current["close"] < current["open"]:
            features["gap_up_trap"] = 1
        else:
            features["gap_up_trap"] = 0

        # 6. 价格位置精细化
        if len(close) >= 20:
            # 是否创20日新低
            features["new_20d_low"] = 1 if current["close"] <= close.tail(20).min() * 1.01 else 0
            # 是否从低点反弹
            low_20 = close.tail(20).min()
            features["bounce_from_low"] = round((current["close"] / low_20 - 1) * 100, 2)

        # 7. 量能特征
        vol = hist["vol"]
        if len(vol) >= 6:
            vol_1 = vol.iloc[-1]
            vol_5 = vol.tail(5).mean()
            vol_20 = vol.tail(20).mean()

            features["vol_vs_5d"] = round(vol_1 / (vol_5 + 1e-10), 4)
            features["vol_vs_20d"] = round(vol_1 / (vol_20 + 1e-10), 4)

            # 放量上涨/缩量下跌 是好信号
            price_change = current["pct_chg"]
            features["vol_price_divergence"] = 1 if (price_change > 0 and vol_1 > vol_5) or (price_change < 0 and vol_1 < vol_5) else 0

        return features


def run_experiment_006():
    """
    Experiment 006: 基于发现的精细化特征
    假设: 深跌反弹 + 超卖 + 趋势背离 的组合能有效预测次日上涨
    """
    print("\n" + "="*80)
    print("Experiment 006: 精细化反转特征")
    print("="*80)

    # 加载数据
    data_loader = DataLoader()
    excel_path = Path(__file__).parent.parent / "assets" / "池子_20251104.xlsx"
    pool_df = data_loader.load_stock_pool(str(excel_path))

    min_date = pool_df["pool_date"].min().strftime("%Y%m%d")
    max_date = (pool_df["pool_date"].max() + timedelta(days=30)).strftime("%Y%m%d")

    backtest = BacktestEngine(data_loader)
    trading_days = backtest.get_trading_days(min_date, max_date)

    all_stocks = list(set().union(*pool_df["stock_list"]))
    start_fetch = (datetime.strptime(min_date, "%Y%m%d") - timedelta(days=60)).strftime("%Y%m%d")

    print(f"获取日线数据 ({len(all_stocks)} 只股票)...")
    daily_df = data_loader.fetch_daily_data(all_stocks, start_fetch, max_date)
    data_loader.daily_data = daily_df

    # 使用高级特征工程
    feature_engineer = AdvancedFeatureEngineer(daily_df)

    print("\n运行回测...")
    result_df = backtest.run_backtest(feature_engineer, pool_df, trading_days)

    print(f"总样本数: {len(result_df)}")
    print(f"次日上涨率: {result_df['next_up'].mean()*100:.1f}%")

    # 评估新特征
    new_features = [
        "deep_rebound", "rebound_strength", "rsi_oversold", "rsi_overbought",
        "trend_divergence", "trend_accel", "vol_regime", "vol_contraction",
        "gap_down_reversal", "gap_reversal_strength", "gap_up_trap",
        "new_20d_low", "bounce_from_low", "vol_vs_5d", "vol_vs_20d"
    ]

    print("\n" + "="*80)
    print("新特征评估")
    print("="*80)

    results = []
    for feat in new_features:
        if feat in result_df.columns:
            eval_result = backtest.evaluate_feature(result_df, feat)
            if 'error' not in eval_result:
                results.append({
                    'feature': feat,
                    'corr': eval_result.get('correlation', 0),
                    'abs_corr': eval_result.get('abs_correlation', 0),
                    'quintile_diff': eval_result.get('quintile_diff_up_rate', 0)
                })
                print(f"{feat:25s} | 相关: {eval_result.get('correlation', 0):7.4f} | 分组差: {eval_result.get('quintile_diff_up_rate', 0):7.4f}")

    # 排序并展示最佳特征
    results_df = pd.DataFrame(results).sort_values('abs_corr', ascending=False)
    print("\n最佳新特征 (按相关性):")
    print(results_df.head(10).to_string(index=False))

    # 保存结果
    output_dir = Path(__file__).parent.parent / "output"
    output_dir.mkdir(exist_ok=True)
    result_df.to_csv(output_dir / "experiment_006_advanced_features.csv", index=False, encoding="utf-8-sig")

    return result_df, results_df


def analyze_strategy_combinations(result_df: pd.DataFrame):
    """
    分析不同策略组合的效果
    """
    print("\n" + "="*80)
    print("策略组合分析")
    print("="*80)

    strategies = []

    # 策略 1: 深跌反弹
    s1 = result_df[result_df["deep_rebound"] == 1]
    if len(s1) > 10:
        strategies.append({
            "name": "深跌反弹",
            "count": len(s1),
            "up_rate": s1["next_up"].mean(),
            "avg_return": s1["next_pct_chg"].mean()
        })

    # 策略 2: RSI超卖
    s2 = result_df[result_df["rsi_oversold"] == 1]
    if len(s2) > 10:
        strategies.append({
            "name": "RSI超卖",
            "count": len(s2),
            "up_rate": s2["next_up"].mean(),
            "avg_return": s2["next_pct_chg"].mean()
        })

    # 策略 3: 大幅低开反转
    s3 = result_df[result_df["gap_down_reversal"] == 1]
    if len(s3) > 10:
        strategies.append({
            "name": "低开高走",
            "count": len(s3),
            "up_rate": s3["next_up"].mean(),
            "avg_return": s3["next_pct_chg"].mean()
        })

    # 策略 4: 避免诱多
    s4 = result_df[result_df["gap_up_trap"] == 1]
    if len(s4) > 10:
        strategies.append({
            "name": "高开低走(应避免)",
            "count": len(s4),
            "up_rate": s4["next_up"].mean(),
            "avg_return": s4["next_pct_chg"].mean()
        })

    # 策略 5: 组合策略 - 深跌反弹 + 超卖
    s5 = result_df[(result_df["deep_rebound"] == 1) & (result_df["rsi_oversold"] == 1)]
    if len(s5) > 5:
        strategies.append({
            "name": "深跌反弹+RSI超卖",
            "count": len(s5),
            "up_rate": s5["next_up"].mean(),
            "avg_return": s5["next_pct_chg"].mean()
        })

    # 策略 6: 组合策略 - 低开反转 + 超卖
    s6 = result_df[(result_df["gap_down_reversal"] == 1) & (result_df["rsi_oversold"] == 1)]
    if len(s6) > 5:
        strategies.append({
            "name": "低开反转+RSI超卖",
            "count": len(s6),
            "up_rate": s6["next_up"].mean(),
            "avg_return": s6["next_pct_chg"].mean()
        })

    # 基准
    baseline_up_rate = result_df["next_up"].mean()
    baseline_return = result_df["next_pct_chg"].mean()

    print(f"\n{'策略':<25} {'样本数':<8} {'上涨率':<10} {'平均收益':<10} {'vs基准':<10}")
    print("-" * 70)
    print(f"{'基准(全样本)':<25} {len(result_df):<8} {baseline_up_rate*100:<10.1f} {baseline_return:<10.2f} {'-':<10}")

    for s in strategies:
        vs_baseline = (s["up_rate"] - baseline_up_rate) * 100
        print(f"{s['name']:<25} {s['count']:<8} {s['up_rate']*100:<10.1f} {s['avg_return']:<10.2f} {vs_baseline:+.1f}%")

    # 找出最佳策略
    best = max(strategies, key=lambda x: x["up_rate"]) if strategies else None
    if best:
        print(f"\n🏆 最佳策略: {best['name']}")
        print(f"   上涨率: {best['up_rate']*100:.1f}% (vs 基准 {baseline_up_rate*100:.1f}%)")
        print(f"   平均收益: {best['avg_return']:+.2f}%")

    return strategies


def train_optimized_model(result_df: pd.DataFrame):
    """
    使用最优特征训练模型
    """
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import roc_auc_score, classification_report

    print("\n" + "="*80)
    print("优化模型训练")
    print("="*80)

    # 选择最优特征
    selected_features = [
        "morning_max_down", "rebound_strength", "rsi_oversold",
        "gap_down_reversal", "gap_reversal_strength", "gap_up_trap",
        "trend_divergence", "vol_regime", "dist_to_ma5"
    ]

    available_features = [f for f in selected_features if f in result_df.columns]

    X = result_df[available_features].fillna(0)
    y = result_df["next_up"]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.3, random_state=42)

    # 训练 GBDT
    model = GradientBoostingClassifier(n_estimators=100, max_depth=4, learning_rate=0.1, random_state=42)
    model.fit(X_train, y_train)

    # 评估
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    auc = roc_auc_score(y_test, y_prob)
    accuracy = (y_pred == y_test).mean()

    print(f"\n模型性能:")
    print(f"  AUC: {auc:.4f}")
    print(f"  准确率: {accuracy:.4f}")

    # 特征重要性
    importance = pd.DataFrame({
        'feature': available_features,
        'importance': model.feature_importances_
    }).sort_values('importance', ascending=False)

    print(f"\n特征重要性:")
    print(importance.to_string(index=False))

    # 输出预测概率分布
    result_df['predict_prob'] = model.predict_proba(X)[:, 1]

    high_conf = result_df[result_df['predict_prob'] > 0.6]
    print(f"\n高置信度预测 (prob > 0.6): {len(high_conf)} 只")
    if len(high_conf) > 0:
        print(f"  实际上涨率: {high_conf['next_up'].mean()*100:.1f}%")
        print(f"  平均收益: {high_conf['next_pct_chg'].mean():+.2f}%")

    return model, importance


def main():
    """主入口"""
    # 运行 Experiment 006
    result_df, feature_ranking = run_experiment_006()

    if result_df is not None and len(result_df) > 0:
        # 分析策略组合
        strategies = analyze_strategy_combinations(result_df)

        # 训练优化模型
        model, importance = train_optimized_model(result_df)

        # 生成最终报告
        print("\n" + "="*80)
        print("Experiment 006 总结")
        print("="*80)
        print(f"样本数: {len(result_df)}")
        print(f"基准上涨率: {result_df['next_up'].mean()*100:.1f}%")
        print(f"\n最佳新特征:")
        for _, row in feature_ranking.head(5).iterrows():
            print(f"  {row['feature']}: 相关 {row['corr']:.4f}, 分组差 {row['quintile_diff']:.4f}")


if __name__ == "__main__":
    main()

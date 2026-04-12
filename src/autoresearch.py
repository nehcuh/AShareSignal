"""
AutoResearch Engine for AShareSignal
基于 autoresearch 方法论的自动化股票预测研究

核心循环:
1. 提出假设 (Hypothesis)
2. 设计实验 (Experiment)
3. 快速验证 (Validate)
4. 记录结果 (Log)
5. 迭代优化 (Iterate)
"""

import tushare as ts
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json
import warnings
warnings.filterwarnings('ignore')

TUSHARE_TOKEN = "fd6cf8fc8404cf6f93ca6091c1e603d9bc3a65f5a536c77dbb882e60"
ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()


class ExperimentStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class Experiment:
    """实验记录"""
    id: str
    name: str
    hypothesis: str  # 假设
    features: List[str]  # 使用的特征
    status: ExperimentStatus = ExperimentStatus.PENDING
    result: Dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    notes: str = ""


class ResearchLogger:
    """研究日志记录器"""

    def __init__(self, log_file: str = "research_log.md"):
        self.log_file = Path(log_file)
        self.experiments: List[Experiment] = []

    def log_experiment(self, exp: Experiment):
        """记录实验到 markdown"""
        self.experiments.append(exp)

        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(f"\n### Experiment {exp.id}: {exp.name}\n")
            f.write(f"**时间**: {exp.timestamp}\n\n")
            f.write(f"**假设**: {exp.hypothesis}\n\n")
            f.write(f"**特征**: {', '.join(exp.features)}\n\n")
            f.write(f"**状态**: {exp.status.value}\n\n")

            if exp.result:
                f.write(f"**结果**:\n")
                for key, value in exp.result.items():
                    f.write(f"- {key}: {value}\n")
                f.write(f"\n")

            if exp.notes:
                f.write(f"**结论**: {exp.notes}\n\n")

            f.write("---\n")

        print(f"✅ 实验 {exp.id} 已记录")


class DataLoader:
    """数据加载器 - 缓存机制避免重复请求"""

    def __init__(self):
        self._cache = {}
        self.stock_pool = None
        self.daily_data = None
        self.moneyflow_data = None
        self.limit_list_data = None

    def load_stock_pool(self, excel_path: str) -> pd.DataFrame:
        """加载股票池"""
        if self.stock_pool is not None:
            return self.stock_pool

        df = pd.read_excel(excel_path)
        df["pool_date"] = pd.to_datetime(df["pool_date"])
        df["stock_list"] = df["pool_data"].str.split(",")
        self.stock_pool = df
        return df

    def fetch_daily_data(self, ts_codes: List[str], start_date: str, end_date: str) -> pd.DataFrame:
        """获取日线数据"""
        cache_key = f"daily_{start_date}_{end_date}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        all_data = []
        for i in range(0, len(ts_codes), 100):
            batch = ts_codes[i:i+100]
            try:
                df = pro.daily(ts_code=",".join(batch), start_date=start_date, end_date=end_date)
                if df is not None and len(df) > 0:
                    all_data.append(df)
            except Exception as e:
                print(f"  获取数据失败: {e}")

        if not all_data:
            return pd.DataFrame()

        result = pd.concat(all_data, ignore_index=True)
        self._cache[cache_key] = result
        return result

    def fetch_moneyflow(self, ts_codes: List[str], trade_date: str) -> pd.DataFrame:
        """获取资金流向数据"""
        cache_key = f"moneyflow_{trade_date}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        all_data = []
        for i in range(0, len(ts_codes), 100):
            batch = ts_codes[i:i+100]
            try:
                df = pro.moneyflow(ts_code=",".join(batch), trade_date=trade_date)
                if df is not None and len(df) > 0:
                    all_data.append(df)
            except Exception as e:
                print(f"  获取资金流向失败: {e}")

        if not all_data:
            return pd.DataFrame()

        result = pd.concat(all_data, ignore_index=True)
        self._cache[cache_key] = result
        return result

    def fetch_limit_list(self, trade_date: str) -> pd.DataFrame:
        """获取涨跌停数据"""
        cache_key = f"limit_{trade_date}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            df = pro.limit_list(trade_date=trade_date)
            self._cache[cache_key] = df
            return df
        except Exception as e:
            print(f"  获取涨跌停数据失败: {e}")
            return pd.DataFrame()


class FeatureEngineer:
    """特征工程 - 系统化特征生成"""

    def __init__(self, daily_df: pd.DataFrame):
        self.daily_df = daily_df

    def extract_all_features(self, ts_code: str, pool_date: str) -> Optional[Dict]:
        """提取某只股票在某日的全部特征"""
        # 获取该股票的历史数据
        stock_data = self.daily_df[
            (self.daily_df["ts_code"] == ts_code) &
            (self.daily_df["trade_date"] <= pool_date)
        ].copy().sort_values("trade_date")

        if len(stock_data) < 20:
            return None

        features = {"ts_code": ts_code, "pool_date": pool_date}

        # 基础特征
        current = stock_data.iloc[-1]
        features.update(self._extract_price_features(current))

        # 历史统计特征
        hist = stock_data.iloc[:-1] if len(stock_data) > 1 else stock_data
        features.update(self._extract_hist_features(hist))

        # 技术指标
        features.update(self._extract_technical_features(hist))

        # 上午模式特征（用日线模拟）
        features.update(self._extract_morning_features(current))

        return features

    def _extract_price_features(self, current: pd.Series) -> Dict:
        """基础价格特征"""
        return {
            "close": current["close"],
            "open": current["open"],
            "high": current["high"],
            "low": current["low"],
            "pre_close": current["pre_close"],
            "pct_chg": current["pct_chg"],
            "vol": current["vol"],
            "amount": current.get("amount", 0),
        }

    def _extract_hist_features(self, hist: pd.DataFrame) -> Dict:
        """历史统计特征"""
        close = hist["close"]
        pct_chg = hist["pct_chg"]
        vol = hist["vol"]

        features = {}

        # 收益率统计
        if len(pct_chg) >= 5:
            features["return_mean_5"] = round(pct_chg.tail(5).mean(), 4)
            features["return_std_5"] = round(pct_chg.tail(5).std(), 4)
            features["up_days_5"] = int((pct_chg.tail(5) > 0).sum())

        if len(pct_chg) >= 20:
            features["return_mean_20"] = round(pct_chg.tail(20).mean(), 4)
            features["return_std_20"] = round(pct_chg.tail(20).std(), 4)
            features["up_days_20"] = int((pct_chg.tail(20) > 0).sum())

        # 价格位置
        if len(close) >= 20:
            high_20 = close.tail(20).max()
            low_20 = close.tail(20).min()
            features["price_pos_20"] = round(
                (close.iloc[-1] - low_20) / (high_20 - low_20 + 1e-10), 4
            )

        # 均线位置
        if len(close) >= 5:
            ma5 = close.tail(5).mean()
            features["dist_to_ma5"] = round((close.iloc[-1] / ma5 - 1) * 100, 2)

        if len(close) >= 10:
            ma10 = close.tail(10).mean()
            features["dist_to_ma10"] = round((close.iloc[-1] / ma10 - 1) * 100, 2)
            features["ma5_above_ma10"] = 1 if close.tail(5).mean() > ma10 else 0

        if len(close) >= 20:
            ma20 = close.tail(20).mean()
            features["dist_to_ma20"] = round((close.iloc[-1] / ma20 - 1) * 100, 2)

        # 量比
        if len(vol) >= 6:
            features["volume_ratio"] = round(vol.iloc[-1] / vol.tail(6).iloc[:-1].mean(), 2)

        return features

    def _extract_technical_features(self, hist: pd.DataFrame) -> Dict:
        """技术指标特征"""
        close = hist["close"]
        high = hist["high"]
        low = hist["low"]

        features = {}

        # RSI
        if len(close) >= 7:
            delta = close.diff()
            gain = delta.where(delta > 0, 0).rolling(6).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(6).mean()
            rs = gain / loss.replace(0, np.inf)
            rsi = (100 - (100 / (1 + rs))).iloc[-1]
            features["rsi_6"] = round(rsi, 2) if not pd.isna(rsi) else 50

        # KDJ
        if len(close) >= 9:
            low_9 = low.tail(9).min()
            high_9 = high.tail(9).max()
            rsv = (close.iloc[-1] - low_9) / (high_9 - low_9 + 1e-10) * 100
            features["kdj_j"] = round(rsv, 2)

        return features

    def _extract_morning_features(self, current: pd.Series) -> Dict:
        """上午模式特征（用日线模拟）"""
        open_p = current["open"]
        close_p = current["close"]
        high_p = current["high"]
        low_p = current["low"]
        pre_close = current["pre_close"]

        features = {
            "morning_gap_pct": round((open_p - pre_close) / pre_close * 100, 2),
            "morning_return": round((close_p - pre_close) / pre_close * 100, 2),
            "morning_max_up": round((high_p - open_p) / open_p * 100, 2),
            "morning_max_down": round((low_p - open_p) / open_p * 100, 2),
            "morning_range": round((high_p - low_p) / open_p * 100, 2),
            "intraday_trend": 1 if close_p > open_p else (-1 if close_p < open_p else 0),
        }

        return features


class BacktestEngine:
    """回测引擎 - 快速验证特征有效性"""

    def __init__(self, data_loader: DataLoader):
        self.data_loader = data_loader

    def get_trading_days(self, start_date: str, end_date: str) -> List[str]:
        """获取交易日列表"""
        try:
            cal = pro.trade_cal(exchange="SSE", start_date=start_date, end_date=end_date)
            if cal is None or len(cal) == 0:
                print(f"  警告: 无法获取交易日历 {start_date} ~ {end_date}")
                return []
            if "is_open" not in cal.columns:
                print(f"  警告: 交易日历数据格式异常, 列名: {cal.columns.tolist()}")
                return cal["cal_date"].tolist() if "cal_date" in cal.columns else []
            return sorted(cal[cal["is_open"] == 1]["cal_date"].tolist())
        except Exception as e:
            print(f"  获取交易日历失败: {e}")
            return []

    def run_backtest(
        self,
        feature_engineer: FeatureEngineer,
        pool_df: pd.DataFrame,
        trading_days: List[str]
    ) -> pd.DataFrame:
        """运行回测，返回带特征和次日涨跌的数据集"""

        all_samples = []

        for idx, row in pool_df.iterrows():
            pool_date = row["pool_date"].strftime("%Y%m%d")
            ts_codes = row["stock_list"]

            # 找到下一个交易日
            next_date = None
            for d in trading_days:
                if d > pool_date:
                    next_date = d
                    break

            if next_date is None:
                continue

            # 获取次日涨跌数据
            next_data = self.data_loader.daily_data[
                self.data_loader.daily_data["trade_date"] == next_date
            ]

            for code in ts_codes:
                # 提取特征
                features = feature_engineer.extract_all_features(code, pool_date)
                if features is None:
                    continue

                # 匹配次日涨跌
                next_row = next_data[next_data["ts_code"] == code]
                if len(next_row) == 0:
                    continue

                next_pct = next_row.iloc[0]["pct_chg"]
                features["next_date"] = next_date
                features["next_pct_chg"] = round(next_pct, 4)
                features["next_up"] = 1 if next_pct > 0 else 0

                all_samples.append(features)

        return pd.DataFrame(all_samples)

    def evaluate_feature(self, df: pd.DataFrame, feature: str) -> Dict:
        """评估单个特征对次日涨跌的预测能力"""

        if feature not in df.columns or df[feature].isna().all():
            return {"error": f"Feature {feature} not available"}

        # 计算与次日涨跌的相关性
        corr = df[feature].corr(df["next_pct_chg"])

        # 分组分析
        try:
            df['quintile'] = pd.qcut(df[feature], q=5, labels=['Q1', 'Q2', 'Q3', 'Q4', 'Q5'], duplicates='drop')

            quintile_stats = []
            for q in ['Q1', 'Q2', 'Q3', 'Q4', 'Q5']:
                subset = df[df['quintile'] == q]
                if len(subset) > 0:
                    quintile_stats.append({
                        'quintile': q,
                        'count': len(subset),
                        'up_rate': subset['next_up'].mean(),
                        'avg_return': subset['next_pct_chg'].mean(),
                        'feature_mean': subset[feature].mean()
                    })

            # 计算区分度 (Q5 vs Q1)
            if len(quintile_stats) >= 2:
                diff_up_rate = quintile_stats[-1]['up_rate'] - quintile_stats[0]['up_rate']
                diff_return = quintile_stats[-1]['avg_return'] - quintile_stats[0]['avg_return']
            else:
                diff_up_rate = 0
                diff_return = 0

            return {
                "correlation": round(corr, 4),
                "abs_correlation": round(abs(corr), 4),
                "quintile_diff_up_rate": round(diff_up_rate, 4),
                "quintile_diff_return": round(diff_return, 4),
                "quintile_stats": quintile_stats
            }

        except Exception as e:
            return {
                "correlation": round(corr, 4),
                "error": str(e)
            }


class AutoResearch:
    """自动研究主引擎"""

    def __init__(self):
        self.logger = ResearchLogger()
        self.data_loader = DataLoader()
        self.backtest = BacktestEngine(self.data_loader)

    def initialize_data(self):
        """初始化数据加载"""
        print("="*80)
        print("初始化数据...")
        print("="*80)

        # 加载股票池
        excel_path = Path(__file__).parent.parent / "assets" / "池子_20251104.xlsx"
        pool_df = self.data_loader.load_stock_pool(str(excel_path))
        print(f"股票池: {len(pool_df)} 个交易日, {len(set().union(*pool_df['stock_list']))} 只股票")

        # 获取交易日历
        min_date = pool_df["pool_date"].min().strftime("%Y%m%d")
        max_date = (pool_df["pool_date"].max() + timedelta(days=30)).strftime("%Y%m%d")
        trading_days = self.backtest.get_trading_days(min_date, max_date)

        # 获取日线数据
        all_stocks = list(set().union(*pool_df["stock_list"]))
        start_fetch = (datetime.strptime(min_date, "%Y%m%d") - timedelta(days=60)).strftime("%Y%m%d")

        print(f"\n获取日线数据 ({len(all_stocks)} 只股票)...")
        daily_df = self.data_loader.fetch_daily_data(all_stocks, start_fetch, max_date)
        self.data_loader.daily_data = daily_df
        print(f"获取到 {len(daily_df)} 条日线记录")

        return pool_df, trading_days

    def run_experiment(self, exp_id: str, name: str, hypothesis: str, features: List[str]):
        """运行单个实验"""
        print(f"\n{'='*80}")
        print(f"Experiment {exp_id}: {name}")
        print(f"{'='*80}")

        exp = Experiment(
            id=exp_id,
            name=name,
            hypothesis=hypothesis,
            features=features
        )
        exp.status = ExperimentStatus.RUNNING

        # 初始化数据
        pool_df, trading_days = self.initialize_data()

        # 创建特征工程器
        feature_engineer = FeatureEngineer(self.data_loader.daily_data)

        # 运行回测
        print(f"\n运行回测...")
        result_df = self.backtest.run_backtest(feature_engineer, pool_df, trading_days)

        if len(result_df) == 0:
            exp.status = ExperimentStatus.FAILED
            exp.notes = "无有效样本"
            self.logger.log_experiment(exp)
            return None

        print(f"总样本数: {len(result_df)}")
        print(f"次日上涨率: {result_df['next_up'].mean()*100:.1f}%")

        # 评估每个特征
        feature_results = {}
        for feat in features:
            if feat in result_df.columns:
                eval_result = self.backtest.evaluate_feature(result_df, feat)
                feature_results[feat] = eval_result
                print(f"\n{feat}:")
                print(f"  相关性: {eval_result.get('correlation', 'N/A')}")
                print(f"  五分组差异(上涨率): {eval_result.get('quintile_diff_up_rate', 'N/A')}")

        exp.result = {
            "total_samples": len(result_df),
            "up_rate": round(result_df["next_up"].mean(), 4),
            "feature_results": feature_results
        }

        exp.status = ExperimentStatus.SUCCESS
        self.logger.log_experiment(exp)

        return result_df

    def systematic_feature_scan(self, result_df: pd.DataFrame):
        """系统化扫描所有特征"""
        print(f"\n{'='*80}")
        print("系统化特征扫描")
        print(f"{'='*80}")

        # 自动发现所有数值特征
        numeric_cols = result_df.select_dtypes(include=[np.number]).columns.tolist()
        exclude_cols = ['next_pct_chg', 'next_up', 'close', 'open', 'high', 'low', 'vol', 'amount', 'pre_close']
        feature_cols = [c for c in numeric_cols if c not in exclude_cols]

        print(f"扫描 {len(feature_cols)} 个特征...")

        results = []
        for feat in feature_cols:
            eval_result = self.backtest.evaluate_feature(result_df, feat)
            if 'error' not in eval_result:
                results.append({
                    'feature': feat,
                    'abs_corr': eval_result.get('abs_correlation', 0),
                    'quintile_diff': abs(eval_result.get('quintile_diff_up_rate', 0))
                })

        # 排序输出
        results_df = pd.DataFrame(results).sort_values('abs_corr', ascending=False)

        print("\n特征排名（按相关性）:")
        print(results_df.head(20).to_string(index=False))

        return results_df


def main():
    """主入口"""
    research = AutoResearch()

    # 运行实验 005: 全面特征扫描
    print("\n" + "="*80)
    print("AutoResearch Engine Starting")
    print("="*80)

    # 先运行一个基础实验获取完整数据集
    result_df = research.run_experiment(
        exp_id="005",
        name="全面特征集测试",
        hypothesis="系统化提取的所有特征可以有效预测次日涨跌",
        features=["price_pos_20", "dist_to_ma5", "rsi_6", "kdj_j", "morning_gap_pct", "volume_ratio"]
    )

    if result_df is not None:
        # 系统化扫描
        feature_ranking = research.systematic_feature_scan(result_df)

        # 保存数据集供后续使用
        output_dir = Path(__file__).parent.parent / "output"
        output_dir.mkdir(exist_ok=True)
        result_df.to_csv(output_dir / "autoresearch_dataset.csv", index=False, encoding="utf-8-sig")
        print(f"\n数据集已保存: output/autoresearch_dataset.csv")


if __name__ == "__main__":
    main()

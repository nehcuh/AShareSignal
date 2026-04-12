"""
AutoResearch: 下午买入时机 & 次日卖出时机研究

方法论: autoresearch (假设 → 实验 → 验证 → 记录 → 迭代)

数据来源: pytdx 全天5分钟K线
研究对象: 3/26 和 3/27 两日筛选出的 A/B 级股票
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, time, timedelta
from typing import List, Dict, Optional, Tuple
import sys
import json

sys.path.append(str(Path(__file__).parent))
from pytdx_minute import PytdxMinuteManager, PERIOD_MAP

OUTPUT_DIR = Path(__file__).parent.parent / "output"
CACHE_DIR = Path(__file__).parent.parent / "data" / "pytdx_timing_cache"


# ===========================================================================
# 数据层: 全天分钟数据下载
# ===========================================================================

class FullDayMinuteDownloader:
    """下载全天5分钟K线数据（上午+下午）"""

    def __init__(self):
        self.manager = PytdxMinuteManager(
            cache_dir=str(CACHE_DIR / "fullday")
        )

    def download_fullday(
        self, ts_code: str, trade_date: str, freq: str = "5"
    ) -> Optional[pd.DataFrame]:
        """下载全天5分钟数据，返回上午和下午两个session"""
        cache_path = CACHE_DIR / "fullday" / f"{ts_code.replace('.','_')}_{trade_date}_{freq}min.pkl"
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        if cache_path.exists():
            import pickle
            with open(cache_path, 'rb') as f:
                return pickle.load(f)

        # 连接并下载数据
        if not self.manager.connect():
            return None

        try:
            market, code = self.manager._ts_code_to_pytdx(ts_code)
            period = PERIOD_MAP.get(freq, 0)

            data = self.manager.api.get_security_bars(period, market, code, 0, 800)
            if not data:
                return None

            df = self.manager.api.to_df(data)
            df['datetime'] = pd.to_datetime(df['datetime'])
            df['date'] = df['datetime'].dt.strftime('%Y%m%d')
            df['time'] = df['datetime'].dt.time

            # 筛选目标日期
            day_df = df[df['date'] == trade_date].copy()
            if len(day_df) == 0:
                return None

            # 保存缓存
            import pickle
            with open(cache_path, 'wb') as f:
                pickle.dump(day_df, f)

            return day_df
        except Exception as e:
            print(f"  下载失败 {ts_code}: {e}")
            return None

    def split_sessions(self, df: pd.DataFrame) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
        """将全天数据拆分为上午和下午"""
        if df is None or len(df) == 0:
            return None, None

        morning = df[(df['time'] >= time(9, 30)) & (df['time'] <= time(11, 30))].copy()
        afternoon = df[(df['time'] >= time(13, 0)) & (df['time'] <= time(15, 0))].copy()

        return morning, afternoon


# ===========================================================================
# 分析层: 下午买入时机
# ===========================================================================

class AfternoonBuyAnalyzer:
    """分析下午最佳买入时机"""

    def analyze_stock(
        self, ts_code: str, name: str,
        afternoon_df: pd.DataFrame,
        morning_close: float,
        morning_return: float,
        score: int
    ) -> Optional[Dict]:
        """
        分析单只股票下午买入时机

        对比几个关键买入时间点:
        - 13:00 开盘直接买
        - 13:15 开盘后观察
        - 13:30 确认方向后
        - 13:45 下午趋势明确
        - 14:00 尾盘策略
        - 14:30 最后小时
        - 全天最低点 (理想参考)
        """
        if afternoon_df is None or len(afternoon_df) < 3:
            return None

        af = afternoon_df.sort_values('time').reset_index(drop=True)
        first_close = af.iloc[0]['close']  # 下午开盘价

        # 全天参考: 下午最低价和最高价
        af_low = af['low'].min()
        af_high = af['high'].max()
        af_close = af.iloc[-1]['close']  # 收盘价

        # 计算不同买入点的收益 (买入价 vs 收盘价)
        buy_points = {}

        # 13:00 买入
        buy_points['13:00'] = {
            'price': first_close,
            'return_vs_close': round((af_close - first_close) / first_close * 100, 4),
            'return_vs_morning': round((af_close - morning_close) / morning_close * 100, 4),
        }

        # 后续时间点
        time_targets = ['13:15', '13:30', '13:45', '14:00', '14:30']
        for t in time_targets:
            h, m = map(int, t.split(':'))
            target = time(h, m)
            # 找到包含该时间的K线
            mask = af['time'] <= target
            if mask.any():
                idx = mask[mask].index[-1]
                price = af.loc[idx, 'close']
                buy_points[t] = {
                    'price': price,
                    'return_vs_close': round((af_close - price) / price * 100, 4),
                }

        # 下午最低点 (理想情况)
        low_idx = af['low'].idxmin()
        low_price = af.loc[low_idx, 'low']
        low_time = af.loc[low_idx, 'time']
        buy_points['ideal_low'] = {
            'price': low_price,
            'return_vs_close': round((af_close - low_price) / low_price * 100, 4),
            'time': str(low_time),
        }

        # 下午走势特征
        afternoon_return = round((af_close - first_close) / first_close * 100, 4)
        afternoon_range = round((af_high - af_low) / first_close * 100, 4)

        # 下午开盘后30分钟趋势 (决定性方向)
        if len(af) >= 6:
            first_30min_close = af.iloc[5]['close']
            first_30min_return = round((first_30min_close - first_close) / first_close * 100, 4)
        else:
            first_30min_return = 0

        # 下午收盘前30分钟趋势
        if len(af) >= 6:
            last_30min_open = af.iloc[-6]['open']
            last_30min_return = round((af_close - last_30min_open) / last_30min_open * 100, 4)
        else:
            last_30min_return = 0

        return {
            'ts_code': ts_code,
            'name': name,
            'score': score,
            'morning_return': morning_return,
            'morning_close': morning_close,
            'afternoon_return': afternoon_return,
            'afternoon_range': afternoon_range,
            'afternoon_close': af_close,
            'afternoon_low': af_low,
            'afternoon_high': af_high,
            'first_30min_return': first_30min_return,
            'last_30min_return': last_30min_return,
            'buy_points': buy_points,
        }

    def aggregate_results(self, results: List[Dict]) -> pd.DataFrame:
        """汇总所有股票的买入时机分析"""
        rows = []
        for r in results:
            if r is None:
                continue
            row = {
                'ts_code': r['ts_code'],
                'name': r['name'],
                'score': r['score'],
                'morning_return': r['morning_return'],
                'afternoon_return': r['afternoon_return'],
                'afternoon_range': r['afternoon_range'],
            }
            # 展开买入点收益
            for bp_name, bp_data in r['buy_points'].items():
                if 'return_vs_close' in bp_data:
                    row[f'buy_{bp_name}_ret'] = bp_data['return_vs_close']
            rows.append(row)
        return pd.DataFrame(rows)


# ===========================================================================
# 分析层: 次日卖出时机
# ===========================================================================

class NextDaySellAnalyzer:
    """分析次日最佳卖出时机"""

    def analyze_stock(
        self, ts_code: str, name: str,
        buy_price: float,
        next_day_df: pd.DataFrame,
        score: int
    ) -> Optional[Dict]:
        """
        分析次日最佳卖出时机

        对比几个关键卖出时间点:
        - 09:30 开盘卖出
        - 09:45 开盘后观察
        - 10:00 上午走势确认
        - 10:30 半小时
        - 11:00 上午中段
        - 11:30 上午收盘
        - 全天最高点 (理想参考)
        """
        if next_day_df is None or len(next_day_df) == 0:
            return None

        df = next_day_df.sort_values('time').reset_index(drop=True)

        # 只看上午session (我们主要关注上午卖出)
        morning = df[(df['time'] >= time(9, 30)) & (df['time'] <= time(11, 30))].copy()
        if len(morning) < 3:
            morning = df.head(min(12, len(df)))

        if len(morning) == 0:
            return None

        open_price = morning.iloc[0]['open']
        high = morning['high'].max()
        low = morning['low'].min()
        close_1130 = morning.iloc[-1]['close']

        # 全天数据
        full_high = df['high'].max()
        full_low = df['low'].min()
        full_close = df.iloc[-1]['close']

        # 计算不同卖出点相对买入价的收益
        sell_points = {}

        # 上午各时间点
        time_targets = [
            ('09:30', time(9, 30)),
            ('09:45', time(9, 45)),
            ('10:00', time(10, 0)),
            ('10:30', time(10, 30)),
            ('11:00', time(11, 0)),
            ('11:30', time(11, 30)),
        ]

        for label, target_time in time_targets:
            mask = morning['time'] <= target_time
            if mask.any():
                idx = mask[mask].index[-1]
                price = morning.loc[idx, 'close']
                sell_points[label] = {
                    'price': price,
                    'return': round((price - buy_price) / buy_price * 100, 4),
                }

        # 全天最高点 (理想)
        high_idx = df['high'].idxmax()
        ideal_high = df.loc[high_idx, 'high']
        ideal_high_time = df.loc[high_idx, 'time']
        sell_points['ideal_high'] = {
            'price': ideal_high,
            'return': round((ideal_high - buy_price) / buy_price * 100, 4),
            'time': str(ideal_high_time),
        }

        # 收盘卖出
        sell_points['close'] = {
            'price': full_close,
            'return': round((full_close - buy_price) / buy_price * 100, 4),
        }

        # 上午最高点
        if len(morning) > 0:
            morning_high = morning['high'].max()
            sell_points['morning_high'] = {
                'price': morning_high,
                'return': round((morning_high - buy_price) / buy_price * 100, 4),
            }

        return {
            'ts_code': ts_code,
            'name': name,
            'score': score,
            'buy_price': buy_price,
            'next_open': open_price,
            'next_high': full_high,
            'next_low': full_low,
            'next_close': full_close,
            'morning_1130_close': close_1130,
            'morning_high': morning['high'].max() if len(morning) > 0 else open_price,
            'sell_points': sell_points,
        }

    def aggregate_results(self, results: List[Dict]) -> pd.DataFrame:
        """汇总卖出时机分析"""
        rows = []
        for r in results:
            if r is None:
                continue
            row = {
                'ts_code': r['ts_code'],
                'name': r['name'],
                'score': r['score'],
                'buy_price': r['buy_price'],
                'next_open': r['next_open'],
                'next_close': r['next_close'],
                'next_return': round((r['next_close'] - r['buy_price']) / r['buy_price'] * 100, 4),
            }
            for sp_name, sp_data in r['sell_points'].items():
                if 'return' in sp_data:
                    row[f'sell_{sp_name}_ret'] = sp_data['return']
            rows.append(row)
        return pd.DataFrame(rows)


# ===========================================================================
# AutoResearch 主引擎
# ===========================================================================

class TimingResearchEngine:
    """时机研究引擎"""

    def __init__(self):
        self.downloader = FullDayMinuteDownloader()
        self.buy_analyzer = AfternoonBuyAnalyzer()
        self.sell_analyzer = NextDaySellAnalyzer()
        self.experiments = []

    def load_screening_data(self, date_str: str) -> pd.DataFrame:
        """加载筛选结果"""
        file_path = OUTPUT_DIR / f"screening_mainboard_{date_str}.csv"
        if not file_path.exists():
            # 尝试 pytdx 格式
            file_path = OUTPUT_DIR / f"screening_pytdx_{date_str}.csv"
        if not file_path.exists():
            print(f"未找到 {date_str} 的筛选结果")
            return pd.DataFrame()
        return pd.read_csv(file_path)

    def get_recommended_stocks(self, df: pd.DataFrame, min_score: int = 75) -> pd.DataFrame:
        """筛选推荐股票"""
        return df[df['score'] >= min_score].copy()

    def run_experiment_01(self, trade_date: str, next_date: str):
        """
        实验 01: 下午买入时机验证

        假设: 上午深跌反弹的股票，下午13:00-13:30存在最佳买入窗口
        """
        print("\n" + "=" * 80)
        print(f"实验 01: 下午买入时机验证 — {trade_date}")
        print("=" * 80)
        print(f"假设: 上午深跌反弹的股票，下午13:00-13:30存在最佳买入窗口")
        print()

        # 加载筛选数据
        screening_df = self.load_screening_data(trade_date)
        if screening_df.empty:
            return

        rec_df = self.get_recommended_stocks(screening_df)
        print(f"推荐股票: {len(rec_df)} 只 (score >= 75)")

        if len(rec_df) == 0:
            return

        # 限制数量以控制时间
        sample_df = rec_df.head(80) if len(rec_df) > 80 else rec_df
        print(f"样本: {len(sample_df)} 只")

        results = []
        for i, row in sample_df.iterrows():
            ts_code = row['ts_code']
            name = row.get('name', '')

            if (i + 1) % 10 == 0:
                print(f"  进度: {i+1}/{len(sample_df)}")

            # 下载全天数据
            fullday = self.downloader.download_fullday(ts_code, trade_date)
            if fullday is None:
                continue

            morning_df, afternoon_df = self.downloader.split_sessions(fullday)

            if morning_df is None or afternoon_df is None:
                continue

            morning_close = morning_df.iloc[-1]['close']
            morning_return = row.get('morning_return', 0)
            score = row.get('score', 0)

            result = self.buy_analyzer.analyze_stock(
                ts_code, name, afternoon_df, morning_close, morning_return, score
            )
            if result:
                results.append(result)

        if not results:
            print("无有效结果")
            return results

        # 汇总分析
        agg_df = self.buy_analyzer.aggregate_results(results)

        print(f"\n{'=' * 60}")
        print(f"结果汇总: {len(agg_df)} 只股票")
        print(f"{'=' * 60}")

        # 各买入时间点平均收益
        buy_cols = [c for c in agg_df.columns if c.startswith('buy_') and c.endswith('_ret')]
        print("\n【各买入时间点平均收益 (买入→收盘)】")
        print("-" * 50)
        avg_rets = {}
        for col in sorted(buy_cols):
            label = col.replace('buy_', '').replace('_ret', '')
            avg_ret = agg_df[col].mean()
            pos_rate = (agg_df[col] > 0).mean()
            avg_rets[label] = avg_ret
            print(f"  {label:>12s} 买入: 平均收益 {avg_ret:+.3f}%  盈利概率 {pos_rate:.1%}")

        # 按评分分组
        print("\n【按评分分组: 下午收盘收益】")
        print("-" * 50)
        if 'afternoon_return' in agg_df.columns:
            for score_range in [(100, 200), (85, 99), (75, 84)]:
                sub = agg_df[(agg_df['score'] >= score_range[0]) & (agg_df['score'] <= score_range[1])]
                if len(sub) > 0:
                    avg = sub['afternoon_return'].mean()
                    pos_rate = (sub['afternoon_return'] > 0).mean()
                    print(f"  评分 {score_range[0]}-{score_range[1]}: {len(sub)}只, 平均收益 {avg:+.3f}%, 盈利概率 {pos_rate:.1%}")

        # 下午走势分类
        print("\n【下午走势分类统计】")
        print("-" * 50)
        if 'afternoon_return' in agg_df.columns:
            up = (agg_df['afternoon_return'] > 0.5).sum()
            flat = ((agg_df['afternoon_return'] >= -0.5) & (agg_df['afternoon_return'] <= 0.5)).sum()
            down = (agg_df['afternoon_return'] < -0.5).sum()
            print(f"  下午上涨 >0.5%: {up}只 ({up/len(agg_df):.1%})")
            print(f"  下午横盘 ±0.5%: {flat}只 ({flat/len(agg_df):.1%})")
            print(f"  下午下跌 >0.5%: {down}只 ({down/len(agg_df):.1%})")

        # 保存详细结果
        output_file = OUTPUT_DIR / f"timing_buy_{trade_date}.csv"
        agg_df.to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f"\n详细结果已保存: {output_file}")

        return results

    def run_experiment_02(self, trade_date: str, next_date: str, buy_time: str = "13:30"):
        """
        实验 02: 次日卖出时机验证

        假设: 次日上午10:00-10:30为最佳卖出窗口
        """
        print("\n" + "=" * 80)
        print(f"实验 02: 次日卖出时机验证 — 持仓 {trade_date} 买入 → {next_date} 卖出")
        print("=" * 80)
        print(f"假设: 次日上午10:00-10:30为最佳卖出窗口")
        print(f"买入时间: 下午 {buy_time}")
        print()

        # 加载筛选数据
        screening_df = self.load_screening_data(trade_date)
        if screening_df.empty:
            return

        rec_df = self.get_recommended_stocks(screening_df)
        sample_df = rec_df.head(80) if len(rec_df) > 80 else rec_df
        print(f"样本: {len(sample_df)} 只")

        results = []
        for i, row in sample_df.iterrows():
            ts_code = row['ts_code']
            name = row.get('name', '')

            if (i + 1) % 10 == 0:
                print(f"  进度: {i+1}/{len(sample_df)}")

            # 获取买入日的全天数据 (确定买入价)
            fullday_buy = self.downloader.download_fullday(ts_code, trade_date)
            if fullday_buy is None:
                continue

            _, afternoon_df = self.downloader.split_sessions(fullday_buy)
            if afternoon_df is None or len(afternoon_df) < 3:
                continue

            # 确定买入价 (模拟在 buy_time 买入)
            af = afternoon_df.sort_values('time').reset_index(drop=True)
            h, m = map(int, buy_time.split(':'))
            target = time(h, m)
            mask = af['time'] <= target
            if not mask.any():
                continue
            buy_idx = mask[mask].index[-1]
            buy_price = af.loc[buy_idx, 'close']

            # 获取次日全天数据
            fullday_next = self.downloader.download_fullday(ts_code, next_date)
            if fullday_next is None:
                continue

            score = row.get('score', 0)
            result = self.sell_analyzer.analyze_stock(
                ts_code, name, buy_price, fullday_next, score
            )
            if result:
                results.append(result)

        if not results:
            print("无有效结果")
            return results

        # 汇总分析
        agg_df = self.sell_analyzer.aggregate_results(results)

        print(f"\n{'=' * 60}")
        print(f"结果汇总: {len(agg_df)} 只股票")
        print(f"{'=' * 60}")

        # 各卖出时间点平均收益
        sell_cols = [c for c in agg_df.columns if c.startswith('sell_') and c.endswith('_ret')]
        print("\n【各卖出时间点平均收益 (买入价→卖出价)】")
        print("-" * 50)
        for col in sorted(sell_cols):
            label = col.replace('sell_', '').replace('_ret', '')
            avg_ret = agg_df[col].mean()
            pos_rate = (agg_df[col] > 0).mean()
            print(f"  {label:>15s} 卖出: 平均收益 {avg_ret:+.3f}%  盈利概率 {pos_rate:.1%}")

        # 隔夜收益统计
        print("\n【隔夜收益统计】")
        print("-" * 50)
        if 'next_return' in agg_df.columns:
            print(f"  平均隔夜收益: {agg_df['next_return'].mean():+.3f}%")
            print(f"  中位数收益: {agg_df['next_return'].median():+.3f}%")
            print(f"  盈利概率: {(agg_df['next_return'] > 0).mean():.1%}")
            print(f"  最大收益: {agg_df['next_return'].max():+.3f}%")
            print(f"  最大亏损: {agg_df['next_return'].min():+.3f}%")

        # 按评分分组
        print("\n【按评分分组: 次日收益】")
        print("-" * 50)
        for score_range in [(100, 200), (85, 99), (75, 84)]:
            sub = agg_df[(agg_df['score'] >= score_range[0]) & (agg_df['score'] <= score_range[1])]
            if len(sub) > 0:
                avg = sub['next_return'].mean()
                pos_rate = (sub['next_return'] > 0).mean()
                print(f"  评分 {score_range[0]}-{score_range[1]}: {len(sub)}只, 平均收益 {avg:+.3f}%, 盈利概率 {pos_rate:.1%}")

        # 保存
        output_file = OUTPUT_DIR / f"timing_sell_{trade_date}_to_{next_date}.csv"
        agg_df.to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f"\n详细结果已保存: {output_file}")

        return results

    def run_experiment_03(self, results_01: list, results_02: list, trade_date: str):
        """
        实验 03: 综合分析 — 最优买卖策略组合

        假设: 结合下午买入和次日卖出的最佳时间点，可以构建稳定的短线策略
        """
        print("\n" + "=" * 80)
        print(f"实验 03: 综合买卖策略组合分析")
        print("=" * 80)

        if not results_01 or not results_02:
            print("缺少前置实验数据")
            return

        # 找到两个实验都有的股票
        buy_stocks = {r['ts_code'] for r in results_01 if r}
        sell_stocks = {r['ts_code'] for r in results_02 if r}
        common = buy_stocks & sell_stocks

        print(f"买入实验有效: {len(buy_stocks)} 只")
        print(f"卖出实验有效: {len(sell_stocks)} 只")
        print(f"交集: {len(common)} 只")

        if len(common) < 5:
            print("样本不足")
            return

        # 构建综合数据
        buy_map = {r['ts_code']: r for r in results_01 if r}
        sell_map = {r['ts_code']: r for r in results_02 if r}

        combo_rows = []
        for code in common:
            br = buy_map[code]
            sr = sell_map[code]

            row = {
                'ts_code': code,
                'name': br.get('name', sr.get('name', '')),
                'score': br.get('score', 0),
                'morning_return': br.get('morning_return', 0),
                'afternoon_return': br.get('afternoon_return', 0),
            }

            # 下午各买入点收益
            for bp_name, bp_data in br.get('buy_points', {}).items():
                if 'return_vs_close' in bp_data:
                    row[f'buy_{bp_name}_ret'] = bp_data['return_vs_close']

            # 次日各卖出点收益
            for sp_name, sp_data in sr.get('sell_points', {}).items():
                if 'return' in sp_data:
                    row[f'sell_{sp_name}_ret'] = sp_data['return']

            combo_rows.append(row)

        combo_df = pd.DataFrame(combo_rows)

        # 策略组合回测
        print(f"\n{'=' * 60}")
        print("策略组合回测 (买入时间 × 卖出时间)")
        print(f"{'=' * 60}")

        buy_time_cols = [c for c in combo_df.columns
                         if c.startswith('buy_') and c.endswith('_ret') and 'ideal' not in c]
        sell_time_cols = [c for c in combo_df.columns
                          if c.startswith('sell_') and c.endswith('_ret') and 'ideal' not in c
                          and 'morning_high' not in c and 'close' not in c]

        strategy_results = []

        print(f"\n{'买入时间':>10s} | {'卖出时间':>10s} | {'平均收益':>8s} | {'盈利概率':>8s} | {'样本数':>6s}")
        print("-" * 60)

        for bc in buy_time_cols:
            buy_label = bc.replace('buy_', '').replace('_ret', '')
            for sc in sell_time_cols:
                sell_label = sc.replace('sell_', '').replace('_ret', '')

                # 组合收益 = 下午买入收益 + 次日卖出收益
                combo_ret = combo_df[bc].fillna(0) + combo_df[sc].fillna(0)
                avg_ret = combo_ret.mean()
                pos_rate = (combo_ret > 0).mean()
                n = combo_ret.notna().sum()

                strategy_results.append({
                    'buy_time': buy_label,
                    'sell_time': sell_label,
                    'avg_return': round(avg_ret, 4),
                    'win_rate': round(pos_rate, 4),
                    'count': n,
                })

                if n >= 5:
                    marker = " ★" if avg_ret > 0.5 and pos_rate > 0.55 else ""
                    print(f"  {buy_label:>8s} | {sell_label:>8s} | {avg_ret:>+7.3f}% | {pos_rate:>7.1%} | {n:>5d}{marker}")

        # 找到最优策略
        if strategy_results:
            strat_df = pd.DataFrame(strategy_results)
            strat_df = strat_df[strat_df['count'] >= 5]
            best = strat_df.loc[strat_df['avg_return'].idxmax()]
            print(f"\n【最优策略组合】")
            print(f"  买入时间: 下午 {best['buy_time']}")
            print(f"  卖出时间: 次日 {best['sell_time']}")
            print(f"  平均收益: {best['avg_return']:+.3f}%")
            print(f"  盈利概率: {best['win_rate']:.1%}")

            # 保存策略回测结果
            strat_df.to_csv(
                OUTPUT_DIR / f"timing_strategies_{trade_date}.csv",
                index=False, encoding='utf-8-sig'
            )

        # 保存综合数据
        combo_df.to_csv(
            OUTPUT_DIR / f"timing_combo_{trade_date}.csv",
            index=False, encoding='utf-8-sig'
        )

        return combo_df


# ===========================================================================
# 主入口
# ===========================================================================

def main():
    """主入口: 运行完整的时机研究"""
    print("=" * 80)
    print("AutoResearch: 下午买入 & 次日卖出时机研究")
    print(f"日期: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 80)

    engine = TimingResearchEngine()

    # 交易日对: (筛选日, 次交易日)
    # 3/26 → 3/27, 3/27 → 3/28
    trade_pairs = [
        ("20260326", "20260327"),
        ("20260327", "20260328"),
    ]

    all_buy_results = []
    all_sell_results = []

    for trade_date, next_date in trade_pairs:
        print(f"\n{'#' * 80}")
        print(f"# 研究日: {trade_date} → 次日: {next_date}")
        print(f"{'#' * 80}")

        # 实验 01: 下午买入时机
        buy_results = engine.run_experiment_01(trade_date, next_date)
        if buy_results:
            all_buy_results.extend(buy_results)

        # 实验 02: 次日卖出时机
        sell_results = engine.run_experiment_02(trade_date, next_date, buy_time="13:30")
        if sell_results:
            all_sell_results.extend(sell_results)

    # 实验 03: 综合分析
    engine.run_experiment_03(all_buy_results, all_sell_results, "20260326-27")

    print("\n" + "=" * 80)
    print("研究完成")
    print("=" * 80)


if __name__ == "__main__":
    main()

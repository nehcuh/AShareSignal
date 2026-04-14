---
title: autoresearch.py — 核心引擎
type: entity
tags: [核心模块, autoresearch, 回测, 特征工程]
created: 2026-04-14
updated: 2026-04-14
related_files:
  - src/autoresearch.py
  - src/experiment_006.py
  - research_log.md
  - output/autoresearch_dataset.csv
---

# autoresearch.py — 核心引擎

## 模块概述

`autoresearch.py` 是 AShareSignal 项目的**核心引擎**，实现了基于 Karpathy 方法论的策略迭代框架。该模块包含 5 个核心类，负责数据加载、特征提取、回测评估、实验管理和日志记录的完整闭环。

**代码行数**: ~1000+ 行（项目最大单文件）

## 核心类

### 1. `DataLoader`
数据加载器，负责从 Tushare API 和本地文件获取原始数据。

```python
class DataLoader:
    def __init__(self, token=None):
        # token 参数可选，默认使用硬编码值 [REDACTED]
        self.pro = ts.pro_api(token)
    
    def load_stock_pool(self) -> Dict[str, List[str]]:
        """从 assets/池子_20251104.xlsx 加载股票池
        返回: {日期字符串: [股票代码列表]}
        """
    
    def fetch_daily_data(self, code: str) -> pd.DataFrame:
        """从 Tushare 获取指定股票的日线数据
        包含: daily + daily_basic + moneyflow + stk_limit
        """
    
    def get_trading_days(self) -> List[str]:
        """获取交易日历（排除周末和节假日）"""
```

**重要方法**:
- `load_stock_pool()`: 解析 Excel，处理日期偏移（可能有 +3 个月）
- `fetch_daily_data()`: 合并多个 Tushare 接口数据（OHLCV + 换手率 + 资金流向 + 涨跌停价）
- `get_trading_days()`: 缓存交易日历，避免重复 API 调用

### 2. `FeatureEngineer`
特征工程师，从原始日线数据中提取预测特征。

```python
class FeatureEngineer:
    def extract_all_features(self, stock_data: pd.DataFrame, eval_date: str) -> Optional[pd.Series]:
        """提取所有特征（主入口）
        参数:
          stock_data: 日线数据 DataFrame
          eval_date: 评估日期（只使用此日期之前的数据，防泄露）
        返回: 特征 Series 或 None（数据不足时）
        """
    
    def _extract_price_features(self, df, idx) -> Dict:
        """基础价格特征: price_pos_N, dist_to_ma_N, daily_return, amplitude"""
    
    def _extract_hist_features(self, df, idx) -> Dict:
        """历史统计: return_mean/std_N, max/min_return_N"""
    
    def _extract_technical_features(self, df, idx) -> Dict:
        """技术指标: RSI(6/12), KDJ(K/D/J), MACD"""
    
    def _extract_morning_features(self, df, idx) -> Dict:
        """上午模式: morning_gap_pct, morning_return, morning_max_up/down
        注意: 用日线OHLC模拟，精度有限
        """
```

**提取的特征数**: 约 30+ 个基础特征

### 3. `BacktestEngine`
回测引擎，运行策略回测并评估特征预测力。

```python
class BacktestEngine:
    def run_backtest(self, pool, data_loader, feature_engineer) -> pd.DataFrame:
        """运行完整回测
        对股票池中每个交易日的每只股票:
        1. 获取日线数据
        2. 提取特征（使用 eval_date 前的数据）
        3. 匹配次日实际涨跌作为标签
        返回: 包含所有特征和标签的 DataFrame
        """
    
    def evaluate_feature(self, dataset, feature_name) -> Dict:
        """评估单个特征的预测能力
        计算:
        - Pearson 相关性
        - 五分位分组分析（Q1-Q5 各组的上涨率）
        - 区分度（Q5 vs Q1 上涨率差和收益差）
        """
    
    def get_trading_days(self) -> List[str]:
        """获取交易日历"""
```

### 4. `AutoResearch`
自动研究引擎，编排整个实验循环。

```python
class AutoResearch:
    def __init__(self):
        self.data_loader = DataLoader()
        self.feature_engineer = FeatureEngineer()
        self.backtest_engine = BacktestEngine()
        self.research_logger = ResearchLogger()
    
    def systematic_feature_scan(self, dataset) -> pd.DataFrame:
        """系统化扫描所有数值特征，按预测力排序
        对每个特征:
        1. 计算与次日涨跌的相关性
        2. 运行五分位分组分析
        3. 计算区分度
        返回: 按相关性排序的特征排名表
        """
    
    def run_experiment(self, experiment: Experiment) -> Dict:
        """运行单个实验"""
```

### 5. `ResearchLogger`
研究日志记录器，将实验结果写入 Markdown 文件。

```python
class ResearchLogger:
    def log_experiment(self, experiment: Experiment):
        """将实验结果写入 research_log.md
        格式: Markdown 表格 + 结论描述
        """
```

## 数据结构

### Experiment
```python
@dataclass
class Experiment:
    id: str                    # 实验编号
    name: str                  # 实验名称
    hypothesis: str            # 假设描述
    features: List[str]        # 使用的特征列表
    status: ExperimentStatus   # PENDING / RUNNING / SUCCESS / FAILED
    result: Dict               # 结果数据
    timestamp: str             # 时间戳
    notes: str                 # 结论
```

### ExperimentStatus
```python
class ExperimentStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
```

## 模块间依赖

```
autoresearch.py (本模块)
    │
    ├── ts.pro_api() ← Tushare SDK (token: [REDACTED])
    ├── assets/池子_20251104.xlsx ← 股票池数据
    ├── research_log.md ← 实验日志输出
    └── output/autoresearch_dataset.csv ← 回测数据集输出
```

## 关键设计决策

1. **eval_date 时间过滤** — 所有特征提取严格使用 `stock_data[trade_date < eval_date]`，防止未来数据泄露
2. **日线模拟上午特征** — 在没有分钟数据时，用 `(open + high + close) / 3` 估算 11:30 价位
3. **五分位评估法** — 将特征值排序后分为 5 组，比较 Q5（最高组）和 Q1（最低组）的上涨率差异
4. **自动特征扫描** — `systematic_feature_scan()` 自动发现预测力最强的特征

## 技术债

1. **Token 硬编码** — `[REDACTED]`，应使用环境变量
2. **单文件过大** — 5 个类放在一个文件中，建议拆分为独立模块
3. **错误处理不足** — API 调用缺乏重试和超时机制
4. **缓存缺失** — `fetch_daily_data()` 每次都调用 API，应增加本地缓存

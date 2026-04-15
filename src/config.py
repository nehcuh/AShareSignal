"""
AShareSignal 统一配置入口
"""

import os
from pathlib import Path
import tushare as ts

# =============================================================================
# API Tokens (统一走环境变量)
# =============================================================================
TUSHARE_TOKEN = os.environ.get("TUSHARE_TOKEN", "")

if TUSHARE_TOKEN:
    ts.set_token(TUSHARE_TOKEN)

# 暴露 pro_api 实例供各模块直接使用
try:
    pro = ts.pro_api()
except Exception:
    pro = None

# =============================================================================
# Paths
# =============================================================================
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"
CACHE_DIR = DATA_DIR / "minute_cache"
ASSETS_DIR = PROJECT_ROOT / "assets"
STOCK_POOL_EXCEL = ASSETS_DIR / "池子_20251104.xlsx"

# Output subdirs
OUTPUT_RAW_DIR = OUTPUT_DIR / "raw"
OUTPUT_REPORTS_DIR = OUTPUT_DIR / "reports"
OUTPUT_ARCHIVE_DIR = OUTPUT_DIR / "archive"
OUTPUT_LATEST_DIR = OUTPUT_DIR / "latest"

# =============================================================================
# Data source settings
# =============================================================================
DATA_SOURCE_PRIORITY = ["pytdx", "akshare", "tushare", "sina"]

# =============================================================================
# Strategy parameters
# =============================================================================
SIGNAL_TIME = "11:30"
ENTRY_TIME = "13:00"
STOCK_UNIVERSE = "main_board_non_st"

# =============================================================================
# Champion Strategy Definition (Phase 2 Baseline)
# =============================================================================
CHAMPION_STRATEGY = {
    "name": "champion_baseline",
    "description": "主板非ST上午特征评分策略，作为所有实验的基准",
    "signal_generation": "morning_feature_screening",
    "signal_time": "11:30",
    "universe": "main_board_non_st",
    "entry_rule": {
        "type": "fixed_time",
        "time": "13:00",
        "price": "pm_open",  # 下午开盘价
    },
    "exit_rule": {
        "type": "stop_loss_close",
        "stop_loss_pct": 3.0,  # 回撤超 3% 止损，否则收盘卖
    },
    "veto_rules": [
        # Experiment 05 结论：上午最后 5 分钟（11:25-11:30）跌幅超 0.5% 则禁买
        {"type": "last_5m_return", "threshold": -0.5, "operator": ">="}
    ],
    "regime_filter": {
        # 实验 04 结论：上证指数大涨日(>1%)停用策略
        "enabled": False,
        "index_ts_code": "000001.SH",
        "condition": "index_pct_chg <= 1.0",
    },
    "position_sizing": {
        "max_positions_per_day": 5,
        "allocation": "equal_weight",
    },
    "selection_criteria": {
        # 评分阈值：A-强烈推荐(>=70) 或 B-推荐关注(>=60)
        # 使用 >=60 保证 baseline 有足够样本；实验中可切换
        "score_threshold": 60,
        "exclude_ratings": ["D-暂不关注"],
        "top_n": 5,
        "sort_by": "score",
    },
    "slippage": 0.001,  # 0.1%
    "data_source": "pytdx_minute",
}

# =============================================================================
# Tushare pro_api lazy getter (带缓存)
# =============================================================================
_tushare_pro = None


def get_tushare_pro():
    """获取 Tushare pro_api 实例（延迟初始化）"""
    global _tushare_pro
    if _tushare_pro is None:
        _tushare_pro = ts.pro_api()
    return _tushare_pro

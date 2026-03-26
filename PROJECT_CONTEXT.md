# Project Context

## Session Handoff

<!-- handoff:start -->
### 2026-03-26 12:40
**Session Summary**: Created real-time stock screening tool for A-share main board stocks

**Key Decisions**:
- Built `src/screen_mainboard_today.py` using akshare for real-time spot data
- Implemented market classification to filter main board only (excludes STAR 688, ChiNext 300/301, Beijing 8/430)
- Created scoring algorithm based on morning price action signals

**What Was Done**:
- Created screening tool with 8 scoring rules (positive/negative signals)
- Successfully analyzed 3,128 main board non-ST stocks
- Generated 171 "A-强烈推荐" rated stocks, 475 "B-推荐关注"
- Results saved to `output/screening_mainboard_20260326.csv`
- Top pick: 002213.SZ 大为股份 (score 120, signals: 深跌反弹|低开高走|量价齐升)

**Technical Discoveries**:
- akshare returns Chinese column names (代码/名称/最新价/涨跌幅/今开/最高/最低/昨收/换手率/振幅/成交额)
- Main board codes: 000/001/002/003 (SZ), 600/601/603/605 (SH)

**Next Steps**:
- Validate screening strategy with historical backtest
- Consider adding minute-level data for more accurate morning feature extraction
- Compare predicted performance vs actual next-day returns
<!-- handoff:end -->

## Project Overview

AShareSignal - A-share stock screening and prediction system

### Key Files
- `src/screen_mainboard_today.py` - Main board stock screening tool (today's creation)
- `src/predict_real_minute.py` - Real minute data prediction
- `src/minute_data_manager.py` - Minute data cache manager
- `assets/池子_20251104.xlsx` - Historical stock pool data

### Data Sources
- akshare - Free real-time A-share data
- Tushare Pro - Historical data (requires token)

### Output
- `output/screening_mainboard_YYYYMMDD.csv` - Daily screening results

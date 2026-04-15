"""
output/ 目录生命周期规范化脚本
按照 ROADMAP P0.5 规则迁移现有文件到新的目录结构
"""

import os
import shutil
import re
from pathlib import Path
from datetime import datetime

OUTPUT_DIR = Path("output")
RAW_DIR = OUTPUT_DIR / "raw"
REPORTS_DIR = OUTPUT_DIR / "reports"
ARCHIVE_DIR = OUTPUT_DIR / "archive"
LATEST_DIR = OUTPUT_DIR / "latest"


def ensure_dirs():
    RAW_DIR.mkdir(exist_ok=True)
    REPORTS_DIR.mkdir(exist_ok=True)
    ARCHIVE_DIR.mkdir(exist_ok=True)
    LATEST_DIR.mkdir(exist_ok=True)


def parse_date_from_filename(filename: str) -> str | None:
    """从文件名中提取 YYYYMMDD 日期"""
    m = re.search(r"(\d{8})", filename)
    return m.group(1) if m else None


def classify_file(path: Path) -> tuple[Path, str]:
    """
    返回 (目标目录, 说明)
    """
    name = path.name
    lower = name.lower()

    # 汇总报告类
    if lower.startswith("signal") and lower.endswith(".csv"):
        return REPORTS_DIR, "signal report"
    if lower.startswith("stock_pool_tracking") and lower.endswith(".xlsx"):
        return REPORTS_DIR, "tracking report"

    # 原始输出类（screening、tracking、analysis）
    if lower.startswith("screening_") and lower.endswith(".csv"):
        return RAW_DIR, "screening raw"
    if lower.startswith("stock_tracking_") and lower.endswith(".csv"):
        return RAW_DIR, "stock tracking raw"
    if lower.startswith("stock_analysis_result_") and lower.endswith(".csv"):
        return RAW_DIR, "analysis raw"

    # 默认保留在 output/ 根目录（未知类型，不移动）
    return OUTPUT_DIR, "keep in root"


def move_to_archive(path: Path, yyyymm: str) -> Path:
    """将文件移入 archive/YYYYMM/"""
    archive_month = ARCHIVE_DIR / yyyymm
    archive_month.mkdir(exist_ok=True)
    dest = archive_month / path.name
    if dest.exists():
        print(f"  [WARN] {dest} already exists, overwriting")
        shutil.copy2(path, dest)
        path.unlink()
    else:
        shutil.move(str(path), str(dest))
    return dest


def organize():
    ensure_dirs()

    # 收集 output/ 下的直接子文件和子目录（排除新建的四个目录自身）
    entries = [
        p for p in OUTPUT_DIR.iterdir()
        if p.name not in {"raw", "reports", "archive", "latest"}
    ]

    moved_count = 0
    archive_count = 0

    for entry in entries:
        if entry.is_dir():
            # 将 historical_filter 等目录整体移入 raw/
            dest = RAW_DIR / entry.name
            if dest.exists():
                print(f"[SKIP DIR] {entry.name} -> {dest} already exists")
            else:
                shutil.move(str(entry), str(dest))
                print(f"[MOVE DIR] {entry.name} -> {dest.relative_to(OUTPUT_DIR)}")
                moved_count += 1
            continue

        target_dir, reason = classify_file(entry)
        date_str = parse_date_from_filename(entry.name)

        # 如果是 raw/ 文件且日期早于当前月份，进一步归档到 archive/YYYYMM/
        if target_dir == RAW_DIR and date_str:
            file_yyyymm = date_str[:6]
            current_yyyymm = datetime.now().strftime("%Y%m")
            if file_yyyymm < current_yyyymm:
                dest = move_to_archive(entry, file_yyyymm)
                print(f"[ARCHIVE] {entry.name} ({reason}) -> {dest.relative_to(OUTPUT_DIR)}")
                archive_count += 1
                continue

        dest = target_dir / entry.name
        if dest.exists():
            print(f"[SKIP FILE] {entry.name} -> {dest} already exists")
        else:
            shutil.move(str(entry), str(dest))
            print(f"[MOVE FILE] {entry.name} ({reason}) -> {dest.relative_to(OUTPUT_DIR)}")
            moved_count += 1

    # 更新 latest/ 软链接：指向 raw/ 或 archive/ 中最新的 final_top5 和 minute_precise
    update_latest_links()

    print("\n" + "=" * 60)
    print(f"整理完成：移动 {moved_count} 个文件/目录，归档 {archive_count} 个文件")


def update_latest_links():
    """在 latest/ 下创建指向最新 screening 文件的软链接（或复制）"""
    patterns = {
        "latest_final_top5.csv": re.compile(r"screening_\d{8}_final_top5\.csv"),
        "latest_minute_precise.csv": re.compile(r"screening_\d{8}_minute_precise\.csv"),
        "latest_daily_approx.csv": re.compile(r"screening_\d{8}_daily_approx\.csv"),
    }

    # 扫描 raw/ 和 archive/ 下所有匹配文件
    all_files = []
    for root in [RAW_DIR, ARCHIVE_DIR]:
        if root.exists():
            all_files.extend(root.rglob("screening_*.csv"))

    for link_name, pattern in patterns.items():
        matches = [p for p in all_files if pattern.match(p.name)]
        if not matches:
            continue
        matches.sort(key=lambda p: p.name)
        newest = matches[-1]
        link_path = LATEST_DIR / link_name
        # 如果已存在软链接或文件，先删除
        if link_path.exists() or link_path.is_symlink():
            link_path.unlink()
        # 使用相对路径的软链接
        rel_target = os.path.relpath(newest, LATEST_DIR)
        link_path.symlink_to(rel_target)
        print(f"[LATEST] {link_name} -> {rel_target}")


if __name__ == "__main__":
    organize()

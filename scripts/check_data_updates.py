#!/usr/bin/env python3
"""
Check USCIS and DOS websites for new data files and download them.

Usage:
    python scripts/check_data_updates.py              # check + download
    python scripts/check_data_updates.py --dry-run    # check only, no download
"""
import argparse
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
USCIS_DIR = REPO_ROOT / "data" / "raw" / "uscis"
DOS_DIR = REPO_ROOT / "data" / "raw" / "dos"

MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]

USCIS_BASE = "https://www.uscis.gov/sites/default/files/document/data"
DOS_BASE = "https://travel.state.gov/content/dam/visas/Statistics/Immigrant-Statistics/MonthlyIVIssuances/Excel"


def emit_env(key: str, val: str):
    """写 $GITHUB_ENV，供 workflow 后续步骤(Bark 通知)读取。"""
    p = os.environ.get("GITHUB_ENV")
    if not p:
        return
    with open(p, "a", encoding="utf-8") as f:
        f.write(f"{key}<<__EOF__\n{val}\n__EOF__\n")


def newest_inventory_month():
    """本地已有的最新 I-485 Inventory 月份 (year, month)，用于逾期告警。"""
    latest = None
    for f in USCIS_DIR.glob("I485_Pending_Inventory_*.xlsx"):
        m = __import__("re").search(r"I485_Pending_Inventory_([a-z]+)_(\d{4})", f.name)
        if m and m.group(1) in MONTHS:
            d = (int(m.group(2)), MONTHS.index(m.group(1)) + 1)
            if latest is None or d > latest:
                latest = d
    return latest


def probe_url(url: str) -> bool:
    req = urllib.request.Request(url, method="HEAD")
    req.add_header("User-Agent", "EB1A-DataUpdater/1.0")
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return resp.status == 200
    except (urllib.error.HTTPError, urllib.error.URLError, OSError):
        return False


def download(url: str, dest: Path) -> bool:
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "EB1A-DataUpdater/1.0")
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.read())
        return True
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
        print(f"  DOWNLOAD FAILED: {e}")
        return False


def check_i485_inventory(dry_run: bool) -> list[str]:
    """Check for new monthly I-485 Pending Inventory snapshots."""
    new_files = []
    now = datetime.now()

    for year in range(2025, now.year + 1):
        for month_name in MONTHS:
            month_idx = MONTHS.index(month_name) + 1
            if year == now.year and month_idx > now.month:
                break

            local = USCIS_DIR / f"I485_Pending_Inventory_{month_name}_{year}.xlsx"
            if local.exists():
                continue

            url = f"{USCIS_BASE}/eb_inventory_{month_name}_{year}.xlsx"
            if probe_url(url):
                new_files.append(str(local.relative_to(REPO_ROOT)))
                if not dry_run:
                    if download(url, local):
                        print(f"  DOWNLOADED: {local.name}")
                    else:
                        new_files.pop()
                else:
                    print(f"  AVAILABLE: {local.name}")

    return new_files


def check_i140_quarterly(dry_run: bool) -> list[str]:
    """Check for new I-140 quarterly reports."""
    new_files = []
    now = datetime.now()
    current_fy = now.year if now.month >= 10 else now.year
    # e.g. May 2026 -> FY2026, Nov 2026 -> FY2027

    for fy in range(2024, current_fy + 2):
        for q in range(1, 5):
            local = USCIS_DIR / f"I140_FY{fy}_Q{q}.xlsx"
            if local.exists():
                continue

            for suffix in [f"i140_fy{fy}_q{q}.xlsx", f"i140_fy{fy}_q{q}_0.xlsx"]:
                url = f"{USCIS_BASE}/{suffix}"
                if probe_url(url):
                    new_files.append(str(local.relative_to(REPO_ROOT)))
                    if not dry_run:
                        if download(url, local):
                            print(f"  DOWNLOADED: {local.name}")
                        else:
                            new_files.pop()
                    else:
                        print(f"  AVAILABLE: {local.name}")
                    break

    return new_files


def check_i140_approved(dry_run: bool) -> list[str]:
    """Check for new I-140/I-360/I-526 Approved Awaiting Visa reports."""
    new_files = []
    now = datetime.now()
    current_fy = now.year if now.month >= 10 else now.year

    for fy in range(2025, current_fy + 2):
        for q in range(1, 5):
            local = USCIS_DIR / f"I140_I360_I526_Approved_FY{fy}_Q{q}.xlsx"
            if local.exists():
                continue

            url = f"{USCIS_BASE}/eb_i140_i360_i526_performancedata_fy{fy}_q{q}.xlsx"
            if probe_url(url):
                new_files.append(str(local.relative_to(REPO_ROOT)))
                if not dry_run:
                    if download(url, local):
                        print(f"  DOWNLOADED: {local.name}")
                    else:
                        new_files.pop()
                else:
                    print(f"  AVAILABLE: {local.name}")

    return new_files


def fy_months(fy: int) -> list[tuple[str, int]]:
    """Return (month_name, calendar_year) for all 12 months of a fiscal year."""
    result = []
    for m in range(10, 13):
        result.append((MONTHS[m - 1], fy - 1))
    for m in range(1, 10):
        result.append((MONTHS[m - 1], fy))
    return result


def check_dos_issuance(dry_run: bool) -> list[str]:
    """Check for new DOS Monthly IV Issuance files."""
    new_files = []
    now = datetime.now()
    current_fy = now.year if now.month >= 10 else now.year + 1

    for fy in range(2024, current_fy + 1):
        for month_name, cal_year in fy_months(fy):
            if cal_year > now.year or (cal_year == now.year and MONTHS.index(month_name) + 1 > now.month):
                continue

            local = DOS_DIR / f"iv_issuance_{month_name}_{cal_year}.xlsx"
            if local.exists():
                continue

            encoded_month = month_name.upper() + f" {cal_year}"
            encoded = encoded_month.replace(" ", "%20")
            url = (
                f"{DOS_BASE}/FY{fy}/"
                f"{encoded}%20-%20IV%20Issuances%20by%20FSC%20or%20Place%20of%20Birth"
                f"%20and%20Visa%20Class.xlsx"
            )
            if probe_url(url):
                new_files.append(str(local.relative_to(REPO_ROOT)))
                if not dry_run:
                    if download(url, local):
                        print(f"  DOWNLOADED: {local.name}")
                    else:
                        new_files.pop()
                else:
                    print(f"  AVAILABLE: {local.name}")

    return new_files


def main():
    parser = argparse.ArgumentParser(description="Check for new USCIS/DOS data files")
    parser.add_argument("--dry-run", action="store_true", help="Check only, don't download")
    args = parser.parse_args()

    USCIS_DIR.mkdir(parents=True, exist_ok=True)
    DOS_DIR.mkdir(parents=True, exist_ok=True)

    all_new = []

    print("Checking USCIS I-485 Pending Inventory...")
    all_new.extend(check_i485_inventory(args.dry_run))

    print("Checking USCIS I-140 Quarterly Reports...")
    all_new.extend(check_i140_quarterly(args.dry_run))

    print("Checking USCIS I-140/I-360/I-526 Approved Awaiting Visa...")
    all_new.extend(check_i140_approved(args.dry_run))

    print("Checking DOS Monthly IV Issuance...")
    all_new.extend(check_dos_issuance(args.dry_run))

    print()
    if all_new:
        action = "found" if args.dry_run else "downloaded"
        print(f"=== {len(all_new)} new file(s) {action} ===")
        for f in all_new:
            print(f"  {f}")
    else:
        print("=== All data is up to date ===")

    # 通知 + 逾期告警：写入 $GITHUB_ENV，供 workflow 用 Bark 推送
    notes = []
    if all_new:
        names = "、".join(Path(f).name for f in all_new)
        notes.append(f"新增 {len(all_new)} 个数据文件：{names}")
    inv = newest_inventory_month()
    if inv:
        now = datetime.now()
        behind = (now.year - inv[0]) * 12 + (now.month - inv[1])
        if behind >= 2:
            notes.append(f"⚠️ I-485 Inventory 最新仅到 {inv[0]}-{inv[1]:02d}（落后 {behind} 个月）"
                         "，可能 USCIS 改了命名或漏抓，请核查 check_data_updates.py 的 URL。")
    if notes:
        emit_env("BARK_TITLE", "EB1A 数据更新" + ("（含告警⚠️）" if any("⚠️" in n for n in notes) else ""))
        emit_env("BARK_BODY", "；".join(notes))
        emit_env("DATA_NOTIFY", "1")

    # Set GitHub Actions output
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
            fh.write(f"new_files={len(all_new)}\n")

    return 0 if not all_new or not args.dry_run else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Check USCIS and DOS websites for new data files and download them.

Usage:
    python scripts/check_data_updates.py              # check + download
    python scripts/check_data_updates.py --dry-run    # check only, no download
"""
import argparse
import os
import re
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


def _get_text(url: str) -> str:
    """GET 页面文本(失败返回空串)。仅 runner 能真正访问官网,容器/沙箱会被挡。"""
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mozilla/5.0 EB1A-DataUpdater/1.0")
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return resp.read().decode("utf-8", "ignore")
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
        print(f"  无法获取页面 {url}: {e}")
        return ""


DOS_LIST_PAGE = ("https://travel.state.gov/content/travel/en/legal/visa-law0/visa-statistics/"
                 "immigrant-visa-statistics/monthly-immigrant-visa-issuances.html")


def dos_official_latest():
    """从 DOS 列表页解析"官方实际已发布"的最新 FSC/出生地 月度签发 (year, month)。
    只有官方比本地新才算真漏抓——消除"按日历落后但官方根本没发"的误报。
    仅 runner 能访问官网;容器/沙箱被挡时返回 None(调用方退回日历预算)。"""
    html = _get_text(DOS_LIST_PAGE)
    if not html:
        return None
    best = None
    for mon, yr in re.findall(
            r'Excel/FY\d+/([A-Za-z]+)%20(\d{4})%20-%20IV%20Issuances%20by%20FSC', html):
        ml = mon.lower()
        if ml in MONTHS:
            ym = (int(yr), MONTHS.index(ml) + 1)
            if best is None or ym > best:
                best = ym
    return best


def _supplement_latest_quarter():
    """data/i140_china_receipts_supplement.json 里最新季度的"季度末" (year, month)。
    社区手工补充的收件数据已进模型,故新鲜度应把它算上(否则误报 xlsx 漏抓)。"""
    import json
    p = REPO_ROOT / "data" / "i140_china_receipts_supplement.json"
    if not p.exists():
        return None
    try:
        quarters = json.load(open(p, encoding="utf-8")).get("quarters", {})
    except (OSError, ValueError):
        return None
    qend = {1: (-1, 12), 2: (0, 3), 3: (0, 6), 4: (0, 9)}
    best = None
    for tag in quarters:
        m = re.match(r"FY(\d+)_Q(\d+)", tag)
        if m:
            fy, q = int(m.group(1)), int(m.group(2))
            dy, mo = qend[q]
            ym = (fy + dy, mo)
            if best is None or ym > best:
                best = ym
    return best


def _newest_month(directory, pattern, regex):
    """目录里匹配 regex(month_name, year) 的最新 (year, month)。"""
    latest = None
    for f in directory.glob(pattern):
        m = re.search(regex, f.name)
        if m and m.group(1) in MONTHS:
            d = (int(m.group(2)), MONTHS.index(m.group(1)) + 1)
            if latest is None or d > latest:
                latest = d
    return latest


def _newest_quarter(pattern, regex):
    """USCIS 季度文件最新的"季度末" (year, month)。FY 季度→日历月：
    Q1=上一日历年12月, Q2=3月, Q3=6月, Q4=9月。"""
    qend = {1: (-1, 12), 2: (0, 3), 3: (0, 6), 4: (0, 9)}
    latest = None
    for f in USCIS_DIR.glob(pattern):
        m = re.search(regex, f.name)
        if m:
            fy, q = int(m.group(1)), int(m.group(2))
            dy, mo = qend[q]
            ym = (fy + dy, mo)
            if latest is None or ym > latest:
                latest = ym
    return latest


def newest_inventory_month():
    """本地已有的最新 I-485 Inventory 月份 (year, month)。"""
    return _newest_month(USCIS_DIR, "I485_Pending_Inventory_*.xlsx",
                         r"I485_Pending_Inventory_([a-z]+)_(\d{4})")


def freshness_report():
    """逐源新鲜度巡检。返回 (report_lines, stale_notes)。
    核心原则：对照"实际可得/已在模型里的数据",而非死板的日历——
    官方自己慢(还没发)不算漏抓,只有"官方已发/数据存在但我们没拿到"才告警。
    report_lines 永远打印(被动存活证明,不推 Bark);stale_notes 非空才告警。"""
    now = datetime.now()
    def behind(ym):
        return (now.year - ym[0]) * 12 + (now.month - ym[1])
    lines, stale = ["## 数据源新鲜度巡检"], []

    def calendar(name, ym, budget, extra=""):
        """USCIS 列表页不可抓 → 退回日历预算判定。"""
        if ym is None:
            lines.append(f"  {name}: ❓ 本地无文件"); stale.append(f"{name} 本地无任何文件"); return
        b = behind(ym); flag = "⚠️漏抓?" if b > budget else "✅"
        lines.append(f"  {name}: 最新 {ym[0]}-{ym[1]:02d}（落后 {b} 月，预算 {budget}）{flag}{extra}")
        if b > budget:
            stale.append(f"{name} 仅到 {ym[0]}-{ym[1]:02d}（落后 {b} 月，疑似漏抓/改名，请核查 URL）")

    # I-485 库存：USCIS 列表页不可抓 → 日历预算
    calendar("I-485 库存(月)", newest_inventory_month(), 3)

    # DOS：对照官网列表页"实际已发布最新"。官方比本地新才算真漏抓(消除日历误报)
    dos_local = _newest_month(DOS_DIR, "iv_issuance_*.xlsx", r"iv_issuance_([a-z]+)_(\d{4})")
    dos_official = dos_official_latest()
    if dos_official is None:
        calendar("DOS 签发量(月)", dos_local, 5, "（官网不可达，按日历预算）")
    elif dos_local is None or dos_official > dos_local:
        loc = f"{dos_local[0]}-{dos_local[1]:02d}" if dos_local else "无"
        lines.append(f"  DOS 签发量(月): 官方已发 {dos_official[0]}-{dos_official[1]:02d}，本地 {loc} ⚠️真漏抓")
        stale.append(f"DOS 官方已发布 {dos_official[0]}-{dos_official[1]:02d} 但本地缺，请修抓取/URL")
    else:
        lines.append(f"  DOS 签发量(月): 本地 {dos_local[0]}-{dos_local[1]:02d} = 官方最新 ✅（官方暂未发更新）")

    # I-140 收件：本地 xlsx 与 supplement 取较新——衡量"数据是否已在模型里",而非是否抓到 xlsx
    i140_xlsx = _newest_quarter("I140_FY*_Q*.xlsx", r"I140_FY(\d+)_Q(\d+)")
    i140_sup = _supplement_latest_quarter()
    i140_latest = max([x for x in (i140_xlsx, i140_sup) if x], default=None)
    calendar("I-140 季度收件", i140_latest, 9)
    if i140_xlsx and i140_sup and i140_sup > i140_xlsx:
        lines.append(f"    (注:自动 xlsx 仅到 {i140_xlsx[0]}-{i140_xlsx[1]:02d}；较新季度由 supplement.json "
                     "提供;USCIS 已把该系列改为 CSV 命名,自动抓取待修[非紧急,数据已在模型])")

    # I-140 待签(季)：USCIS 列表页不可抓 → 日历预算(当前 ✅)
    calendar("I-140 待签(季)", _newest_quarter("I140_I360_I526_Approved_FY*_Q*.xlsx",
                                               r"Approved_FY(\d+)_Q(\d+)"), 9)
    return lines, stale


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

    for fy in range(2022, current_fy + 2):
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

    for fy in range(2024, current_fy + 2):
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

    # 逐源新鲜度巡检：报表永远写运行摘要(被动存活证明，不推 Bark)；
    # 只有"有问题"(漏抓/逾期)或"有新数据"才推 Bark —— 空跑一律静默。
    report, stale = freshness_report()
    print()
    for ln in report:
        print(ln)
    sp = os.environ.get("GITHUB_STEP_SUMMARY")
    if sp:
        try:
            with open(sp, "a", encoding="utf-8") as fh:
                fh.write("\n".join(report) + "\n")
        except OSError:
            pass

    notes = []
    if all_new:
        names = "、".join(Path(f).name for f in all_new)
        notes.append(f"新增 {len(all_new)} 个数据文件：{names}")
    if stale:
        notes.append("⚠️ " + "；".join(stale))
    if notes:
        emit_env("BARK_TITLE", "EB1A 数据" + ("（漏抓告警⚠️）" if stale else "更新"))
        emit_env("BARK_BODY", "；".join(notes))
        emit_env("DATA_NOTIFY", "1")

    # Set GitHub Actions output
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
            fh.write(f"new_files={len(all_new)}\n")

    return 0 if not all_new or not args.dry_run else 0


if __name__ == "__main__":
    sys.exit(main())

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


def diagnose(stale_names):
    """逐"漏抓"源抓取官方列表页，正则提取相关文件链接并打印真实当前 URL/命名，
    用于判断是『官方还没发』还是『改名/换路径』。仅在检测到漏抓时调用(随告警同跑)。"""
    pages = {
        "DOS 签发量(月)": (
            "https://travel.state.gov",
            "https://travel.state.gov/content/travel/en/legal/visa-law0/visa-statistics/"
            "immigrant-visa-statistics/monthly-immigrant-visa-issuances.html",
            r'href="([^"]*IV%20Issuances[^"]*|[^"]*IV Issuances[^"]*)"',
        ),
        "I-140 季度收件": (
            "https://www.uscis.gov",
            "https://www.uscis.gov/tools/reports-and-studies/immigration-and-citizenship-data",
            r'href="([^"]*[iI]140[^"]*\.xlsx)"',
        ),
        "I-140 待签(季)": (
            "https://www.uscis.gov",
            "https://www.uscis.gov/tools/reports-and-studies/immigration-and-citizenship-data",
            r'href="([^"]*i140_i360_i526[^"]*\.xlsx)"',
        ),
        "I-485 库存(月)": (
            "https://www.uscis.gov",
            "https://www.uscis.gov/tools/reports-and-studies/immigration-and-citizenship-data",
            r'href="([^"]*eb_inventory[^"]*\.xlsx)"',
        ),
    }
    out = ["", "## 漏抓源诊断（官网列表页真实链接）"]
    for name in stale_names:
        cfg = pages.get(name)
        if not cfg:
            continue
        origin, page, pat = cfg
        out.append(f"### {name} — 列表页 {page}")
        html = _get_text(page)
        if not html:
            out.append("  ⚠️ 列表页拉取失败（容器内属正常；以 runner 日志为准）")
            continue
        seen, links = set(), []
        for m in re.findall(pat, html):
            u = m if m.startswith("http") else origin + m
            if u not in seen:
                seen.add(u); links.append(u)
        if not links:
            out.append("  未匹配到任何文件链接 → 可能页面结构/命名已变，或为 JS 动态渲染。")
        else:
            out.append(f"  匹配到 {len(links)} 个链接，最近若干：")
            for u in links[-10:]:
                out.append(f"    {u}")
    for ln in out:
        print(ln)
    return out


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
    report_lines 永远打印(被动存活证明,不推 Bark);stale_notes 非空才告警。
    每源给一个"正常滞后预算"(月);超出=疑似漏抓/USCIS 改名,需人核查 URL。"""
    now = datetime.now()
    def behind(ym):
        return (now.year - ym[0]) * 12 + (now.month - ym[1])
    sources = [
        ("I-485 库存(月)", newest_inventory_month(), 3),
        ("DOS 签发量(月)", _newest_month(DOS_DIR, "iv_issuance_*.xlsx",
                                       r"iv_issuance_([a-z]+)_(\d{4})"), 5),
        ("I-140 季度收件", _newest_quarter("I140_FY*_Q*.xlsx", r"I140_FY(\d+)_Q(\d+)"), 9),
        ("I-140 待签(季)", _newest_quarter("I140_I360_I526_Approved_FY*_Q*.xlsx",
                                          r"Approved_FY(\d+)_Q(\d+)"), 9),
    ]
    lines, stale = ["## 数据源新鲜度巡检"], []
    for name, ym, budget in sources:
        if ym is None:
            lines.append(f"  {name}: ❓ 本地无文件")
            stale.append(f"{name} 本地无任何文件")
            continue
        b = behind(ym)
        flag = "⚠️漏抓?" if b > budget else "✅"
        lines.append(f"  {name}: 最新 {ym[0]}-{ym[1]:02d}（落后 {b} 月，预算 {budget}）{flag}")
        if b > budget:
            stale.append(f"{name} 仅到 {ym[0]}-{ym[1]:02d}（落后 {b} 月，疑似漏抓/改名，请核查 URL）")
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

    # 有漏抓 → 抓官网列表页打印真实链接，判断改名 vs 未发布(随告警同跑)
    diag = []
    if stale:
        stale_names = [s.split(" 仅到")[0].split(" 本地无")[0] for s in stale]
        diag = diagnose(stale_names)

    sp = os.environ.get("GITHUB_STEP_SUMMARY")
    if sp:
        try:
            with open(sp, "a", encoding="utf-8") as fh:
                fh.write("\n".join(report + diag) + "\n")
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

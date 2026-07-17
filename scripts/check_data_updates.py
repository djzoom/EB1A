#!/usr/bin/env python3
"""
Check USCIS and DOS websites for new data files and download them.

Usage:
    python scripts/check_data_updates.py              # check + download
    python scripts/check_data_updates.py --dry-run    # check only, no download
"""
import argparse
import json
import os
import re
import sys
import urllib.parse
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


# travel.state.gov(Akamai)对非浏览器 UA 返回 403(2026-07 起连 Actions runner 也被挡),
# 用完整浏览器头提高通过率;仍被挡时靠锚点文件兜底(见 _dos_anchor)。
BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _request(url: str, method: str = "GET") -> urllib.request.Request:
    req = urllib.request.Request(url, method=method)
    for k, v in BROWSER_HEADERS.items():
        req.add_header(k, v)
    return req


def _get_text(url: str) -> str:
    """GET 页面文本(失败返回空串并打印 HTTP 状态,便于区分 403被挡/404没发)。
    仅 runner 能真正访问官网,容器/沙箱会被挡。"""
    try:
        resp = urllib.request.urlopen(_request(url), timeout=30)
        return resp.read().decode("utf-8", "ignore")
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
        print(f"  无法获取页面 {url}: {e}")
        return ""


DOS_LIST_PAGE = ("https://travel.state.gov/content/travel/en/legal/visa-law0/visa-statistics/"
                 "immigrant-visa-statistics/monthly-immigrant-visa-issuances.html")


def _wayback_recent_text(url, max_age_days=35):
    """官网屏蔽 runner 时的兜底：取该页 Wayback 新近(≤max_age_days 天)快照的文本。
    过旧快照会低估『官方最新』造成假阴性（官方恢复发布却报"没发"），故宁可弃用，
    并请求主动存档刷新（Save Page Now，匿名 GET 实测会真实触发抓取），下次巡检再读。"""
    snap = None
    try:
        body = _get_text("https://archive.org/wayback/available?url="
                         + urllib.parse.quote(url, safe=""))
        if body:
            snap = json.loads(body).get("archived_snapshots", {}).get("closest")
    except ValueError:
        snap = None
    if snap and snap.get("available") and str(snap.get("status")) == "200":
        try:
            ts = datetime.strptime(snap["timestamp"], "%Y%m%d%H%M%S")
        except (ValueError, KeyError):
            ts = None
        if ts and (datetime.utcnow() - ts).days <= max_age_days:
            print(f"  [wayback] 官网不可达，改用 {ts:%Y-%m-%d} 的列表页快照核对官方最新")
            return _get_text(snap["url"])
        print("  [wayback] 列表页快照过旧，弃用并请求刷新存档（下次巡检读取）")
    else:
        print("  [wayback] 列表页暂无可用快照，请求主动存档（下次巡检读取）")
    try:
        urllib.request.urlopen(_request("https://web.archive.org/save/" + url), timeout=15)
    except (urllib.error.URLError, OSError, TimeoutError):
        pass
    return ""


def dos_official_latest():
    """从 DOS 列表页解析"官方实际已发布"的最新 FSC/出生地 月度签发 (year, month)。
    只有官方比本地新才算真漏抓——消除"按日历落后但官方根本没发"的误报。
    正则不锚定 Excel/FY 路径:xlsx 和 PDF 链接都算"官方已发布",并兼容
    NOVEMBER2021 这类无空格的历史命名变体（Wayback 快照里的改写链接同样匹配）。
    官网被挡(403)时退而读列表页的新近 Wayback 快照——官方恢复发布也能在
    ≤35 天内被发现,不再依赖锚点 120 天过期提醒;两路都不可得才返回 None。"""
    html = _get_text(DOS_LIST_PAGE)
    if not html:
        html = _wayback_recent_text(DOS_LIST_PAGE)
    if not html:
        return None
    best = None
    for mon, yr in re.findall(
            r'([A-Za-z]+)(?:%20|\s)?(\d{4})%20-%20IV%20Issuances%20by%20FSC', html):
        ml = mon.lower()
        if ml in MONTHS:
            ym = (int(yr), MONTHS.index(ml) + 1)
            if best is None or ym > best:
                best = ym
    if best is None:
        print("  DOS 列表页已取回但未解析到任何 FSC 月度链接——页面结构可能已改版,请人工核查")
    return best


def _dos_anchor():
    """读取 data/dos_publication_anchor.json —— 人工核实的"官方实际最新发布"锚点。
    官网对 runner 不可达(403 反爬)时,以锚点代替官网核对:本地 ≥ 锚点即"官方停更,
    非漏抓",不告警;锚点超过 valid_days 未复核则提醒人工确认(防止官方恢复发布后失聪)。
    返回 ((year, month), verified_on: datetime, valid_days) 或 None。"""
    import json
    p = REPO_ROOT / "data" / "dos_publication_anchor.json"
    if not p.exists():
        return None
    try:
        with open(p, encoding="utf-8") as fh:
            d = json.load(fh)
        m = re.match(r"(\d{4})-(\d{2})$", d["latest"])
        ver = datetime.strptime(d["verified_on"], "%Y-%m-%d")
        return (int(m.group(1)), int(m.group(2))), ver, int(d.get("valid_days", 120))
    except (OSError, ValueError, KeyError, AttributeError, TypeError):
        print("  dos_publication_anchor.json 解析失败,忽略锚点")
        return None


def _supplement_latest_quarter():
    """data/i140_china_receipts_supplement.json 里最新季度的"季度末" (year, month)。
    社区手工补充的收件数据已进模型,故新鲜度应把它算上(否则误报 xlsx 漏抓)。"""
    import json
    p = REPO_ROOT / "data" / "i140_china_receipts_supplement.json"
    if not p.exists():
        return None
    try:
        with open(p, encoding="utf-8") as fh:
            quarters = json.load(fh).get("quarters", {})
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

    # DOS：对照官网列表页"实际已发布最新"。官方比本地新才算真漏抓(消除日历误报)。
    # 官网不可达(403 反爬)时退而对照人工锚点;两者都没有才落到日历预算。
    def fmt(ym):
        return f"{ym[0]}-{ym[1]:02d}"
    dos_local = _newest_month(DOS_DIR, "iv_issuance_*.xlsx", r"iv_issuance_([a-z]+)_(\d{4})")
    dos_official = dos_official_latest()
    anchor = _dos_anchor()
    if dos_official is None and anchor:
        aym, ver, valid = anchor
        age = (now - ver).days
        if dos_local and dos_local >= aym:
            if age <= valid:
                lines.append(f"  DOS 签发量(月): 本地 {fmt(dos_local)} = 锚点官方最新 {fmt(aym)} ✅"
                             f"（官网不可达；{ver:%Y-%m-%d} 人工核实官方停更于 {fmt(aym)}，非漏抓）")
            else:
                lines.append(f"  DOS 签发量(月): 本地 {fmt(dos_local)}；锚点已 {age} 天未复核 ⚠️")
                stale.append(f"DOS 官网持续不可达且锚点已 {age} 天(>{valid})未复核"
                             f"（{ver:%Y-%m-%d} 核实官方仅发至 {fmt(aym)}）——"
                             "请人工确认官方是否恢复发布并更新 data/dos_publication_anchor.json")
        else:
            loc = fmt(dos_local) if dos_local else "无"
            lines.append(f"  DOS 签发量(月): 本地 {loc} < 锚点官方 {fmt(aym)} ⚠️真漏抓")
            stale.append(f"DOS 官方(人工锚点)已发布 {fmt(aym)} 但本地仅 {loc}，请修抓取/URL")
    elif dos_official is None:
        calendar("DOS 签发量(月)", dos_local, 5, "（官网不可达，按日历预算）")
    elif dos_local is None or dos_official > dos_local:
        loc = f"{dos_local[0]}-{dos_local[1]:02d}" if dos_local else "无"
        lines.append(f"  DOS 签发量(月): 官方已发 {dos_official[0]}-{dos_official[1]:02d}，本地 {loc} ⚠️真漏抓")
        stale.append(f"DOS 官方已发布 {dos_official[0]}-{dos_official[1]:02d} 但本地缺，请修抓取/URL")
    else:
        lines.append(f"  DOS 签发量(月): 本地 {dos_local[0]}-{dos_local[1]:02d} = 官方最新 ✅（官方暂未发更新）")

    # I-140 收件：自动抓取(xlsx 或 *_rec_cob.csv)与 supplement 取较新——衡量"数据是否已在模型里"
    i140_auto = max([x for x in (
        _newest_quarter("I140_FY*_Q*.xlsx", r"I140_FY(\d+)_Q(\d+)"),
        _newest_quarter("I140_FY*_Q*_rec_cob.csv", r"I140_FY(\d+)_Q(\d+)"),
    ) if x], default=None)
    i140_sup = _supplement_latest_quarter()
    i140_latest = max([x for x in (i140_auto, i140_sup) if x], default=None)
    calendar("I-140 季度收件", i140_latest, 9)
    if i140_auto and i140_sup and i140_sup > i140_auto:
        lines.append(f"    (注:已自动抓到 {i140_auto[0]}-{i140_auto[1]:02d}(xlsx/CSV 均支持)；"
                     f"更新的 {i140_sup[0]}-{i140_sup[1]:02d} 暂由 supplement.json 提供，"
                     "待 USCIS 发布该季文件后自动接替)")

    # I-140 待签(季)：USCIS 列表页不可抓 → 日历预算(当前 ✅)
    calendar("I-140 待签(季)", _newest_quarter("I140_I360_I526_Approved_FY*_Q*.xlsx",
                                               r"Approved_FY(\d+)_Q(\d+)"), 9)
    return lines, stale


def probe_status(url: str):
    """HEAD 探测,返回 HTTP 状态码(连接失败返回 None)。403=被反爬挡,404=文件不存在。"""
    try:
        resp = urllib.request.urlopen(_request(url, method="HEAD"), timeout=15)
        return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except (urllib.error.URLError, OSError):
        return None


def probe_url(url: str) -> bool:
    return probe_status(url) == 200


_probe_diag_done = set()


def probe_diag(source: str, url: str):
    """探测并在该数据源首次未命中时打印一行状态码诊断。
    区分 403(被反爬挡)与 404(官方未发布/命名不符)正是 2026-07 DOS 误报的教训——
    USCIS 各源若也被封锁,没有这行日志就会静默失败、几个月后才以误导文案告警。"""
    st = probe_status(url)
    if st != 200 and source not in _probe_diag_done:
        _probe_diag_done.add(source)
        name = url.rsplit("/", 1)[-1][:60]
        print(f"  [诊断] {source} 首个缺失项探测 {name} → HTTP {st}"
              "（403=被反爬挡，404=官方未发布/命名不符）")
    return st


def download(url: str, dest: Path) -> bool:
    try:
        resp = urllib.request.urlopen(_request(url), timeout=30)
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
            if probe_diag("I-485库存", url) == 200:
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
    """Check for new I-140 quarterly 收件(Rec-COB) reports.

    USCIS 该系列近年命名多变：旧为多 sheet 的 i140_fyYYYY_qN.xlsx(含 Rec-COB 表)，
    近期改为 CSV i140_fyYY_qN_rec_cob.csv。这里对每个缺失季度按候选清单探测，
    命中即按原扩展名下载(xlsx→I140_FY..._Q..xlsx；csv→..._rec_cob.csv)。
    首次抓到 CSV 时打印表头几行到日志，便于据真实格式补解析器(避免盲解析出错)。"""
    new_files = []
    now = datetime.now()
    current_fy = now.year + 1 if now.month >= 10 else now.year

    for fy in range(2022, current_fy + 2):
        for q in range(1, 5):
            local_xlsx = USCIS_DIR / f"I140_FY{fy}_Q{q}.xlsx"
            local_csv = USCIS_DIR / f"I140_FY{fy}_Q{q}_rec_cob.csv"
            if local_xlsx.exists() or local_csv.exists():
                continue

            yy = fy % 100
            # (远端文件名, 本地落地名)；先 xlsx(各后缀)后 CSV(4位/2位 FY)
            candidates = [
                (f"i140_fy{fy}_q{q}.xlsx", local_xlsx),
                (f"i140_fy{fy}_q{q}_0.xlsx", local_xlsx),
                (f"i140_fy{fy}_q{q}_v1.xlsx", local_xlsx),
                (f"i140_fy{fy}_q{q}_rec_cob.csv", local_csv),
                (f"i140_fy{yy}_q{q}_rec_cob.csv", local_csv),
            ]
            for remote, local in candidates:
                url = f"{USCIS_BASE}/{remote}"
                if probe_diag("I-140收件", url) != 200:
                    continue
                new_files.append(str(local.relative_to(REPO_ROOT)))
                if not dry_run:
                    if download(url, local):
                        print(f"  DOWNLOADED: {local.name}  <- {remote}")
                        if local.suffix == ".csv":
                            _dump_csv_head(local)   # 让 runner 日志暴露真实格式
                    else:
                        new_files.pop()
                else:
                    print(f"  AVAILABLE: {local.name}  <- {remote}")
                break

    return new_files


def _dump_csv_head(path, n=6):
    """打印 CSV 前 n 行到日志/运行摘要——用于据真实列结构补写解析器。"""
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            head = [next(fh).rstrip("\n") for _ in range(n)]
    except (OSError, StopIteration) as e:
        head = [f"(读取失败: {e})"]
    msg = [f"## 新 CSV 格式预览: {path.name}"] + [f"  {ln}" for ln in head]
    for ln in msg:
        print(ln)
    sp = os.environ.get("GITHUB_STEP_SUMMARY")
    if sp:
        try:
            with open(sp, "a", encoding="utf-8") as fh:
                fh.write("\n".join(msg) + "\n")
        except OSError:
            pass


def check_i140_approved(dry_run: bool) -> list[str]:
    """Check for new I-140/I-360/I-526 Approved Awaiting Visa reports."""
    new_files = []
    now = datetime.now()
    current_fy = now.year + 1 if now.month >= 10 else now.year

    for fy in range(2024, current_fy + 2):
        for q in range(1, 5):
            local = USCIS_DIR / f"I140_I360_I526_Approved_FY{fy}_Q{q}.xlsx"
            if local.exists():
                continue

            # USCIS 近期给文件名加了版本后缀(如 ..._q1_v1.xlsx);按 v2→v1→无后缀→_0 顺序探测
            stem = f"eb_i140_i360_i526_performancedata_fy{fy}_q{q}"
            for suffix in ("_v2", "_v1", "", "_0"):
                url = f"{USCIS_BASE}/{stem}{suffix}.xlsx"
                if probe_diag("I-140待签", url) == 200:
                    new_files.append(str(local.relative_to(REPO_ROOT)))
                    if not dry_run:
                        if download(url, local):
                            print(f"  DOWNLOADED: {local.name}  <- {stem}{suffix}.xlsx")
                        else:
                            new_files.pop()
                    else:
                        print(f"  AVAILABLE: {local.name}  <- {stem}{suffix}.xlsx")
                    break

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
    """Check for new DOS Monthly IV Issuance files.

    每个缺失月按候选命名探测(标准"MONTH%20YYYY"+历史出现过的无空格"MONTHYYYY"变体)。
    对第一个缺失月打印探测 HTTP 状态码:403=整站反爬挡了 runner(修 UA/等解封),
    404=官方确实没发该月(配合锚点判定停更),二者含义完全不同。"""
    new_files = []
    now = datetime.now()
    current_fy = now.year + 1 if now.month >= 10 else now.year

    for fy in range(2024, current_fy + 1):
        for month_name, cal_year in fy_months(fy):
            if cal_year > now.year or (cal_year == now.year and MONTHS.index(month_name) + 1 > now.month):
                continue

            local = DOS_DIR / f"iv_issuance_{month_name}_{cal_year}.xlsx"
            if local.exists():
                continue

            tail = ("%20-%20IV%20Issuances%20by%20FSC%20or%20Place%20of%20Birth"
                    "%20and%20Visa%20Class.xlsx")
            mon_up = month_name.upper()
            candidates = [
                f"{DOS_BASE}/FY{fy}/{mon_up}%20{cal_year}{tail}",
                f"{DOS_BASE}/FY{fy}/{mon_up}{cal_year}{tail}",   # NOVEMBER2021 式无空格变体
            ]
            for url in candidates:
                if probe_diag("DOS签发", url) != 200:
                    continue
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

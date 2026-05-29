#!/usr/bin/env python3
"""
统计近 N 期签证公告的"实际发布日期"分布，并回测候选嗅探窗口的覆盖率 vs 请求量。

取日期的优先级：
  1) 页面 HTML 里的 lastPublishedDate / releaseDate 等元数据
  2) HTTP 响应头 Last-Modified（archived 静态页通常可靠）
首个仍取不到日期的页面会打印诊断片段，便于定位真实字段。

用法：
    python scripts/analyze_release_times.py            # 默认近 36 期
    python scripts/analyze_release_times.py --months 24
    python scripts/analyze_release_times.py --url <single-url>   # 调试单页（含诊断）

需在能访问 travel.state.gov 的环境运行（GitHub Actions runner 可；本地沙箱会 403）。
"""
import argparse
import re
import urllib.request
import urllib.error
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from collections import Counter

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
MONTHS = ["january", "february", "march", "april", "may", "june",
          "july", "august", "september", "october", "november", "december"]
WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

HTML_PATTERNS = [
    r'"lastPublishedDate"\s*:\s*"([^"]+)"',
    r'lastPublishedDate["\']?\s*content=["\']([^"\']+)',
    r'name=["\']lastPublishedDate["\'][^>]*content=["\']([^"\']+)',
    r'"releaseDate"\s*:\s*"([^"]+)"',
    r'Last Published Date[^0-9]{0,40}(\d{1,2}/\d{1,2}/\d{4})',
    r'Last Published Date[^0-9]{0,40}(\d{4}-\d{2}-\d{2})',
    r'datetime=["\'](\d{4}-\d{2}-\d{2})',
    r'"datePublished"\s*:\s*"([^"]+)"',
    r'"dateModified"\s*:\s*"([^"]+)"',
]


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "ignore"), r.headers.get("Last-Modified")


def parse_any_date(raw):
    raw = raw.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw[:len(fmt)], fmt).date()
        except ValueError:
            pass
    m = re.search(r'(\d{4}-\d{2}-\d{2})|(\d{1,2}/\d{1,2}/\d{4})', raw)
    if m:
        s = m.group(0)
        for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                pass
    return None


def extract_date(html, last_modified):
    for pat in HTML_PATTERNS:
        m = re.search(pat, html, re.I)
        if m:
            d = parse_any_date(m.group(1))
            if d:
                return d, "html"
    if last_modified:
        try:
            return parsedate_to_datetime(last_modified).date(), "last-modified"
        except Exception:
            pass
    return None, None


def diagnostics(html, last_modified):
    print("  --- 诊断（首个无日期页面）---")
    print("  Last-Modified 头:", last_modified)
    seen = 0
    for kw in ("publish", "modified", "updated", "releasedate", "datetime", "datepublished"):
        for m in re.finditer(kw, html, re.I):
            s = max(0, m.start() - 40)
            snippet = re.sub(r"\s+", " ", html[s:m.start() + 60])
            print(f"  [{kw}] …{snippet}…")
            seen += 1
            if seen >= 12:
                break
        if seen >= 12:
            break
    if seen == 0:
        print("  （页面里没有 publish/modified/updated 等字样；可能只能靠 Last-Modified 头）")
    print("  ---------------------------")


def bulletin_url(year, month):
    fy = year + 1 if month >= 10 else year
    return ("https://travel.state.gov/content/travel/en/legal/visa-law0/"
            f"visa-bulletin/{fy}/visa-bulletin-for-{MONTHS[month-1]}-{year}.html")


def last_n_bulletins(n):
    today = date.today()
    y, m = today.year, today.month
    out = []
    for _ in range(n):
        out.append((y, m))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=36)
    ap.add_argument("--url")
    args = ap.parse_args()

    if args.url:
        html, lm = fetch(args.url)
        d, src = extract_date(html, lm)
        print("发布日期:", d, "来源:", src)
        if not d:
            diagnostics(html, lm)
        return

    rows, blocked, dumped = [], 0, False
    for (y, m) in last_n_bulletins(args.months):
        url = bulletin_url(y, m)
        try:
            html, lm = fetch(url)
            d, src = extract_date(html, lm)
            rows.append((y, m, d))
            print(f"{y}-{m:02d}  发布日 {d}  来源 {src}")
            if d is None and not dumped:
                diagnostics(html, lm)
                dumped = True
        except urllib.error.HTTPError as e:
            if e.code == 403:
                blocked += 1
            print(f"{y}-{m:02d}  HTTP {e.code}")
        except Exception as e:
            print(f"{y}-{m:02d}  ERR {type(e).__name__}")

    if blocked:
        print(f"\n⚠️  {blocked} 期 403——该环境被屏蔽。")

    got = [(y, m, d) for (y, m, d) in rows if d]
    if not got:
        print("\n仍未取到日期。请把上面的诊断片段贴出，据此修正解析。")
        return

    days = [d.day for (_, _, d) in got]
    wds = [d.weekday() for (_, _, d) in got]
    print(f"\n===== 发布日期分布（{len(got)}/{len(rows)} 期取到）=====")
    print("按几号:", dict(sorted(Counter(days).items())))
    print("按星期:", {WD[k]: v for k, v in sorted(Counter(wds).items())})
    print(f"几号范围: {min(days)}–{max(days)}  中位: {sorted(days)[len(days)//2]}")
    print(f"周末发布: {sum(1 for w in wds if w >= 5)} 次（应为0）")

    print("\n===== 回测候选窗口（覆盖率 / 每月最坏请求数，命中即停后大降）=====")
    for name, lo, hi in [("9–16号", 9, 16), ("10–15号", 10, 15),
                         ("11–15号", 11, 15), ("12–14号", 12, 14)]:
        cov = sum(1 for d in days if lo <= d <= hi)
        wd_in = sorted(set(WD[d.weekday()] for (_, _, d) in got if lo <= d.day <= hi))
        # 每天 30 分钟一次、ET 12–20（8h=16槽）；窗口天数 × 16
        worst = (hi - lo + 1) * 16
        print(f"  {name}: 覆盖 {cov}/{len(got)} ({100*cov//len(got)}%), "
              f"涉及星期 {wd_in}, 最坏 ~{worst} 次/月")


if __name__ == "__main__":
    main()

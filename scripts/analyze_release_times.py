#!/usr/bin/env python3
"""
统计近 N 期签证公告的"实际发布日期"分布，并回测候选嗅探窗口。

重要：travel.state.gov 的 HTTP Last-Modified 头被 CDN 设成"当前时间"，不是发布日，已弃用。
只从页面 HTML 抠发布日期；抠不到就打印诊断片段（前 2 个无日期页面）以定位真实字段。

用法：
    python scripts/analyze_release_times.py            # 默认近 36 期
    python scripts/analyze_release_times.py --url <url> # 调试单页（必出诊断）
"""
import argparse
import re
import urllib.request
import urllib.error
from datetime import date, datetime
from collections import Counter

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
MONTHS = ["january", "february", "march", "april", "may", "june",
          "july", "august", "september", "october", "november", "december"]
MON_RE = "January|February|March|April|May|June|July|August|September|October|November|December"
WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

HTML_PATTERNS = [
    r'"lastPublishedDate"\s*:\s*"([^"]+)"',
    r'lastPublishedDate["\']?\s*content=["\']([^"\']+)',
    r'"datePublished"\s*:\s*"([^"]+)"',
    r'"dateModified"\s*:\s*"([^"]+)"',
    r'Last Published Date[^0-9A-Za-z]{0,40}(\d{1,2}/\d{1,2}/\d{4})',
    r'Last Published Date[^0-9A-Za-z]{0,40}(\d{4}-\d{2}-\d{2})',
    # 文字日期，如 "April 14, 2026"，常出现在 published/updated 附近
    r'(?:published|updated|posted)[^A-Za-z0-9]{0,30}((?:' + MON_RE + r')\s+\d{1,2},\s+\d{4})',
]


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "ignore"), r.headers.get("Last-Modified")


def parse_any_date(raw):
    raw = raw.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y"):
        try:
            return datetime.strptime(raw[:len(fmt) + 4], fmt).date()
        except ValueError:
            pass
    return None


def extract_date(html):
    for pat in HTML_PATTERNS:
        m = re.search(pat, html, re.I)
        if m:
            d = parse_any_date(m.group(1))
            if d:
                return d
    return None


def diagnostics(html, last_modified, url):
    print(f"  --- 诊断: {url.rsplit('/',1)[1]} ---")
    print("  Last-Modified 头(仅参考，已知=CDN当前时间):", last_modified)
    seen = 0
    for kw in ("published", "publish", "last updated", "updated", "posted",
               "releasedate", "datetime", "datepublished", "datemodified"):
        for m in re.finditer(re.escape(kw), html, re.I):
            s = max(0, m.start() - 50)
            snippet = re.sub(r"\s+", " ", html[s:m.start() + 70])
            print(f"  [{kw}] …{snippet}…")
            seen += 1
            if seen >= 14:
                break
        if seen >= 14:
            break
    # 页面后 40% 里的文字日期（AEM 常把发布日放在页脚）
    tail = html[int(len(html) * 0.6):]
    dts = re.findall(r'(?:' + MON_RE + r')\s+\d{1,2},\s+\d{4}|\d{1,2}/\d{1,2}/\d{4}', tail)
    print("  页脚区文字日期样本:", list(dict.fromkeys(dts))[:8] or "无")
    if seen == 0:
        print("  （无 publish/updated 字样）")
    print("  ------------------------")


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
        d = extract_date(html)
        print("发布日期:", d)
        diagnostics(html, lm, args.url)
        return

    rows, dumped = [], 0
    for (y, m) in last_n_bulletins(args.months):
        url = bulletin_url(y, m)
        try:
            html, lm = fetch(url)
            d = extract_date(html)
            rows.append((y, m, d))
            print(f"{y}-{m:02d}  发布日 {d}")
            if d is None and dumped < 2:
                diagnostics(html, lm, url)
                dumped += 1
        except Exception as e:
            print(f"{y}-{m:02d}  ERR {type(e).__name__}")

    got = [(y, m, d) for (y, m, d) in rows if d]
    print(f"\n取到日期 {len(got)}/{len(rows)} 期")
    if not got:
        print("HTML 里没抠到发布日期。请把上面的「诊断」片段贴出，据此定位字段；"
              "若页面确实不含发布日，则放弃历史挖掘，改用探测器在线自学习真实发布时刻。")
        return

    days = [d.day for (_, _, d) in got]
    wds = [d.weekday() for (_, _, d) in got]
    print(f"\n===== 发布日期分布 =====")
    print("按几号:", dict(sorted(Counter(days).items())))
    print("按星期:", {WD[k]: v for k, v in sorted(Counter(wds).items())})
    print(f"几号范围: {min(days)}–{max(days)}  中位: {sorted(days)[len(days)//2]}")
    print(f"周末发布: {sum(1 for w in wds if w >= 5)} 次（应为0）")
    print("\n===== 回测候选窗口 =====")
    for name, lo, hi in [("9–16号", 9, 16), ("10–15号", 10, 15), ("11–15号", 11, 15)]:
        cov = sum(1 for d in days if lo <= d <= hi)
        worst = (hi - lo + 1) * 16  # ET12-20、30min一次=16槽/天
        print(f"  {name}: 覆盖 {cov}/{len(got)} ({100*cov//len(got)}%), 最坏 ~{worst} 次/月")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
统计近 N 期签证公告的"实际发布日期"分布，并回测候选嗅探窗口的覆盖率 vs 请求量。

数据来源：travel.state.gov 每期 bulletin 页面的元数据 lastPublishedDate（只有日期，没有时刻；
时刻分布由 sniff_visa_bulletin.py 在线自学习记录）。

用法：
    python scripts/analyze_release_times.py            # 默认近 36 期
    python scripts/analyze_release_times.py --months 24
    python scripts/analyze_release_times.py --url <single-url>   # 调试单页解析

注意：本脚本需在能访问 travel.state.gov 的环境运行（GitHub Actions runner 或本机）。
沙箱/部分 IP 会被 gov 返回 403。
"""
import argparse
import re
import sys
import urllib.request
import urllib.error
from datetime import date, datetime
from collections import Counter

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
MONTHS = ["january", "february", "march", "april", "may", "june",
          "july", "august", "september", "october", "november", "december"]
WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def bulletin_url(year, month):
    """month: 1-12。URL 的 FY 文件夹 = 财年（10月起跳下一财年）。"""
    fy = year + 1 if month >= 10 else year
    return ("https://travel.state.gov/content/travel/en/legal/visa-law0/"
            f"visa-bulletin/{fy}/visa-bulletin-for-{MONTHS[month-1]}-{year}.html")


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "ignore")


def extract_publish_date(html):
    """从 AEM 元数据里抠发布日期。尝试多种字段，返回 datetime.date 或 None。"""
    patterns = [
        r'lastPublishedDate"\s*content="([^"]+)"',
        r'"lastPublishedDate"\s*:\s*"([^"]+)"',
        r'name="releaseDate"\s*content="([^"]+)"',
        r'dcterms\.(?:modified|created)"\s*content="([^"]+)"',
        r'"publishDate"\s*:\s*"([^"]+)"',
    ]
    for pat in patterns:
        m = re.search(pat, html, re.I)
        if m:
            raw = m.group(1).strip()
            for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S.%f%z"):
                try:
                    return datetime.strptime(raw[:len(fmt)+6], fmt).date()
                except ValueError:
                    continue
            # 退而求其次：抓一个 YYYY-MM-DD 或 M/D/YYYY
            m2 = re.search(r'(\d{4}-\d{2}-\d{2})|(\d{1,2}/\d{1,2}/\d{4})', raw)
            if m2:
                s = m2.group(0)
                for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
                    try:
                        return datetime.strptime(s, fmt).date()
                    except ValueError:
                        continue
    return None


def last_n_bulletins(n):
    """返回最近 n 期 (year, month)，从本月往前。"""
    today = date.today()
    y, m = today.year, today.month
    out = []
    for _ in range(n):
        out.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=36)
    ap.add_argument("--url", help="只解析这一个 URL（调试用）")
    args = ap.parse_args()

    if args.url:
        try:
            d = extract_publish_date(fetch(args.url))
            print("发布日期:", d)
        except Exception as e:
            print("FAIL:", type(e).__name__, str(e)[:200])
        return

    rows = []  # (bulletin_year, bulletin_month, publish_date)
    blocked = 0
    for (y, m) in last_n_bulletins(args.months):
        url = bulletin_url(y, m)
        try:
            d = extract_publish_date(fetch(url))
            rows.append((y, m, d))
            print(f"{y}-{m:02d}  发布日 {d}  ({url.rsplit('/',1)[1]})")
        except urllib.error.HTTPError as e:
            if e.code == 403:
                blocked += 1
            print(f"{y}-{m:02d}  HTTP {e.code}")
        except Exception as e:
            print(f"{y}-{m:02d}  ERR {type(e).__name__}")

    if blocked:
        print(f"\n⚠️  {blocked} 期被 gov 返回 403——当前环境可能被屏蔽（沙箱常见）。"
              "请在 GitHub Actions 里手动 dispatch 本脚本，runner IP 通常可访问。")

    got = [(y, m, d) for (y, m, d) in rows if d]
    if not got:
        print("\n没有拿到任何发布日期，无法统计/回测。")
        return

    days = [d.day for (_, _, d) in got]
    wds = [d.weekday() for (_, _, d) in got]
    print(f"\n===== 发布日期分布（{len(got)} 期）=====")
    print("按几号:", dict(sorted(Counter(days).items())))
    print("按星期:", {WD[k]: v for k, v in sorted(Counter(wds).items())})
    print(f"几号范围: {min(days)}–{max(days)}  中位: {sorted(days)[len(days)//2]}")
    weekend = sum(1 for w in wds if w >= 5)
    print(f"周末发布次数: {weekend}（应为 0 → 可放心扣除周末）")

    print("\n===== 回测候选嗅探窗口（覆盖率 vs 每月最坏请求数）=====")
    # 每月最坏请求数 = 窗口天数 × 每天槽数（命中即停，故为上界）
    candidates = [
        ("9–16 号, 每30min, ET12-20(8h)", 9, 16, 8 * 2),
        ("10–15 号, 每30min, ET12-20(8h)", 10, 15, 8 * 2),
        ("自学习收窄: 命中星期±1, 命中时刻±1h, 每30min(3h)", None, None, 3 * 2),
    ]
    for name, lo, hi, slots_per_day in candidates:
        if lo is None:
            covered = len(got)  # 自学习窗口按定义覆盖历史命中
            span_days = 3       # 收窄后约 3 个工作日
        else:
            covered = sum(1 for d in days if lo <= d <= hi)
            span_days = sum(1 for wd in range(lo, hi + 1))  # 粗略：窗口天数
        worst = span_days * slots_per_day
        print(f"  {name}: 覆盖 {covered}/{len(got)} ({100*covered//len(got)}%), "
              f"最坏 ~{worst} 次/月（命中即停后大幅下降）")


if __name__ == "__main__":
    main()

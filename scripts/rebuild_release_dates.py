#!/usr/bin/env python3
"""用 Wayback CDX API 重建签证公告的发布日真值。

为什么需要：现有 RELEASE_HISTORY 的来源不明、不可独立验证，其中 2026-09 一期
甚至是抓取器故障期间按历史规律回填的伪造值（整点 12:00 ET）。本脚本改用可复核的
公开档案作为唯一来源，每条标注来源与精度。

精度语义（重要，勿混用）：
  CDX 返回的是「档案馆首次抓到 200 的时刻」，它是发布时间的【上界】——
  真实发布只会更早，不会更晚。故所有 CDX 值一律标 precision='upper_bound'。
  这也意味着：若早期条目取自上界，真实的「发布日后移」漂移只会比实测更大。

交叉校验：同时取索引页 visa-bulletin.html 的快照序列，观察其 "Current Visa Bulletin"
指向月份的变化时点，作为月份页首见的旁证。

用法：
    python scripts/rebuild_release_dates.py                 # 回溯 36 期，打印结果
    python scripts/rebuild_release_dates.py --months 24
    python scripts/rebuild_release_dates.py --write         # 同时写 data/release_dates_cdx.json

注意：本脚本需要能访问 web.archive.org。在被封锁的环境（如本仓库的 GitHub runner
出口 IP、或代理受限的容器）中会全部失败并如实报错，不会产出半真半假的数据。
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sniff_visa_bulletin import MONTHS, bulletin_url, next_month  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "release_dates_cdx.json")
INDEX_PAGE = "https://travel.state.gov/content/travel/en/legal/visa-law0/visa-bulletin.html"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120 Safari/537.36")
CDX = "https://web.archive.org/cdx/search/cdx"


def cdx_first_200(url, limit=1):
    """查该 URL 最早的 200 快照。返回 (datetime_utc, raw_timestamp) 或 None。"""
    q = urllib.parse.urlencode({
        "url": url, "output": "json", "fl": "timestamp,statuscode",
        "filter": "statuscode:200", "limit": str(limit),
    })
    req = urllib.request.Request(f"{CDX}?{q}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=40) as r:
        rows = json.loads(r.read().decode("utf-8", "ignore"))
    # 首行是表头
    if not rows or len(rows) < 2:
        return None
    ts = rows[1][0]
    return datetime.strptime(ts, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc), ts


def month_iter(back):
    """自本月起向前回溯 back 期，产出 (year, month)。"""
    now = datetime.now(timezone.utc)
    y, m = now.year, now.month
    for _ in range(back):
        yield y, m
        m -= 1
        if m == 0:
            y, m = y - 1, 12


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=36, help="回溯期数（默认 36）")
    ap.add_argument("--write", action="store_true", help="写入 data/release_dates_cdx.json")
    ap.add_argument("--sleep", type=float, default=1.0, help="每次查询间隔秒（避免被限流）")
    args = ap.parse_args()

    rows, failures = [], 0
    print(f"## Wayback CDX 重建发布日（回溯 {args.months} 期）\n")
    for y, m in month_iter(args.months):
        tag = f"{y}-{m:02d}"
        url = bulletin_url(y, m)
        try:
            hit = cdx_first_200(url)
        except Exception as e:
            failures += 1
            print(f"  {tag}: ❌ 查询失败 {type(e).__name__}: {str(e)[:70]}")
            time.sleep(args.sleep)
            continue
        if not hit:
            print(f"  {tag}: — 无 200 快照（该期可能太新，或档案馆未收录）")
            time.sleep(args.sleep)
            continue
        dt, raw = hit
        rows.append({
            "bulletin": tag,
            "first_seen_utc": dt.isoformat(),
            "release_date": dt.date().isoformat(),
            "source": "wayback_cdx",
            # CDX 首见 = 上界：真实发布不晚于此刻，只会更早
            "precision": "upper_bound",
            "cdx_timestamp": raw,
        })
        print(f"  {tag}: {dt:%Y-%m-%d %H:%M} UTC（上界，日={dt.day}）")
        time.sleep(args.sleep)

    rows.sort(key=lambda r: r["bulletin"])
    print(f"\n重建 {len(rows)} 期，失败 {failures} 期")

    if failures and not rows:
        print("\n⚠️ 全部查询失败——通常是出口 IP 被封或无外网。"
              "本脚本拒绝产出部分数据，请在可访问 web.archive.org 的环境重跑。")
        return 1

    if len(rows) >= 4:
        days = [datetime.fromisoformat(r["first_seen_utc"]).day for r in rows[-12:]]
        half = len(days) // 2
        mean = lambda a: sum(a) / len(a)
        print(f"\n近 {len(days)} 期发布日: {days}")
        print(f"  均值 {mean(days):.1f}  极差 {min(days)}–{max(days)}")
        if len(days) >= 6:
            drift = mean(days[half:]) - mean(days[:half])
            print(f"  漂移 {drift:+.1f} 天（后半段 vs 前半段）"
                  + ("  ← 注意：上界口径下真实漂移只会更大" if drift > 0 else ""))

    # 索引页交叉校验：观察 Current Visa Bulletin 指向的变化时点
    try:
        idx = cdx_first_200(INDEX_PAGE, limit=1)
        print(f"\n索引页最早 200 快照: {idx[0]:%Y-%m-%d} " if idx else "\n索引页无快照")
        print("  （索引页滞后于月份页，仅作旁证；勿用作首见判据）")
    except Exception as e:
        print(f"\n索引页交叉校验失败: {type(e).__name__}")

    if args.write:
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump({
                "_readme": [
                    "Wayback CDX 重建的签证公告发布日。每条 precision=upper_bound：",
                    "CDX 首见 200 是发布时间的上界，真实发布不晚于此刻。",
                    "据此做漂移分析时，真实漂移只会大于实测值。",
                ],
                "_generated_utc": datetime.now(timezone.utc).isoformat(),
                "rows": rows,
            }, f, ensure_ascii=False, indent=2)
        print(f"\n已写入 {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

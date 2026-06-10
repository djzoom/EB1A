#!/usr/bin/env python3
"""用 Wayback Machine 首次快照近似 DOS 签证公告的历史释出日期，回填 release_log
作为自学习冷启动样本，并据此推荐 sniff 的活跃日窗 / 时段 / 频率。

数据源：Wayback CDX API（公开、免鉴权）
  https://web.archive.org/cdx/search/cdx?url=<bulletin_url>&output=json&fl=timestamp&filter=statuscode:200&limit=3
取最早一次 200 快照的 timestamp(UTC) ≈ 该期上线时间。Wayback 抓取通常滞后数小时~1 天，
故只用其『日』近似释出日；『时』偏噪声，不回填（hour=None），留给真实命中去收窄时段窗口。

需在能访问 web.archive.org 的环境运行（GitHub runner / 有外网的本机；本仓库沙箱会 403）。

注：本工具为「分析用」——不写 release_log。日窗已固定为安全网(见 sniffer 的
DEFAULT_DAY_LO/HI)，核心高发区固化为 CORE_DAY_LO/HI；本脚本用于定期复核这些常量
是否仍贴合最新历史分布。

用法：
  python scripts/backfill_release_dates.py            # 拉 Wayback 历史并打印推荐窗口/核心区
  python scripts/backfill_release_dates.py --months 30
"""
import argparse
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sniff_visa_bulletin import bulletin_url, ET

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
CDX = ("https://web.archive.org/cdx/search/cdx?url={url}"
       "&output=json&fl=timestamp&filter=statuscode:200&limit=3")


def prev_month(y, m):
    return (y - 1, 12) if m == 1 else (y, m - 1)


def earliest_ts(url):
    """返回该 URL 在 Wayback 最早一次 200 快照的 UTC timestamp(YYYYMMDDhhmmss) 或 None。"""
    q = CDX.format(url=urllib.parse.quote(url, safe=""))
    req = urllib.request.Request(q, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    if not data:
        return None
    rows = data[1:] if data[0] and str(data[0][0]).lower() == "timestamp" else data
    return rows[0][0] if rows else None  # CDX 默认按 timestamp 升序 → 首行最早


def to_et(ts):
    dt = datetime.strptime(ts, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    return dt.astimezone(ET) if ET else dt


def pct(sorted_vals, p):
    n = len(sorted_vals)
    return sorted_vals[min(n - 1, max(0, int(math.ceil(p / 100 * n)) - 1))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=24)
    args = ap.parse_args()

    now = datetime.now(ET) if ET else datetime.utcnow()
    y, m = now.year, now.month
    samples = []
    print(f"# 用 Wayback 首次快照近似最近 {args.months} 期公告释出时刻\n")
    for _ in range(args.months):
        tag = f"{y}-{m:02d}"
        url = bulletin_url(y, m)
        try:
            ts = earliest_ts(url)
        except Exception as e:
            print(f"{tag}: 查询失败 {type(e).__name__}: {str(e)[:80]}")
            ts = None
        if ts:
            et = to_et(ts)
            samples.append({"bulletin": tag, "et": et})
            print(f"{tag}: 首照 ET {et:%Y-%m-%d %H:%M} (周{et.weekday() + 1}) day={et.day}")
        else:
            print(f"{tag}: 无快照")
        time.sleep(0.6)  # 礼貌限速
        y, m = prev_month(y, m)

    days = sorted(s["et"].day for s in samples)
    if not days:
        print("\n无样本，无法推荐（检查能否访问 web.archive.org）。")
        return
    n = len(days)
    p10, p50, p90 = pct(days, 10), pct(days, 50), pct(days, 90)
    wk = {}
    for s in samples:
        wk[s["et"].weekday()] = wk.get(s["et"].weekday(), 0) + 1
    wk_names = ["一", "二", "三", "四", "五", "六", "日"]

    rec_lo, rec_hi = max(1, p10 - 1), min(28, p90 + 1)
    span = rec_hi - rec_lo + 1
    exp_days = max(1, p50 - rec_lo + 1)

    print(f"\n## 释出『日』分布(ET)  n={n}  min={days[0]}  p10={p10}  中位={p50}  p90={p90}  max={days[-1]}")
    print("## 释出星期分布  " + "  ".join(f"周{wk_names[d]}={wk.get(d, 0)}" for d in range(7)))
    print("\n## 推荐 sniff 配置（最少请求 + 最及时）")
    print(f"   活跃日窗 DEFAULT_DAY_LO/HI = {rec_lo}, {rec_hi}   （覆盖 p10–p90 ±1，不漏抓晚发月份）")
    print(f"   活跃时段 DEFAULT_HOUR_LO/HI = 12, 18           （DOS 多在午后上线；真实命中后自动收窄）")
    print(f"   探测频率 = 活跃窗口内每 15 分钟一次            （窗口外门控零请求）")
    print(f"   预计请求量 ≤ {24 * span} 次/期(最坏，整窗未命中)；命中即停后期望 ≈ {24 * exp_days} 次/期")
    print(f"   建议核心高发区 CORE_DAY_LO/HI = {max(1, p10 - 1)}, {min(28, p90 + 1)}（密探）；"
          f"安全窗 DEFAULT_DAY 应更宽以兜住尾部晚发")
    print("\n(分析用：不写 release_log。如发现分布与现有 CORE_DAY/安全窗常量明显偏离，再据此手动调常量。)")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""判断"现在该不该开着自建 runner"，供 runner_ctl.sh auto 调用。

判定与探测器 run() 的目标口径保持一致（当月 + 下月中所有尚未定案的期），
数据读 GitHub 上 main 分支的实时状态而非本地 clone——工作流是往 main 推的，
本地 clone 可能已经落后好几天。

输出：第一行 on / off，第二行理由。退出码 0=on，10=off，2=判定失败。
判定失败时按 on 处理（宁可多开一会儿，也别漏掉当期公告）。

用法：
    python3 scripts/runner_window.py            # 打印决策
    python3 scripts/runner_window.py --verbose  # 附带各期定案状态
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sniff_visa_bulletin import UA, next_month, now_et  # noqa: E402

REPO = os.environ.get("EB1A_REPO", "djzoom/EB1A")
RAW = f"https://raw.githubusercontent.com/{REPO}/main"
# 公告定案后，USCIS 的 AOS 用表页通常还要滞后 1–2 天才更新，抓它同样需要住宅 IP。
# 所以"抓到公告"不等于"可以关"，再留几天把用表补判掉；超过宽限期就不再为它开着。
CHART_GRACE_DAYS = 7
# 历史 12 期发布日全部落在 12–20 号。过了这天还没抓到，就不是「官方还没发」，
# 而是托管探测出了问题——此时才值得让本机接管。
OVERDUE_DAY = 20


def _get(path, timeout=20):
    url = f"{RAW}/{path}?_cb={int(datetime.now().timestamp())}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore")


def settled(log, tag):
    """该期是否已定案（有记录且不是 partial）。"""
    return any(r.get("bulletin") == tag and not r.get("partial") for r in log)


def detected_at(log, tag):
    for r in log:
        if r.get("bulletin") == tag:
            raw = (r.get("detected_et") or "")[:10]
            try:
                return datetime.strptime(raw, "%Y-%m-%d")
            except ValueError:
                return None
    return None


def chart_pending():
    """返回 (是否待确认, 状态串)。抓不到时按"待确认"处理（保守，倾向多开一会儿）。"""
    try:
        html = _get("index.html", timeout=30)
    except Exception as e:
        return True, f"读取失败({type(e).__name__})"
    chart = re.search(r"var FILING_CHART = '([^']*)'", html)
    state = re.search(r"var FILING_CHART_STATE = '([^']*)'", html)
    c = chart.group(1) if chart else "?"
    s = state.group(1) if state else "unknown"
    return (c == "?" or s != "ok"), f"FILING_CHART={c} state={s}"


def decide(verbose=False):
    t = now_et()
    cur = (t.year, t.month)
    nxt = next_month(*cur)
    cur_tag, nxt_tag = f"{cur[0]}-{cur[1]:02d}", f"{nxt[0]}-{nxt[1]:02d}"

    try:
        log = json.loads(_get("data/release_log.json"))
    except Exception as e:
        return "on", f"无法读取 release_log（{type(e).__name__}）——按开处理，宁可多开也别漏抓"

    if verbose:
        print(f"# ET {t:%Y-%m-%d %H:%M}｜{cur_tag} {'已定案' if settled(log, cur_tag) else '未定案'}"
              f"｜{nxt_tag} {'已定案' if settled(log, nxt_tag) else '未定案'}", file=sys.stderr)

    if not settled(log, cur_tag):
        return "on", f"当月期 {cur_tag} 尚未定案——探测器会绕过发布窗门控直接补探，需要通道"

    if not settled(log, nxt_tag):
        # 公告本身托管 runner 就能抓到（实测：travel.state.gov 403 但 adoption.state.gov 200，
        # WAF 按 hostname 配规则）。所以发布窗内不必让本机常开——那是每月白开两周。
        # 只在「历史发布日 12–20 全部过完仍没抓到」时接管，作为托管探测失效的保险。
        if t.day > OVERDUE_DAY:
            return "on", (f"下月期 {nxt_tag} 未定案，且今日 {t.day} 号已过历史发布窗末（{OVERDUE_DAY} 号）"
                          "——托管探测疑似失效，本机接管")
        return "off", (f"{nxt_tag} 未定案，但仍在正常发布窗内（今日 {t.day} 号）——"
                       "公告由托管 runner 抓，本机不必开")

    pending, detail = chart_pending()
    if pending:
        d = detected_at(log, nxt_tag) or detected_at(log, cur_tag)
        age = (datetime.now() - d).days if d else 0
        if age <= CHART_GRACE_DAYS:
            return "on", (f"{nxt_tag} 已定案但 USCIS 递交用表待确认（{detail}），"
                          f"抓 USCIS 同样要住宅 IP——宽限期第 {age}/{CHART_GRACE_DAYS} 天")
        return "off", (f"{nxt_tag} 已定案；用表仍未确认（{detail}）但已超 {CHART_GRACE_DAYS} 天宽限，"
                       "不再为它长开——需要时手动 on 或人工录入")

    return "off", f"{cur_tag} 与 {nxt_tag} 均已定案、用表已确认（{detail}）——无待办"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    try:
        decision, reason = decide(args.verbose)
    except Exception as e:
        print("on")
        print(f"判定异常（{type(e).__name__}: {str(e)[:120]}）——按开处理")
        return 0
    print(decision)
    print(reason)
    return 0 if decision == "on" else 10


if __name__ == "__main__":
    sys.exit(main())

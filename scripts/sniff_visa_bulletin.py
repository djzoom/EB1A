#!/usr/bin/env python3
"""
自学习签证公告探测器（EB-1 中国大陆）。

设计目标：尽量轻 + 自己回测自己。
- 门控（命中即退、零请求）：按美东时间 America/New_York 判断 工作日 / 非联邦假日 /
  高概率日 / 高概率时段 / 是否已抓到目标月；任一不满足立即退出。
- 探测：对可预测的"下月 bulletin URL" 发 GET，404=未发，200=已发。
- 命中：解析 EB-1 中国大陆 表A(Final Action)/表B(Dates for Filing) + USCIS 当月开放表，
  写回 index.html；并把"本次实际探到的美东时刻"记进 data/release_log.json。
- 自学习：≥3 条真实记录后，把高概率"星期/几号/时段"窗口收窄到历史命中范围（±缓冲），
  下次门控更紧 → 越用越轻。探测频率由 workflow 的 cron 决定（每 30 分钟）。

依赖：仅标准库。需在能访问 travel.state.gov 的环境运行（Actions runner / 本机；沙箱会 403）。

用法：
    python scripts/sniff_visa_bulletin.py            # 正常运行（CI 调用）
    python scripts/sniff_visa_bulletin.py --dry-run  # 不写文件、不提交，只打印
    python scripts/sniff_visa_bulletin.py --force     # 跳过时间门控，强制探一次（调试）
"""
import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import date, datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:
    ET = None  # 老 Python 兜底；门控会退化为 UTC

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, "index.html")
LOG = os.path.join(ROOT, "data", "release_log.json")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
MONTHS = ["january", "february", "march", "april", "may", "june",
          "july", "august", "september", "october", "november", "december"]

# 美国联邦假日（每年初更新一次即可）。这几天 gov 不发布。
FED_HOLIDAYS = {
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-05-25", "2026-06-19",
    "2026-07-03", "2026-09-07", "2026-10-12", "2026-11-11", "2026-11-26", "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-05-31", "2027-06-18",
    "2027-07-05", "2027-09-06", "2027-10-11", "2027-11-11", "2027-11-25", "2027-12-24",
}

# 固定安全日窗（不因有限历史收窄，防早发/晚发漏抓）。7–26：历史多在 8–17，但偶有 20 号及其后。
DEFAULT_DAY_LO, DEFAULT_DAY_HI = 7, 26
DEFAULT_HOUR_LO, DEFAULT_HOUR_HI = 12, 20   # 美东 12:00–20:00（DOS 多在午后上线）
MIN_RECORDS_TO_TUNE = 3
# 分层探测：核心日(历史释出高发 10–17)全时段密探；窗口内其余为肩部日，仅少数时点稀疏探，省请求。
CORE_DAY_LO, CORE_DAY_HI = 10, 17
SHOULDER_HOURS = (13, 16, 19)   # 肩部日只在这些 ET 整点(及其 :30)探测；含傍晚 19 点以兜住晚发


def now_et():
    return datetime.now(ET) if ET else datetime.utcnow()


def bulletin_url(year, month):
    fy = year + 1 if month >= 10 else year
    return ("https://travel.state.gov/content/travel/en/legal/visa-law0/"
            f"visa-bulletin/{fy}/visa-bulletin-for-{MONTHS[month-1]}-{year}.html")


def next_month(y, m):
    return (y + 1, 1) if m == 12 else (y, m + 1)


def load_log():
    try:
        with open(LOG, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_log(rows):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def learned_window(log):
    """日窗固定为安全网（绝不因有限历史收窄 → 不漏早发/晚发）；仅从真实命中的『小时』收窄时段窗口。
    返回 (day_lo,day_hi,hour_lo,hour_hi,tuned?)。tuned 表示时段是否已按真实命中收窄。"""
    hours = [r["hour"] for r in log if r.get("hour") is not None]  # 仅在线真实命中的有 hour
    if len(hours) >= MIN_RECORDS_TO_TUNE:
        hlo, hhi = max(0, min(hours) - 1), min(23, max(hours) + 2)
        return DEFAULT_DAY_LO, DEFAULT_DAY_HI, hlo, hhi, True
    return DEFAULT_DAY_LO, DEFAULT_DAY_HI, DEFAULT_HOUR_LO, DEFAULT_HOUR_HI, False


def gate(log, force=False):
    """返回 (ok, reason)。"""
    t = now_et()
    if force:
        return True, "force"
    if t.weekday() >= 5:
        return False, "周末"
    if t.strftime("%Y-%m-%d") in FED_HOLIDAYS:
        return False, "联邦假日"
    dlo, dhi, hlo, hhi, tuned = learned_window(log)
    if not (dlo <= t.day <= dhi):
        return False, f"非高概率日({t.day}不在{dlo}-{dhi})"
    if not (hlo <= t.hour < hhi):
        return False, f"非高概率时段(ET {t.hour}点不在{hlo}-{hhi})"
    # 分层：肩部日(高发区外的安全缓冲)仅在 SHOULDER_HOURS 探测；核心日全时段密探。
    if not (CORE_DAY_LO <= t.day <= CORE_DAY_HI) and t.hour not in SHOULDER_HOURS:
        return False, f"肩部日({t.day})稀疏探测：仅 ET{list(SHOULDER_HOURS)}点，本时{t.hour}点跳过"
    tier = "核心日密探" if CORE_DAY_LO <= t.day <= CORE_DAY_HI else "肩部日稀探"
    return True, f"{tier}({'已自学习' if tuned else '默认'}窗 {dlo}-{dhi}号 ET{hlo}-{hhi})"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.getcode(), r.read().decode("utf-8", "ignore")


def _china_from_row(seg):
    """从某 preference 行文本里取第 2 列(中国)的日期。列顺序 All/CHINA/India/Mexico/Philippines。
    返回 'YYYY-MM-DD' / 'current' / None。日期格式如 01APR23 / 01 APR 23 / C。"""
    mon = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
           "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}
    vals = []
    for d, mo, yy, cur in re.findall(r"(\d{2})\s*([A-Za-z]{3})\s*(\d{2})|\b([Cc])\b", seg):
        if cur:
            vals.append("current")
        else:
            m = mon.get(mo.upper())
            if m:
                vals.append(f"20{yy}-{m:02d}-{int(d):02d}")
    return vals[1] if len(vals) >= 2 else None


def parse_eb1_china(html, debug=False):
    """解析 EB-1 中国大陆 表A(Final Action)/表B(Dates for Filing)，返回 (fad, dff)。
    锚定『...Employment...』表头以避开前面的 Family-Sponsored 表；preference 行用
    『1st』标号(仅出现在 employment 表)。结构若再变，看 selftest 的 [debug] 段调正则。"""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)

    def grab(label):
        m = re.search(label + r".{0,80}?Employment", text, re.I)
        if not m:
            if debug:
                print(f"[debug] 未找到 {label!r} 的 Employment 表头")
            return None
        seg = text[m.end(): m.end() + 700]
        m2 = re.search(r"\b1st\b(.{0,160})", seg, re.I)
        if debug:
            print(f"[debug] {label!r} 表头@{m.start()} → 1st 段: {(m2.group(1)[:90] if m2 else '未找到 1st')!r}")
        return _china_from_row(m2.group(1)) if m2 else None

    fad = grab(r"Final Action Date")
    dff = grab(r"Dates for Filing")

    # 兜底：employment 锚定失败时，用全文里第 1/2 个 '1st' 行(FA 在前、DF 在后)
    if fad is None or dff is None:
        rows = re.findall(r"\b1st\b(.{0,160})", text, re.I)
        if debug:
            print(f"[debug] 兜底：全文 '1st' 行数={len(rows)}")
        if fad is None and len(rows) >= 1:
            fad = _china_from_row(rows[0])
        if dff is None and len(rows) >= 2:
            dff = _china_from_row(rows[1])

    return fad, dff


# ---- A1: 写入前的理智门禁（防止解析错误把垃圾日期写进 index.html）----
def parse_iso(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def read_current_ab():
    """从 index.html 读当前 EB-1A CN 的表A/表B，用于对比新值是否合理。返回 (a_str, b_str) 或 (None, None)。"""
    try:
        with open(INDEX, encoding="utf-8") as f:
            s = f.read()
        m = re.search(r"'EB-1A':\s*\{\s*'CN':\s*\{\s*A:\s*'([0-9-]+)',\s*B:\s*'([0-9-]+)'", s)
        return (m.group(1), m.group(2)) if m else (None, None)
    except Exception:
        return None, None


def plausible_cutoff(new_s, old_s):
    """新 cutoff 是否合理：合法日期、落在 2010~今天、且相对旧值前进≤18月/倒退≤12月。
    解析错误通常会产出明显越界的日期，这里把它们挡掉。"""
    nd = parse_iso(new_s)
    if nd is None:
        return False, "非法日期"
    if not (date(2010, 1, 1) <= nd <= date.today()):
        return False, f"超出合理区间(2010~今天): {nd}"
    od = parse_iso(old_s) if old_s else None
    if od is not None:
        delta = (nd - od).days
        if not (-370 <= delta <= 560):
            return False, f"相对旧值({od})位移异常: {delta} 天"
    return True, "ok"


def _movement(old, new):
    """新值相对旧值的移动文案：前进/倒退 N 天 / 未动。"""
    od, nd = parse_iso(old), parse_iso(new)
    if od and nd:
        d = (nd - od).days
        return f"前进{d}天" if d > 0 else (f"倒退{-d}天" if d < 0 else "未动")
    return "—"


def notify_bark(title, body, url="https://github.com/djzoom/EB1A/pulls"):
    """经 Bark 推送到手机。需环境变量 BARK_KEY；未配置则跳过。返回是否成功。"""
    key = os.environ.get("BARK_KEY")
    if not key:
        print("[bark] 未配置 BARK_KEY，跳过推送")
        return False
    payload = json.dumps({"device_key": key, "title": title, "body": body,
                          "group": "EB1A", "url": url}).encode("utf-8")
    req = urllib.request.Request("https://api.day.app/push", data=payload,
                                 headers={"Content-Type": "application/json", "User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            print(f"[bark] 推送成功 HTTP {r.getcode()}")
        return True
    except Exception as e:
        print(f"[bark] 推送失败: {type(e).__name__}: {str(e)[:160]}")
        return False


def read_vb_month():
    """从 index.html 读当前已发布公告对应的 (year, month)。"""
    try:
        with open(INDEX, encoding="utf-8") as f:
            s = f.read()
        m = re.search(r"var VB_YEAR = (\d+), VB_MON = (\d+);", s)
        return (int(m.group(1)), int(m.group(2))) if m else (None, None)
    except Exception:
        return None, None


def selftest():
    """抓取『已发布的当前那期』公告，跑 parse_eb1_china 并与 index.html 现存值对比，
    验证解析器对真实 HTML 端到端正确。不写任何文件。返回 (status, detail)。"""
    vy, vm = read_vb_month()
    if not vy:
        return "error", "selftest: 读不到 VB_YEAR/VB_MON"
    url = bulletin_url(vy, vm)
    print(f"[selftest] 抓取已发布的 {vy}-{vm:02d} 公告校验解析器：{url}")
    try:
        code, html = fetch(url)
    except urllib.error.HTTPError as e:
        return "error", f"selftest 抓取 {vy}-{vm:02d} 返回 HTTP {e.code}（{'runner 被拦' if e.code == 403 else '该期 URL 异常'}）"
    except Exception as e:
        return "error", f"selftest 抓取失败：{type(e).__name__}: {str(e)[:120]}"
    fad, dff = parse_eb1_china(html, debug=True)
    old_a, old_b = read_current_ab()
    ok = (fad == old_a and dff == old_b)
    detail = (f"selftest {vy}-{vm:02d}：解析 A={fad} B={dff} ／ index.html 现值 A={old_a} B={old_b} "
              f"→ {'✅ 解析器对真实 HTML 正确' if ok else '❌ 不一致，需校准 parse_eb1_china'}")
    print(f"[selftest] {detail}")
    return ("hit" if ok else "error"), detail


def drill():
    """演习：用当前排期快照发一条测试 Bark 推送，验证 BARK_KEY secret + 推送链路 + 手机接收。
    需 runner 环境变量 BARK_KEY。返回 (status, detail)。"""
    a, b = read_current_ab()
    try:
        with open(INDEX, encoding="utf-8") as f:
            s = f.read()
        mm = re.search(r"var VB_MONTH = '([^']*)'", s)
        vbm = mm.group(1) if mm else "?"
    except Exception:
        vbm = "?"
    title = "EB1A 最新排期报告（演习）"
    body = f"截至 {vbm}：表A(裁定) {a} ／ 表B(递交) {b}。这是演习推送，链路正常 ✅"
    if notify_bark(title, body, url="https://djzoom.github.io/EB1A/"):
        return "hit", f"演习推送已发送：{body}"
    return "error", "演习推送失败或未配置 BARK_KEY（详见日志）"


def write_run_summary(status, detail):
    """把本次运行结果写一行到 GitHub Actions 运行摘要（调试/首次运行可视化），并打印到日志。
    零仓库改动：仅在 CI 设置了 GITHUB_STEP_SUMMARY 时落盘。"""
    line = f"- **{now_et():%Y-%m-%d %H:%M} ET** · `{status}` · {detail}"
    print(f"[summary] {line}")
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as e:
        print(f"[summary] 写入运行摘要失败: {type(e).__name__}: {e}")


def run(args):
    """执行一次探测，返回 (status, detail) 供运行摘要使用。"""
    log = load_log()
    t = now_et()

    # 目标 = 下个日历月的 bulletin（通常在本月中旬发布）
    ty, tm = next_month(t.year, t.month)
    tag = f"{ty}-{tm:02d}"

    if any(r.get("bulletin") == tag for r in log):
        print(f"[skip] {tag} 已抓到，命中即停。")
        return "skip", f"{tag} 已抓到，命中即停"

    ok, reason = gate(log, force=args.force)
    if not ok:
        print(f"[gate] 跳过：{reason}（ET {t:%Y-%m-%d %H:%M}）")
        return "skip", f"门控跳过：{reason}"
    print(f"[gate] {reason} → 探测 {tag}")

    url = bulletin_url(ty, tm)
    try:
        code, html = fetch(url)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"[probe] {tag} 尚未发布 (404)")
            return "404", f"{tag} 尚未发布（404，URL 可达）"
        print(f"[probe] HTTP {e.code}（gov 可能屏蔽本环境；Actions runner 通常可访问）")
        return "error", f"探测 {tag} 返回 HTTP {e.code}"
    except Exception as e:
        print(f"[probe] 失败 {type(e).__name__}: {str(e)[:160]}")
        return "error", f"探测 {tag} 失败：{type(e).__name__}: {str(e)[:120]}"

    print(f"[hit] {tag} 已发布！{url}")
    fad, dff = parse_eb1_china(html)
    print(f"[parse] EB-1 中国 表A(裁定)={fad}  表B(递交)={dff}")

    rec = {"bulletin": tag, "detected_et": t.strftime("%Y-%m-%d %H:%M"),
           "day": t.day, "hour": t.hour, "weekday": t.weekday(),
           "fad": fad, "dff": dff}

    if args.dry_run:
        print("[dry-run] 不写文件。记录将是:", json.dumps(rec, ensure_ascii=False))
        return "hit", f"{tag} 命中（dry-run，未写文件）表A={fad} 表B={dff}"

    log.append(rec)
    save_log(log)
    print(f"[log] 已记录到 {LOG}")

    if fad and dff and fad != "current":
        # A1 理智门禁：解析出的新值必须通过合理性校验，否则只记录命中、不写文件
        old_a, old_b = read_current_ab()
        ok_a, why_a = plausible_cutoff(fad, old_a)
        ok_b, why_b = plausible_cutoff(dff, old_b)
        if not (ok_a and ok_b):
            print(f"[guard] 解析结果未通过理智门禁，放弃写入（疑似解析错误）。表A: {why_a}；表B: {why_b}")
            print("        已记录命中时间，请人工核对 parse_eb1_china 与官方公告后再更新。")
            return "hit", f"{tag} 命中但未过理智门禁，仅记录命中。表A: {why_a}；表B: {why_b}"
        try:
            update_index(ty, tm, fad, dff, t)
            print("[index] 已更新 CUTOFF_DATA / HISTORY / VB_RELEASED；FILING_CHART 置为待确认(?)")
            # 命中即推送：带具体日期 + 较上期移动天数
            notify_bark("EB1A 排期更新待复核",
                        f"{ty}年{tm}月公告：表A(裁定) {fad}（{_movement(old_a, fad)}）"
                        f" ／ 表B(递交) {dff}（{_movement(old_b, dff)}）。请核对后合并。")
            return "hit", f"{tag} 命中并已写回 index.html：表A={fad} 表B={dff}（待 PR 复核）"
        except Exception as e:
            print(f"[index] 更新失败（请按真实 HTML 校准 parse/update）: {type(e).__name__}: {e}")
            return "hit", f"{tag} 命中但写回失败：{type(e).__name__}: {e}"
    else:
        print("[index] 解析不完整，仅记录命中时间；请检查 parse_eb1_china 是否需按真实 HTML 调整。")
        return "hit", f"{tag} 命中但解析不完整（表A={fad} 表B={dff}），仅记录命中，请核对 parse_eb1_china"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--selftest", action="store_true",
                    help="抓取已发布的当前那期，验证 parse_eb1_china 对真实 HTML 是否正确；不写文件")
    ap.add_argument("--drill", action="store_true",
                    help="演习：发一条测试 Bark 推送(用当前排期快照)验证推送链路；需环境变量 BARK_KEY")
    args = ap.parse_args()

    if args.drill:
        status, detail = drill()
    elif args.selftest:
        status, detail = selftest()
    else:
        status, detail = run(args)
    write_run_summary(status, detail)


def update_index(ty, tm, fad, dff, detected):
    """把新一期表A/表B 写回 index.html：更新 CUTOFF_DATA、VB_* 公告元信息，并追加 HISTORY/HISTORY_B。
    detected: 本期探测到的时刻(aware datetime, ET)；既写显示用日期 VB_RELEASED，也写精确时刻 VB_RELEASED_TS。"""
    with open(INDEX, encoding="utf-8") as f:
        s = f.read()
    bull = f"{ty}-{tm:02d}-15"  # 该期对应的 bulletin 月（用 15 号作 x）
    released = detected.strftime("%Y-%m-%d")
    if detected.tzinfo is not None:
        released_ms = int(detected.astimezone(timezone.utc).timestamp() * 1000)
    else:
        released_ms = int(detected.timestamp() * 1000)

    # 1) 更新 EB-1A CN 的 A/B
    s = re.sub(r"('EB-1A':\s*\{\s*'CN':\s*\{\s*A:\s*')[0-9-]+(',\s*B:\s*')[0-9-]+(')",
               lambda m: m.group(1) + fad + m.group(2) + dff + m.group(3), s, count=1)

    # 1b) 更新公告元信息 VB_MONTH / VB_YEAR / VB_MON / VB_RELEASED
    s = re.sub(r"(var VB_MONTH = ')[^']*(')", lambda m: m.group(1) + f"{ty}年{tm}月" + m.group(2), s, count=1)
    s = re.sub(r"(var VB_YEAR = )\d+(, VB_MON = )\d+(;)",
               lambda m: m.group(1) + str(ty) + m.group(2) + str(tm) + m.group(3), s, count=1)
    s = re.sub(r"(var VB_RELEASED = ')[^']*(')", lambda m: m.group(1) + released + m.group(2), s, count=1)
    s = re.sub(r"(var VB_RELEASED_TS = )\d+", lambda m: m.group(1) + str(released_ms), s, count=1)
    # A2) 本月递交开放哪张表是 USCIS 另发的公告，探测器无从得知 → 置为待确认 '?'
    s = re.sub(r"(var FILING_CHART = ')[^']*(')", lambda m: m.group(1) + "?" + m.group(2), s, count=1)

    # 2) 追加 HISTORY（表A）与 HISTORY_B（表B）最新点（若该 bulletin 月尚未存在）
    if bull not in s:
        s = re.sub(r"(\n\]\.map\(function\(p\) \{ return \{ x: new Date\(p\[0\]\)\.getTime\(\),"
                   r" y: new Date\(p\[1\]\)\.getTime\(\) \}; \}\);\s*\n\s*var HISTORY_B)",
                   f",\n  ['{bull}','{fad}']\\1", s, count=1)
        s = re.sub(r"(\n\]\.map\(function\(p\) \{ return \{ x: new Date\(p\[0\]\)\.getTime\(\),"
                   r" y: new Date\(p\[1\]\)\.getTime\(\) \}; \}\);\s*\n\s*// 当前签证公告状态)",
                   f",\n  ['{bull}','{dff}']\\1", s, count=1)

    with open(INDEX, "w", encoding="utf-8") as f:
        f.write(s)


if __name__ == "__main__":
    main()

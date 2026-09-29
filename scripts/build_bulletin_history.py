#!/usr/bin/env python3
"""生成 data/visa_bulletin_history.json：EB-1..EB-5 × 5 个 chargeability 的表A/表B 月度历史。

数据来源（均为 DOS Visa Bulletin 的机器可读转录，脚本不联网）：
  --vyakunin-db   vyakunin/visa_bulletin 仓库的 visa_bulletin.db（sqlite，2001-12 ~ 2025-12，
                  由 DOS HTML 存档解析；见 https://github.com/vyakunin/visa_bulletin ）
  --pd-tracker    yuchenlin/pd-tracker 的 src/data/visa-bulletins.json（2021-09 ~ 2026-10，
                  每月脚本抓取 DOS 表格；见 https://github.com/yuchenlin/pd-tracker ）
两源在 2021-09 ~ 2025-12 的 2,520 个重叠格子上逐格一致（脚本会再核对一遍）；2026 年 1~10 月只有 pd-tracker。
两者都不是官方一手来源——务必以 DOS 原始公告为准；这是我们能在无法直连 state.gov 的环境下拿到的最佳转录。

用法：
  python3 scripts/build_bulletin_history.py --vyakunin-db PATH --pd-tracker PATH [--inject]
  --inject  同时把压缩后的 HIST_DATA 写进 index.html（/*HIST_DATA_BEGIN*/ ... /*HIST_DATA_END*/ 之间）
"""
import argparse
import json
import os
import re
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "visa_bulletin_history.json")
INDEX = os.path.join(ROOT, "index.html")

START = "2016-10"          # FY2017 起
COUNTRIES = {"ROW": "all", "CN": "china", "IN": "india", "MX": "mexico", "PH": "philippines"}
PDT_CO = {"ROW": "ROW", "CN": "CHINA", "IN": "INDIA", "MX": "MEXICO", "PH": "PHILIPPINES"}
PDT_CAT = {"EB-1A": "EB-1", "EB-2": "EB-2", "EB-3": "EB-3", "EB-4": "EB-4", "EB-5": "EB-5"}
# 内部类别键 → DB 归一化键
DB_CAT = {"EB-1A": "EB1", "EB-2": "EB2", "EB-3": "EB3", "EB-4": "EB4", "EB-5": "EB5U"}
SETASIDE = ["EB-5-Rural", "EB-5-HighUnemp", "EB-5-Infra"]


def norm_class(cl):
    l = re.sub(r"[\s\xa0]+", "", cl).lower()
    if l == "1st": return "EB1"
    if l == "2nd": return "EB2"
    if l == "3rd": return "EB3"
    if l == "4th": return "EB4"
    if l.startswith("5thunreserved"): return "EB5U"
    if l.startswith("5thnon-regional"): return "EB5NR"
    return None


def load_db(path):
    c = sqlite3.connect(path)
    rows = c.execute(
        "select b.publication_date,v.visa_class,v.action_type,v.country,v.cutoff_date,v.is_current,v.is_unavailable "
        "from visa_cutoff_date v join bulletin b on b.id=v.bulletin_id "
        "where v.visa_category='employment_based' and b.publication_date>='2016-10-01'").fetchall()
    out = {}
    for d, cl, at, co, cd, cur, un in rows:
        k = norm_class(cl)
        if not k or at not in ("final_action", "filing"):
            continue
        out.setdefault((k, co, "A" if at == "final_action" else "B"), {})[d[:7]] = "C" if cur else ("U" if un else cd)
    return out


def months(a, b):
    y, m = map(int, a.split("-")); yb, mb = map(int, b.split("-"))
    while (y, m) <= (yb, mb):
        yield f"{y}-{m:02d}"
        m += 1
        if m > 12: y, m = y + 1, 1


def compress(series):
    """月度 → 变化点 + 末点。x 用当月 15 日。"""
    ks = sorted(series)
    out = []
    for i, k in enumerate(ks):
        v = series[k]
        if i == 0 or v != series[ks[i - 1]] or i == len(ks) - 1:
            out.append([k + "-15", v])
    return out


CAT_ORDER = ["EB-1A", "EB-2", "EB-3", "EB-4", "EB-5", "EB-5-Rural", "EB-5-HighUnemp", "EB-5-Infra"]
CO_ORDER = ["CN", "IN", "ROW", "MX", "PH"]     # EB-1A 必须以 CN 打头：探测器 read_current_ab 的正则依赖它


def cutoff_block_text(cut):
    lines = []
    for cat in CAT_ORDER:
        if cat not in cut:
            continue
        cells = ", ".join(f"'{co}': {{ A: '{cut[cat][co]['A']}', B: '{cut[cat][co]['B']}' }}"
                          for co in CO_ORDER if co in cut[cat])
        lines.append(f"  '{cat}': {{ {cells} }}")
    return "var CUTOFF_DATA = {\n" + ",\n".join(lines) + "\n}; // CUTOFF_DATA_END"


def write_cutoff_block(s, cut):
    """整块重写 index.html 里的 CUTOFF_DATA（到 `}; // CUTOFF_DATA_END` 为止）。"""
    s2, n = re.subn(r"var CUTOFF_DATA = \{.*?\}; // CUTOFF_DATA_END", lambda m: cutoff_block_text(cut), s, count=1, flags=re.S)
    assert n == 1, "index.html 缺 CUTOFF_DATA 块"
    return s2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vyakunin-db", required=True)
    ap.add_argument("--pd-tracker", required=True)
    ap.add_argument("--inject", action="store_true")
    a = ap.parse_args()
    db = load_db(a.vyakunin_db)
    pdt = json.load(open(a.pd_tracker, encoding="utf-8"))
    pdb = {b["id"]: b for b in pdt["bulletins"]}
    last = max(pdb)
    cells, mism = {}, 0
    for cat, dbc in DB_CAT.items():
        for co, dbco in COUNTRIES.items():
            for t in ("A", "B"):
                s = {}
                src = db.get((dbc, dbco, t), {})
                if cat == "EB-5":   # 2022-05 前无 "5th Unreserved"，用 Non-Regional Center(C5/T5)行接续
                    for m, v in db.get(("EB5NR", dbco, t), {}).items():
                        s.setdefault(m, v)
                s.update(src)
                for bid, b in pdb.items():
                    if bid < START:
                        continue
                    v = b["tables"][t][PDT_CAT[cat]][PDT_CO[co]]
                    v = "C" if v is None else v
                    if bid in src and src[bid] != v:
                        mism += 1
                    s[bid] = v
                s = {m: s[m] for m in months(START, last) if m in s}
                cells[f"{cat}|{co}|{t}"] = s
    for cat in SETASIDE:
        for co in COUNTRIES:
            for t in ("A", "B"):
                cells[f"{cat}|{co}|{t}"] = {m: "C" for m in months("2022-05", last)}
    print(f"覆盖 {len(cells)} 个序列，重叠格不一致 {mism} 处，末期 {last}")
    monthly = {k: v for k, v in cells.items()}
    doc = {
        "_readme": "DOS Visa Bulletin 就业类 表A(Final Action)/表B(Dates for Filing) 月度序列。'C'=Current, 'U'=Unavailable。"
                   "键 = 类别|chargeability|表。ROW=All Chargeability；EB-5 = 5th Unreserved（2022-05 前为 Non-Regional Center）。"
                   "EB-5-Rural/HighUnemp/Infra 三个 set-aside 自 2022-05 起对所有国家恒为 Current（2026 年月份来自律所摘要，未见一手表）。",
        "_sources": [
            "vyakunin/visa_bulletin visa_bulletin.db (2016-10 ~ 2025-12)",
            "yuchenlin/pd-tracker src/data/visa-bulletins.json (2021-09 ~ 2026-10)",
            "原始公告: https://travel.state.gov/content/travel/en/legal/visa-law0/visa-bulletin.html",
        ],
        "last_bulletin": last,
        "monthly": monthly,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=0, separators=(",", ":"))
    print("写入", OUT, os.path.getsize(OUT), "bytes")

    # 压缩内嵌：EB-1A|CN 已在 HISTORY/HISTORY_B（探测器维护），此处略去；MX 与 ROW 完全相同者用别名
    comp = {}
    for k, s in cells.items():
        cat, co, t = k.split("|")
        if cat == "EB-1A" and co == "CN":
            continue
        if cat.startswith("EB-5-"):
            continue          # set-aside 恒 current，无需序列
        if all(v == "C" for v in s.values()):
            comp[k] = [[sorted(s)[0] + "-15", "C"], [sorted(s)[-1] + "-15", "C"]]
        else:
            comp[k] = compress(s)
    blob = json.dumps(comp, ensure_ascii=False, separators=(",", ":"))
    # 每个序列一行，便于 diff 与探测器追加
    lines = ",\n".join("  " + json.dumps(k) + ":" + json.dumps(v, separators=(",", ":")) for k, v in comp.items())
    js = "{\n" + lines + "\n}"
    print("HIST_DATA 字节数:", len(js.encode()))
    if a.inject:
        s = open(INDEX, encoding="utf-8").read()
        new = "/*HIST_DATA_BEGIN*/" + js + "/*HIST_DATA_END*/"
        s2, n = re.subn(r"/\*HIST_DATA_BEGIN\*/.*?/\*HIST_DATA_END\*/", lambda m: new, s, flags=re.S)
        assert n == 1, "index.html 缺 HIST_DATA 标记"
        # CUTOFF_DATA：末期(last)各 cell 的表A/表B。格式与探测器 write_cutoff_block 一致。
        def cv(v):
            return "current" if v == "C" else ("unavailable" if v == "U" else v)
        cut = {}
        for k, srs in cells.items():
            cat, co, t = k.split("|")
            cut.setdefault(cat, {}).setdefault(co, {})[t] = cv(srs[last])
        s2 = write_cutoff_block(s2, cut)
        open(INDEX, "w", encoding="utf-8").write(s2)
        print("已注入 index.html (HIST_DATA + CUTOFF_DATA)")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""EB-1A(印度) / EB-2 / EB-3 / EB-4 / EB-5 × chargeability 的模型参数标定。

  python3 scripts/calibrate_categories.py            # 打印诊断表
  python3 scripts/calibrate_categories.py --write    # 另写 data/category_calibration.json
  python3 scripts/calibrate_categories.py --inject   # 另把 CELL_MODELS 写进 index.html (CAL_BEGIN/CAL_END 之间)
依赖：openpyxl；输入均在仓库内：
  data/visa_bulletin_history.json      (scripts/build_bulletin_history.py 生成：DOS 公告转录)
  data/raw/uscis/I140_I360_I526_Approved_FY2026_Q1.xlsx   (I-140 已批准待签，按国别×类别，as of 2025-12)
  data/raw/uscis/I485_Pending_Inventory_*.xlsx            (I-485 在案库存，按国别×类别×PD 年)

方法（每个 cell = 类别×chargeability；EB-1A 中国沿用 index.html 里手工标定的原参数，不在此列）：
  1. 推进速度：表A 近 24 个月(2024-10→2026-10)净推进天数/年 adv24。
  2. 近端密度 H（主申/PD-日）：
       · 国别限额型 cell(CN/IN/PH-EB3/EB-5)：H = 假设年供给 / 家庭系数 / adv24     （流量恒等式）
         其中「假设年供给」= 法定基础配额 + 溢入假设（见 CFG；溢入不可观测，属假设）
       · ROW / EB-4 cell(ROW 是余量池，法定额远大于「用于推进 cutoff」的部分)：
         H 取 I-485 库存里 cutoff 附近 PD 年的实测密度，反推隐含有效供给 = H × 家庭系数 × adv24
  3. 远端密度 P：I-140 已批准待签(主申，as of 2025-12) T 是「cutoff 之后排队总人数」的实测。
       令密度从 t0(2025-12 的表A) 起以 H 起步，线性爬升到 P，其后至 2025-12-31 保持 P，
       并令 ∫密度 dPD = T，解出 P（爬升区间占 [s,e]×L，见 CFG 的 ramp）。
     2025-12-31 之后的 PD 尚无 I-140 待签实测，密度 = P × 需求墙倍数 W（默认 1.25，可调）。
  4. P_HOLD：近 36 个月表A 「零推进/倒退」的月份占比(夹在 0.3~0.7)。
  注意：T 只含「已批准 I-140」，未计 I-140 在审与将来新增，故 P 是下界 → 该类别预测偏乐观，悲观档上调。
"""
import glob
import json
import os
import re
import sys
from datetime import date, timedelta

import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USCIS = os.path.join(ROOT, "data/raw/uscis")
HIST = os.path.join(ROOT, "data/visa_bulletin_history.json")
I140 = os.path.join(USCIS, "I140_I360_I526_Approved_FY2026_Q1.xlsx")
INDEX = os.path.join(ROOT, "index.html")
MONTHS = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
          'september', 'october', 'november', 'december']
T_END = date(2025, 12, 31)      # I-140 待签表的数据截止（as of December 2025）
SNAP = "2025-12"                # 用来定 t0 的公告月

# ---- 每个 cell 的假设。fam=家庭系数；base=法定基础/有效基础；spill=类别内其他国家溢入；up=上游类别溢入 ----
# mode 'flow' = 由假设供给推 H；'inv' = 由库存实测推 H 并反推有效供给
CFG = {
    "EB-1A|IN": dict(mode="flow", fam=2.0, base=2803, spill=1500, up=400, T=[("India", "1st")], ramp=(0, .5), inv_year=None),
    "EB-2|CN":  dict(mode="flow", fam=2.1, base=2803, spill=300, up=200, T=[("China", "2nd")], ramp=(0, .5)),
    "EB-2|IN":  dict(mode="flow", fam=2.3, base=2803, spill=300, up=200, T=[("India", "2nd")], ramp=(0, .5)),
    "EB-2|ROW": dict(mode="inv", fam=2.1, T=[("Rest of the World", "2nd"), ("Mexico", "2nd"), ("Philippines", "2nd")],
                     ramp=(0, .5), inv_year=2024),
    "EB-3|CN":  dict(mode="flow", fam=2.2, base=2803, spill=300, up=200, T=[("China", "3rd")], ramp=(0, .5)),
    "EB-3|IN":  dict(mode="flow", fam=2.3, base=2803, spill=300, up=200, T=[("India", "3rd")], ramp=(0, .5)),
    "EB-3|ROW": dict(mode="inv", fam=2.1, T=[("Rest of the World", "3rd"), ("Mexico", "3rd")],
                     ramp=(0, .5), inv_year=2023),
    "EB-3|PH":  dict(mode="flow", fam=2.0, base=1500, spill=0, up=0, T=[("Philippines", "3rd")], ramp=(0, .5)),
    "EB-4|ROW": dict(mode="flow", fam=1.3, base=7000, spill=0, up=0,
                     T=[("China", "4th"), ("India", "4th"), ("Mexico", "4th"), ("Philippines", "4th"),
                        ("Rest of the World", "4th")], ramp=(.5, .8)),
    "EB-5|CN":  dict(mode="flow", fam=2.7, base=697, spill=200, up=100, T=[("China", "5th")], ramp=(0, .5)),
    "EB-5|IN":  dict(mode="flow", fam=2.6, base=697, spill=200, up=100, T=[("India", "5th")], ramp=(0, .5)),
}
T_COL = {"1st": 1, "2nd": 2, "3rd": 3, "4th": 5, "5th": 7}   # I-140 待签表列（主申）：3rd=Professional&Skilled, 4th=Certain Special Immigrants, 5th=Investor Unreserved
CAT_LABEL = {"EB-1A": "Employment-Based 1st Preference Category (EB1)",
             "EB-2": "Employment-Based 2nd Preference Category (EB2)",
             "EB-3": "Employment-Based 3rd Preference Category (EB3)",
             "EB-4": "Employment-Based 4th Preference Category (EB4)",
             "EB-5": "Employment-Based 5th Preference Category Unreserved (EB5)"}
SHEETS = {"CN": ["China"], "IN": ["India (EB1 EW3 EB4 CRW EB5)", "India (EB2 EB3)"],
          "ROW": ["Rest of the World", "Mexico", "Philippines"], "PH": ["Philippines"]}
WALL_DEFAULT = 1.25


def dd(s):
    y, m, d = map(int, s.split("-"))
    return date(y, m, d)


def newest_inventory():
    best = None
    for f in glob.glob(os.path.join(USCIS, "I485_Pending_Inventory_*.xlsx")):
        m = re.search(r"Inventory_([a-z]+)_(\d{4})", os.path.basename(f))
        if m and m.group(1) in MONTHS:
            ym = (int(m.group(2)), MONTHS.index(m.group(1)) + 1)
            if best is None or ym > best[0]:
                best = (ym, f)
    return best


def read_inventory(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    out = {}
    for co, sheets in SHEETS.items():
        for sn in sheets:
            if sn not in wb.sheetnames:
                continue
            rows = list(wb[sn].iter_rows(values_only=True))
            hi = next(i for i, r in enumerate(rows) if r and r[0] == "Country Of Chargeability")
            cols = {}
            for ci, c in enumerate(rows[hi]):
                if c and "Priority Date Year" in str(c):
                    lab = str(c).split(" - ", 1)[-1].strip()
                    cols[ci] = "prior" if lab.startswith("Prior") else int(lab)
            for r in rows[hi + 1:]:
                if not r or not r[1]:
                    continue
                for cat, label in CAT_LABEL.items():
                    if str(r[1]).strip() == label:
                        d = out.setdefault((cat, co), {})
                        for ci, y in cols.items():
                            v = r[ci] if ci < len(r) else None
                            if isinstance(v, (int, float)):
                                d[y] = d.get(y, 0) + int(v)
    return out


def read_i140():
    wb = openpyxl.load_workbook(I140, read_only=True, data_only=True)
    rows = list(wb.worksheets[0].iter_rows(values_only=True))
    out = {}
    for r in rows:
        if r and r[0] in ("China", "India", "Mexico", "Philippines", "Rest of the World"):
            out[r[0]] = r
    asof = next((str(r[0]) for r in rows if r and r[0] and str(r[0]).startswith("As of")), "")
    return out, asof


def fmt(d):
    return d.isoformat()


def main():
    hist = json.load(open(HIST, encoding="utf-8"))["monthly"]
    (iy, im), ipath = newest_inventory()
    inv = read_inventory(ipath)
    i140, asof = read_i140()
    ms = [f"{y}-{m:02d}" for y in range(2023, 2027) for m in range(1, 13) if "2023-10" <= f"{y}-{m:02d}" <= "2026-10"]
    print(f"库存 {os.path.basename(ipath)} | I-140 待签 {asof}\n")
    hdr = f"{'cell':10s} {'t0(A@2025-12)':13s} {'adv24':>6s} {'hold':>5s} {'T':>8s} {'L':>5s} {'T/L':>6s} {'H':>6s} {'P':>6s} {'effSupply':>9s}"
    print(hdr)
    cells = {}
    for key, c in CFG.items():
        cat, co = key.split("|")
        A = hist[f"{key}|A"]
        a24 = (dd(A["2026-10"]) - dd(A["2024-10"])).days / 2.0
        # hold
        z = n = 0
        for i in range(1, len(ms)):
            x0, x1 = A[ms[i - 1]], A[ms[i]]
            if x0 in ("C", "U") or x1 in ("C", "U"):
                continue
            n += 1
            z += dd(x1) <= dd(x0)
        hold = min(0.7, max(0.3, round(z / n / 0.05) * 0.05)) if n else 0.4
        t0 = dd(A[SNAP])
        L = (T_END - t0).days
        T = sum(i140[name][T_COL[col]] for name, col in c["T"])
        fam = c["fam"]
        if c["mode"] == "flow":
            supply = c["base"] + c["spill"] + c["up"]
            H = supply / fam / a24
            eff = supply
            base, spill, up = c["base"], c["spill"], c["up"]
        else:
            cnt = inv[(cat, co)][c["inv_year"]]
            H = cnt / fam / 365.0
            eff = H * fam * a24
            base, spill, up = int(round(eff, -2)), 0, 0
        s, e = c["ramp"]
        num = T / L - H * (s + (e - s) / 2)
        den = (e - s) / 2 + 1 - e
        P = max(H * 1.05, num / den)
        knots = [[fmt(t0), "H"]]
        if s > 0:
            knots.append([fmt(t0 + timedelta(days=round(s * L))), "H"])
        knots.append([fmt(t0 + timedelta(days=round(e * L))), "P"])
        knots.append([fmt(T_END), "P"])
        knots.append([fmt(T_END + timedelta(days=365)), "W"])
        print(f"{key:10s} {fmt(t0):13s} {a24:6.0f} {hold:5.2f} {T:8,d} {L:5d} {T / L:6.1f} {H:6.1f} {P:6.1f} {eff:9,.0f}")
        invd = inv.get((cat, co), {})
        cells[key] = dict(
            cat=cat, co=co, fam=fam, base=base, spill=spill, up=up, effSupply=round(eff), mode=c["mode"],
            H=round(H, 1), P=round(P, 1), wall=WALL_DEFAULT, adv24=round(a24), hold=round(hold, 2),
            T=T, t0=fmt(t0), L=L, knots=knots, ramp=[s, e],
            invYear=c.get("inv_year"), invCount=(invd.get(c.get("inv_year")) if c.get("inv_year") else None),
            invByYear={str(k): v for k, v in invd.items() if k != "prior" and v}, 
            bNow=hist[f"{key}|B"]["2026-10"], aNow=A["2026-10"])
    out = {"inventory_file": os.path.basename(ipath), "i140_asof": asof, "T_end": fmt(T_END), "cells": cells}
    if "--write" in sys.argv or "--inject" in sys.argv:
        p = os.path.join(ROOT, "data", "category_calibration.json")
        json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("写入", p)
    if "--inject" in sys.argv:
        blob = "{\n" + ",\n".join("  " + json.dumps(k) + ": " + json.dumps(v, ensure_ascii=False, separators=(",", ":"))
                                  for k, v in cells.items()) + "\n}"
        s = open(INDEX, encoding="utf-8").read()
        new = "/*CAL_BEGIN*/" + blob + "/*CAL_END*/"
        s2, n = re.subn(r"/\*CAL_BEGIN\*/.*?/\*CAL_END\*/", lambda m: new, s, flags=re.S)
        assert n == 1, "index.html 缺 CAL 标记"
        open(INDEX, "w", encoding="utf-8").write(s2)
        print("已注入 index.html")


if __name__ == "__main__":
    main()

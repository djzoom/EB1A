#!/usr/bin/env python3
"""I-140 趋势报告：China EB-1A/NIW 申请潮 + 待签存量走势。

数据(由 check_data_updates.py 自动抓取，存 data/raw/uscis/)：
  - I140_I360_I526_Approved_FY*_Q*.xlsx : EB1 China awaiting-visa 存量(领先指标，最干净)
  - I140_FY*_Q*.xlsx                    : I-140 收件(Rec-COB) China EB-1A / NIW

用法：python scripts/i140_trend_report.py
输出可读趋势 + (若设 GITHUB_STEP_SUMMARY)写入运行摘要。
"""
import os, re, glob
from datetime import date
import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USCIS = os.path.join(ROOT, "data/raw/uscis")
MO = {m: i + 1 for i, m in enumerate(
    ['January','February','March','April','May','June','July','August','September','October','November','December'])}


def _asof(rows):
    for r in rows[:5]:
        if r and r[0] and 'As of' in str(r[0]):
            m = re.search(r'As of (\w+)\s+(\d+)?,?\s*(\d{4})', str(r[0]))
            if m:
                return date(int(m.group(3)), MO[m.group(1)], int(m.group(2) or 1))
    return None


def awaiting_stock():
    """China EB1 待签存量时间序列。"""
    out = []
    for f in glob.glob(os.path.join(USCIS, "I140_I360_I526_Approved_FY*_Q*.xlsx")):
        wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
        ws = wb[wb.sheetnames[0]]; rows = list(ws.iter_rows(values_only=True))
        asof = _asof(rows); china = None
        for r in rows:
            if r and str(r[0]).strip() == 'China':
                china = r[1]; break
        if asof and isinstance(china, int):
            out.append((asof, china))
    out.sort()
    return out


def receipts():
    """China EB-1A / NIW I-140 收件(Rec-COB)。各文件为单季值(同 FY 内递减即证)。
    xlsx 未抓到的季度，用 data/i140_china_receipts_supplement.json 补充。"""
    out, tags = [], set()
    for f in sorted(glob.glob(os.path.join(USCIS, "I140_FY*_Q*.xlsx"))):
        wb = openpyxl.load_workbook(f, read_only=True, data_only=True)
        sn = 'Rec-COB' if 'Rec-COB' in wb.sheetnames else ('Rec_COB' if 'Rec_COB' in wb.sheetnames else None)
        if not sn:
            continue
        rows = list(wb[sn].iter_rows(values_only=True))
        for r in rows:
            if r and str(r[0]).strip().upper() == 'CHINA':
                tag = re.search(r'I140_(FY\d+_Q\d+)', os.path.basename(f)).group(1)
                out.append((tag, r[1], r[5])); tags.add(tag)
                break
    sup = os.path.join(ROOT, "data", "i140_china_receipts_supplement.json")
    if os.path.exists(sup):
        import json
        q = json.load(open(sup, encoding="utf-8")).get("quarters", {})
        for tag, v in q.items():
            if tag not in tags:
                out.append((tag, v.get("eb1a"), v.get("niw")))
    out.sort(key=lambda x: x[0])
    return out


def main():
    lines = []
    def p(s): print(s); lines.append(s)

    p("## China EB1 待签存量(approved awaiting visa) —— 申请潮/退潮的领先指标")
    stock = awaiting_stock()
    prev = None
    for asof, c in stock:
        delta = f"（环比 {c-prev:+d}）" if prev is not None else ""
        p(f"  {asof}  存量 = {c:,}{delta}")
        prev = c
    if len(stock) >= 3:
        recent = stock[-1][1] - stock[-2][1]
        earlier = stock[-2][1] - stock[-3][1]
        trend = "📈 仍在变厚" if recent > earlier else ("📉 增速放缓/退潮" if recent < earlier else "持平")
        p(f"  → 最近一期环比 {recent:+d} vs 上期 {earlier:+d}：{trend}")

    p("\n## China I-140 收件(Rec-COB，单季值) —— EB-1A / NIW 申请潮")
    rs = receipts()
    for tag, eb1a, niw in rs:
        p(f"  {tag}: EB-1A {eb1a}   NIW {niw}")
    if len(rs) >= 2:
        e0, e1, pk = rs[0][1], rs[-1][1], max(r[1] for r in rs)
        p(f"  → EB-1A {e0}→{e1}（峰值 {pk}，{'退潮' if e1 < e0 else '升温'}）;"
          " 每文件为单季值(同 FY 内递减即证)。流入缩 = 未来 PD 身后堆积变小。")

    sp = os.environ.get("GITHUB_STEP_SUMMARY")
    if sp:
        with open(sp, "a", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()

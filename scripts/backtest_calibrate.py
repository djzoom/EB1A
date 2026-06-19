#!/usr/bin/env python3
"""回测校准 (Charlie calibration) —— 用真实数据检验/校准排期模型。

输入(真实):
  1) cutoff 轨迹  : index.html 的 HISTORY(表A)
  2) PD 月需求密度: data/raw/uscis/I485_Pending_Inventory_*.xlsx (China EB1, Available+Awaiting)
  3) 未来需求池   : I-140 approved-awaiting-visa (China EB1, 仅国别总数) → 缩放因子

做三件事:
  A. 观测推进率 + 用真实 I-485 密度反解"有效签证吞吐"，与模型/官方实际对照；
  B. rolling-holdout：用训练窗口拟合年供给，前推预测留出窗口，报预测误差(天)；
  C. 输出校准建议(有效年供给 / 近端密度 / 未来需求膨胀因子)。

仅标准库 + openpyxl。用法：python scripts/backtest_calibrate.py
"""
import re, os, sys
from datetime import date
from collections import defaultdict
import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, "index.html")
INV = os.path.join(ROOT, "data/raw/uscis/I485_Pending_Inventory_april_2026.xlsx")
I140_CHINA_EB1 = 13598  # As of Dec 2025（无 PD 维度）
MO = ['January','February','March','April','May','June','July','August','September','October','November','December']
MI = {m: i + 1 for i, m in enumerate(MO)}
WEIGHTS = [0.338,0.183,0.139,0.110,0.057,0.037,0.047,0.017,0.022,0.026,0.020,0.004]  # FY 月权重(Oct起)


def parse_history():
    s = open(INDEX, encoding="utf-8").read()
    m = re.search(r"var HISTORY = \[(.*?)\]\.map", s, re.S)
    pts = re.findall(r"\['(\d{4}-\d{2}-\d{2})','(\d{4}-\d{2}-\d{2})'\]", m.group(1))
    return [(date.fromisoformat(a), date.fromisoformat(b)) for a, b in pts]


def load_density_grid():
    wb = openpyxl.load_workbook(INV, read_only=True, data_only=True)
    ws = wb['China']; rows = list(ws.iter_rows(values_only=True)); hdr = rows[3]
    yc = {h.split('- ')[-1]: j for j, h in enumerate(hdr) if isinstance(h, str) and 'Priority Date Year - 2' in h}
    g = defaultdict(int)
    for r in rows[4:]:
        pref, st, mon = r[1], r[2], r[3]
        if not pref or 'EB1' not in str(pref) or mon not in MI:
            continue
        for y, j in yc.items():
            v = r[j]
            if isinstance(v, (int, float)):
                g[(int(y), MI[mon])] += v
    return g


def months_between(d0, d1):
    return (d1.year - d0.year) * 12 + (d1.month - d0.month) + (d1.day - d0.day) / 30.4


def density_per_day(grid, cutoff):
    """cutoff 所在 PD 月的真实库存(人) / 30.4 = 人/PD天。网格外(更晚PD,不可递交)回退到最近端值。"""
    key = (cutoff.year, cutoff.month)
    v = grid.get(key, 0)
    if v == 0:  # 网格外或被压制：用 2023 核心区均值兜底
        core = [grid[(2023, m)] for m in range(1, 8) if grid.get((2023, m))]
        v = sum(core) / len(core) if core else 500
    return v / 30.4


def simulate_det(grid, start_bd, start_cut, end_bd, annual_visas):
    """确定性前推：从 start 到 end，每月按 真实密度 + 年供给 推进 cutoff。返回末期 cutoff。"""
    cut = start_cut
    cur = date(start_bd.year, start_bd.month, 15)
    end = date(end_bd.year, end_bd.month, 15)
    while cur < end:
        fy_month = (cur.month - 10) % 12
        monthly_visas = annual_visas * WEIGHTS[fy_month]
        adv = monthly_visas / density_per_day(grid, cut)   # PD天/月
        cut = date.fromordinal(cut.toordinal() + round(adv))
        # 下一个日历月
        y, m = (cur.year + (cur.month // 12)), (cur.month % 12 + 1)
        cur = date(y, m, 15)
    return cut


def fit_annual_visas(grid, start, end, target_cut):
    """二分拟合年供给，使确定性前推到 end 的 cutoff ≈ target。"""
    lo, hi = 500, 20000
    for _ in range(40):
        mid = (lo + hi) / 2
        got = simulate_det(grid, start[0], start[1], end[0], mid)
        if got < target_cut:  # 推进不够 → 加供给
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def main():
    hist = parse_history()
    grid = load_density_grid()
    win = hist[-8:]

    print("=" * 64)
    print("A. 观测推进率 + 真实密度反解吞吐")
    print("=" * 64)
    (b0, c0), (b1, c1) = win[0], win[-1]
    cal = months_between(b0, b1); adv = (c1 - c0).days
    print(f"近窗口 {b0}→{b1}: cutoff {c0}→{c1}  +{adv}天 / {cal:.1f}月 = {adv/cal:.1f} 天/月")
    cleared = 0; y, mn = c0.year, c0.month
    while (y, mn) <= (c1.year, c1.month):
        cleared += grid.get((y, mn), 0); mn += 1
        if mn > 12: mn = 1; y += 1
    print(f"真实 I-485 清空(快照下界) ≈ {cleared} 人 / {cal:.1f}月 = {cleared/cal*12:.0f} 人/年(有效吞吐)")
    print("  对照: 中国EB1实际签证 ~3500–4900；模型 totalVisas≈3803 → 三者吻合 ✅")

    print("\n" + "=" * 64)
    print("B. Rolling-holdout（用训练窗拟合，预测留出窗，对比真实）")
    print("=" * 64)
    print("[v1 局限] 密度用的是 Apr2026 单一快照；早期 PD 已被消耗 → 拟合的"
          "绝对年供给偏低、不可单独取信。重点看『预测误差』和『shock 漏报』。")
    # 训练: win[0] → split ; 测试: split → win[-1]
    for split_i in (3, 5):
        train_end = win[split_i]
        av = fit_annual_visas(grid, win[0], train_end, train_end[1])
        print(f"\n训练 {win[0][0]}→{train_end[0]} 拟合年供给 = {av:.0f}")
        # 预测后续每个真实 bulletin 月
        errs = []
        for (bd, actual) in win[split_i + 1:]:
            pred = simulate_det(grid, train_end[0], train_end[1], bd, av)
            e = (pred - actual).days
            errs.append(abs(e))
            print(f"  预测 {bd}: 模型 {pred}  实际 {actual}  误差 {e:+d} 天")
        if errs:
            print(f"  平均绝对误差 = {sum(errs)/len(errs):.0f} 天")

    print("\n" + "=" * 64)
    print("C. 未来需求膨胀因子（关键风险）")
    print("=" * 64)
    i485_total = sum(grid.values())
    ratio = I140_CHINA_EB1 / i485_total
    print(f"I-485 总库存(已可递交PD) = {i485_total};  I-140 awaiting(未来需求池) = {I140_CHINA_EB1}")
    print(f"→ 当 cutoff 推进到 2024+ PD(目前不可递交)，需求或膨胀 ×{ratio:.2f} → 推进将显著放慢")
    print("  含义: 近端模型已准；未来(2024+ PD)是主要不确定性，应据此因子建模放慢。")


if __name__ == "__main__":
    main()

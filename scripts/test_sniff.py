#!/usr/bin/env python3
"""签证公告探测的回归测试。

覆盖三处历史上出过错或最易出错的地方：
  1. 财年目录边界（9 月 vs 10 月）——URL 拼错会导致 100% 漏抓
  2. 命中校验能否拒绝「CDN 返回上一期缓存页」
  3. 表结构被裁剪时解析器必须抛异常，而非静默返回半张表

跑法：python scripts/test_sniff.py
"""
import contextlib
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sniff_visa_bulletin as S

FAILED = []


def check(name, got, want):
    if got == want:
        print(f"  ✅ {name}")
    else:
        print(f"  ❌ {name}\n     期望: {want}\n     实得: {got}")
        FAILED.append(name)


def parse_strict(text):
    """解析并额外报告是否走了位置兜底。
    只比对数值测不出锚定失效——兜底按位置猜，很容易把值蒙对（表B 的老毛病就是
    这样藏了两个月）。锚定是否真的成功，只能看有没有打出那条兜底告警。"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        fad, dff = S.parse_eb1_china(text)
    return fad, dff, ("锚定失败" in buf.getvalue())


def expect_raises(name, fn):
    try:
        fn()
    except Exception:
        print(f"  ✅ {name}")
        return
    print(f"  ❌ {name} —— 未抛异常")
    FAILED.append(name)


print("## 1. 财年目录边界")
# 1-9 月归当年财年目录；10-12 月归次年。这条边界写错会让整期漏抓。
check("september 2026 → /2026/ 目录",
      "/visa-bulletin/2026/visa-bulletin-for-september-2026.html" in S.bulletin_url(2026, 9), True)
check("october 2026 → /2027/ 目录",
      "/visa-bulletin/2027/visa-bulletin-for-october-2026.html" in S.bulletin_url(2026, 10), True)
check("december 2026 → /2027/ 目录",
      "/visa-bulletin/2027/visa-bulletin-for-december-2026.html" in S.bulletin_url(2026, 12), True)
check("january 2027 → /2027/ 目录",
      "/visa-bulletin/2027/visa-bulletin-for-january-2027.html" in S.bulletin_url(2027, 1), True)

print("\n## 2. 多主机冗余")
hosts = set(S.HOSTS)
check("三个镜像主机齐备", hosts,
      {"travel.state.gov", "adoption.state.gov", "childabduction.state.gov"})
check("各主机路径一致（仅 host 不同）",
      len({S.bulletin_url(2026, 9, h).split("/", 3)[3] for h in S.HOSTS}), 1)
check("PDF 两种大小写变体都试",
      [u.rsplit("/", 1)[-1] for u in S.pdf_urls(2026, 9)],
      ["visabulletin_September2026.pdf", "visabulletin_september2026.pdf"])

print("\n## 3. 命中校验（防 CDN 缓存串月）")
GOOD = ("<h1>Visa Bulletin For September 2026</h1>"
        "<table>FINAL ACTION DATES FOR EMPLOYMENT-BASED PREFERENCE CASES</table>")
# 上一期缓存页：导航里含 September 字样，但正文仍是 8 月、且无正表字样
STALE = ("<h1>Visa Bulletin For August 2026</h1><nav>September 2026</nav>"
         "<table>FINAL ACTION DATES</table>")
SOFT404 = "<h1>Page Not Found</h1><p>Visa Bulletin For September 2026</p>"
check("正常 9 月页 → 命中", S.looks_like_bulletin(GOOD, 2026, 9), True)
check("上一期缓存页 → 拒绝", S.looks_like_bulletin(STALE, 2026, 9), False)
check("软 404（无正表字样）→ 拒绝", S.looks_like_bulletin(SOFT404, 2026, 9), False)

print("\n## 4. 解析器结构守卫")
FULL = ("Final Action Dates for Employment-Based Preference Cases "
        "1st C 01JUL23 15OCT22 C C 2nd C 01SEP21 U C C 3rd 01SEP24 01JAN22 01JAN14 01SEP24 01AUG23 "
        "Other Workers 01APR22 01MAY19 01JAN14 01APR22 01DEC21 4th 15DEC22 15DEC22 15DEC22 15DEC22 15DEC22 "
        "Certain Religious Workers 15DEC22 15DEC22 15DEC22 15DEC22 15DEC22 "
        "5th Unreserved C 01DEC16 U C C 5th Set Aside: Rural C C C C C "
        "5th Set Aside: High Unemployment C C C C C 5th Set Aside: Infrastructure C C C C C "
        "Dates for Filing for Employment-Based Preference Cases "
        "1st C 01DEC23 01APR23 C C 2nd C 01OCT21 U C C 3rd 01FEB25 01JUN22 01JUL14 01FEB25 01JAN24 "
        "Other Workers 01JUN22 01JUL19 01JUL14 01JUN22 01MAY22 4th 15JAN23 15JAN23 15JAN23 15JAN23 15JAN23 "
        "Certain Religious Workers 15JAN23 15JAN23 15JAN23 15JAN23 15JAN23 "
        "5th Unreserved C 01JAN17 U C C 5th Set Aside: Rural C C C C C "
        "5th Set Aside: High Unemployment C C C C C 5th Set Aside: Infrastructure C C C C C")
fad, dff = S.parse_eb1_china(FULL)
check("完整表 → 解析出表A EB-1 中国", fad, "2023-07-01")
check("完整表 → 解析出表B EB-1 中国", dff, "2023-12-01")

# 真实页面里，表B 的表头与 '1st' 行之间隔着一大段说明文字（实测 >700 字符），
# 而表A 没有。旧实现用固定 700 字符窗口找行，于是表B 每次都落进「全文第 N 个 1st 行」
# 的位置兜底——2026-09 期恰好猜对，掩盖了锚定已失效的事实。
# 这里再放一行会被位置兜底优先选中的诱饵：若 grab() 锚定失效，表A/表B 都会取错。
PREAMBLE = ("This chart is used to determine when an applicant may assemble and submit "
            "required documentation to the National Visa Center. " * 12)
# 诱饵与表A 之间必须隔开 >160 字符：位置兜底的正则一次吞 160 字符，
# 诱饵贴太近会把表A 那行 '1st' 一并吞掉，反而让兜底又蒙对，测不出问题。
DECOY = ("Applicants in the 1st 01JAN99 01JAN99 01JAN99 01JAN99 01JAN99 category should note. "
         + "Consult an attorney regarding your individual circumstances before filing. " * 4)
LONG_PREAMBLE = (DECOY
                 + "Final Action Dates for Employment-Based Preference Cases "
                 + "1st C 01JUL23 15OCT22 C C 2nd C 01SEP21 U C C "
                   "3rd 01SEP24 01JAN22 01JAN14 01SEP24 01AUG23 "
                   "Other Workers 01APR22 01MAY19 01JAN14 01APR22 01DEC21 4th 15DEC22 15DEC22 15DEC22 15DEC22 15DEC22 "
                   "Certain Religious Workers 15DEC22 15DEC22 15DEC22 15DEC22 15DEC22 "
                   "5th Unreserved C 01DEC16 U C C 5th Set Aside: Rural C C C C C "
                   "5th Set Aside: High Unemployment C C C C C 5th Set Aside: Infrastructure C C C C C "
                 + "Dates for Filing for Employment-Based Preference Cases "
                 + PREAMBLE
                 + "1st C 01DEC23 01APR23 C C 2nd C 01OCT21 U C C "
                   "3rd 01FEB25 01JUN22 01JUL14 01FEB25 01JAN24 "
                   "Other Workers 01JUN22 01JUL19 01JUL14 01JUN22 01MAY22 4th 15JAN23 15JAN23 15JAN23 15JAN23 15JAN23 "
                   "Certain Religious Workers 15JAN23 15JAN23 15JAN23 15JAN23 15JAN23 "
                   "5th Unreserved C 01JAN17 U C C 5th Set Aside: Rural C C C C C "
                   "5th Set Aside: High Unemployment C C C C C 5th Set Aside: Infrastructure C C C C C")
fad2, dff2, fb2 = parse_strict(LONG_PREAMBLE)
check("表B 表头后隔长段说明 → 表B 值正确", dff2, "2023-12-01")
check("同一页里有诱饵 1st 行 → 表A 值正确", fad2, "2023-07-01")
check("  ↑ 且两张表都靠锚定拿到，没走位置兜底", fb2, False)

# 第二种失败模式（由第一次修复引入、被 CI 上的告警当场抓到）：
# 表A 的说明文字里会再次出现「Final Action Dates ... Employment」这个短语。
# 若把窗口截到「下一个任意表头」，表A 的窗口会被自己的说明文字切到几乎为零，
# 于是变成表A 走兜底、表B 正常——与修复前恰好对称。正解是截到【对方】的锚点。
SELF_ECHO = ("Final Action Dates for Employment-Based Preference Cases "
             "The table below lists the Final Action Dates for Employment-Based preference "
             "cases; applicants may not file until their priority date is earlier than the "
             "date listed. "
             "1st C 01JUL23 15OCT22 C C 2nd C 01SEP21 U C C "
             "3rd 01SEP24 01JAN22 01JAN14 01SEP24 01AUG23 "
             "Other Workers 01APR22 01MAY19 01JAN14 01APR22 01DEC21 4th 15DEC22 15DEC22 15DEC22 15DEC22 15DEC22 "
             "Certain Religious Workers 15DEC22 15DEC22 15DEC22 15DEC22 15DEC22 "
             "5th Unreserved C 01DEC16 U C C 5th Set Aside: Rural C C C C C "
             "5th Set Aside: High Unemployment C C C C C 5th Set Aside: Infrastructure C C C C C "
             "Dates for Filing for Employment-Based Preference Cases "
             "This chart may be used to determine when to assemble documents. "
             "1st C 01DEC23 01APR23 C C 2nd C 01OCT21 U C C "
             "3rd 01FEB25 01JUN22 01JUL14 01FEB25 01JAN24 "
             "Other Workers 01JUN22 01JUL19 01JUL14 01JUN22 01MAY22 4th 15JAN23 15JAN23 15JAN23 15JAN23 15JAN23 "
             "Certain Religious Workers 15JAN23 15JAN23 15JAN23 15JAN23 15JAN23 "
             "5th Unreserved C 01JAN17 U C C 5th Set Aside: Rural C C C C C "
             "5th Set Aside: High Unemployment C C C C C 5th Set Aside: Infrastructure C C C C C")
fad3, dff3, fb3 = parse_strict(SELF_ECHO)
check("表A 说明里重复出现自己的标题 → 表A 值正确", fad3, "2023-07-01")
check("同一页表B 仍然正确", dff3, "2023-12-01")
check("  ↑ 且窗口没被自我截断，没走位置兜底", fb3, False)

TRUNCATED = ("Final Action Dates for Employment-Based Preference Cases "
             "1st C 01JUL23 15OCT22 C C 2nd C 01SEP21 U C C "
             "3rd 01SEP24 01JAN22 01JAN14 01SEP24 01AUG23")
expect_raises("表被裁剪至 3 行 → 抛异常（不返回半张表）",
              lambda: S.parse_eb1_china(TRUNCATED))

print("\n## 4b. 多类别解析（EB-1A..EB-5 × ROW/CN/IN/MX/PH，表A+表B）")
# 夹具 = 2026-10 期(FY2027 首期)的数值，按 DOS 页面文字形态重建（含真实的括号说明与 6 行标签）。
# 数值来自 DOS 公告转录（yuchenlin/pd-tracker，与 vyakunin 库逐格一致），非直接抓取的 HTML。
OCT26 = (
    "Visa Bulletin For October 2026 "
    "A. FINAL ACTION DATES FOR EMPLOYMENT-BASED PREFERENCE CASES "
    "Employment-Based All Chargeability Areas Except Those Listed CHINA-mainland born INDIA MEXICO PHILIPPINES "
    "1st C 01JUL23 01FEB23 C C "
    "2nd 01JAN25 01OCT21 01NOV13 01JAN25 01JAN25 "
    "3rd 15MAY24 08JAN22 01JAN14 15MAY24 15AUG23 "
    "Other Workers 01JAN22 01OCT19 01JAN14 01JAN22 01JAN22 "
    "4th 15DEC22 15DEC22 15DEC22 15DEC22 15DEC22 "
    "Certain Religious Workers 15DEC22 15DEC22 15DEC22 15DEC22 15DEC22 "
    "5th Unreserved (including C5, T5, I5, R5, NU, RU) C 01DEC16 01DEC23 C C "
    "5th Set Aside: Rural (20%, including NR, RR) C C C C C "
    "5th Set Aside: High Unemployment (10%, including NH, RH) C C C C C "
    "5th Set Aside: Infrastructure (2%, including RI) C C C C C "
    "B. DATES FOR FILING OF EMPLOYMENT-BASED VISA APPLICATIONS "
    "Employment-Based All Chargeability Areas Except Those Listed CHINA-mainland born INDIA MEXICO PHILIPPINES "
    "1st C 01JUL24 01JUL24 C C "
    "2nd 15MAR26 01JAN23 15JAN15 15MAR26 15MAR26 "
    "3rd 01AUG24 01APR24 15JAN15 01AUG24 01JAN24 "
    "Other Workers 01MAR26 01JUL19 01JUL14 01MAR26 01JAN24 "
    "4th 01JAN25 01JAN25 01JAN25 01JAN25 01JAN25 "
    "Certain Religious Workers 01JAN25 01JAN25 01JAN25 01JAN25 01JAN25 "
    "5th Unreserved (including C5, T5, I5, R5) C 01MAR21 01MAY24 C C "
    "5th Set Aside: Rural (20%, including NR, RR) C C C C C "
    "5th Set Aside: High Unemployment (10%, including NH, RH) C C C C C "
    "5th Set Aside: Infrastructure (2%, including RI) C C C C C")
# 夹具里 A 表标题借用 "Final Action Dates ... Employment" 的锚点写法
OCT26 = OCT26.replace("A. FINAL ACTION DATES FOR EMPLOYMENT-BASED PREFERENCE CASES",
                      "Final Action Dates for Employment-Based Preference Cases").replace(
                      "B. DATES FOR FILING OF EMPLOYMENT-BASED VISA APPLICATIONS",
                      "Dates for Filing of Employment-Based Visa Applications")
cells = S.parse_eb_cells(OCT26)
check("共解析 8 类 × 5 国 = 40 格", len(cells), 40)
check("EB-1A 中国 A/B", cells[("EB-1A", "CN")], ("2023-07-01", "2024-07-01"))
check("EB-1A 印度 A/B", cells[("EB-1A", "IN")], ("2023-02-01", "2024-07-01"))
check("EB-1A ROW = Current", cells[("EB-1A", "ROW")], ("current", "current"))
check("EB-2 中国", cells[("EB-2", "CN")], ("2021-10-01", "2023-01-01"))
check("EB-2 印度", cells[("EB-2", "IN")], ("2013-11-01", "2015-01-15"))
check("EB-2 ROW / 墨西哥 / 菲律宾同日", {cells[("EB-2", c)] for c in ("ROW", "MX", "PH")}, {("2025-01-01", "2026-03-15")})
check("EB-3 中国", cells[("EB-3", "CN")], ("2022-01-08", "2024-04-01"))
check("EB-3 菲律宾落后于 ROW", cells[("EB-3", "PH")], ("2023-08-15", "2024-01-01"))
check("EB-4 各国同日", {cells[("EB-4", c)] for c in S.CELL_COLS}, {("2022-12-15", "2025-01-01")})
check("EB-5 非预留 中国", cells[("EB-5", "CN")], ("2016-12-01", "2021-03-01"))
check("EB-5 非预留 印度", cells[("EB-5", "IN")], ("2023-12-01", "2024-05-01"))
check("EB-5 括号说明里的 C5/NU 不被当成 Current", cells[("EB-5", "ROW")], ("current", "current"))
check("EB-5 三个预留类全 Current", {cells[(k, c)] for k in ("EB-5-Rural", "EB-5-HighUnemp", "EB-5-Infra") for c in S.CELL_COLS},
      {("current", "current")})
check("EW / 宗教工作者行被跳过、不串位", ("EW", "CN") in cells or (None, "CN") in cells, False)
# 与 EB-1 中国旧解析器一致（EB-1A 中国的更新路径不得受影响）
fadx, dffx, fbx = parse_strict(OCT26)
check("旧解析器 parse_eb1_china 在同一夹具上不变", (fadx, dffx, fbx), ("2023-07-01", "2024-07-01", False))
# 含 El Salvador/Guatemala/Honduras 第 6 列的旧版式
OLD6 = ("Final Action Dates for Employment-Based Preference Cases "
        "1st C 01JUL23 C 01FEB23 C C 2nd C 01SEP21 C U C C 3rd 01SEP24 01JAN22 01JAN22 01JAN14 01SEP24 01AUG23 "
        "Other Workers 01APR22 01MAY19 01APR22 01JAN14 01APR22 01DEC21 4th 15DEC22 15DEC22 15DEC22 15DEC22 15DEC22 15DEC22 "
        "5th Unreserved C 01DEC16 C U C C "
        "Dates for Filing for Employment-Based Preference Cases "
        "1st C 01DEC23 C 01APR23 C C 2nd C 01OCT21 C U C C 3rd 01FEB25 01JUN22 01JUN22 01JUL14 01FEB25 01JAN24 "
        "Other Workers 01JUN22 01JUL19 01JUN22 01JUL14 01JUN22 01MAY22 4th 15JAN23 15JAN23 15JAN23 15JAN23 15JAN23 15JAN23 "
        "5th Unreserved C 01JAN17 C U C C")
c6 = S.parse_eb_cells(OLD6)
check("6 列版式：丢掉 ESGH 后列不串位（印度 EB-2 = Unavailable）", c6[("EB-2", "IN")], ("unavailable", "unavailable"))
check("6 列版式：中国 EB-3", c6[("EB-3", "CN")], ("2022-01-01", "2022-06-01"))
# 失败模式：多类别解析失败必须只告警、返回 None，不能抛（否则会拖垮 EB-1A 中国更新）
buf2 = io.StringIO()
with contextlib.redirect_stdout(buf2):
    bad = S.parse_cells_safe(TRUNCATED)
check("表被裁剪 → parse_cells_safe 返回 None 并告警", (bad is None, "多类别解析失败" in buf2.getvalue()), (True, True))

# 写回：CUTOFF_DATA 整块重写 + HIST_DATA 追加，且 EB-1A/CN 的旧正则仍可匹配
MINI = ("var CUTOFF_DATA = {\n"
        "  'EB-1A': { 'CN': { A: '2023-07-01', B: '2024-07-01' }, 'IN': { A: '2023-01-01', B: '2024-01-01' } },\n"
        "  'EB-2': { 'CN': { A: '2021-06-01', B: '2022-01-01' } }\n"
        "}; // CUTOFF_DATA_END\n"
        "var HIST_DATA = /*HIST_DATA_BEGIN*/{\n"
        "  \"EB-2|CN|A\":[[\"2021-06-15\",\"2021-06-01\"],[\"2026-09-15\",\"2021-06-01\"]],\n"
        "  \"EB-2|IN|A\":[[\"2026-08-15\",\"2013-04-01\"]]\n"
        "}/*HIST_DATA_END*/;\n")
new = S.apply_cells_to_index(MINI, {("EB-2", "CN"): ("2021-10-01", "2023-01-01"),
                                    ("EB-2", "IN"): ("unavailable", "2015-01-15"),
                                    ("EB-1A", "CN"): ("2099-01-01", "2099-01-01")}, "2026-10-15")
cut = S.read_cutoff_block(new)
check("CUTOFF_DATA 更新 EB-2 中国", cut["EB-2"]["CN"], {"A": "2021-10-01", "B": "2023-01-01"})
check("CUTOFF_DATA 新增 EB-2 印度(unavailable)", cut["EB-2"]["IN"], {"A": "unavailable", "B": "2015-01-15"})
check("EB-1A 中国不被多类别写回改动", cut["EB-1A"]["CN"], {"A": "2023-07-01", "B": "2024-07-01"})
check("EB-1A 行仍以 CN 打头(read_current_ab 正则依赖)",
      bool(__import__("re").search(r"'EB-1A':\s*\{\s*'CN':\s*\{\s*A:\s*'([0-9-]+)',\s*B:\s*'([0-9-]+)'", new)), True)
import json as _json2  # noqa: E402
_h = _json2.loads(new.split("/*HIST_DATA_BEGIN*/")[1].split("/*HIST_DATA_END*/")[0])
check("HIST_DATA 变化 → 追加新点", _h["EB-2|CN|A"][-1], ["2026-10-15", "2021-10-01"])
check("HIST_DATA 新序列按 U 记入", _h["EB-2|IN|A"][-1], ["2026-10-15", "U"])
_h2 = _json2.loads(S.apply_cells_to_index(MINI, {("EB-2", "CN"): ("2021-06-01", "2022-01-01")}, "2026-10-15")
                   .split("/*HIST_DATA_BEGIN*/")[1].split("/*HIST_DATA_END*/")[0])
check("HIST_DATA 平台期 → 只挪末点，不膨胀", _h2["EB-2|CN|A"], [["2021-06-15", "2021-06-01"], ["2026-10-15", "2021-06-01"]])
# 真实 index.html：块可读且往返幂等（防止格式漂移让探测器下次写坏文件）
_idx = open(S.INDEX, encoding="utf-8").read()
check("index.html 的 CUTOFF_DATA 往返幂等", S.write_cutoff_block(_idx, S.read_cutoff_block(_idx)) == _idx, True)
check("index.html 的 EB-1A/CN 仍可被 read_current_ab 读到", all(S.read_current_ab()), True)
_ab = S.read_current_ab()
check("index.html 的 HIST_DATA 是合法 JSON", isinstance(_json2.loads(
    _idx.split("/*HIST_DATA_BEGIN*/")[1].split("/*HIST_DATA_END*/")[0]), dict), True)

print("\n## 5. shell 脚本:变量后紧跟中文必须加花括号")
# 2026-09-18 真实事故:uscis_chart_watch.sh 里的 "...递交用 $label。已自动上线。"
# 在 macOS 自带的 bash 3.2 上,全角句号被吞进变量名 → 查 `label。` 这个不存在的
# 变量 → 撞上 set -u → 脚本当场退出。数据已推送但 Bark 没发出去。
# 这类写法在 Linux/新 bash 上正常,只在用户的机器上炸——本地跑测试也测不出来,
# 只能靠静态扫描。
import glob as _glob  # noqa: E402
import os as _os  # noqa: E402
import re as _re  # noqa: E402
_bad = []
_pat = _re.compile(r'\$[A-Za-z_][A-Za-z0-9_]*[^\x00-\x7F]')
_root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
for _f in sorted(_glob.glob(_os.path.join(_root, "scripts", "*.sh"))):
    for _i, _line in enumerate(open(_f, encoding="utf-8"), 1):
        if _pat.search(_line):
            _bad.append(f"{_os.path.basename(_f)}:{_i}")
check(f"scripts/*.sh 无裸 $VAR 紧跟多字节字符{'（命中: ' + ', '.join(_bad) + '）' if _bad else ''}",
      _bad, [])

print("\n## 6. 密探窗口:cron 与门控必须同步")
# cron 决定"跑不跑",CORE_DAY_HI 决定"探不探"。只放宽一边等于没放宽——
# 2026-09 就差点这样:cron 加密到 17 号,而实测发布日含 20 号。
import os as _os  # noqa: E402
import re as _re  # noqa: E402
_wf = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                    ".github", "workflows", "sniff-visa-bulletin.yml")
_m = _re.search(r"cron:\s*'[\d,]+ [\d-]+ (\d+)-(\d+) \* \*'", open(_wf, encoding="utf-8").read())
check("cron 加密档期与 CORE_DAY_LO/HI 一致",
      (int(_m.group(1)), int(_m.group(2))) if _m else None,
      (S.CORE_DAY_LO, S.CORE_DAY_HI))
# 历史实测发布日必须全部落在密探窗内,否则命中当天会被稀疏探测拖慢数小时
import json as _json  # noqa: E402
_days = [r["day"] for r in _json.load(open(_os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "data", "release_log.json"),
    encoding="utf-8")) if r.get("day") is not None]   # 发布日未知的补录期不是观测值，不参与
check(f"历史发布日 {sorted(_days)} 全在密探窗 {S.CORE_DAY_LO}-{S.CORE_DAY_HI} 内",
      all(S.CORE_DAY_LO <= d <= S.CORE_DAY_HI for d in _days), True)

print("\n## 7. 兜底分支不得谎报「已发布」")
# 2026-09 的真实 bug:fetch_filing_chart 改成返回 (chart, fetched_ok) 后,
# probe_target 里的 Wayback 兜底分支漏改,接成了单值 → 拿到元组 → 元组恒为真
# → 无条件走进「USCIS AOS 页已出现该月 → 公告已发布！」。
# 更糟的是它返回 pending,而 run() 的逾期告警条件是 status not in ("hit","pending"),
# 于是「过 20 号仍未命中推 critical 告警」这道防线被一并抑制。
import types  # noqa: E402

_saved = {k: getattr(S, k) for k in
          ("probe_published", "wayback_check", "wayback_last_capture",
           "wayback_save", "fetch_filing_chart")}
try:
    S.probe_published = lambda ty, tm: (None, "travel.state.gov HTTP 403", None)
    S.wayback_check = lambda url: None
    S.wayback_last_capture = lambda url: None
    S.wayback_save = lambda url: None
    # USCIS 页取回成功、但没提到目标月 —— 也就是"还没发布"
    S.fetch_filing_chart = lambda ty, tm: (None, True)
    st, detail = S.probe_target(2026, 10, "2026-10", [],
                                types.SimpleNamespace(dry_run=True, force=True),
                                S.now_et())
    check("USCIS 未提及该月 → 不得判为已发布", "公告已发布" in detail, False)
    check("  ↑ 且状态不能是 pending(否则逾期 critical 告警会被抑制)", st == "pending", False)
finally:
    for k, v in _saved.items():
        setattr(S, k, v)

print("\n## 6. 逾期提醒限频（每天至多一次）")
# 发布窗外每天约 28 次 cron(*/30)，早期实现每次探测都推 Bark → 刷屏。
# 只认 ET 09:00–09:29 一个槽；此处遍历当日全部 cron 槽，命中数必须恰好为 1。
from datetime import datetime, timezone  # noqa: E402

try:
    from zoneinfo import ZoneInfo
    _ET = ZoneInfo("America/New_York")
except Exception:
    _ET = None


def _slots(y, mo):
    """当日实际会触发的 cron 槽（UTC 13–23 与 0–2，每半小时），换算到 ET。"""
    out = []
    for h in list(range(13, 24)) + [0, 1, 2]:
        for mi in (0, 30):
            out.append(datetime(y, mo, 22, h, mi, tzinfo=timezone.utc).astimezone(_ET))
    return out


if _ET:
    summer = [s for s in _slots(2026, 9) if S.is_daily_alert_slot(s)]
    winter = [s for s in _slots(2026, 12) if S.is_daily_alert_slot(s)]
    check("夏令时当日命中次数 = 1", len(summer), 1)
    check("冬令时当日命中次数 = 1", len(winter), 1)
    check("命中的是 ET 09:00 那一槽", summer and summer[0].hour == 9, True)
else:
    print("  ⏭ 无 zoneinfo，跳过")

print()
if FAILED:
    print(f"❌ {len(FAILED)} 项失败: {FAILED}")
    sys.exit(1)
print("✅ 全部通过")

#!/usr/bin/env python3
"""签证公告探测的回归测试。

覆盖三处历史上出过错或最易出错的地方：
  1. 财年目录边界（9 月 vs 10 月）——URL 拼错会导致 100% 漏抓
  2. 命中校验能否拒绝「CDN 返回上一期缓存页」
  3. 表结构被裁剪时解析器必须抛异常，而非静默返回半张表

跑法：python scripts/test_sniff.py
"""
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
fad2, dff2 = S.parse_eb1_china(LONG_PREAMBLE)
check("表B 表头后隔长段说明 → 仍锚定到正确的表B 行", dff2, "2023-12-01")
check("同一页里有诱饵 1st 行 → 表A 不被位置兜底带偏", fad2, "2023-07-01")

TRUNCATED = ("Final Action Dates for Employment-Based Preference Cases "
             "1st C 01JUL23 15OCT22 C C 2nd C 01SEP21 U C C "
             "3rd 01SEP24 01JAN22 01JAN14 01SEP24 01AUG23")
expect_raises("表被裁剪至 3 行 → 抛异常（不返回半张表）",
              lambda: S.parse_eb1_china(TRUNCATED))

print()
if FAILED:
    print(f"❌ {len(FAILED)} 项失败: {FAILED}")
    sys.exit(1)
print("✅ 全部通过")

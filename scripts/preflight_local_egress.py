#!/usr/bin/env python3
"""本机出口连通性预检：判断这台机器的 IP 能不能直连 DOS / USCIS。

装 runner 之前先跑这个。GitHub 托管 runner 走 Azure 机房段，被 Akamai 整段 403；
自建 runner 的价值完全取决于「你这条出口是不是干净的住宅 IP」——云 VPS 同样会被挡。
预检 3 分钟给答案，避免装完一小时才发现照样 403。

判读：
  200/206  通道通且资源存在
  404      通道通，只是该期尚未发布（正常，不是失败）
  405      通道通，只是该主机禁 HEAD（正常）
  403      被 WAF 挡 —— 这条出口不可用
  超时/重置 多半是本地网络/代理问题，不等于被封，可重跑一次

用法：
    python3 scripts/preflight_local_egress.py          # 全量预检
    python3 scripts/preflight_local_egress.py --quiet  # 只输出结论行
退出码：0 = 可用（关键探测通道全部非 403）；1 = 不可用。
"""
import argparse
import os
import sys
import urllib.error
import urllib.request
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sniff_visa_bulletin import UA, HOSTS, bulletin_url, pdf_urls  # noqa: E402

USCIS_AOS = ("https://www.uscis.gov/green-card/green-card-processes-and-procedures/"
             "visa-availability-priority-dates/adjustment-of-status-filing-charts-from-the-visa-bulletin")
USCIS_DATA = "https://www.uscis.gov/sites/default/files/document/data"
DOS_INDEX = "https://travel.state.gov/content/travel/en/legal/visa-law0/visa-bulletin.html"


def _pad(text, width):
    """中文字符占两列，用显示宽度对齐表格。"""
    w = sum(2 if ord(c) > 0x2E7F else 1 for c in text)
    return text + " " * max(0, width - w)


def probe(url, method="GET"):
    """返回 (状态码或 None, 说明)。只读首字节，不下载正文。"""
    headers = {"User-Agent": UA, "Cache-Control": "no-cache"}
    if method == "GET":
        headers["Range"] = "bytes=0-1023"
    req = urllib.request.Request(url, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.getcode(), ""
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:80]}"


def egress_ip():
    """尽力查一下出口 IP，仅用于人工判断是不是住宅线路；失败不影响预检。"""
    try:
        req = urllib.request.Request("https://api.ipify.org", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read().decode("ascii", "ignore").strip()
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true", help="只打印结论")
    args = ap.parse_args()

    t = date.today()
    # 取上个月那期：一定已发布，因此 200 才是「通道通 + 资源在」的干净证据。
    py, pm = (t.year - 1, 12) if t.month == 1 else (t.year, t.month - 1)

    checks = [
        ("DOS 公告索引页", DOS_INDEX, "GET", True),
        (f"DOS {py}-{pm:02d} 月份页", bulletin_url(py, pm), "GET", True),
        (f"DOS {py}-{pm:02d} PDF", pdf_urls(py, pm)[0], "HEAD", True),
        ("USCIS AOS 用表页", USCIS_AOS, "GET", True),
        ("USCIS 数据目录", f"{USCIS_DATA}/", "HEAD", False),
    ]
    # 镜像主机：任一可用即够，逐个记录但不单独否决。
    for h in HOSTS[1:]:
        checks.append((f"镜像 {h}", bulletin_url(py, pm, h), "GET", False))

    results, blocked, key_blocked = [], 0, 0
    for name, url, method, key in checks:
        code, err = probe(url, method)
        results.append((name, code, err, key))
        if code == 403:
            blocked += 1
            if key:
                key_blocked += 1

    if not args.quiet:
        ip = egress_ip()
        print(f"出口 IP: {ip or '查询失败(不影响判定)'}")
        print(f"探测基准期: {py}-{pm:02d}（上一期，官方一定已发布）\n")
        for name, code, err, key in results:
            mark = {403: "✗ 被挡", None: "? 网络异常"}.get(code, "✓ 通")
            if code in (404, 405):
                mark = "✓ 通"
            flag = "[关键]" if key else "      "
            print(f"{flag} {_pad(name, 32)} {str(code or '—'):>5}  {mark}  {err}")
        print()

    if key_blocked:
        print(f"结论：不可用 —— {key_blocked} 个关键通道返回 403，这条出口被 WAF 挡了。")
        print("      若当前在云 VPS / 公司网络 / 机房 VPN 上，换成家庭宽带再跑一次。")
        return 1
    if any(c is None for _, c, _, k in results if k):
        print("结论：未定 —— 关键通道出现网络异常（超时/重置），不等于被封。")
        print("      检查本机代理设置后重跑；连续两次异常再判为不可用。")
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        if proxy:
            print(f"      注意：当前设了 HTTPS_PROXY={proxy}——抓取会走代理出口而非本机 IP，"
                  "先 unset 再跑。")
        return 1
    print(f"结论：可用 —— 关键通道全部放行（被挡 {blocked} 个非关键镜像）。")
    print("      这台机器适合做自建 runner，执行 scripts/setup_local_runner.sh 继续。")
    return 0


if __name__ == "__main__":
    sys.exit(main())

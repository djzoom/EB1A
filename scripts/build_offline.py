#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
打包离线单文件版 EB1A.html。

把仓库的 index.html 加工成一个完全自包含、双击即用、离线可跑的单文件：
  - 内联 React / HeroUI Pro 的 CSS 与单文件 JS
  - 去掉 GSAP 动画外链（现有 gsapReady() 守卫会让动画自动跳过）
  - 去掉 PWA 的 manifest / icon 外链（本地无服务器，会 404）
  - 注入 base64 秒表 favicon
  - 加一行「离线版 · 数据截至 {VB_MONTH} · 不自动更新」提示

数据无需在此更新：index.html 里的公告常量由 CI（sniff_visa_bulletin.py）在每期
公告发布时自动改写并提交到 main，本脚本只消费最新的 index.html。

用法：python3 scripts/build_offline.py
产物：dist/EB1A.html
"""

import base64
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "index.html"
ICON = ROOT / "icon-192.png"
DIST = ROOT / "dist"


def ensure_ui_assets():
    subprocess.run(["node", str(ROOT / "scripts" / "build_ui.mjs")], cwd=ROOT, check=True)


def main(skip_ui=False) -> int:
    if not SRC.exists():
        print(f"找不到 {SRC}", file=sys.stderr)
        return 1

    if not skip_ui:
        ensure_ui_assets()
    html = SRC.read_text(encoding="utf-8")

    # 先验证两个入口都存在，避免打出无界面或仍需 HTTP 的假离线包。
    css = (ROOT / "assets" / "ui.css").read_text(encoding="utf-8")
    js = (ROOT / "assets" / "ui.js").read_text(encoding="utf-8")
    css = re.sub(r"</style", r"<\\/style", css, flags=re.I)
    js = re.sub(r"</script", r"<\\/script", js, flags=re.I)
    html, n_css = re.subn(r'<link\b[^>]*\bhref=["\'](?:\./)?assets/ui\.css["\'][^>]*>',
                          lambda _: "<style>\n" + css + "\n</style>", html)
    html, n_js = re.subn(r'<script\b[^>]*\bsrc=["\'](?:\./)?assets/ui\.js["\'][^>]*>\s*</script>',
                         lambda _: "<script>\n" + js + "\n</script>", html)
    if n_css != 1 or n_js != 1:
        print("离线构建失败：index.html 必须且只能引用一次 assets/ui.css 和 assets/ui.js", file=sys.stderr)
        return 1

    # 1) 去动画：移除 GSAP 外链脚本
    html, n_gsap = re.subn(r'[ \t]*<script src="vendor/gsap\.min\.js"></script>\n?', "", html)

    # 2) 去 PWA 外链：manifest + 三个 icon link（离线本地会 404）
    html, n_manifest = re.subn(r'[ \t]*<link rel="manifest"[^>]*>\n?', "", html)
    html, n_icons = re.subn(r'[ \t]*<link rel="(?:apple-touch-icon|icon)"[^>]*>\n?', "", html)

    # 3) 注入 base64 favicon（来自秒表 icon-192.png）
    if ICON.exists():
        b64 = base64.b64encode(ICON.read_bytes()).decode("ascii")
        favicon = f'<link rel="icon" type="image/png" href="data:image/png;base64,{b64}">\n'
        html = html.replace("<title>", favicon + "<title>", 1)
    else:
        print(f"警告：缺少 {ICON}，离线文件将无 favicon", file=sys.stderr)

    # 4) 解析当月公告月份（用于提示文案与产物命名）
    m = re.search(r"var VB_MONTH = '([^']*)'", html)
    vb_month = m.group(1) if m else "当前快照"

    # 5) 在页脚加一行离线提示（找页脚版权行前插入）
    notice = (
        f'    <span style="display:block;margin-top:6px;font-size:11px;opacity:0.85">'
        f'离线版 · 数据截至 {vb_month} · 不会自动同步未来公告</span>\n'
    )
    # 插到页脚的「© 2026 djzoom」前；找不到就插到 </body> 前兜底
    if "© 2026 djzoom" in html:
        html = html.replace("    © 2026 djzoom", notice + "    © 2026 djzoom", 1)
    else:
        html = html.replace("</body>", notice + "</body>", 1)

    DIST.mkdir(exist_ok=True)
    out = DIST / "EB1A.html"
    out.write_text(html, encoding="utf-8")

    print(f"✓ 已生成 {out}")
    print(f"  公告快照：{vb_month}")
    print(f"  移除：GSAP×{n_gsap}  manifest×{n_manifest}  icon-link×{n_icons}")
    print(f"  大小：{out.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

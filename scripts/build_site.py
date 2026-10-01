#!/usr/bin/env python3
"""构建 Pages 共用的静态站点，以及可直接下载的离线压缩包。"""

import json
import os
import shutil
import zipfile
from pathlib import Path

from build_offline import main as build_offline

ROOT = Path(__file__).resolve().parent.parent
ASSETS = (
    "index.html", "manifest.json", "sw.js", "icon.svg", "icon-192.png",
    "icon-512.png", "icon-maskable-512.png", "apple-touch-icon.png",
    "vendor/gsap.min.js",
)


def main():
    site = ROOT / "dist" / "site"
    # 只清理由本脚本生成的目录，避免旧资源混进后续发布。
    if site.exists():
        shutil.rmtree(site)
    for name in ASSETS:
        target = site / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    (site / ".nojekyll").touch()
    # 让线上可核对版本；本地构建不依赖 git 或外网。
    (site / "version.json").write_text(
        json.dumps({"commit": os.environ.get("GITHUB_SHA", "local")}) + "\n",
        encoding="utf-8",
    )
    if build_offline() != 0:
        raise SystemExit("离线构建失败")
    with zipfile.ZipFile(ROOT / "dist" / "EB1A-offline.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(ROOT / "dist" / "EB1A.html", "EB1A.html")
        archive.writestr("使用说明.txt", "绿卡排期推演（EB-1～EB-5，多国家）\n\n"
                         "用浏览器打开 EB1A.html 即可，完全离线运行。\n"
                         "本文件为数据快照，不会自动同步未来公告；请下载新版本获取更新。\n"
                         "预测仅供参考，不构成法律或移民建议。实际排期以官方签证公告为准。\n")
    print(f"✓ 站点：{site}；离线包：dist/EB1A-offline.zip")


if __name__ == "__main__":
    main()

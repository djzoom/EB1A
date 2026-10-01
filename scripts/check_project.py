#!/usr/bin/env python3
"""不访问外网的语法、JSON 和静态资源检查。"""

import argparse
import ast
import json
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, unquote

ROOT = Path(__file__).resolve().parent.parent


class PageChecks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inline = False
        self.scripts = []
        self.assets = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script":
            self.inline = not attrs.get("src") and attrs.get("type", "text/javascript") in (
                "text/javascript", "application/javascript", "module")
            if self.inline:
                self.scripts.append("")
        asset = attrs.get("src") if tag in ("script", "img") else None
        if tag == "link" and attrs.get("rel") in ("stylesheet", "manifest", "icon", "apple-touch-icon"):
            asset = attrs.get("href")
        if asset:
            self.assets.append(asset)

    def handle_data(self, data):
        if self.inline:
            self.scripts[-1] += data

    def handle_endtag(self, tag):
        if tag == "script":
            self.inline = False


def main(source_only=False):
    for path in sorted((ROOT / "scripts").glob("*.py")):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for path in sorted((ROOT / "scripts").glob("*.sh")):
        subprocess.run(["bash", "-n", str(path)], check=True)
    for path in [*sorted((ROOT / "scripts").glob("*.mjs")), *sorted(ROOT.glob("*.js"))]:
        subprocess.run(["node", "--check", str(path)], check=True)
    subprocess.run(["node", str(ROOT / "scripts" / "build_ui.mjs"), "--check"], cwd=ROOT, check=True)
    for path in [ROOT / "manifest.json", *sorted((ROOT / "data").glob("*.json"))]:
        json.loads(path.read_text(encoding="utf-8"))
    subprocess.run(["node", "--check", str(ROOT / "sw.js")], check=True)
    page = PageChecks()
    page.feed((ROOT / "index.html").read_text(encoding="utf-8"))
    if not page.scripts:
        raise SystemExit("index.html 中没有可检查的脚本")
    for script in page.scripts:
        subprocess.run(["node", "--check"], input=script, text=True, check=True)
    for asset in page.assets:
        url = urlsplit(asset)
        if source_only and url.path.removeprefix("./") in ("assets/ui.js", "assets/ui.css"):
            continue
        if not url.scheme and not url.netloc and not (ROOT / unquote(url.path)).is_file():
            raise SystemExit(f"缺少页面资源：{asset}")
    if not source_only:
        subprocess.run(["node", "--check", str(ROOT / "assets" / "ui.js")], check=True)
    print("✓ Python / Shell / JavaScript 语法、JSON 和页面资源检查通过")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-only", action="store_true", help="不要求生成的 UI 产物；供无授权令牌的 PR 检查")
    main(source_only=parser.parse_args().source_only)

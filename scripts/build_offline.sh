#!/usr/bin/env bash
# 一条命令：拉取最新数据 → 打包离线单文件 → 生成可分发 zip。
#
# 用法：bash scripts/build_offline.sh
# 产物：dist/EB1A.html、dist/EB1A_排期预测器.zip
set -euo pipefail

cd "$(dirname "$0")/.."

echo "▸ 1/3 拉取最新数据（main）…"
git pull --ff-only origin main || echo "  （拉取跳过/失败，使用本地 index.html 继续）"

echo "▸ 2/3 打包离线单文件…"
python3 scripts/build_offline.py

echo "▸ 3/3 生成分发 zip…"
DIST=dist
cat > "$DIST/使用说明.txt" << 'TXT'
EB-1A 中国申请人绿卡排期预测器（离线版）

【如何使用】
用浏览器打开 EB1A.html 即可（双击文件，或拖进 Chrome / Edge / Safari）。
完全离线运行，无需联网、无需安装。输入你的优先日（Priority Date），
即可估算大约何时排到，并给出快 / 中 / 慢三档预测与置信区间。

【关于数据】
本文件为离线快照，签证公告数据截至打包当月，不会自动同步未来公告。
如需最新数据，请获取新一期的离线文件。

【免责声明】
本工具为基于公开数据（USCIS / DOS）的统计估算，仅供参考，
不构成法律或移民建议，亦不对预测准确性作任何保证。
实际排期以美国国务院官方签证公告为准，重要决策请咨询持牌移民律师。
TXT

cd "$DIST"
rm -f "EB1A_排期预测器.zip"
zip -q "EB1A_排期预测器.zip" "EB1A.html" "使用说明.txt"
cd - > /dev/null

echo "✓ 完成"
echo "  单文件：dist/EB1A.html"
echo "  压缩包：dist/EB1A_排期预测器.zip"

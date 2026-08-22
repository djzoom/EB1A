#!/usr/bin/env bash
# 一键部署自建 GitHub Actions runner（住宅 IP，绕开 DOS/USCIS 对机房 IP 的 403）。
#
# 用法：
#   1) 先跑预检：python3 scripts/preflight_local_egress.py
#   2) 到 GitHub 取注册令牌（约 1 小时过期）：
#      https://github.com/djzoom/EB1A/settings/actions/runners/new
#   3) bash scripts/setup_local_runner.sh <令牌>
#
# 脚本做的事：查依赖 → 下载对应平台 runner → 用 eb1a-fetch 标签注册 →
# 装成开机自启服务 → macOS 关休眠 → 打印下一步（设 RUNNER_LABEL 变量）。
# 幂等：已注册过会提示先注销，不会重复注册。
set -euo pipefail

REPO_URL="https://github.com/djzoom/EB1A"
LABELS="self-hosted,eb1a-fetch"
RUNNER_DIR="${RUNNER_DIR:-$HOME/actions-runner}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

die() { echo "错误：$*" >&2; exit 1; }
step() { echo; echo "── $* ──"; }

TOKEN="${1:-}"
[ -n "$TOKEN" ] || die "缺少注册令牌。到 $REPO_URL/settings/actions/runners/new 取，然后：
  bash scripts/setup_local_runner.sh <令牌>"

step "0/6 环境检查"
case "$(uname -s)" in
  Darwin) OS=osx ;;
  Linux)  OS=linux ;;
  *) die "不支持的系统 $(uname -s)（仅 macOS / Linux）" ;;
esac
case "$(uname -m)" in
  arm64|aarch64) ARCH=arm64 ;;
  x86_64|amd64)  ARCH=x64 ;;
  *) die "不支持的架构 $(uname -m)" ;;
esac
PLATFORM="${OS}-${ARCH}"
echo "平台: $PLATFORM"

command -v curl >/dev/null || die "缺 curl"
command -v tar  >/dev/null || die "缺 tar"

PY="$(command -v python3 || true)"
[ -n "$PY" ] || die "缺 python3（探测脚本需要 3.11+）"
PYV="$("$PY" -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
echo "python3: $PYV"
"$PY" -c 'import sys;sys.exit(0 if sys.version_info[:2]>=(3,11) else 1)' \
  || echo "  ⚠️ 低于 3.11。工作流的 setup-python 会尝试自己下载，但装个系统 3.11+ 更稳。"

step "1/6 出口连通性预检"
# 这一步决定后面五步值不值得做：出口若被 403，装 runner 也是白装。
if [ -f "$REPO_ROOT/scripts/preflight_local_egress.py" ]; then
  if "$PY" "$REPO_ROOT/scripts/preflight_local_egress.py"; then
    echo "预检通过。"
  else
    echo
    read -r -p "预检未通过（见上）。仍要继续安装？[y/N] " ans
    [ "${ans:-N}" = "y" ] || [ "${ans:-N}" = "Y" ] || die "已中止。换到住宅宽带后重试。"
  fi
else
  echo "未找到预检脚本，跳过（建议在仓库根目录运行本脚本）。"
fi

step "2/6 下载 runner"
if [ -f "$RUNNER_DIR/config.sh" ]; then
  echo "$RUNNER_DIR 已存在 runner，跳过下载。"
else
  mkdir -p "$RUNNER_DIR"
  echo "下载到 $RUNNER_DIR ..."
  curl -fsSL -o "$RUNNER_DIR/actions-runner.tar.gz" \
    "https://github.com/actions/runner/releases/latest/download/actions-runner-${PLATFORM}.tar.gz" \
    || die "下载失败。可到 https://github.com/actions/runner/releases 手动下载 ${PLATFORM} 包解压到 $RUNNER_DIR"
  tar xzf "$RUNNER_DIR/actions-runner.tar.gz" -C "$RUNNER_DIR"
  rm -f "$RUNNER_DIR/actions-runner.tar.gz"
fi

step "3/6 注册（标签 $LABELS）"
cd "$RUNNER_DIR"
if [ -f .runner ]; then
  echo "已注册过，跳过。要重装先注销："
  echo "  cd $RUNNER_DIR && sudo ./svc.sh stop && sudo ./svc.sh uninstall && ./config.sh remove --token <remove token>"
else
  # --labels 必须带 eb1a-fetch：工作流的 runs-on 认这个标签，GitHub 网页给的默认命令不含它。
  ./config.sh --url "$REPO_URL" --token "$TOKEN" --labels "$LABELS" \
              --name "$(hostname -s)-eb1a" --unattended --replace \
    || die "注册失败（令牌过期？重新到 $REPO_URL/settings/actions/runners/new 取）"
fi

step "4/6 装成开机自启服务"
# 必须走 svc.sh，不能用 ./run.sh —— 后者关终端就停，重启后不会自动接管。
if [ "$OS" = osx ]; then
  ./svc.sh install && ./svc.sh start
else
  sudo ./svc.sh install "$(whoami)" && sudo ./svc.sh start
fi
sleep 3
./svc.sh status || true

step "5/6 关休眠"
# 机器睡着 = runner 掉线 = 发布窗内的探测任务全部排队，等于没装。
if [ "$OS" = osx ]; then
  echo "需要 sudo 关闭休眠（笔记本合盖也不睡）："
  sudo pmset -a sleep 0 disablesleep 1 && sudo pmset -g | grep -E 'sleep|disablesleep' || true
else
  command -v systemctl >/dev/null && sudo systemctl mask sleep.target suspend.target 2>/dev/null || true
  echo "已尝试禁用挂起（无 systemd 时请自行确认）。"
fi

step "6/6 最后一步：在 GitHub 打开开关"
cat <<EOF

runner 已就绪，但工作流还没切过来。到：

  $REPO_URL/settings/variables/actions

新建仓库变量：
  Name : RUNNER_LABEL
  Value: eb1a-fetch

设上 = 抓取类工作流走这台机器；删掉 = 立刻回退 ubuntu-latest（逃生口）。

验证（约 1 分钟）：
  $REPO_URL/actions/workflows/sniff-visa-bulletin.yml
  → Run workflow，勾 selftest → 看日志里 403 是否变成 200

看门狗（强烈建议，防机器掉线后静默排队）：
  bash $REPO_ROOT/scripts/runner_watchdog.sh --install

EOF

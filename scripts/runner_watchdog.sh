#!/usr/bin/env bash
# 自建 runner 看门狗：定时检查服务是否在跑、出口是否仍未被封，异常时自愈 + Bark 报警。
#
# 为什么需要：runner 掉线时 GitHub 不会报错，只会把 job 挂在 queued（最多等 24 小时）。
# 发布窗内每 10 分钟一次触发，掉线一晚上就是几十个排队任务 + 当期公告漏抓——
# 而页面上只会显示「尚未发布」，没人知道是探测断了。看门狗把这种静默失败变成一条推送。
#
# 用法：
#   bash scripts/runner_watchdog.sh            # 手动跑一次
#   bash scripts/runner_watchdog.sh --install  # 装进 crontab（每 30 分钟）
#   bash scripts/runner_watchdog.sh --remove   # 从 crontab 卸载
#
# Bark：设环境变量 BARK_KEY，或写进 ~/.eb1a_bark_key（一行 key）。未配置则只打印不推送。
set -uo pipefail

RUNNER_DIR="${RUNNER_DIR:-$HOME/actions-runner}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="${STATE_DIR:-$HOME/.eb1a-watchdog}"
MARKER="# eb1a-runner-watchdog"
ALERT_COOLDOWN=$((6 * 3600))   # 同类告警最多 6 小时一条，避免刷屏

mkdir -p "$STATE_DIR"
PY="$(command -v python3 || true)"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# 同类告警在冷却期内只打印不推送。
alert() {
  local kind="$1" title="$2" body="$3"
  local stamp="$STATE_DIR/last_$kind"
  local now; now=$(date +%s)
  local prev=0
  [ -f "$stamp" ] && prev=$(cat "$stamp" 2>/dev/null || echo 0)
  log "告警[$kind] $body"
  if [ $((now - prev)) -lt "$ALERT_COOLDOWN" ]; then
    log "  （冷却期内，跳过推送）"
    return
  fi
  echo "$now" > "$stamp"
  local key="${BARK_KEY:-}"
  [ -z "$key" ] && [ -f "$HOME/.eb1a_bark_key" ] && key="$(tr -d '[:space:]' < "$HOME/.eb1a_bark_key")"
  if [ -z "$key" ] || [ -z "$PY" ]; then
    log "  （未配置 BARK_KEY，只记录不推送）"
    return
  fi
  BARK_KEY="$key" BARK_TITLE="$title" BARK_BODY="$body" \
    "$PY" "$REPO_ROOT/scripts/sniff_visa_bulletin.py" --send-bark >/dev/null 2>&1 \
    && log "  已推送" || log "  推送失败"
}

install_cron() {
  # cron 里没有登录 shell 的环境变量，Bark key 一律从 ~/.eb1a_bark_key 读。
  local line="*/30 * * * * bash $REPO_ROOT/scripts/runner_watchdog.sh >> $STATE_DIR/watchdog.log 2>&1 $MARKER"
  if crontab -l 2>/dev/null | grep -qF "$MARKER"; then
    log "已安装过，先卸载再重装以更新路径：bash $0 --remove"
    exit 0
  fi
  { crontab -l 2>/dev/null; echo "$line"; } | crontab -
  log "已装入 crontab（每 30 分钟一次），日志：$STATE_DIR/watchdog.log"
  log "Bark 报警需要 key：echo '<你的 BARK_KEY>' > ~/.eb1a_bark_key && chmod 600 ~/.eb1a_bark_key"
  exit 0
}

remove_cron() {
  crontab -l 2>/dev/null | grep -vF "$MARKER" | crontab -
  log "已从 crontab 移除"
  exit 0
}

case "${1:-}" in
  --install) install_cron ;;
  --remove)  remove_cron ;;
  "")        ;;
  *) echo "未知参数 $1（可用：--install / --remove）" >&2; exit 2 ;;
esac

fail=0

# ① runner 服务在不在
if [ ! -f "$RUNNER_DIR/svc.sh" ]; then
  log "跳过服务检查：$RUNNER_DIR 下没有 runner（未安装？）"
else
  cd "$RUNNER_DIR"
  status_out="$( { [ "$(uname -s)" = Darwin ] && ./svc.sh status || sudo -n ./svc.sh status; } 2>&1 )"
  if echo "$status_out" | grep -Eqi 'running|active \(running\)|started'; then
    log "runner 服务：运行中"
  else
    log "runner 服务：未运行 —— 尝试拉起"
    if [ "$(uname -s)" = Darwin ]; then ./svc.sh start >/dev/null 2>&1; else sudo -n ./svc.sh start >/dev/null 2>&1; fi
    sleep 5
    recheck="$( { [ "$(uname -s)" = Darwin ] && ./svc.sh status || sudo -n ./svc.sh status; } 2>&1 )"
    if echo "$recheck" | grep -Eqi 'running|active \(running\)|started'; then
      alert svc_restart "EB1A runner 已自动重启" \
        "自建 runner 服务此前停止，看门狗已拉起。若反复发生请检查这台机器的电源/网络。"
    else
      fail=1
      alert svc_down "EB1A runner 掉线⚠️" \
        "自建 runner 服务停止且自动拉起失败。签证公告探测任务正在 GitHub 上排队（最多等 24h）。请上机排查，或先到仓库 Settings → Variables 删掉 RUNNER_LABEL 回退托管 runner。"
    fi
  fi
fi

# ② 出口还通不通（住宅 IP 也可能被新规则命中）
if [ -n "$PY" ] && [ -f "$REPO_ROOT/scripts/preflight_local_egress.py" ]; then
  if "$PY" "$REPO_ROOT/scripts/preflight_local_egress.py" --quiet >/dev/null 2>&1; then
    log "出口连通性：正常"
  else
    fail=1
    alert egress_blocked "EB1A 抓取出口异常⚠️" \
      "本机到 DOS/USCIS 的关键通道预检未通过（403 或网络异常）。自建 runner 即使在跑也抓不到数据，请核查网络，必要时人工录入。"
  fi
fi

[ "$fail" = 0 ] && log "巡检正常" || log "巡检发现问题（见上）"
exit "$fail"

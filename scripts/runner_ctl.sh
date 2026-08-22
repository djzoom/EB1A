#!/usr/bin/env bash
# 自建 runner 开关：一条命令同时管「本机服务」和「GitHub 上的 RUNNER_LABEL 变量」。
#
# 两者的分工要分清：
#   RUNNER_LABEL 变量 = 真正的开关，决定抓取类工作流的活派给谁（自建 / ubuntu-latest）
#   本机 runner 服务  = 有没有人接活
# 变量没设时，本机服务即使在跑也只是空转，不会接到任何活——所以变量才是权威状态，
# 关的时候先删变量、再停服务；开的时候先起服务、再设变量（避免变量已切走但没人接）。
#
# 用法：
#   bash scripts/runner_ctl.sh on            # 打开：起服务 + 设变量
#   bash scripts/runner_ctl.sh off           # 关闭：删变量 + 停服务
#   bash scripts/runner_ctl.sh status        # 看三方状态（服务 / 变量 / 当前该不该开）
#   bash scripts/runner_ctl.sh state         # 只打印 on/off/unknown（给脚本用）
#   bash scripts/runner_ctl.sh auto          # 按发布窗自动开关，跑一次
#   bash scripts/runner_ctl.sh --install-auto  # 装进 crontab（每小时一次）
#   bash scripts/runner_ctl.sh --remove-auto   # 卸载
#
# 改 GitHub 变量需要凭据，二选一：
#   ① 装了 gh CLI 并 gh auth login（最省事）
#   ② 细粒度 PAT 写进 ~/.eb1a_gh_token（权限：本仓库 Variables = Read and write）
#      echo 'github_pat_xxx' > ~/.eb1a_gh_token && chmod 600 ~/.eb1a_gh_token
set -uo pipefail

REPO="${EB1A_REPO:-djzoom/EB1A}"
VAR_NAME="RUNNER_LABEL"
VAR_VALUE="eb1a-fetch"
RUNNER_DIR="${RUNNER_DIR:-$HOME/actions-runner}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="${STATE_DIR:-$HOME/.eb1a-watchdog}"
MARKER="# eb1a-runner-auto"
TOKEN_FILE="$HOME/.eb1a_gh_token"

mkdir -p "$STATE_DIR"
IS_MAC=false; [ "$(uname -s)" = Darwin ] && IS_MAC=true
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
die() { echo "错误：$*" >&2; exit 1; }

# ---------- GitHub 变量读写 ----------

gh_token() {
  [ -n "${GH_TOKEN:-}" ] && { echo "$GH_TOKEN"; return; }
  [ -f "$TOKEN_FILE" ] && tr -d '[:space:]' < "$TOKEN_FILE"
}

# 打印变量当前值；未设置则打印空串。返回 0=查到，1=未设置，2=查不了（无凭据/网络）
var_get() {
  if command -v gh >/dev/null && gh auth status >/dev/null 2>&1; then
    local out rc
    out="$(gh api "repos/$REPO/actions/variables/$VAR_NAME" --jq .value 2>&1)"; rc=$?
    [ $rc -eq 0 ] && { echo "$out"; return 0; }
    echo "$out" | grep -qi "not found" && return 1
    echo "  gh: $(echo "$out" | head -1)" >&2; return 2
  fi
  local tok; tok="$(gh_token)"
  [ -n "$tok" ] || return 2
  local body code
  body="$(curl -sS -w '\n%{http_code}' -H "Authorization: Bearer $tok" \
          -H "Accept: application/vnd.github+json" \
          "https://api.github.com/repos/$REPO/actions/variables/$VAR_NAME" 2>/dev/null)" || return 2
  code="$(printf '%s' "$body" | tail -n1)"
  case "$code" in
    200) printf '%s' "$body" | sed '$d' | sed -n 's/.*"value"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p'; return 0 ;;
    404) return 1 ;;
    *) echo "  API 返回 $code" >&2; return 2 ;;
  esac
}

var_set() {
  if command -v gh >/dev/null && gh auth status >/dev/null 2>&1; then
    gh api --method PATCH "repos/$REPO/actions/variables/$VAR_NAME" \
       -f name="$VAR_NAME" -f value="$VAR_VALUE" >/dev/null 2>&1 && return 0
    gh api --method POST "repos/$REPO/actions/variables" \
       -f name="$VAR_NAME" -f value="$VAR_VALUE" >/dev/null 2>&1 && return 0
    return 1
  fi
  local tok; tok="$(gh_token)"
  [ -n "$tok" ] || return 2
  local payload="{\"name\":\"$VAR_NAME\",\"value\":\"$VAR_VALUE\"}" code
  code="$(curl -sS -o /dev/null -w '%{http_code}' -X PATCH \
          -H "Authorization: Bearer $tok" -H "Accept: application/vnd.github+json" \
          -d "$payload" "https://api.github.com/repos/$REPO/actions/variables/$VAR_NAME")"
  [ "$code" = "204" ] && return 0
  code="$(curl -sS -o /dev/null -w '%{http_code}' -X POST \
          -H "Authorization: Bearer $tok" -H "Accept: application/vnd.github+json" \
          -d "$payload" "https://api.github.com/repos/$REPO/actions/variables")"
  [ "$code" = "201" ] && return 0
  echo "  API 返回 $code" >&2; return 1
}

var_del() {
  if command -v gh >/dev/null && gh auth status >/dev/null 2>&1; then
    gh api --method DELETE "repos/$REPO/actions/variables/$VAR_NAME" >/dev/null 2>&1
    var_get >/dev/null; [ $? = 1 ] && return 0   # 回读确认真的没了（404）才算成功
    return 1
  fi
  local tok; tok="$(gh_token)"
  [ -n "$tok" ] || return 2
  local code
  code="$(curl -sS -o /dev/null -w '%{http_code}' -X DELETE \
          -H "Authorization: Bearer $tok" -H "Accept: application/vnd.github+json" \
          "https://api.github.com/repos/$REPO/actions/variables/$VAR_NAME")"
  case "$code" in 204|404) return 0 ;; *) echo "  API 返回 $code" >&2; return 1 ;; esac
}

no_creds_hint() {
  cat >&2 <<EOF
  无法改 GitHub 变量：既没有可用的 gh CLI，也没有 $TOKEN_FILE。
  二选一：
    gh auth login
    echo '<细粒度 PAT，本仓库 Variables=Read and write>' > $TOKEN_FILE && chmod 600 $TOKEN_FILE
  或手动改：https://github.com/$REPO/settings/variables/actions
EOF
}

# ---------- 本机服务 ----------

svc() {   # svc start|stop|status
  [ -f "$RUNNER_DIR/svc.sh" ] || { echo "未安装"; return 3; }
  ( cd "$RUNNER_DIR" && if $IS_MAC; then ./svc.sh "$1"; else sudo ./svc.sh "$1"; fi ) 2>&1
}

svc_running() {
  local out; out="$(svc status)" || true
  echo "$out" | grep -Eqi 'running|active \(running\)|started'
}

# ---------- 命令 ----------

do_on() {
  log "打开自建 runner"
  if [ -f "$RUNNER_DIR/svc.sh" ]; then
    svc_running && log "  服务：已在运行" || { svc start >/dev/null; sleep 3
      svc_running && log "  服务：已启动" || log "  ⚠️ 服务启动失败，请手动检查 $RUNNER_DIR"; }
  else
    log "  ⚠️ $RUNNER_DIR 下没有 runner，先跑 scripts/setup_local_runner.sh"
  fi
  # 服务先起、变量后设：避免活已经派过来却没人接。
  var_set; local rc=$?
  if [ $rc = 0 ]; then
    log "  变量：$VAR_NAME=$VAR_VALUE（抓取类工作流已切到本机）"
    echo on > "$STATE_DIR/switch"
  else
    [ $rc = 2 ] && no_creds_hint || log "  ⚠️ 变量设置失败"
    return 1
  fi
  log "已打开。探测器会在发布窗内每 10 分钟探一次；抓到后记得 off，或用 auto 自动关。"
}

do_off() {
  log "关闭自建 runner"
  # 变量先删：新派的活立刻回到 ubuntu-latest，不会堆在本机队列里等。
  var_del; local rc=$?
  if [ $rc = 0 ]; then
    log "  变量：已删除（工作流回退 ubuntu-latest）"
    echo off > "$STATE_DIR/switch"
  else
    [ $rc = 2 ] && no_creds_hint || log "  ⚠️ 变量删除失败——先别停服务，否则任务会排队"
    return 1
  fi
  if [ -f "$RUNNER_DIR/svc.sh" ]; then
    svc stop >/dev/null && log "  服务：已停止" || log "  ⚠️ 服务停止失败"
  fi
  log "已关闭。托管 runner 仍会按点探测(多半 403)，页面会如实显示「探测受阻」而非「未发布」。"
}

do_status() {
  echo "仓库：$REPO"
  if [ -f "$RUNNER_DIR/svc.sh" ]; then
    svc_running && echo "本机服务：运行中" || echo "本机服务：已停止"
  else
    echo "本机服务：未安装（scripts/setup_local_runner.sh）"
  fi
  local v rc
  v="$(var_get)"; rc=$?
  case $rc in
    0) echo "GitHub 变量：$VAR_NAME=$v  → 抓取走自建 runner【开】" ;;
    1) echo "GitHub 变量：未设置          → 抓取走 ubuntu-latest【关】" ;;
    *) echo "GitHub 变量：查询不了（无凭据/网络），本机记录=$(cat "$STATE_DIR/switch" 2>/dev/null || echo 未知)" ;;
  esac
  echo
  echo "--- 当前该不该开 ---"
  python3 "$REPO_ROOT/scripts/runner_window.py" --verbose 2>&1 | sed 's/^/  /'
  echo
  if crontab -l 2>/dev/null | grep -qF "$MARKER"; then
    echo "自动开关：已装（每小时一次），日志 $STATE_DIR/auto.log"
  else
    echo "自动开关：未装（bash scripts/runner_ctl.sh --install-auto）"
  fi
}

do_auto() {
  local out decision reason want cur rc
  out="$(python3 "$REPO_ROOT/scripts/runner_window.py" 2>/dev/null)"
  decision="$(printf '%s' "$out" | sed -n 1p)"
  reason="$(printf '%s' "$out" | sed -n 2p)"
  [ "$decision" = on ] || [ "$decision" = off ] || { log "auto：判定脚本无输出，跳过本次"; return 1; }
  want="$decision"
  var_get >/dev/null; rc=$?
  case $rc in
    0) cur=on ;;
    1) cur=off ;;
    *) cur="$(cat "$STATE_DIR/switch" 2>/dev/null || echo unknown)" ;;
  esac
  if [ "$cur" = "$want" ]; then
    log "auto：维持【$cur】——$reason"
    return 0
  fi
  log "auto：$cur → $want ——$reason"
  if [ "$want" = on ]; then do_on; else do_off; fi
}

install_auto() {
  local line="5 * * * * bash $REPO_ROOT/scripts/runner_ctl.sh auto >> $STATE_DIR/auto.log 2>&1 $MARKER"
  crontab -l 2>/dev/null | grep -qF "$MARKER" && { log "已装过，先 --remove-auto 再重装"; exit 0; }
  { crontab -l 2>/dev/null; echo "$line"; } | crontab -
  log "已装入 crontab：每小时 :05 判定一次，日志 $STATE_DIR/auto.log"
  log "注意 cron 里没有登录 shell 的环境变量——改变量的凭据请用 $TOKEN_FILE（gh CLI 的登录态也可用）"
  exit 0
}

remove_auto() {
  crontab -l 2>/dev/null | grep -vF "$MARKER" | crontab -
  log "已移除自动开关"
  exit 0
}

# 只打印 on/off/unknown，供看门狗等脚本判断，不做网络窗口判定。
do_state() {
  local rc
  var_get >/dev/null; rc=$?
  case $rc in
    0) echo on ;;
    1) echo off ;;
    *) cat "$STATE_DIR/switch" 2>/dev/null || echo unknown ;;
  esac
}

case "${1:-status}" in
  on)            do_on ;;
  state)         do_state ;;
  off)           do_off ;;
  status)        do_status ;;
  auto)          do_auto ;;
  --install-auto) install_auto ;;
  --remove-auto)  remove_auto ;;
  *) die "未知命令 ${1}（可用：on / off / status / state / auto / --install-auto / --remove-auto）" ;;
esac

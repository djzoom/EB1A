#!/usr/bin/env bash
# USCIS 递交用表值守：每小时从住宅 IP 问一次 USCIS，直到拿到本期用表(A/B)为止。
#
# 为什么单独做一个，而不是塞进自建 runner：
#   实测两条通道的可达性不一样——
#     DOS 公告   托管 runner 200(走 adoption.state.gov 镜像) ／ 住宅 IP 200
#     USCIS 用表 托管 runner 403                              ／ 住宅 IP 200
#   公告归托管 runner 抓，不需要你的机器。真正只有住宅 IP 能做的，就剩「问一次 USCIS」
#   这一个 HTTP 请求。为它注册一个 GitHub runner、常驻服务、承担离线排队风险，
#   杀鸡用牛刀。一个 cron 就够。
#
# 值守语义：USCIS 可能拖很久(实测 2026-09 期公告发布 8 天后仍挂着 "Coming soon")，
# 所以这不是「跑一次就完」。拿不到就继续每小时问，拿到了 resolve_filing_chart 会
# 自己短路(不再发请求)，成本趋近于零。下一期公告上线把 FILING_CHART 重置回 '?'，
# 值守自动重新开始。
#
# 用法：
#   bash scripts/uscis_chart_watch.sh            # 跑一次
#   bash scripts/uscis_chart_watch.sh --install  # 装进 crontab（每小时）
#   bash scripts/uscis_chart_watch.sh --remove   # 卸载
#
# Bark：BARK_KEY 环境变量，或 ~/.eb1a_bark_key（一行 key）。未配置则只记录不推送。
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="${STATE_DIR:-$HOME/.eb1a-watchdog}"
MARKER="# eb1a-uscis-chart-watch"
BRANCH="${EB1A_BRANCH:-main}"

mkdir -p "$STATE_DIR"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

case "${1:-}" in
  --install)
    line="17 * * * * bash $REPO_ROOT/scripts/uscis_chart_watch.sh >> $STATE_DIR/chart.log 2>&1 $MARKER"
    if crontab -l 2>/dev/null | grep -qF "$MARKER"; then
      log "已装过，先 --remove 再重装"; exit 0
    fi
    { crontab -l 2>/dev/null; echo "$line"; } | crontab -
    log "已装入 crontab：每小时 :17 值守一次，日志 $STATE_DIR/chart.log"
    log "Bark：echo '<BARK_KEY>' > ~/.eb1a_bark_key && chmod 600 ~/.eb1a_bark_key"
    exit 0 ;;
  --remove)
    crontab -l 2>/dev/null | grep -vF "$MARKER" | crontab -
    log "已移除值守"; exit 0 ;;
  "") ;;
  *) echo "未知参数 $1（可用：--install / --remove）" >&2; exit 2 ;;
esac

cd "$REPO_ROOT" || { log "进不去仓库目录"; exit 1; }

cur_branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
if [ "$cur_branch" != "$BRANCH" ]; then
  # 不擅自切分支——你可能正在这个 clone 上做别的事。只读跑一遍报告结果，不提交。
  log "当前在 $cur_branch 而非 $BRANCH，只做只读检查、不提交"
  READONLY=1
else
  READONLY=0
  git pull -q --ff-only origin "$BRANCH" 2>/dev/null \
    || log "拉取 $BRANCH 失败（网络？本地有改动？）——继续用本地状态跑"
fi

before="$(grep -m1 "var FILING_CHART = " index.html || true)"
python3 scripts/sniff_visa_bulletin.py --filing-chart
after="$(grep -m1 "var FILING_CHART = " index.html || true)"

if git diff --quiet -- index.html; then
  log "index.html 无变化"
  exit 0
fi

if [ "$READONLY" = 1 ]; then
  log "有变化但当前不在 $BRANCH，已回滚改动、不提交"
  git checkout -- index.html
  exit 0
fi

git add index.html
git -c user.name="uscis-chart-watch" \
    -c user.email="$(git config user.email || echo noreply@localhost)" \
    commit -q -m "Auto: USCIS 递交用表状态更新（本机值守）"
if git push -q origin "$BRANCH"; then
  log "已提交并推送：$after"
else
  log "⚠️ 推送失败，改动留在本地 commit 里"
  exit 1
fi

# 只有真正判定出 A/B 才推送通知——状态在 pending/error 之间来回不值得打扰。
chart="$(printf '%s' "$after" | sed -n "s/.*var FILING_CHART = '\([^']*\)'.*/\1/p")"
if [ "$chart" = A ] || [ "$chart" = B ]; then
  key="${BARK_KEY:-}"
  [ -z "$key" ] && [ -f "$HOME/.eb1a_bark_key" ] && key="$(tr -d '[:space:]' < "$HOME/.eb1a_bark_key")"
  label=$([ "$chart" = A ] && echo "表A(Final Action)" || echo "表B(Dates for Filing)")
  if [ -n "$key" ]; then
    BARK_KEY="$key" BARK_TITLE="EB1A · 本月递交用表已确认" \
    BARK_BODY="USCIS 确认本月职业类递交用 $label。已自动上线。" \
      python3 scripts/sniff_visa_bulletin.py --send-bark >/dev/null 2>&1 \
      && log "已推送 Bark（用表 $chart）" || log "Bark 推送失败"
  else
    log "用表判定为 $chart（未配置 BARK_KEY，跳过推送）"
  fi
fi

# 自建 Runner 配置指南

> ## 先读这段：多数情况下你不需要自建 runner
>
> 实测（2026-08-22，托管 runner 与住宅 IP 各跑一遍）：
>
> | 数据源 | GitHub 托管 runner | 住宅 IP |
> |---|---|---|
> | **DOS 公告**（表A/表B cutoff） | ✅ 200 —— 走 `adoption.state.gov` 镜像 | ✅ 200 |
> | **USCIS AOS 递交用表** | ❌ **403** | ✅ 200 |
>
> WAF 规则是挂在 hostname 上的，不是按出口 IP 段封的：`travel.state.gov` 挡所有人，
> 但同一套内容树的两个镜像主机谁都不挡。**排期数字托管 runner 就能抓到，不需要你的机器。**
>
> 真正只有住宅 IP 能做的，只剩「每小时问一次 USCIS 用表」这一个 HTTP 请求——
> 那件事用 `scripts/uscis_chart_watch.sh` 一个 cron 就够，不必注册 runner。
>
> **所以自建 runner 现在只有一个用途**：托管探测万一失效（过了 20 号仍没抓到公告）时的
> 人工接管保险。装不装取决于你要不要这层冗余。下面的步骤依然有效。

## TL;DR（20 分钟上线）

```bash
git clone https://github.com/djzoom/EB1A.git && cd EB1A

# ① 预检：这条出口能不能直连 DOS/USCIS（云 VPS/公司网络多半不行，必须住宅宽带）
python3 scripts/preflight_local_egress.py

# ② 取注册令牌：https://github.com/djzoom/EB1A/settings/actions/runners/new
# ③ 一键装（下载+注册 eb1a-fetch 标签+装开机自启服务+关休眠）
bash scripts/setup_local_runner.sh <令牌>

# ④ 看门狗：掉线自动重启 + Bark 报警（防静默排队漏抓）
echo '<你的 BARK_KEY>' > ~/.eb1a_bark_key && chmod 600 ~/.eb1a_bark_key
bash scripts/runner_watchdog.sh --install
```

⑤ 配一次改变量的凭据，然后开关随手用：

```bash
gh auth login            # 或：echo '<PAT>' > ~/.eb1a_gh_token && chmod 600 ~/.eb1a_gh_token

bash scripts/runner_ctl.sh on       # 排期快到了，打开
bash scripts/runner_ctl.sh off      # 抓到了，关掉
bash scripts/runner_ctl.sh status   # 看现在什么状态

bash scripts/runner_ctl.sh --install-auto   # 想省心：自动开、自动关
```

⑥ 验证：先 `on`，再 Actions → Sniff Visa Bulletin → Run workflow 勾 `selftest`，看日志里 403 是否变 200。

下面是每一步的原理与排障细节。

## 为什么要自建

USCIS 与 DOS 的 Akamai 把 GitHub 托管 runner 的出口 IP（Azure 机房段）整体挡掉了，
四个数据源探测全部返回 403：

```
[诊断] I-485库存 → HTTP 403
[诊断] I-140收件 → HTTP 403
[诊断] I-140待签 → HTTP 403
[诊断] DOS签发   → HTTP 403
```

自建 runner 让抓取走**你自己的住宅 IP**，绕开这层封锁。

代价是真实的：**2026-08 与 2026-09 两期公告都是 403 漏抓后人工录入的**
（见 `data/release_log.json` 里的 `via: manual`）。托管 runner 下探测器只剩
Wayback 快照这一条间接通道，快照要等社区先去存档，延迟不可控；而页面在探不到时
只会显示「尚未发布」——静默失败，没人知道是通道断了。

> **重要**：云 VPS（DigitalOcean / AWS / 阿里云等）同样是机房 IP，大概率照样被 403。
> 只有住宅宽带出口才可靠。选机器时务必用家里的设备。

---

## 一、安全前提（公开仓库必读）

本仓库是 **public**，自建 runner 跑在你家里的机器上，因此：

| 风险 | 现状 | 要求 |
|---|---|---|
| fork 的 PR 在你机器上跑任意代码 | ✅ 当前无 workflow 用 `pull_request` 触发 | **永远不要**给走自建 runner 的 workflow 加 `pull_request` / `pull_request_target` 触发 |
| 第三方 PR 自动执行 | 需手动确认 | Settings → Actions → General → Fork pull request workflows 设为 **Require approval for all external contributors** |
| runner 可访问家庭内网 | 取决于部署方式 | 优先跑在容器 / 虚拟机里，别直接裸跑在主力机上 |
| 任务间状态残留 | 默认持久 | 本仓库无 fork 代码执行风险，用常驻 runner 即可（见下方说明） |

> **关于 `--ephemeral`**：GitHub 推荐公开仓库用一次性 runner。但本项目的
> `sniff-visa-bulletin` 在发布窗内每 10 分钟触发一次，ephemeral 模式下每个任务
> 都要注销重连，一天数十次，反而增加失败面。鉴于本仓库无 `pull_request` 触发、
> 不存在第三方代码执行风险，**建议用常驻 runner**（不加 `--ephemeral`）。

---

## 二、注册 Runner

> 推荐直接跑 `bash scripts/setup_local_runner.sh <令牌>`——下面这些步骤它都做了
> （平台/架构自动识别、带 `--labels eb1a-fetch` 注册、`svc.sh` 装服务、关休眠、查 Python 版本）。
> 以下手动步骤留作排障时对照。

### 1. 取注册令牌

GitHub 网页：`Settings → Actions → Runners → New self-hosted runner`
选好操作系统后，页面会给出带令牌的命令（令牌约 1 小时过期）。

### 2. 安装（macOS）

Apple Silicon 用 `osx-arm64`，Intel Mac 用 `osx-x64`。
GitHub 网页会给出当前最新版本号的下载命令，照抄即可；关键是**下一步的配置参数**。

```bash
mkdir -p ~/actions-runner && cd ~/actions-runner
curl -o actions-runner.tar.gz -L \
  https://github.com/actions/runner/releases/latest/download/actions-runner-osx-arm64.tar.gz
tar xzf actions-runner.tar.gz

# ⚠️ 必须带 --labels eb1a-fetch：工作流的 runs-on 认这个标签，
#    网页默认给的命令不含它，装完会接不上活。
./config.sh --url https://github.com/djzoom/EB1A \
            --token <粘贴网页给的令牌> \
            --labels self-hosted,eb1a-fetch
```

### 2'. 安装（Linux x64 / NAS / 树莓派）

```bash
mkdir -p ~/actions-runner && cd ~/actions-runner
# 树莓派等 ARM 设备把 linux-x64 换成 linux-arm64
curl -o actions-runner.tar.gz -L \
  https://github.com/actions/runner/releases/latest/download/actions-runner-linux-x64.tar.gz
tar xzf actions-runner.tar.gz
./config.sh --url https://github.com/djzoom/EB1A \
            --token <令牌> --labels self-hosted,eb1a-fetch
```

### 3. 装成开机自启服务

```bash
# macOS
./svc.sh install && ./svc.sh start && ./svc.sh status

# Linux（systemd）
sudo ./svc.sh install $(whoami) && sudo ./svc.sh start && sudo ./svc.sh status
```

> **别用 `./run.sh`**：那是前台运行，终端一关 runner 就停。必须走 `svc.sh` 装成
> 开机自启服务，机器重启后才会自动接管。

顺手关掉休眠，否则机器睡着时任务会一直排队：

```bash
sudo pmset -a sleep 0 disablesleep 1     # macOS
```

### 4. 依赖

runner 机器需要 Python 3.11+（工作流里的 `setup-python` 在自建机上会尝试下载对应版本，
装了系统 Python 3.11 更稳）：

```bash
python3 --version   # 确认 ≥ 3.11
```

---

## 三、开关：手动开合 / 自动开合

### 3.0 先分清两个东西

| | 是什么 | 状态在哪 |
|---|---|---|
| `RUNNER_LABEL` 变量 | **真正的开关**——决定抓取类工作流的活派给谁 | GitHub 仓库变量 |
| 本机 runner 服务 | 有没有人接活 | 你机器上的 launchd / systemd |

变量没设时，本机服务即使在跑也只是空转、接不到任何活。所以：

- **开**：先起服务、后设变量（避免活派过来却没人接）
- **关**：先删变量、后停服务（避免活堆在本机队列里排队）

`runner_ctl.sh` 就是按这个顺序做的，别手动分开操作。

### 3.1 手动开合（日常用法）

```bash
bash scripts/runner_ctl.sh on       # 打开
bash scripts/runner_ctl.sh off      # 关闭
bash scripts/runner_ctl.sh status   # 服务 / 变量 / 当前该不该开，三行看全
bash scripts/runner_ctl.sh state    # 只打印 on|off|unknown（给脚本用）
```

改 GitHub 变量需要凭据，二选一，只配一次：

```bash
gh auth login                                    # ① 装了 gh CLI 最省事
echo 'github_pat_xxx' > ~/.eb1a_gh_token         # ② 细粒度 PAT
chmod 600 ~/.eb1a_gh_token                       #    权限：本仓库 Variables = Read and write
```

> PAT 只需要 Variables 读写这一项权限，别给多。这个文件别同步到网盘。
> 没有凭据时脚本会提示你手动改：
> `Settings → Secrets and variables → Actions → Variables`。

节奏大致是：每月 7 号前后打开 → 公告出来、数据自动上线并推送到手机 → 确认后关掉。
一个月开着一到两周，其余时间机器上什么都不跑。

### 3.2 USCIS 用表值守（与 runner 无关，建议装）

用表是唯一必须走住宅 IP 的东西，但它只需要一个 HTTP 请求，不值得为它开整台 runner：

```bash
bash scripts/uscis_chart_watch.sh            # 跑一次
bash scripts/uscis_chart_watch.sh --install  # 装进 crontab（每小时 :17）
bash scripts/uscis_chart_watch.sh --remove   # 卸载
```

**值守语义，不是跑一次就完。** USCIS 可能拖很久——实测 2026-09 期公告 8/14 发布，
到 8/22 官网仍挂着「Coming soon」。所以拿不到就继续每小时问；一旦判定出 A/B，
`resolve_filing_chart()` 会自己短路（不再发请求），成本趋近于零；下一期公告上线
把 `FILING_CHART` 重置回 `'?'`，值守自动重新开始。

判定出结果时推一条 Bark，并自动 commit + push 上线。

> `data-update.yml` 里的用表步骤已加 `if: runner.environment == 'self-hosted'` —— 
> 在托管 runner 上跑那一步只会写下「获取失败」，掩盖「USCIS 尚未公布」这个真相。

### 3.3 自动开合（装上就不用管）

```bash
bash scripts/runner_ctl.sh --install-auto   # 每小时 :05 判定一次
bash scripts/runner_ctl.sh --remove-auto    # 卸载
```

判定逻辑在 `scripts/runner_window.py`，与探测器 `run()` 的目标口径一致
（当月 + 下月中所有尚未定案的期），可以单独跑来看它怎么想的：

```bash
python3 scripts/runner_window.py --verbose
```

三条规则，按顺序：

1. **当月期还没定案** → 开。说明上一轮发布被错过了，探测器会绕过发布窗门控直接补探。
2. **下月期未定案 且 已过 20 号** → 开。历史 12 期发布日全部落在 12–20 号；
   过了这天还没抓到，就不是「官方还没发」而是托管探测出了问题，此时本机接管。
   **常规发布窗内本机保持关闭**——公告归托管 runner 抓，为它开两周是白开。
3. **其余** → 关。用表不在这里判，由 `uscis_chart_watch.sh` 值守。

判定读的是 GitHub 上 `main` 的实时状态（`release_log.json` + `index.html`），
不是你本地 clone，所以本地仓库旧了也不影响。读不到时**按开处理**——
宁可多开一会儿，也别漏掉当期公告。

> **自动模式的已知缺口**：27 号–6 号这段窗外时间是关着的，交给托管 runner
> 的稀疏哨兵（它会 403）。历史 12 期发布日全部落在 12–20 号，所以风险很小；
> 真出现极端早发，规则 1 会在下个月 1 号把它捞回来（当月期未定案 → 开 → 补探）。

手动和自动可以混用：手动 `on` 之后，下一次 auto 判定若认为该关，会把它关掉。
想让它别插手，先 `--remove-auto`。

### 3.4 哪些工作流读这个变量

只有需要外网抓取的两个工作流读 `RUNNER_LABEL`（`runs-on: ${{ vars.RUNNER_LABEL || 'ubuntu-latest' }}`）：

| 工作流 | 是否走自建 | 原因 |
|---|---|---|
| `data-update.yml` | ✅ | 抓 USCIS 数据，需绕 403 |
| `sniff-visa-bulletin.yml` | ✅ | 抓 DOS 签证公告，需绕 403 |
| `deploy-pages.yml` | ❌ 固定托管 | Pages 部署依赖 GitHub 环境，且不抓外网 |
| `package-offline.yml` | ❌ 固定托管 | 只打包，不抓外网 |

删掉变量 = 立刻回退 `ubuntu-latest`，这是任何时候都能用的逃生口
（`runner_ctl.sh off` 做的就是这件事，外加停掉本机服务）。

---

## 四、验证

### 4.0 装之前先预检（不占用令牌、不改任何配置）

```bash
python3 scripts/preflight_local_egress.py
```

它用探测器同一套 URL 和 UA，从**本机**打一遍 DOS 月份页 / DOS PDF / USCIS AOS 页 /
两个镜像主机，基准期取上一期（官方一定已发布，所以 200 才是干净证据）：

- `结论：可用` → 这台机器值得装 runner
- `结论：不可用` → 出口被 WAF 挡（云 VPS / 公司网络 / 机房 VPN 都会这样），换住宅宽带
- `结论：未定` → 超时或本机代理干扰，先 `unset HTTPS_PROXY` 再跑一次

### 4.1 切换后在 GitHub 上验证

手动触发一次，看诊断行的状态码：

```
Actions → Check Data Updates → Run workflow
```

成功的标志——403 变成 200 或 404：

```
[诊断] I-485库存 首个缺失项探测 eb_inventory_june_2025.xlsx → HTTP 404
```

- `404` = 通道通了，只是官方确实没发这一期（正常）
- `200` = 通道通了且文件存在，会自动下载并开 PR
- 仍是 `403` = 住宅 IP 也被挡，或 runner 没接管（检查 Actions 页面 job 是否跑在自建 runner 上）

---

## 五、运维注意

**开关关着时，看门狗会自动跳过巡检**——故意关掉的 runner 不是故障，不该报警。

**机器离线时任务会排队。** 自建 runner 掉线后，指向它的 job 会一直等，
GitHub 最多等 24 小时才取消。签证公告探测在发布窗内每 10 分钟一次，
若 runner 长期离线会堆积大量排队任务。

应对：
- 机器设为不休眠（macOS：`sudo pmset -a sleep 0 disablesleep 1`；`setup_local_runner.sh` 已自动做）
- **装看门狗**（下节）——把"静默排队"变成手机上的一条推送
- 长期出门 / 机器要关机前，**删掉 `RUNNER_LABEL` 变量**回退到托管 runner
- 定期看 Actions 页面有无长时间 queued 的任务

### 看门狗

```bash
bash scripts/runner_watchdog.sh --install   # 每 30 分钟一次，写 crontab
bash scripts/runner_watchdog.sh             # 手动跑一次看输出
bash scripts/runner_watchdog.sh --remove    # 卸载
```

每次巡检做两件事：

1. **服务在不在** —— 停了先自动 `svc.sh start`；拉不起来才报警（Bark：
   「runner 掉线，任务正在排队，请上机或先删 RUNNER_LABEL 回退」）。
2. **出口还通不通** —— 跑一遍预检。住宅 IP 也可能被新的 WAF 规则命中，
   这时 runner 明明在跑却什么都抓不到，是最难发现的一种坏法。

Bark key 从 `~/.eb1a_bark_key` 读（cron 没有登录 shell 的环境变量）。
同类告警 6 小时内只推一条，不会刷屏。日志在 `~/.eb1a-watchdog/watchdog.log`。

**令牌与凭据**：`~/actions-runner/.credentials` 存有仓库凭据，
别把这个目录同步到网盘或备份到公开位置。

**注销 runner**：

```bash
cd ~/actions-runner
./svc.sh stop && ./svc.sh uninstall
./config.sh remove --token <网页重新生成的 remove token>
```

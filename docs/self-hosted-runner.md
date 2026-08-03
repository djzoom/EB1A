# 自建 Runner 配置指南

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

## 三、切到自建 runner

工作流的 `runs-on` 读仓库变量 `RUNNER_LABEL`，**没设时默认用 GitHub 托管**，
所以随时可一键切换、一键回退：

```
Settings → Secrets and variables → Actions → Variables → New repository variable
  Name:  RUNNER_LABEL
  Value: eb1a-fetch
```

- **设为 `eb1a-fetch`** → 抓取类工作流走你的自建 runner
- **删掉该变量** → 立刻回退到 `ubuntu-latest`（出问题时的逃生口）

只有需要外网抓取的两个工作流读这个变量：

| 工作流 | 是否走自建 | 原因 |
|---|---|---|
| `data-update.yml` | ✅ | 抓 USCIS 数据，需绕 403 |
| `sniff-visa-bulletin.yml` | ✅ | 抓 DOS 签证公告，需绕 403 |
| `deploy-pages.yml` | ❌ 固定托管 | Pages 部署依赖 GitHub 环境，且不抓外网 |
| `package-offline.yml` | ❌ 固定托管 | 只打包，不抓外网 |

---

## 四、验证

切换后手动触发一次，看诊断行的状态码：

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

**机器离线时任务会排队。** 自建 runner 掉线后，指向它的 job 会一直等，
GitHub 最多等 24 小时才取消。签证公告探测在发布窗内每 10 分钟一次，
若 runner 长期离线会堆积大量排队任务。

应对：
- 机器设为不休眠（macOS：`sudo pmset -a sleep 0 disablesleep 1`）
- 长期出门 / 机器要关机前，**删掉 `RUNNER_LABEL` 变量**回退到托管 runner
- 定期看 Actions 页面有无长时间 queued 的任务

**令牌与凭据**：`~/actions-runner/.credentials` 存有仓库凭据，
别把这个目录同步到网盘或备份到公开位置。

**注销 runner**：

```bash
cd ~/actions-runner
./svc.sh stop && ./svc.sh uninstall
./config.sh remove --token <网页重新生成的 remove token>
```

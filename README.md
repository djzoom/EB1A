# EB1A Priority Date Predictor

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

EB-1 ~ EB-5 排期预测工具（EB-1A / EB-2 / EB-3 / EB-4 / EB-5 及三类 EB-5 预留；中国大陆、印度、其他国家 ROW、墨西哥、菲律宾）。EB-1A 中国大陆为最初的、参数经手工标定并回测的主场景。基于公开政府数据（USCIS / DOS），用供给 + 队列密度的第一性原理方法估算 Priority Date 何时到期。

## 在线 Demo

主站：https://gc.bracketboss2026.com/

备用站：https://s546126.github.io/gctime/

也可直接打开 `index.html`。离线包：https://github.com/s546126/gctime/releases/download/offline-latest/EB1A-offline.zip

## 语言、图表与分享

界面支持中文、印地语、西班牙语、巴西葡萄牙语、日语、韩语、阿拉伯语、德语、法语和意大利语。首次进入和页首均可选语言，默认中文，选择仅保存在本地。词典随应用打包，覆盖图表提示、参数来源、错误和免责声明，无翻译 API；离线单文件也可切换语言。阿拉伯语使用 RTL 布局，但日期输入保持年／月／日，时间轴仍从左到右。

切换语言只更新显示，不改变档案、参数、情景或已计算的预测。翻译由机器辅助编写，尚未经各语言母语者审校。

趋势图固定绿色为表 A、琥珀色为表 B；实线为历史，虚线为当前选中表的预测，同一张表始终同色。历史光标同时展示同月 A/B 值，缺失月份明确提示，不借用邻月数据；预测提示会注明当前表及乐观／中位／保守区间。

“分享链接”包含类别、出生国、优先日、表 A/B、速度、情景、供给、参数和界面语言，放在 URL `#` 片段内，不随 HTTP 请求发送。链接接收者先进入共享预览，不覆盖其已保存条件；点击“更新预测”才保存。“修改条件”打开或聚焦条件表单；“重新加载”重载当前发布版本，不主动抓取官方公告，保留档案但重置未保存的高级参数。

## 方法

工具不直接外推 cutoff 时间序列，而是还原签证分配的底层过程：

1. **库存（demand）**：按 country × subcategory × PD-bucket × stage 拆分排队人群，而非用单一总量。
2. **供给（supply）**：每财年法定配额 + 单国 7% 上限 + 其他国家用不完的溢出。
3. **密度**：估算目标 PD 之前还有多少人，决定需要消耗多少签证号才能轮到。
4. **不确定性**：用蒙特卡洛模拟给出 P10 / P50 / P90 区间，而非单点预测。

## 多类别 / 多国家

首次打开时可选类别与出生国（随时可在编辑面板修改，保存在 localStorage `eb1a_user_profile`）。每个 类别×国家 有独立的表A/表B 当期值、历史序列与模型参数：

- 数据：`data/visa_bulletin_history.json`（2016-10 → 2026-10，脚本 `scripts/build_bulletin_history.py`）
- 参数：`scripts/calibrate_categories.py` 由「表A 近 24 月推进速度 + I-140 已批准待签（cutoff 之后排队总量）+ I-485 库存」标定，写入 `index.html` 的 `CELL_MODELS`
- 表A 为 Current 的格子（如 EB-1 ROW、EB-5 ROW、EB-5 三个预留类）直接显示「已 current，无需等待」
- EW（其他工人）与 EB-4 宗教工作者行暂未收录；EB-2..5 及非中国格子的参数含较多假设（溢入、家庭系数），置信度低于 EB-1A 中国

## 已知局限与改进方向

- DOS NVC 领事队列不在公开数据中，需用律所估算补全。
- stage transition rates（I-140 → I-485 → 发放）是黑盒，只能从库存变化反推。
- Cross-chargeability（跨国家归属）在官方数据中不可见。
- 回测应使用 rolling holdout（用历史快照前推、对比真实），而非 in-sample 拟合。

改进方向是重写为 agent-based / discrete-event 模拟，真正还原 DOS 月度签证分配过程。详见 [`CLAUDE_CODE_BOOTSTRAP.md`](./CLAUDE_CODE_BOOTSTRAP.md) 和 [`DATA_SOURCES.md`](./DATA_SOURCES.md)。

## 项目结构

```
EB1A/
├── index.html               # 预测工具主页面
├── README.md
├── CLAUDE_CODE_BOOTSTRAP.md  # 架构 / 开发接手指南
├── DATA_SOURCES.md           # 完整数据源清单 (17 个)
├── LICENSE                   # MIT
├── data/                     # 公开政府数据 (USCIS / DOS / 社区)
├── docs/                     # 运维文档 (自建 runner 部署等)
└── scripts/                  # 数据抓取 / 校准 / 验证脚本
```

## 数据自动更新

排期数据由 GitHub Actions 定时探测 DOS 签证公告并自动上线。两条数据通道的可达性不同
（2026-08-22 实测，托管 runner 与住宅 IP 各跑一遍）：

| 数据源 | GitHub 托管 runner | 住宅 IP |
|---|---|---|
| **DOS 公告**（表A/表B cutoff） | ✅ 200 —— 走 `adoption.state.gov` 镜像 | ✅ 200 |
| **USCIS AOS 递交用表**（用A还是用B） | ❌ 403 | ✅ 200 |

WAF 规则挂在 hostname 上，不是按出口 IP 段封：`travel.state.gov` 挡所有自动化访问，
但同一套内容树的镜像主机（`adoption.state.gov` / `childabduction.state.gov`）谁都不挡。
所以**排期数字全自动，不需要自己的机器**；只有 USCIS 用表必须从住宅 IP 取。

用表值守（一个 cron，不需要注册 runner）：

```bash
bash scripts/uscis_chart_watch.sh --install   # 每小时问一次 USCIS，直到拿到 A/B
```

自建 runner 只在托管探测失效（过了 20 号仍没抓到公告）时作为人工接管的保险，
部署与开关见 [`docs/self-hosted-runner.md`](./docs/self-hosted-runner.md)。

## 关键数据源

完整 17 个来源见 [`DATA_SOURCES.md`](./DATA_SOURCES.md)。

**核心数据 (USCIS 自己发布的 cohort 数据)**:
- I-485 Pending Inventory XLSX (月度, by PD month × country × category)
- I-140 Approved Awaiting Visa XLSX (季度)
- DOS Monthly Immigrant Visa Issuance
- DOS Annual Report of Visa Office

**社区资源**:
- VisaGrader (历史 cutoff): https://visagrader.com
- Papers (thepapers.co): 队列等待估计
- GreenCardClock: 中国 EB 完整分析
- Lucid Professional Writing: EB-5 月度精确解读
- ImmigrationRoad: CP/AOS 比例

**同类开源项目**:
- vyakunin/visa_bulletin: Django + Bazel (https://visa-bulletin.us/)
- visabulletin.ai: timeline + cohort comparison

## CI 与部署

界面使用 React 19、HeroUI Pro 和 Tailwind CSS 4；预测模型与公告数据仍保留在 `index.html`，数据机器人继续按原有格式更新。

自有源码沿用项目 MIT 协议；HeroUI Pro 是独立商业依赖，不受本仓库 MIT 协议覆盖。仓库不包含授权包源文件，只有合法授权的构建环境才能下载该依赖；发布的是应用编译产物。

`CI` 在 push、PR 和手动运行时检查工作流语法、Python/Shell/JavaScript/JSX、JSON 和公告解析器。仓库分支 push 与 main 手动运行还会下载授权组件、构建站点并执行 Chromium 回归测试。PR 只执行不需要凭据的源码检查，不运行 HeroUI 授权安装；维护者应在受信分支验证 UI 后合并。浏览器覆盖 40 个类别×国家组合的两种远期速度、表A/B 并列预测、设置持久化、停留上限与财年锚点，以及离线产物。测试不依赖实时政府网站。

只有 `main` 验证通过后才发布 GitHub Pages、Cloudflare Pages 和离线 Release；三个发布任务消费同一次构建产物。`version.json` 记录构建 commit，便于核对线上版本。数据机器人写入 `main` 后会显式派发 `CI`，因为 `GITHUB_TOKEN` 产生的 push 不会触发其他工作流。

一次性配置：

1. GitHub Settings → Pages → Source 选择 **GitHub Actions**。初次启用需要仓库管理员，工作流 token 无权创建 Pages 站点。
2. Cloudflare 创建 Pages 项目 `gctime`，生产分支 `main`。仓库 Secrets 配置 `CLOUDFLARE_API_TOKEN`（目标账户的 Cloudflare Pages:Edit）与 `CLOUDFLARE_ACCOUNT_ID`，然后设置仓库变量 `CLOUDFLARE_ENABLED=true`。启用后缺少凭据会明确失败；未启用时该发布 job 显示 skipped。
3. Cloudflare Pages → gctime → Custom domains 绑定 `gc.bracketboss2026.com`。
4. 重新发布可运行 `gh workflow run ci.yml --repo s546126/gctime --ref main`；子工作流不能绕过 CI 独立发布。
5. 从 HeroUI Pro Dashboard 获取 CI/CD token，设置仓库 Secret `HEROUI_AUTH_TOKEN`。该令牌仅传给 `npm rebuild @heroui-pro/react` 的授权下载步骤；其它依赖安装使用 `npm ci --ignore-scripts`。不要把令牌放入源码、前端环境变量或生成产物。

本地验证：

```bash
npm ci --ignore-scripts
# 已完成 heroui-pro login，或已通过环境提供 HEROUI_AUTH_TOKEN 后：
npm rebuild @heroui-pro/react
npm run build
npx playwright install chromium
python3 scripts/check_project.py
python3 scripts/test_sniff.py
npm test
go run github.com/rhysd/actionlint/cmd/actionlint@v1.7.12
```

`npm run build:ui` 把 `src/shell.jsx` 和 `src/styles.css` 编译为忽略提交的 `assets/ui.js`、`assets/ui.css`，不拆分 chunk、不生成 source map。`npm run build` 继续生成 `dist/site/`、`dist/EB1A.html` 和 `dist/EB1A-offline.zip`；直接运行 `python3 scripts/build_site.py` 也会先编译 UI。

`npm test` 自动完整构建，在真实子路径运行浏览器测试；CI 用 `GCTIME_PREBUILT=1` 复用刚验证的产物。离线 HTML 内联 React/HeroUI 的 JS 和 CSS，不需要 CDN 或本地服务器。站点 service worker 预缓存这些资源，并以构建内容指纹更新缓存。当前页面未自动注册 service worker；相关测试主动注册以验证分发的 worker，单 HTML 离线版无需注册。

没有 HeroUI Pro 授权的贡献者可运行 `npm ci --ignore-scripts`、`python3 scripts/check_project.py --source-only` 和 `python3 scripts/test_sniff.py` 完成源码检查；该结果不代表 UI 已通过构建或浏览器测试。

可选：`BARK_KEY` 用于通知；`RUNNER_LABEL` 用于住宅出口自建 runner。没有住宅出口时 USCIS 抓取可能返回 403，定时任务成功不等于数据已刷新。

## 开发 (Claude Code)

```bash
git clone https://github.com/s546126/gctime.git
cd gctime
claude  # 启动 Claude Code

# 第一条 message:
# "Read DATA_SOURCES.md and CLAUDE_CODE_BOOTSTRAP.md.
#  Start Phase 1: implement Cohort and GlobalState dataclasses
#  in src/cohort.py, and allocate_monthly in src/allocator.py.
#  Use synthetic data first. Write unit tests for INA rules."
```

## 历史数据要点

- EB-1 China FY 推进: FY24 +266 天 / FY25 +44 天 / FY26 (前 8 月) +100 天
- 三年均值: μ=153 天/年, σ=91 天/年
- 71% 月份有推进, 29% 完全不动 (脉冲式)
- USCIS June 2024 EB-1 China I-140 pending: 9,208 主申
- 法定中国 EB-1 基础配额: 2,803 (40,040 × 7%)

## 使用

首次打开 `index.html` 时，会弹出欢迎面板要求输入你自己的 Priority Date、类别、出生国等信息。数据仅保存在浏览器 localStorage，不会上传。

预测结果（P50 中位 + 90% 置信区间）以你输入的 PD 为准计算。

## License

MIT - 见 [LICENSE](./LICENSE)

## 免责声明

**这不是法律建议**。预测基于公开数据的统计估算。实际移民结果受政策变化、行政命令、立法和个人情况影响。请咨询持牌移民律师获取法律建议。

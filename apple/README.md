# EB1A · 原生 iOS App

> 状态：**Milestone 1 已落地**（核心引擎 + 数据 + SwiftUI 首版 UI + 公告通知 + 测试）。
> 目标：把已上线的 EB1A 排期预测做成一个**原生 SwiftUI iOS App**——不是网页套壳，而是用 Swift 重新实现整套预测模型与界面。

---

## 0. 为什么是原生（而非瘦壳）

| | 瘦壳 (WKWebView) | **原生 Swift（本方案）** |
|---|---|---|
| 本质 | 加载线上网页 | SwiftUI 重画 UI + Swift 重写模型 |
| App Store 4.2 风险 | 高（易被判套壳） | 无（天然原生） |
| 体验 | 受网页限制 | 原生手势/图表/通知 |
| 代价 | 几乎零 | 模型与 UI 要维护「网页 JS + Swift」两份 |

代价的应对：**核心算法单独成模块**（`Core/`），与 UI 解耦，对照网页 `index.html` 的 `simulate()` 等函数逐行移植，便于日后同步。

---

## 1. 构建方式（重要）

本仓库容器是 Linux，**无 Xcode**，所以这里只提交源码，构建在你的 Mac 上完成。
工程用 [XcodeGen](https://github.com/yonyz/XcodeGen) 描述（`project.yml`），`.xcodeproj` 在 Mac 上一键生成——避免手写易损坏的工程文件。

```bash
# 在 Mac 上：
brew install xcodegen          # 仅首次
cd apple
xcodegen generate             # 由 project.yml 生成 EB1A.xcodeproj
open EB1A.xcodeproj           # Xcode 打开 → 选模拟器 → ⌘R 运行
```

> 没装 XcodeGen 也行：在 Xcode 里新建一个 iOS App 工程，把 `EB1A/` 下的 `.swift` 全部拖进去即可——逻辑代码不依赖工程生成器。

---

## 2. 工程结构

```
apple/
├── README.md
├── project.yml                       # XcodeGen 工程描述（生成 .xcodeproj）
├── EB1A/
│   ├── EB1AApp.swift                 # @main 入口
│   ├── Core/                         # ★ 纯 Swift，无 UI，对照 index.html 移植
│   │   ├── Theme.swift               # 配色板，1:1 对应网页 CSS :root（样式一致）
│   │   ├── EBDate.swift              # UTC 日历 / 造日期工具
│   │   ├── ModelParams.swift         # 7 个模型参数 + 三套预设(现实/乐观/悲观)
│   │   ├── VisaData.swift            # HISTORY / HISTORY_B / 当前 cutoff / 月权重
│   │   ├── SimulationEngine.swift    # gaussian/getPDDensity/simulate/monteCarlo/percentilePaths/crossings
│   │   ├── Formatters.swift          # 中文日期/等待时间格式化
│   │   └── BulletinWatcher.swift     # 轮询 release_log.json + 本地通知
│   ├── ViewModels/
│   │   └── PredictionViewModel.swift # 后台跑 500 次蒙特卡洛
│   └── Views/
│       ├── ContentView.swift         # 根视图 + 欢迎/主界面切换
│       ├── WelcomeView.swift         # 首次输入优先日
│       ├── HeroCardView.swift        # 预计排到 + 快/中/慢
│       ├── ForecastChartView.swift   # Swift Charts 走势图(历史+p10/p50/p90)
│       └── SettingsView.swift        # 预设切换 + 通知开关
└── Tests/
    └── EngineTests.swift             # 引擎确定性单测(密度/路径长度/百分位单调)
```

---

## 3. 核心引擎移植对照

`SimulationEngine.swift` 严格对应 `index.html` 第 465–575 行：

| 网页 JS | Swift |
|---|---|
| `gaussian(mu, sigma)` (Box-Muller) | `gaussian(_:_:)` |
| `getPDDensity(pdDate, params)` (5 段分段线性) | `getPDDensity(_:)` |
| `MONTHLY_WEIGHTS` | `monthlyWeights` |
| `simulate(params)` (144 月，路径级 regime 系数，10 月跳变，±30% 噪声) | `simulate()` |
| `monteCarlo(params, n)` | `monteCarlo(_:)` |
| `percentilePaths(allPaths)` | `percentilePaths(_:)` |
| `findCrossingsDistribution(allPaths)` | `findCrossingsDistribution(_:)` |

为可复现，引擎对 RNG 泛型化并统一用可种子化的 `SplitMix64`：App 以**用户 PD 派生种子**（同一 PD 每次结果一致、无抖动），单测用固定种子。

---

## 4. 公告推送通知

`BulletinWatcher` 轮询仓库的
`https://raw.githubusercontent.com/djzoom/EB1A/main/data/release_log.json`，
发现新一期公告（`bulletin` 字段出现更大的 `YYYY-MM`）时发**本地通知**：

> 📢 2026年7月 签证公告已发布 · 表A 2023-04-01 / 表B 2023-12-01

- **触发时机（M1）**：App 启动 + 每次回到前台时检查（`scenePhase == .active`）。无需自建后端/APNs。
- **后台轮询（M2 待做）**：接 `BGAppRefreshTask`，需在 Info.plist 加
  `BGTaskSchedulerPermittedIdentifiers` 与 `UIBackgroundModes=fetch`（XcodeGen 里补 `INFOPLIST_KEY_*` 或单独 plist）。

---

## 5. 路线图

- [x] **M1**：核心引擎 + 数据 + 首版 UI（欢迎/结果卡/走势图）+ 前台公告通知 + 单测
- [~] **M2**（进行中）
  - [x] 等待时间图 + 走势/等待时间模式切换（对齐 `drawWaitTimeChart`）
  - [x] 走势图收紧坐标域（2023→穿越缓冲）+ 表B 历史线
  - [x] 算法说明（①②③④ 实时代入）+ 关于本工具 折叠区
  - [ ] 图表 tooltip / 拖动取值
  - [ ] 参数滑杆与「数据来源」说明（PARAM_META）
  - [ ] `BGAppRefreshTask` 后台轮询（需 Info.plist 背景模式，真机验证）
- [ ] **M3**：cutoff/历史数据从仓库远程同步（而非内置常量），与网页自动更新对齐
- [ ] **M4**：App Icon 资产目录、App Store Connect 元数据、隐私问卷（不收集数据）、提交审核

---

## 6. 待你确认

- [ ] Bundle ID（默认 `com.djwz.eb1a`）
- [ ] App 显示名（默认「EB1A 排期预测」）
- [ ] 最低 iOS 版本（默认 **iOS 16**，Swift Charts 需 16+）
- [ ] 是否同时出 iPad 版（当前 `TARGETED_DEVICE_FAMILY=1,2` 已含 iPad）

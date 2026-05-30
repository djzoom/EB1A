# EB1A · macOS App（MAS 上架方案）

> 状态：**方案文档（待审）**。本目录尚未包含 Xcode 工程；确认本方案后再生成工程文件。
> 目标：把已上线的 EB1A PWA 包装成一个可在 **Mac App Store（MAS）** 上架的原生 macOS App。

---

## 1. 总体策略

**瘦壳（thin shell）+ 原生增值**：

- 用 SwiftUI + `WKWebView` 加载线上地址 `https://djzoom.github.io/EB1A/`；
- 网页（排期模型、文案、UI）一改，App 内容**自动同步**，无需为每次内容更新重新过审；
- 在壳层补足**原生功能**，使其不构成 App Store 审核指南 4.2 所指的「纯套壳网站」。

### 为什么不是打包离线资源
打包离线（把 `index.html`／图标塞进 bundle 本地加载）会让每次内容更新都必须重新发版过审，与本项目「公告一出 30 分钟内自动上线」的节奏冲突。瘦壳让网页侧的自动部署继续发挥作用。

### 为什么不是混合方案（暂不做）
混合（本地兜底 + 线上优先）体验最好，但实现更复杂（缓存一致性、版本协商）。本工具的 PWA Service Worker 已提供浏览器侧离线兜底；Mac 壳首版先做纯线上，断网时显示友好的重试页即可。后续如有需要再升级为混合。

---

## 2. 过审关键：原生增值功能

App Store 审核指南 **4.2（Minimum Functionality）**：纯粹加载网站的壳会被拒。本方案提供两类原生能力作为「存在理由」：

### 2.1 新签证公告推送通知（核心卖点）
- App 后台**轮询**仓库的 `data/release_log.json`（GitHub raw，公开、无需鉴权）；
- 发现新一期签证公告（`release_log` 出现新条目）时，发**本地通知**（`UNUserNotificationCenter`）：
  「📢 {年月} 签证公告已发布 · 表A {FAD} / 表B {DFF}」；
- 点击通知 → 唤起 App 并刷新到最新页面。

> 数据来源已存在：网页侧的 self-learning 探测器会在公告发布后约 30 分钟内更新 `data/release_log.json` 并提交到仓库。Mac App 只需消费这个文件，不需要自己抓 USCIS/DOS。

**轮询节奏（macOS）**：App 在前台时每 ~30 分钟查一次；进入后台用 `NSBackgroundActivityScheduler` 以「省电」优先级安排周期检查。不依赖服务器推送（无需自建后端、无 APNs 证书），实现最简。

### 2.2 原生菜单栏 / Dock 角标 / 快捷键
- 标准 macOS 菜单：**⌘R 刷新**、**⌘← / ⌘→ 前进后退**、**⌘L 跳转最新公告**、**⌘, 偏好设置**；
- **Dock 角标**：显示「距你排到的估算天数」或「有新公告」红点（需用户先在网页里填过 PD，壳层通过 `WKScriptMessageHandler` 读取页面派发的数值）；
- 「**通知设置**」偏好面板：开关公告推送、设定轮询频率。

> 这些都是 Safari 打开网站做不到的原生体验，是 4.2 的有力佐证。

---

## 3. 工程结构（确认后生成）

```
apple/
├── README.md                      # 本文档
├── EB1A.xcodeproj/                # Xcode 工程
└── EB1A/
    ├── EB1AApp.swift              # @main，App 生命周期、菜单命令
    ├── ContentView.swift          # 承载 WebView 的根视图
    ├── WebView.swift              # NSViewRepresentable 包装 WKWebView
    ├── BulletinWatcher.swift      # 轮询 release_log.json + 发本地通知
    ├── AppCommands.swift          # ⌘R / ⌘L 等菜单命令
    ├── Preferences.swift          # 通知/频率偏好（@AppStorage）
    ├── Info.plist                 # Bundle ID、权限、ATS
    ├── EB1A.entitlements          # App Sandbox + 出站网络
    └── Assets.xcassets/           # AppIcon（复用墨绿图标，见 §6）
```

---

## 4. 关键实现要点

### 4.1 WebView 壳
```swift
// WebView.swift（示意）
struct WebView: NSViewRepresentable {
    let url = URL(string: "https://djzoom.github.io/EB1A/")!
    func makeNSView(context: Context) -> WKWebView {
        let cfg = WKWebViewConfiguration()
        // 注入桥：页面可 window.webkit.messageHandlers.eb1a.postMessage({...})
        cfg.userContentController.add(context.coordinator, name: "eb1a")
        let wv = WKWebView(frame: .zero, configuration: cfg)
        wv.load(URLRequest(url: url))
        return wv
    }
    // updateNSView / Coordinator(WKScriptMessageHandler) 略
}
```

### 4.2 公告轮询 + 本地通知
```swift
// BulletinWatcher.swift（示意）
let raw = URL(string: "https://raw.githubusercontent.com/djzoom/EB1A/main/data/release_log.json")!
// 1. 拉取 JSON  2. 与上次记录的最新 published 比对（存 UserDefaults）
// 3. 有新条目 → UNUserNotificationCenter 发本地通知
// 前台 Timer(30min)；后台 NSBackgroundActivityScheduler(.utility, repeats)
```

### 4.3 权限 / 签名
- **App Sandbox**：开启（MAS 强制）；
- **出站网络**：`com.apple.security.network.client = true`（访问 github.io 与 raw.githubusercontent.com）；
- **通知**：首启请求 `UNUserNotificationCenter` 授权；
- **ATS**：两个域名均为 HTTPS，无需放宽 ATS。

---

## 5. 上架步骤（MAS）

1. App Store Connect 新建 App，Bundle ID（建议 `com.djwz.eb1a` 或你常用前缀）；
2. Xcode 选 **Apple Distribution / Mac App Store** 签名（你已是 Apple Developer，证书可在 Xcode 自动管理）；
3. Archive → Distribute App → App Store Connect 上传；
4. 填写元数据：分类「工具 / 参考」；隐私问卷声明「不收集数据」（壳不采集，PD 仅存浏览器 localStorage）；
5. 审核备注里**主动说明原生增值**：本地公告推送、原生菜单/快捷键/Dock 角标——预防 4.2 质疑；
6. 提交审核。

### 已知审核风险与对策
| 风险 | 对策 |
|---|---|
| 4.2 纯套壳被拒 | 突出 §2 原生功能；审核备注明确列出 |
| 隐私合规 | 声明不收集；PD 仅本地，链路 HTTPS |
| 离线无内容 | 断网显示原生重试页（非白屏） |

---

## 6. App 图标

复用网页 PWA 的墨绿图标体系（仓库根目录 `icon-512.png` / `icon.svg`）。macOS AppIcon 需要 16/32/128/256/512 @1x@2x 全套，可由 `icon.svg` 用 `cairosvg` 或 `sips`/`iconutil` 批量导出为 `.icns` 放进 `Assets.xcassets`。设计 prompt 见仓库聊天记录（墨绿渐变底 + 上升白柱）。

---

## 7. 待你确认 / 决策项

- [ ] Bundle ID 命名（默认建议 `com.djwz.eb1a`）
- [ ] App 显示名（默认 `EB1A 排期预测`）
- [ ] 最低 macOS 版本（建议 macOS 13 Ventura，覆盖广 + SwiftUI 成熟）
- [ ] 是否需要 iPad/iPhone 版（本方案仅 macOS；iOS 可后续以同壳 + Catalyst/多平台 target 扩展）

确认后我生成完整 Xcode 工程文件（你在本地 Mac 打开即可 Archive 上传）。

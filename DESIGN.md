# GC Time · 编辑式排期工作台

## 1. 视觉主题
面向查询个人绿卡排期的申请人，采用安静、明确、内容优先的绿灰工作台。预测日期与真实曲线是视觉中心；不使用营销 hero、装饰照片、玻璃效果或无意义的区块编号。布局变化 5/10、动效 2/10、信息密度 6/10。

本轮参考 Impeccable 的分组、去嵌套卡片原则，Taste 的既有项目 redesign 流程，以及 Emil Kowalski apple-design 的即时反馈、尺寸相关排版、克制动效。Apple HIG 的图表建议用于突出数据、保留解释、减少无用网格。Claude Design /design 是可选画板工具，本轮未运行其发布流程。

## 2. 颜色
浅色画布 `oklch(96.2% .006 160)`，白色内容区，主文本 `oklch(25% .022 160)`，绿色重点 `oklch(43% .10 161)`，琥珀色保守情景 `oklch(53% .12 70)`。深色模式使用同一语义 token，用户选择仅存本地。

## 3. 字体
使用平台系统字体 `-apple-system / BlinkMacSystemFont / Segoe UI / PingFang SC / Microsoft YaHei`。此页面是数据操作界面，采用 Apple typography 的可读性优先原则，不为差异化下载字体。标题 26px/650，预测 36–52px/600、行高 1.08、字距 -.03em，A/B 预测 22–28px，正文 12–14px，次要信息 11–12px。日期和图轴采用等宽数字。无远程字体，单 HTML 离线保持一致。

## 4. 组件
继续使用真实 HeroUI Pro `Widget` 与 HeroUI `Button`，不换框架。Widget 是语义分组，不等于每块都要单独卡片：预测和趋势共同占据一张连续工作纸面，档案在低强调侧栏。A/B 保留边界、选中填色和选择标记，先展示预测，再展示明确标注的当前排期。原有表单保留原生语义。

圆角尺度 6 / 8 / 12 / 20px；按钮 8px、A/B 12px。按钮按下立即 scale(.97)，100ms ease-out；hover 只对鼠标启用，focus 为 2px 绿色轮廓。

## 5. 布局
容器上限 1600px，4px 间距基准。桌面 248px 档案侧栏、32px 栏间距和自适应主区；预测日期与 A/B 对照并排，趋势图紧随其后，不再重复套灰色外壳。主要间距为 8 / 12 / 16 / 24 / 32px。首屏优先给出条件、结论、区间和趋势，数据假设在下方。所有断点共用一套 DOM。

SVG viewBox 与实际容器尺寸一致，桌面 340px 高、手机 280px 高。窄屏减少刻度数量，不缩小整张图。resize 只重画已有路径，不重跑模拟或重播动画。

## 6. 层级
一张工作纸面使用 `0 1px 3px rgb(22 42 33 / .10), 0 4px 14px rgb(22 42 33 / .025)`，内部不再套阴影卡片。档案透明、参数表低强调、结果突出。趋势用细分隔线连接上下文。

切换立即给出真实日期，180ms 轻微透明度反馈；取消首屏日期滚动。预测扇区 650ms 展开、标记无弹跳；完整模拟动画只由“推演”按钮主动触发。尊重 reduced-motion，不锁输入、不添加依赖。此产品没有新拖拽面板，因此不引入弹簧库或惯性滚动。

## 7. 约束
- 不改预测公式、500 次模拟、类别/国家集合、供给和速度选择。
- 不移动公告机器人读写的常量和标记。
- React 独占外壳；原引擎独占 LegacySlot 内的 DOM。
- 不把 HeroUI token、授权包源码或 source map 提交到仓库。
- 不新增服务器、账户、遥测或外部字体依赖。
- 离线 HTML 必须内联所有必要 JS/CSS。

## 8. 响应式和可访问性
≥1200px 并排预测；768–1199px 保留侧栏，主结果纵排；<768px 单列、档案按需展开。验证 375 / 768 / 1024 / 1440 / 1920px。控件至少 40px，日期输入 16px 防止 iOS 缩放；键盘焦点、减少动效、高对比度与深色模式同步检查。辅助信息不再依赖 9px 文字。图表主结论始终在图外可见，tooltip 只补充细节。

## 9. 后续组件提示
- “添加说明段：透明背景，12px/400、行高 1.8，颜色 `var(--text2)`；标题 16px/600、字距 -.2px，不添加容器卡片。”
- “添加档案操作按钮：8px 圆角、44px 高、12px/600，`var(--blue)` 底与 `var(--accent-foreground)` 字，按压 scale(.97)，100ms ease-out，focus 2px；reduced-motion 禁用缩放。”
- “添加日期指标：等宽数字，28px/600、行高 1.3、字距 -.02em，颜色 `var(--text)`；说明 12px/400、`var(--text2)`，不截断日期。”

参考：
- https://github.com/pbakaus/impeccable
- https://github.com/Leonxlnx/taste-skill/tree/main/skills/redesign-skill
- https://github.com/emilkowalski/skills/blob/main/skills/apple-design/SKILL.md
- https://developer.apple.com/design/human-interface-guidelines/charts
- https://code.claude.com/docs/en/commands

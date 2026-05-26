# EB1A Predictor 完整对话历史

记录从 2026-05-23 起,围绕 EB-1A 中国大陆排期预测工具的全过程开发。

## 第一阶段: V1-V5 探索期 (2026-05-23)

### V1: eb1-china-simulator.html
- 起点: 最简化的排期模拟
- 单一参数: 月推进速度
- 仅输出 P50

### V2-V3: eb1-china-simulator-v2/v2-1/v3.html  
- 引入蒙特卡洛 (100 次)
- 加入 P10/P50/P90 分位
- 加入 10 月跳跃概念
- 加入"大跳跃概率"参数

### V4: eb1-china-simulator-v4.html
- 加入 sensitivity analysis (eb1-sensitivity-analysis.html)
- 加入退化风险参数
- 加入历史回测雏形

### V5: eb1-china-simulator-v5.html
- 完善预设系统 (baseline/optimistic/pessimistic)
- 加入参数源说明卡片
- 加入 Garfield 完整时间线 T0-T6 (garfield-timeline.html)
- 加入因素总览 (garfield-factors-overview.html)
- 加入糖果店比喻教学 (candy-store-explainer.html)

### 早期产品化探索
- pathsight-mvp.html: 试图把工具变成 PathSight 产品
- xhs-eb1a-estimate.html: 小红书风格的简化预测

## 第二阶段: V11-V18 系统化 (2026-05-25 to 2026-05-26)

### V11-V13: eb1a-predictor-v11/v12/v13.html
- 重命名为 "EB 排期预测",定位为通用工具
- 重做 UI: 顶部预测条 + 分位卡 + 图表 + 参数 + 时间线
- 参数源说明系统 (点参数名弹窗)
- 默认预设 baseline

### V14: eb1a-predictor-v14.html (2,100 行)
- **重大架构**: 加入用户档案编辑
- 支持 6 个 EB 类别 × 5 个国家 × 2 个 chart (A/B)
- 9 个签证路径 (AOS + 8 个领事馆 CP)
- 默认改 CP 广州
- I-485 Chart A/B 兼容
- 60 种组合全覆盖

### V15: eb1a-predictor-v15.html (2,324 行)
- 移除 "black swan" 预设
- 严格校准到 FY26 H1 真实数据 (8 个月推进 99 天)
- 加入历史回测面板 (FY24/25/26 H1)

### V16: eb1a-predictor-v16.html (2,953 行)
- 图表 3 模式: forecast / inventory / multi
- I-485 库存数据可视化
- 多类别历史曲线对比
- 表 A / 表 B 双线

### V17: eb1a-predictor-v17.html (2,994 行)
- **关键 bug 修复**: 月度权重模型重做
- monthlyPace → annualAdvance (避免概念混淆)
- 修复 10 月跳跃在起始月的触发逻辑

### V18: eb1a-predictor-v18.html (2,996 行) - "5.5 年预测有问题"
- **用户洞察触发重大修正**: V17 的 baseline 严重低估
- 校准依据: 三年真实均值 153 天/年 + Papers 共识 + 律所共识
- annualAdvance default 100 → 180
- octoberJump 30 → 45
- bigJumpProb 20% → 30%
- 历史回测全部 good:
  - FY26 H1: 实 99 / 预测 103 (差 4%)
  - FY25: 实 44 / 预测 44 (差 0%)
  - FY24: 实 266 / 预测 267 (差 0%)
- **P50 = 2028-04**

## 第三阶段: V19-V21 哲学反思 (2026-05-26)

### V19: eb1a-predictor-v19.html (3,580 行) - 脉冲模型
**触发**: 用户要求"采样观察历史数据 + 一亩三分地共识 + 找出未完善"

发现 V18 月度权重的根本概念错误:
- 我用的是"签证发放数量月度分布"
- 但 cutoff 推进是"脉冲式"(71% 月份有动,29% 完全不动)

V19 全面改造:
1. **脉冲式月度模型** (4 个脉冲月: Oct/Jan/Apr/Jul)
2. **多模型并列对比** (V19 / Papers / FY24 / FY26 / 律所 / FY25 共 6 种)
3. **概率密度柱状图** (每月 current 概率) + 分位数视图 toggle
4. **印度状态参数** (indiaSpilloverFactor: 0-100%)
- 6 个参数, 3 个预设 (温和/乐观/悲观)
- **P50 = 2029-01** (温和默认)

### V20: eb1a-predictor-v20.html (3,410 行) - 奥卡姆剃刀
**触发**: 用户要求"用奥卡姆剃刀原则修正模型"

砍掉所有冗余:
- 6 个参数 → **2 个** (yearMu=153, yearSigma=91)
- 4 个魔法脉冲月 → 删除
- 85% 脉冲触发概率 → 删除
- 印度因子 → 删除
- 退化分支 → 删除

模型本质:
```
每个 FY: yearAdvance ~ Normal(μ=153, σ=91)
每月: cutoff += yearAdvance / 12
```

回测结果 (诚实版):
- FY26 H1: z=0.5σ → good
- FY25: z=1.2σ → medium  
- FY24: z=1.2σ → medium

**关键发现**: V19 (6 参数) 和 V20 (2 参数) 给出几乎相同的 P50。复杂度是冗余的。

- **P50 = 2029-03**

### V21: eb1a-predictor-v21.html (3,634 行) - 第一性原理
**触发**: 用户要求"列出所有需要的参数,来源,用第一性原理重构"

突破: cutoff 不是被推动的,是被定义的:
```
cutoff_advance × density(cutoff) = visa_count
```

7 个物理参数 (全部来自法规或观测):
- chinaBaseQuota: 2,803 (INA 法定)
- spilloverROW: 800 (Procl. 10998)
- spilloverIndia: 400 (DOS June 2026 警告)
- eb4eb5Spillover: 200
- familyMultiplier: 1.9
- densityHigh: 15 主申/天 (2023-2024 PD)
- densityPeak: 18 主申/天 (2024+ PD)

动态密度函数:
- 早期 PD 稀疏 (5/天)
- 近期 PD 密集 (18/天)
- 解释 FY24 大年 + FY25 慢年的真实机制

**P50 = 2028-12**

## V18-V21 四模型共识

| 模型 | 哲学 | 参数数 | P50 |
|------|------|--------|-----|
| V18 | 经验拟合 | 5 | 2028-04 |
| V19 | 脉冲事件 | 6 | 2029-01 |
| V20 | 奥卡姆 | 2 | 2029-03 |
| V21 | 第一性原理 | 7 | 2028-12 |

**4 个独立模型 P50 都在 2028末-2029中,这是真实可信预测**。

## 第四阶段: V22 架构反思 (待开发)

### 用户提出的根本改进方向

1. **visa-number supply 做主状态** (不再用"推进多少天"做输入)
2. **demand 改成 country × subcategory × PD-bucket × stage 的 cohort**
3. **India 影响改成显式竞争 E1 号码** (不再用 multiplier)
4. **回测改成 rolling holdout** (不再"喂历史参数复现历史")

### 关键数据发现

USCIS 自己发布完整 cohort 数据 (V11-V21 完全没用上):

1. **I-485 Pending Inventory** XLSX (月度) - 直接提供 `country × category × PD year × PD month → count`
2. **I-140 Approved Awaiting Visa** XLSX (季度)
3. **DOS Monthly Visa Issuance** (月度)
4. **DOS Annual Report** (年度)

详见 DATA_SOURCES.md。

### 同类开源项目

- **vyakunin/visa_bulletin** (https://github.com/vyakunin/visa_bulletin)
  - 268 commits, Django + Bazel + Docker
  - 已在线: https://visa-bulletin.us/
  - 可参考其架构

V22 目标: 完全重写为 agent-based simulation,在 Claude Code 中开发。
详见 CLAUDE_CODE_BOOTSTRAP.md。

## 开发背景

工具最初为 EB-1A 中国大陆申请人设计,PD 在 2024 年中,后泛化为支持多类别、多国家的通用预测工具。首次运行时要求用户输入自己的 Priority Date 等信息。

## 关键技术决策日志

| 日期 | 决策 | 触发 |
|------|------|------|
| 2026-05-23 | 启动单文件 HTML 工具 | 初始需求 |
| 2026-05-25 | V14 加入 60 种组合 | 通用化 |
| 2026-05-25 | V14 加入多路径支持 | 中国大陆主流 |
| 2026-05-26 | V18 大幅校准 | 用户指出"5.5 年错误" |
| 2026-05-26 | V19 引入脉冲模型 | 真实数据 71% pulse rate |
| 2026-05-26 | V20 奥卡姆剃刀 | 复杂度审计 |
| 2026-05-26 | V21 第一性原理 | 物理守恒方程 |
| 2026-05-26 | V22 架构定型 (待开发) | 用户提出 cohort/rolling holdout |

## 历史数据点 (visagrader 84 月 + Papers + USCIS)

### EB-1 China FY 推进
- FY23: -228 天 (出现排期,倒退)
- FY24: +266 天 (大年,4 大脉冲)
- FY25: +44 天 (慢年,印度抢占)
- FY26 (前 8 月): +100 天 (年化 150)

### USCIS 2024-06 Backlog
- EB-1 China I-140 pending: 9,208 主申
- EB-1 India I-140 pending: 16,808 主申
- EB-2 China I-140 pending: 34,629 主申

### FY 申请量 (中国 EB-1A)
- FY22: ~3,000
- FY23: 6,236
- FY24: 7,160
- FY25 Q4: 1,840 (季度)

### 法定配额
- 全球 EB 年配额: 140,000 × 28.6% × 28.6% = 40,040 (EB-1)
- 中国 EB-1 基础: 40,040 × 7% = 2,803

## 数据源完整清单

详见 DATA_SOURCES.md (17 个一/二/三级数据源)。

最重要的 4 个金矿:
1. USCIS I-485 Inventory XLSX (月度,含 PD month × country)
2. USCIS I-140 Approved XLSX (季度)
3. DOS Monthly Visa Issuance
4. DOS Annual Report of Visa Office

## 给 Claude Code 的接手指南

见 CLAUDE_CODE_BOOTSTRAP.md。

第一条 message 建议:
> "Read DATA_SOURCES.md and CLAUDE_CODE_BOOTSTRAP.md. Then start Phase 1: implement Cohort and GlobalState dataclasses in src/cohort.py, and allocate_monthly in src/allocator.py. Use synthetic data first (FY24 = 5200 visas, FY25 = 2200, FY26 = 4000). Write unit tests for INA rules: 7% per-country cap, ROW spillover to CN+IN by PD order, EB-4/5 cross-class spillover."

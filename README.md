# EB1A Priority Date Predictor

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

EB-1A 中国大陆排期预测工具,完整 V1-V21 迭代历史 + V22 架构方向。

## 在线 Demo

打开 `index.html` (V21 最新版),或部署到 GitHub Pages 后访问。

## V11-V21 演进历程

| 版本 | 行数 | 哲学 | 参数数 | P50 (Garfield PD=2024-06) |
|------|------|------|--------|---------------------------|
| V11-V13 | ~1500 | 经验拟合 | 4-5 | 不稳定 |
| V14 | 2100 | + 用户档案 + 60 种组合 | 5 | - |
| V15 | 2324 | 校准 FY26 H1 + 回测面板 | 5 | - |
| V16 | 2953 | + 库存图 + 多类别 | 5 | - |
| V17 | 2994 | annualAdvance 替代 monthlyPace | 5 | - |
| V18 | 2996 | 三年均值校准 | 5 | **2028-04** |
| V19 | 3580 | 脉冲模型 + 印度因子 + 密度图 | 6 | **2029-01** |
| V20 | 3410 | 奥卡姆剃刀 (μ+σ) | **2** | **2029-03** |
| V21 | 3634 | 第一性原理 (supply + density) | 7 | **2028-12** |

**V18-V21 四个独立模型共识 P50: 2028 末 ~ 2029 中**

## V11-V21 共同缺陷 (V22 要解决的)

1. 把 cutoff 时间序列当主状态,而 visa supply 才是真正状态变量
2. demand 当成总量 (9,208),无 cohort 结构 (country × subcategory × PD-bucket × stage)
3. 印度影响用 multiplier,不是显式 EB-1 号码竞争
4. 回测用 in-sample 拟合,不是 rolling holdout

## V22 目标

完全重写为 agent-based / discrete-event 模拟,真正还原 DOS 月度签证分配过程。

详见 [`CLAUDE_CODE_BOOTSTRAP.md`](./CLAUDE_CODE_BOOTSTRAP.md) 和 [`DATA_SOURCES.md`](./DATA_SOURCES.md)。

## 项目结构

```
EB1A/
├── index.html              # V21 (当前默认版本)
├── README.md               # 本文件
├── CONVERSATION_HISTORY.md # V1-V21 完整开发历史
├── CLAUDE_CODE_BOOTSTRAP.md # V22 接手指南
├── DATA_SOURCES.md         # 完整数据源清单 (17 个)
├── LICENSE                 # MIT
├── versions/               # V11-V21 历史 HTML
│   ├── eb1a-predictor-v11.html
│   ├── ...
│   └── eb1a-predictor-v21.html
└── exploration/            # 早期 V1-V5 探索
    ├── eb1-china-simulator.html
    ├── eb1-china-simulator-v2.html
    ├── ...
    ├── garfield-timeline.html
    ├── candy-store-explainer.html
    ├── pathsight-mvp.html
    └── xhs-eb1a-estimate.html
```

## 关键数据源

完整 17 个来源见 [`DATA_SOURCES.md`](./DATA_SOURCES.md)。

**金矿数据 (USCIS 自己发布的 cohort 数据)**:
- I-485 Pending Inventory XLSX (月度, by PD month × country × category)
- I-140 Approved Awaiting Visa XLSX (季度)
- DOS Monthly Immigrant Visa Issuance
- DOS Annual Report of Visa Office

**社区资源**:
- VisaGrader (84 月历史 cutoff): https://visagrader.com
- Papers (thepapers.co): 队列等待估计
- GreenCardClock: FY2025 中国 EB 完整分析
- Lucid Professional Writing: EB-5 月度精确解读
- ImmigrationRoad: CP/AOS 比例

**同类开源项目**:
- vyakunin/visa_bulletin: 268 commits, Django + Bazel (https://visa-bulletin.us/)
- visabulletin.ai: 1995-2026 timeline + cohort comparison

## 部署 GitHub Pages

1. Settings → Pages → Source: main / root → Save
2. 2 分钟后访问: https://djzoom.github.io/EB1A/

## V22 开发 (Claude Code)

```bash
git clone https://github.com/djzoom/EB1A.git
cd EB1A
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
- USCIS 2024-06 EB-1 China I-140 pending: 9,208 主申
- 法定中国 EB-1 基础配额: 2,803 (40,040 × 7%)

## 使用

首次打开 `index.html` 时,会弹出欢迎面板要求输入你的 Priority Date、类别、出生国等信息。数据仅保存在浏览器 localStorage,不会上传。

V18-V21 四个独立模型共识区间: **P50 ≈ 2028 末 ~ 2029 中** (以 EB-1A 中国大陆 2024 年中 PD 为例)

## License

MIT - 见 [LICENSE](./LICENSE)

## 免责声明

**这不是法律建议**。预测基于公开数据的统计估算。实际移民结果受政策变化、行政命令、立法和个人情况影响。请咨询持牌移民律师获取法律建议。

# EB1A Priority Date Predictor

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

EB-1A 中国大陆排期预测工具。基于公开政府数据（USCIS / DOS），用供给 + 队列密度的第一性原理方法估算 Priority Date 何时到期。

## 在线 Demo

打开 `index.html`，或部署到 GitHub Pages 后访问。

## 方法

工具不直接外推 cutoff 时间序列，而是还原签证分配的底层过程：

1. **库存（demand）**：按 country × subcategory × PD-bucket × stage 拆分排队人群，而非用单一总量。
2. **供给（supply）**：每财年法定配额 + 单国 7% 上限 + 其他国家用不完的溢出。
3. **密度**：估算目标 PD 之前还有多少人，决定需要消耗多少签证号才能轮到。
4. **不确定性**：用蒙特卡洛模拟给出 P10 / P50 / P90 区间，而非单点预测。

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
└── scripts/                  # 数据抓取 / 校准 / 验证脚本
```

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

## 部署 GitHub Pages

1. Settings → Pages → Source: main / root → Save
2. 2 分钟后访问: https://djzoom.github.io/EB1A/

## 开发 (Claude Code)

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
- USCIS June 2024 EB-1 China I-140 pending: 9,208 主申
- 法定中国 EB-1 基础配额: 2,803 (40,040 × 7%)

## 使用

首次打开 `index.html` 时，会弹出欢迎面板要求输入你自己的 Priority Date、类别、出生国等信息。数据仅保存在浏览器 localStorage，不会上传。

预测结果（P50 中位 + 90% 置信区间）以你输入的 PD 为准计算。

## License

MIT - 见 [LICENSE](./LICENSE)

## 免责声明

**这不是法律建议**。预测基于公开数据的统计估算。实际移民结果受政策变化、行政命令、立法和个人情况影响。请咨询持牌移民律师获取法律建议。

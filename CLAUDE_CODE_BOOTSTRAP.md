# EB1A Predictor - Claude Code Bootstrap

## 上下文

当前 `index.html` 是单文件 HTML 预测工具，拟合 cutoff 时间序列。已知**根本局限**：

1. 把 cutoff 当主状态，而 visa supply 才是真正的状态变量
2. demand 当成总量，无 cohort 结构
3. India 用 multiplier，不是显式 EB-1 号码竞争
4. 回测用 in-sample 拟合，不是 rolling holdout

## 目标

重写为 agent-based simulation，模拟 DOS 真实月度签证分配。

## 🎯 关键数据源

### USCIS 自己发布完整 cohort 数据

1. **I-485 Pending Inventory** (月度 XLSX):
   - https://www.uscis.gov/tools/reports-and-studies/immigration-and-citizenship-data
   - 文件: "Pending Applications for Employment-Based Preference Categories"
   - Schema: `preference × country × PD_year × PD_month → count`
   - **直接对应 cohort(country, subcat, pd_bucket, stage=I485_filed)**
   - 最新: January 2, 2026 (107.89 KB XLSX)
   - 历史: 2014- 月度发布 (CSV/XLSX)

2. **I-140 Approved Awaiting Visa** (季度 XLSX):
   - 同页面
   - Schema: `preference × country → count` (无 PD 拆分)
   - 对应 cohort(country, subcat, stage=I140_approved_no_485)

3. **DOS Monthly Immigrant Visa Issuance**:
   - https://travel.state.gov/.../monthly-immigrant-visa-issuances.html
   - 实际发放数 by category × country
   - 用于校准 allocator + 反推消耗

4. **DOS Annual Report of Visa Office** (FY 2015-2024 完整发放)

### 同类开源项目可参考

**vyakunin/visa_bulletin** (https://github.com/vyakunin/visa_bulletin):
- Django + Bazel + Docker
- 已有 data/models/extractors/webapp 完整架构
- 在线: https://visa-bulletin.us/
- 方法学: "historical bulletin patterns, I-140 demand data, fiscal year cycles"

**社区数据整理**:
- GreenCardClock: China EB 完整拆分
- Lucid blog (blog.lucidtext.com): EB-5 月度精确解读
- ImmigrationRoad: CP/AOS 比例计算 (~85%/15%)
- visabulletin.ai: timeline + cohort comparison

完整数据源清单见 DATA_SOURCES.md。

## Core State 架构

```python
@dataclass
class Cohort:
    country: Literal['CN', 'IN', 'MX', 'PH', 'ROW']
    subcategory: Literal['EB1A', 'EB1B', 'EB1C', 'EB2', 'EB3', 'NIW', 'EB4', 'EB5_unreserved', 'EB5_rural']
    pd_bucket: tuple[int, int]  # (year, month)
    stage: Literal['I140_pending', 'I140_approved_no_485', 'I485_filed', 'NVC_queued', 'DS260_ready']
    main_applicants: int
    family_multiplier: float = 1.9

@dataclass
class GlobalState:
    fiscal_year: int
    month_in_fy: int
    visa_pools: dict[str, float]
    cohorts: list[Cohort]
    cutoffs: dict[tuple[str, str, str], date]
    visa_issued_log: list[dict]
```

## Visa Allocator (核心算法,源自 INA + Charles Oppenheim)

```python
def allocate_monthly(state, month):
    """每月按 INA 规则分配"""

    # 1. 本月各 category 池子可用
    monthly_eb1_pool = state.visa_pools['EB1'] / months_remaining_in_fy

    # 2. 按 PD 排序所有 ready cohorts
    ready_cohorts = sorted(
        [c for c in state.cohorts if c.stage in ['DS260_ready', 'I485_filed']
         and c.subcategory.startswith('EB1')],
        key=lambda c: (c.pd_bucket, c.country)
    )

    # 3. 7% 单国上限
    country_used = {c: 0 for c in ['CN', 'IN', 'MX', 'PH', 'ROW']}
    country_cap_monthly = (40040 * 0.07) / 12  # ~234

    # 4. 服务队列
    pool_remaining = monthly_eb1_pool
    for cohort in ready_cohorts:
        if pool_remaining <= 0:
            break
        if country_used[cohort.country] >= country_cap_monthly:
            continue

        can_issue = min(
            cohort.main_applicants * cohort.family_multiplier,
            pool_remaining,
            country_cap_monthly - country_used[cohort.country]
        )

        cohort.main_applicants -= can_issue / cohort.family_multiplier
        pool_remaining -= can_issue
        country_used[cohort.country] += can_issue

        state.visa_issued_log.append({
            'month': month, 'cohort': cohort, 'visas': can_issue
        })

    # 5. 月末: ROW 余量溢出到中印 (按 PD 早晚)
    # 6. 重算 cutoff = 本月最后服务 cohort 的 PD
```

## Rolling Holdout 回测

```python
def rolling_backtest():
    test_periods = [
        ('FY24', date(2023, 10, 1), date(2024, 10, 1)),
        ('FY25', date(2024, 10, 1), date(2025, 10, 1)),
        ('FY26_H1', date(2025, 10, 1), date(2026, 4, 1))
    ]

    for name, start, end in test_periods:
        # 用 start 之前的 cohort snapshot
        initial_state = load_state_at(start)

        # 跑 forward simulation
        prediction = simulate(initial_state, months=(end - start).days // 30)

        # 对比真实
        actual_cutoff = load_visa_bulletin(end)
        error_days = (prediction.china_eb1_cutoff - actual_cutoff).days
        report(name, error_days)
```

## 项目结构

```
EB1A/
├── README.md
├── DATA_SOURCES.md
├── CLAUDE_CODE_BOOTSTRAP.md (this file)
├── index.html (当前预测工具)
├── data/
│   ├── raw/{uscis,dos,community}/
│   ├── processed/*.parquet
│   └── README.md
├── scripts/
│   ├── scrape_uscis.py
│   ├── scrape_dos.py
│   └── build_initial_cohorts.py
├── src/
│   ├── cohort.py
│   ├── allocator.py
│   ├── simulator.py
│   ├── backtest.py
│   └── policy.py
├── tests/
└── webapp/    (FastAPI + 新前端)
```

## 任务清单

### Phase 1: Schema + Allocator (合成数据)
- [ ] Cohort / GlobalState dataclass
- [ ] allocate_monthly (INA 规则)
- [ ] 合成数据测试 (FY24=5200, FY25=2200, FY26=4000)
- [ ] 单元测试: 7% 上限, 溢出, 跨类

### Phase 2: 真实数据接入
- [ ] USCIS XLSX scraper (i485_inventory)
- [ ] USCIS XLSX scraper (i140_approved)
- [ ] DOS visa issuance scraper
- [ ] DOS visa bulletin scraper
- [ ] 构建历史 cohort snapshots

### Phase 3: 校准 + 回测
- [ ] Rolling holdout
- [ ] Stage transition rates 反推
- [ ] FY24/25/26 验证
- [ ] Error 分布报告

### Phase 4: Web UI
- [ ] 拆当前 HTML 为 components
- [ ] FastAPI 后端
- [ ] 接入 cohort 引擎
- [ ] 部署

## 示例场景

- 输入: 用户自己的 PD、类别 (如 EB-1A)、出生国
- 当前 cutoff (June 2026): 2023-04-01 (FAD), 2023-12-01 (Filing)
- 首次运行时要求用户输入自己的 PD、类别、出生国等信息

目标: 基于真实 cohort 数据 + INA 规则，给出可解释 + 可回测的 P50。

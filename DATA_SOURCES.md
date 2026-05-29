# EB1A Predictor - 数据源清单

完整可下载/可抓取的公开数据源,用于构建 cohort × country × subcategory × PD-bucket × stage 模型。

---

## 🎯 一级数据源 (官方 + 直接结构化)

### 1. USCIS I-485 Pending Inventory (含 PD bucket)

**最重要数据源**。USCIS 每月发布 XLSX,按"类别 × 国家 × PD 月份 × 数量"切片。

- 入口: https://www.uscis.gov/tools/reports-and-studies/immigration-and-citizenship-data
- 最新: "Pending Applications for Employment-Based Preference Categories as of January 2, 2026" (XLSX, 107.89 KB)
- 历史 CSV 格式 (2014-): 
  - https://www.uscis.gov/sites/default/files/document/data/EB-I-485-PendingInventory-2014-Jan.csv
  - 文件名模式: `EB-I-485-PendingInventory-YYYY-Mon.csv`
- 覆盖: 全部 EB-1/2/3/4/5 + 5 个国家 (China, India, Mexico, Philippines, ROW)

**Schema** (从 2014 CSV 推断):
```
preference_category × country × pd_year × pd_month → count
e.g. EB-1, China, 2024, June → 320
```

**直接对应你提的 cohort 结构** (country × subcat × PD-bucket × stage=I485_filed)。

### 2. USCIS I-140 Approved Awaiting Visa

- 同一页面: "Form I-140, I-360, I-526 Approved EB Petitions Awaiting Visa Final Priority Dates" (XLSX, 22.71 KB)
- 这是 stage=I140_approved 的 cohort 数据

### 3. DOS Monthly Immigrant Visa Issuance (含 country × category)

**实际签证发放数据**,可用于反推 supply。

- 入口: https://travel.state.gov/content/travel/en/legal/visa-law0/visa-statistics/immigrant-visa-statistics/monthly-immigrant-visa-issuances.html
- 月度: 每个 FY 一个 PDF/XLSX
- 类型: 按"国家 × visa category"

### 4. DOS Annual Report of the Visa Office

- 历史(FY 2015-2024) - 完整数据
- 每年发布详细统计
- 入口: https://travel.state.gov/content/travel/en/legal/visa-law0/visa-statistics/annual-reports.html

### 5. DOS Visa Bulletin 历史 (1995-2026)

- 全部历史 cutoff 时间序列
- VisaGrader 已抓取整理: https://visagrader.com/green-card/visa-bulletin/china/EB1
- 直接 source: https://travel.state.gov/content/travel/en/legal/visa-law0/visa-bulletin.html

### 6. USCIS I-140/I-485 Quarterly Reports

- 每季度 receipts / approvals / denials by category × country
- 完整 FY2025 数据已发布
- 入口同 USCIS Immigration Data 页面

---

## 🥈 二级数据源 (社区/律所整理)

### 7. visa-bulletin.us GitHub 仓库

**最接近的同类项目** (3 stars but 268 commits,严肃工程)

- 仓库: https://github.com/vyakunin/visa_bulletin
- 在线: https://visa-bulletin.us/
- 技术栈: Django + Bazel + Docker
- 目录结构:
  - `data/` - 数据
  - `models/` - 模型
  - `extractors/` - 数据提取器
  - `webapp/` - 前端
- 方法学: "Bulletin Forecast Model uses historical bulletin patterns, I-140 demand data, and fiscal year cycles"
- 也有 backtest 功能

**值得 fork 或学习其架构**。

### 8. GreenCardClock

- https://greencardclock.com/blog/china-eb-visa-data-fy2025-eb1-eb2-eb3-eb5
- 详细 FY2025 China EB 数据分析 (含 Q1-Q4 拆分)
- 关键发现:
  - China EB-1A Q4 2025 receipts: 1,840 (季度)
  - China EB-2/NIW 增长 49.3% YoY
  - China EB-5 因 consular freeze 从 942/月暴跌到个位数

### 9. ImmigrationRoad Green Card Tracker

- https://immigrationroad.com/green-card-tracker.php
- 基于 USCIS I-485 inventory
- 关键公式: **CP/AOS 比例 ~85%/15%** (历史均值)
- 按 category 单独计算 CP-to-AOS ratio
- **直接对应你要的 stage=CP vs AOS 拆分**

### 10. Lucid Professional Writing (EB-5 重点)

- https://blog.lucidtext.com/category/eb-5-statistics/
- 每月精确解读 I-485 inventory 变化
- 详细方法学: "net deductions from I-485 inventory ≈ visas issued"
- **可学习他们的反推算法**

### 11. Papers (thepapers.co) - DreamingKevin

- "队列平均等待 2.9 年" 共识
- I-485 inventory 按 PD 分布图

### 12. 一亩三分地 14 季度统计

- 中国 EB-1 I-140 数据按季度
- 反爬,但内容已被各处转载

### 13. Visabulletin.ai Timeline

- https://www.visabulletin.ai/timeline
- 1995-2026 全部历史
- 含 "cohort comparison" 功能 (你提的关键概念)
- AI narrated insights

---

## 🥉 三级数据源 (推理 + 法规)

### 14. INA 法定参数 (硬约束)

- INA Section 201(d): 全球年配额 140,000
- INA Section 203(b): EB 占比 28.6%, 各 EB 子类比例
  - EB-1: 28.6% (40,040)
  - EB-2: 28.6%
  - EB-3: 28.6%
  - EB-4: 7.1%
  - EB-5: 7.1%
- INA Section 202(a)(2): 单国上限 7%

### 15. Presidential Proclamations & Executive Orders

- Proclamation 10998 (2025-09): 75 国 EB-5 暂停
- 影响溢出计算

### 16. CRS Reports (Congressional Research Service)

- https://www.congress.gov/crs-product/R47164 "U.S. Employment-Based Immigration Policy"
- 详细规则解读

### 17. Charles Oppenheim 公开发言

- DOS Chief of Immigrant Visa Control 多年发言
- 每月 visa office 内部 demand 估算流程
- 可以从律所 blog (AILA, Cyrus Mehta, Murthy 等) 抓取

---

## 🛠 自动化抓取建议

### GitHub Actions 工作流 (参考 jerrynsh 的 passport index 项目)

```yaml
# .github/workflows/scrape.yml
on:
  schedule:
    - cron: '0 0 * * 1'  # 每周一
  workflow_dispatch:

jobs:
  scrape:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Scrape USCIS
        run: python scripts/scrape_uscis.py
      - name: Scrape DOS Bulletin
        run: python scripts/scrape_dos.py
      - name: Commit data
        run: |
          git add data/
          git commit -m "Auto-update $(date +%Y-%m-%d)"
          git push
```

### 必要的 scrapers

| 脚本 | 数据源 | 频率 |
|------|--------|------|
| `scrape_uscis_i485_inventory.py` | USCIS XLSX | 月度 |
| `scrape_uscis_i140_approved.py` | USCIS XLSX | 季度 |
| `scrape_dos_visa_bulletin.py` | DOS bulletin HTML | 月度 |
| `scrape_dos_monthly_issuance.py` | DOS PDF/XLSX | 月度 |
| `scrape_uscis_quarterly_reports.py` | USCIS quarterly | 季度 |

---

## 📊 初始 cohort 库存构建步骤

### Phase 1: 静态快照 (用最新数据初始化)

1. 下载 USCIS I-485 Inventory January 2026 XLSX
2. 解析为 cohort 表: (country, category, pd_year, pd_month, count)
3. 应用 CP/AOS 比例 (从 ImmigrationRoad 或自己算)
4. 估算 stage 分布:
   - I-485 pending (有这数据): 直接 stage=I485_filed
   - I-140 approved no I-485: USCIS I-140 approved 数据
   - I-140 pending: 估算或推断
5. 应用 family_multiplier (1.9) 转主申 → 签证

### Phase 2: 历史轨迹回放

1. 拿历史 USCIS I-485 inventory (回到 2017)
2. 拿 DOS 月度 visa issuance
3. 跨期对照: inventory(t) - inventory(t-1) ≈ visas_issued(t) - new_filings(t)
4. 校准 allocator 参数

### Phase 3: Rolling holdout

1. 用 2017-2023 数据 fit
2. 预测 2024 → 对比 FY24 真实
3. 用 2017-2024 fit, 预测 2025 → 对比 FY25 真实
4. 用 2017-2025 fit, 预测 2026 H1 → 对比真实

---

## 🚨 数据局限

诚实承认这些数据的盲点:

1. **DOS NVC consular queue 不在公开数据**
   - 5 万+ China EB applicants 在 NVC 等待面签,但没有按 PD 月度拆分的公开数据
   - 律所估算 + Lucid blog 偶尔披露
2. **stage transition rates 是黑盒**
   - USCIS 不公开"多少 I-140 转 I-485 / 多少放弃 / 多少跨类"
   - 需要从 inventory 变化反推
3. **Cross-chargeability (跨国家归属) 不可见**
   - 有人用配偶国家排队,USCIS 数据不区分
4. **撤回率 / 放弃率**
   - 无官方,估算 8-15%/年

---

## 推荐数据架构

```
data/
├── raw/
│   ├── uscis/
│   │   ├── i485_inventory_2024_01.xlsx
│   │   ├── i485_inventory_2024_02.xlsx
│   │   ├── ...
│   │   ├── i485_inventory_2026_01.xlsx
│   │   └── i140_approved_2025_q4.xlsx
│   ├── dos/
│   │   ├── visa_bulletin_2026_06.json
│   │   ├── monthly_issuance_2025_09.csv
│   │   └── annual_report_fy2024.pdf
│   └── community/
│       ├── greencardclock_china_fy2025.csv
│       └── lucid_eb5_monthly_estimates.csv
├── processed/
│   ├── cohorts_snapshot_2026_01.parquet  # 主 cohort 表
│   ├── visa_issuance_monthly.parquet     # 月度发放
│   ├── stage_transition_rates.parquet    # 反推
│   └── visa_bulletin_history.parquet     # 1995-2026
└── derived/
    ├── allocator_params.json             # 反推 allocator 参数
    └── density_curves.json               # PD 密度估算
```

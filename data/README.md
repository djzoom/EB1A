# Data Directory

Public government data for EB-1A priority date prediction (V22).

All files are from official USCIS/DOS sources or community-curated public datasets.

## USCIS I-485 Pending Inventory (9 snapshots)

Monthly cohort data: category x country x PD-month x count.

| File | Date | Source |
|------|------|--------|
| I485_Pending_Inventory_2024_02.xlsx | Feb 2024 | uscis.gov |
| I485_Pending_Inventory_january_2025.xlsx | Jan 2025 | uscis.gov |
| I485_Pending_Inventory_february_2025.xlsx | Feb 2025 | uscis.gov |
| I485_Pending_Inventory_march_2025.xlsx | Mar 2025 | uscis.gov |
| I485_Pending_Inventory_april_2025.xlsx | Apr 2025 | uscis.gov |
| I485_Pending_Inventory_may_2025.xlsx | May 2025 | uscis.gov |
| I485_Pending_Inventory_october_2025.xlsx | Oct 2025 | uscis.gov |
| I485_Pending_Inventory_november_2025.xlsx | Nov 2025 | uscis.gov |
| I485_Pending_Inventory_december_2025.xlsx | Dec 2025 | uscis.gov |
| I485_Pending_Inventory_january_2026.xlsx | Jan 2026 | uscis.gov |

Gap: Jun-Sep 2025 not published by USCIS.

## USCIS I-140 Quarterly Reports (5 quarters)

Receipts / approvals / denials by category x country.

| File | Period |
|------|--------|
| I140_FY2024_Q3.xlsx | FY2024 Q3 (Apr-Jun 2024) |
| I140_FY2024_Q4.xlsx | FY2024 Q4 (Jul-Sep 2024) |
| I140_FY2025_Q1.xlsx | FY2025 Q1 (Oct-Dec 2024) |
| I140_FY2025_Q2.xlsx | FY2025 Q2 (Jan-Mar 2025) |
| I140_FY2025_Q3.xlsx | FY2025 Q3 (Apr-Jun 2025) |

## USCIS I-140/I-360/I-526 Approved Awaiting Visa

| File | Description |
|------|-------------|
| I140_I360_I526_Approved_FY2025_Q2.xlsx | Approved petitions awaiting visa availability |
| I485_EB_Approvals_FY2023_Q1Q2.xlsx | EB I-485 approval counts |

## DOS Monthly Immigrant Visa Issuance (24 months)

Actual visa issuances by country x visa class. Two full fiscal years.

**FY2024** (Oct 2023 - Sep 2024): 12 files
**FY2025** (Oct 2024 - Sep 2025): 12 files

Format: `iv_issuance_{month}_{year}.xlsx`

## Community Data

| File | Description |
|------|-------------|
| china_visa_backlog_timecourse.csv | EB-1 China cutoff history, 226 rows (2005-2025), from VisaGrader |

## Sources

See [`DATA_SOURCES.md`](../DATA_SOURCES.md) for the full 17-source catalog.

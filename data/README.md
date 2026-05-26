# Data Directory

Real data files are not committed to git (see .gitignore).
This directory is the target for the V22 data pipeline.

## Layout

```
data/
├── raw/
│   ├── uscis/         # Downloaded USCIS XLSX files
│   │   ├── i485_inventory_YYYY_MM.xlsx
│   │   └── i140_approved_YYYY_qN.xlsx
│   ├── dos/           # DOS bulletins and issuance
│   │   ├── visa_bulletin_YYYY_MM.json
│   │   └── monthly_issuance_YYYY_MM.csv
│   └── community/     # GreenCardClock, Lucid blog data
├── processed/
│   ├── cohorts_snapshot_YYYY_MM.parquet
│   ├── visa_issuance_history.parquet
│   ├── stage_transition_rates.parquet
│   └── visa_bulletin_history.parquet
└── derived/
    ├── allocator_params.json
    └── density_curves.json
```

## Scrapers

See `scripts/` (to be created in V22).

Run:
```bash
python scripts/scrape_uscis.py    # Monthly
python scripts/scrape_dos.py       # Monthly
```

## Sources

See `../DATA_SOURCES.md`.

# Data Analysis

A small, dependency-free Python project for analyzing large local information
sets and writing readable summary reports.

The analyzer scans a folder of data files, detects common file types, computes
basic statistics, and writes both Markdown and JSON summaries.

## Supported Inputs

- CSV and TSV files
- JSON files containing objects or arrays
- Markdown and plain text files

## Run

```powershell
python data_analyzer.py
```

By default, the analyzer reads from `data/` and writes to `reports/`.

You can also pass custom paths:

```powershell
python data_analyzer.py --input data --output reports
```

## Outputs

```text
reports/analysis_summary.md
reports/analysis_summary.json
```

The Markdown report is intended for quick human review. The JSON report can be
used by other tools or future automation.

## GitHub Actions

The included workflow runs the analyzer whenever changes are pushed to `main`
and uploads generated reports as an artifact.

## Project Boundaries

This repository is intentionally separate from any topic-specific research
project. Keep reusable data-analysis code here, and keep domain-specific source
materials, reports, and workflows in their own repositories.

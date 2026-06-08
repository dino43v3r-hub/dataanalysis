# Data Analysis

A small, dependency-free Python project for analyzing large local information
sets and writing readable summary reports.

The analyzer scans a folder of data files, detects common file types, computes
basic statistics, flags likely data-quality issues, and writes both Markdown and
JSON summaries.

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

To frame the analysis around a specific problem, pass a goal:

```powershell
python data_analyzer.py --input data --output reports --goal "Find why C drives are filling up and recommend remediation."
```

To generate a local issue-resolution report without calling any external API:

```powershell
python data_analyzer.py --input data --output reports
```

To ask Groq to draft practical resolution notes for each detected issue, set a
model, then enable the resolver:

```powershell
$env:GROQ_MODEL="openai/gpt-oss-20b"
python data_analyzer.py --input data --output reports --resolve-with-groq --prompt-groq-key --prompt-goal
```

The goal is sent to Groq with each detected issue so the generated action plan
is framed around the problem you are trying to solve, not just generic data
quality.

The prompt hides the key as you type and keeps it in memory only for that run.
Do not paste API keys into chat, commit them to source control, or store them in
the Python file. For automation, use a secret manager or a protected CI secret
to provide `GROQ_API_KEY` at runtime.

### GitHub Secret Setup

For GitHub Actions, store the Groq key as a repository secret:

1. Open the GitHub repository.
2. Go to **Settings** > **Secrets and variables** > **Actions**.
3. Create a repository secret named `GROQ_API_KEY`.
4. Paste the Groq API key as the secret value.
5. Run the **Analyze Data** workflow manually from the **Actions** tab.
6. Enable `resolve_with_groq` and choose the model.

GitHub masks secrets in logs, and the workflow passes the key through the
`GROQ_API_KEY` environment variable only during the job.

## Outputs

```text
reports/analysis_summary.md
reports/analysis_summary.json
reports/issue_resolution_report.md
reports/issue_resolution_report.json
```

The Markdown report is intended for quick human review. The JSON report can be
used by other tools or future automation. The issue-resolution report includes
locally generated recommendations by default and Groq-generated resolution notes
when `--resolve-with-groq` is enabled.

## GitHub Actions

The included workflow runs the analyzer whenever changes are pushed to `main`
and uploads generated reports as an artifact.

## Project Boundaries

This repository is intentionally separate from any topic-specific research
project. Keep reusable data-analysis code here, and keep domain-specific source
materials, reports, and workflows in their own repositories.

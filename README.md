# Automation Report Failure Analyzer with Streamlit UI

This project analyzes automation HTML reports in three stages:

1. extract failed test details from the HTML report
2. categorize failures using regex rules
3. generate an Excel workbook with summary and detailed failure sheets

A Streamlit UI is included so users can upload a report, optionally choose a report type, watch logs live, review results in the browser, and download the Excel file.

## What changed

- Added a Streamlit UI in `app.py`
- Added a pipeline runner in `report_failure_pipeline.py`
- Added support for forcing a report type by profile name
- Added sequential orchestration: extractor -> categorizer -> Excel generator
- Added run-folder logging to `Results/Run_<timestamp>/analysis.log`
- Added per-stage progress logging for UI and file output
- Kept each script independently runnable from the command line

## Project structure

```text
html_report_failure_analyzer/
├── app.py
├── report_failure_pipeline.py
├── report_failure_extractor_v1.py
├── report_failure_categorizer_v1.py
├── report_failure_excel_generator_v1.py
├── report_profiles.json
├── failure_categorization.json
├── requirements.txt
├── profiles/
│   ├── testng_custom.json
│   ├── extent_spark.json
│   ├── extent_v2.json
│   └── generic_html.json
└── Results/
    └── Run_YYYYMMDD_HHMMSS/
        ├── original_report.html
        ├── report_failure_details.json
        ├── report_failure_categorization.json
        ├── report_failure_categorization.xlsx
        └── analysis.log
```

## Supported report handling

The profile folder contains JSON files that define how report extraction is done.

When the report type is:

- **Auto Match**: the extractor auto-detects the report type using `report_profiles.json` and the profile JSON files in `profiles/`
- **Selected explicitly**: the chosen profile name is used directly and auto-detection is skipped

Current bundled profiles:

- `testng_custom`
- `extent_spark`
- `extent_v2`
- `generic_html`

## Installation

Use Python 3.9 or later.

```bash
python -m venv .venv
source .venv/bin/activate
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run the Streamlit UI

From the project folder:

```bash
streamlit run app.py
```

## Streamlit UI behavior

The UI provides:

1. **Mandatory HTML report upload**
2. **Optional report type selection** with default `Auto Match`
3. **Sequential execution** of extraction, categorization, and Excel generation
4. **Live logs** visible in the UI
5. **Summary section** after analysis
6. **Details section** after analysis
7. **Excel download button** after generation
8. **Log file** saved to the run folder

## Command line usage

### 1) Extract failed test details

Auto-detect the report type:

```bash
python report_failure_extractor_v1.py path/to/report.html
```

Force a report type:

```bash
python report_failure_extractor_v1.py path/to/report.html --report-type testng_custom
```

Other useful options:

```bash
python report_failure_extractor_v1.py path/to/report.html \
  --profile-index report_profiles.json \
  --profiles-dir profiles \
  --run-dir Results/Run_manual
```

### 2) Categorize extracted failures

```bash
python report_failure_categorizer_v1.py Results/Run_<timestamp>/report_failure_details.json \
  --categorization failure_categorization.json
```

### 3) Generate Excel

```bash
python report_failure_excel_generator_v1.py Results/Run_<timestamp>/report_failure_categorization.json
```

### 4) Run full pipeline in one command

Auto-detect report type:

```bash
python report_failure_pipeline.py path/to/report.html
```

Force a report type:

```bash
python report_failure_pipeline.py path/to/report.html --report-type extent_spark
```

## Output

Each run creates a folder under `Results/Run_<timestamp>/`.

Generated files:

- copied HTML report
- `report_failure_details.json`
- `report_failure_categorization.json`
- `report_failure_categorization.xlsx`
- `analysis.log`

## Notes

- The generic HTML profile is a fallback and may produce noisier extraction for unknown report formats.
- Profile accuracy depends on the structure of the source HTML.
- The Streamlit UI displays the generated summary and categorized details from the JSON output.
- The Excel workbook contains a Summary sheet and a Categorized Failures sheet.

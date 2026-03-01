# Lead Paint Data Validation Pipeline

## Overview
LEEP runs paint studies across multiple countries, with lab results delivered as CSV files and sample metadata maintained separately in spreadsheets (e.g. manufacturer, brand, product type). Reconciling these sources manually is time-consuming, error-prone and inconsistent across programme teams.

This Python script automates the reconciliation and validation process by standardising sample IDs, merging lab results with metadata, converting lead results from % to ppm, and classifying compliance against a configurable threshold (default 90 ppm). It also generates structured issue logs (e.g. unmatched IDs, duplicates, lab QC comments) and a Markdown summary report to speed up review and cross-country analysis.

## Key features
- Standardises sample identifiers to ensure reliable merging between lab results and metadata
- Handles detection-limit values (e.g. "<0.0049%") and converts percentage lead values to ppm
- Classifies samples as Compliant / Non-compliant / Unknown using a configurable threshold (default 90 ppm)
- Flags data quality issues including duplicates, unmatched IDs, negative values and lab QC comments
- Generates cleaned merged outputs, issue logs and a Markdown summary report

## Inputs
The script expects:

- A laboratory CSV file containing: 
    - `Sample ID`
    - `TOTAL` (lead %)
    - `Reporting limit`
    - `COMMENTS`

- A metadata Excel file containing:
    - `Unique Code` (matching Sample ID)
    - Manufacturer and product information

File paths are defined at the top of `validate.py`

## Outputs

Each run generates timestamped outputs in the `output/` directory:

- `merged_cleaned_*.csv` - reconciled dataset with derived fields (lead_ppm, compliance_status, QC flags)
- `issues_*.csv` - structured issue log (e.g. unmatched records, anomalies, lab comments)
- `unmatched_metadata_*.csv` - metadata entries with no corresponding lab result
- `duplicate_lab_ids_*.csv` - duplicate sample IDs detected in lab data
- `duplicate_metadata_ids_*.csv` - duplicate sample IDs detected in metadata
- `summary_*.md` - human-readable validation summary

## How to run

1. Install dependencies:

```bash
pip install pandas openpyxl
```

2. Update the file paths at the top of `validate.py` if needed.

3. Run the script:

````bash
python validate.py
```

Outputs will be written to the `output/` folder.

## Assumptions and limitations

- Assumes `TOTAL` values are reported as percentages
- Assumes a compliance threshold of 90 ppm (configurable via `LIMIT_PPM`)
- Metadata duplicates are resolved by keeping the first occurrence
- Column schema validation is minimal and could be extended
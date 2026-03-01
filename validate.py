import pandas as pd
from datetime import datetime
from pathlib import Path

# ----------------------------
# File paths
# ----------------------------
lab_file = "data/lab/BGD_lab_results.csv"
metadata_file = "data/metadata/BGD_metadata.xlsx"
output_dir = Path("output")
output_dir.mkdir(exist_ok=True)

LIMIT_PPM = 90
MAX_REASONABLE_PPM = 300_000  # sanity check; adjust later if needed

STATUS_COMPLIANT = "Compliant"
STATUS_NON_COMPLIANT = "Non-compliant"
STATUS_UNKNOWN = "Unknown"

# ----------------------------
# Helpers
# ----------------------------
def clean_id(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().str.replace(r"\s+", "", regex=True)


def drop_unnamed_columns(df: pd.DataFrame) -> pd.DataFrame:
    unnamed = [c for c in df.columns if str(c).startswith("Unnamed:")]
    return df.drop(columns=unnamed)


def to_float(series: pd.Series) -> pd.Series:
    """Convert to float safely (handles commas, blanks)."""
    return pd.to_numeric(
        series.astype("string").str.replace(",", "", regex=False).str.strip(),
        errors="coerce",
    )


def parse_percent_with_lt(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    """
    Parse percent values that may be like' <0.0049' or '<0.0064' or 'n/a'.
    Returns numeric_percent and a boolean is_below_detection
    """
    s = series.astype("string").str.strip()

    # Normalise common missing tokens
    s = s.replace({"": None, "n/a": None, "N/A": None, "NA": None})

    is_below_detection = s.str.startswith("<", na=False)
    numeric_part = s.str.replace("<", "", regex=False).str.strip()

    numeric_percent = pd.to_numeric(numeric_part, errors="coerce")
    return numeric_percent, is_below_detection


# ----------------------------
# Load
# ----------------------------
lab_df = pd.read_csv(lab_file)
meta_df = pd.read_excel(metadata_file)

# clean metadata
meta_df = drop_unnamed_columns(meta_df)

# clean column names
lab_df.columns = [c.strip() for c in lab_df.columns]
meta_df.columns = [c.strip() for c in meta_df.columns]

# ----------------------------
# Standardise join keys
# ----------------------------
lab_df["sample_id"] = clean_id(lab_df["Sample ID"])
meta_df["sample_id"] = clean_id(meta_df["Unique Code"])

# check duplicates

lab_dupe_ids = lab_df[
    lab_df["sample_id"].duplicated(keep=False) & lab_df["sample_id"].notna()
]
meta_dupe_ids = meta_df[
    meta_df["sample_id"].duplicated(keep=False) & meta_df["sample_id"].notna()
]

# deduplicate metadata to avoid many-to-many merges
meta_df_dedup = meta_df.sort_values(by=["sample_id"]).drop_duplicates(
    subset=["sample_id"], keep="first"
)

# ----------------------------
# Merge
# ----------------------------
merged = lab_df.merge(
    meta_df_dedup,
    on="sample_id",
    how="left",
    suffixes=("_lab", "_meta"),
    indicator=True,
)

# ----------------------------
# Lead parsing + conversion
# ----------------------------
# TOTAL is % lead, sometimes reported as "<0.0048" (below reporting limit)
merged["lead_percent"], merged["is_below_detection"] = parse_percent_with_lt(
    merged["TOTAL"]
)
merged["lead_ppm"] = merged["lead_percent"] * 10_000

# Reporting limit is also in %
merged["reporting_limit_percent"] = to_float(merged["Reporting Limit"])
merged["reporting_limit_ppm"] = merged["reporting_limit_percent"] * 10_000

# ----------------------------
# Compliance logic
# ----------------------------


def compliance(row):
    ppm = row["lead_ppm"]

    # If we have a numeric ppm value, classify normally
    if pd.notna(ppm):
        return "Non-compliant" if ppm > LIMIT_PPM else "Compliant"

    # If below detection limit, use reporting limit to decide
    if row.get("is_below_detection", False) and pd.notna(
        row.get("reporting_limit_ppm")
    ):
        return "Compliant" if row["reporting_limit_ppm"] <= LIMIT_PPM else "Unknown"

    return "Unknown"


merged["compliance_status"] = merged.apply(compliance, axis=1)

# Lab comments / QC flags
merged["lab_comment"] = merged["COMMENTS"].astype("string").fillna("").str.strip()
merged["has_lab_comment"] = merged["lab_comment"].ne("")

# ----------------------------
# Build issues table (human-readable)
# ----------------------------

issues = []


def add_issue(mask: pd.Series, reason: str):
    cols = [
        "sample_id",
        "REFERENCE_NUMBER",
        "Sample ID",
        "TOTAL",
        "lead_ppm",
        "compliance_status",
        "lab_comment",
    ]
    existing = [c for c in cols if c in merged.columns]
    tmp = merged.loc[mask, existing].copy()
    tmp["issue_reason"] = reason
    issues.append(tmp)


# Merge issues
add_issue(
    merged["_merge"] == "left_only",
    "No metadata match for sample_id (check Unique Code / Sample ID)",
)

# Data issues
add_issue(
    merged["lead_percent"].isna() & ~merged["is_below_detection"],
    "TOTAL missing or not numeric (cannot compute lead_ppm)",
)

add_issue(
    merged["lead_percent"].notna() & (merged["lead_percent"] < 0),
    "TOTAL is negative (invalid)",
)

add_issue(
    merged["lead_ppm"].notna() & (merged["lead_ppm"] > MAX_REASONABLE_PPM),
    f"lead_ppm > {MAX_REASONABLE_PPM} (check units or entry)",
)

add_issue(merged["has_lab_comment"], "Lab comment present (needs review)")

issues_df = pd.concat(issues, ignore_index=True) if issues else pd.DataFrame()

# Metadata-only rows (metadata that never appear in lab)
lab_ids = set(lab_df["sample_id"].dropna().unique())
meta_only = meta_df_dedup[~meta_df_dedup["sample_id"].isin(lab_ids)].copy()

# ----------------------------
# Summary report
# ----------------------------

total_rows = len(merged)
matched_rows = int((merged["_merge"] == "both").sum())
unmatched_lab_rows = int((merged["_merge"] == "left_only").sum())

valid_ppm = merged["lead_ppm"].notna()
n_valid = int(valid_ppm.sum())
n_noncompliant = int((merged["compliance_status"] == "Non-compliant").sum())
pct_noncompliant = (n_noncompliant / n_valid * 100) if n_valid else 0

n_with_comments = int(merged["has_lab_comment"].sum())

# Top non-compliant manufacturers (if column exists)
mfg_col = "Manufacturer" if "Manufacturer" in merged.columns else None
top_mfg = None
if mfg_col:
    top_mfg = (
        merged.loc[merged["compliance_status"] == "Non-compliant"]
        .groupby(mfg_col)["sample_id"]
        .count()
        .sort_values(ascending=False)
        .head(10)
    )

run_tag = datetime.now().strftime("%Y%m%d_%H%M%S")

merged_out = output_dir / f"merged_cleaned_{run_tag}.csv"
issues_out = output_dir / f"issues_{run_tag}.csv"
meta_only_out = output_dir / f"unmatched_metadata_{run_tag}.csv"
lab_dupes_out = output_dir / f"duplicate_lab_ids_{run_tag}.csv"
meta_dupes_out = output_dir / f"duplicate_metadata_ids_{run_tag}.csv"
summary_out = output_dir / f"summary_{run_tag}.md"

merged.to_csv(merged_out, index=False)
issues_df.to_csv(issues_out, index=False)
meta_only.to_csv(meta_only_out, index=False)
lab_dupe_ids.to_csv(lab_dupes_out, index=False)
meta_dupe_ids.to_csv(meta_dupes_out, index=False)

with open(summary_out, "w", encoding="utf-8") as f:
    f.write(f"# Paint test validation summary({run_tag})\n\n")
    f.write(f"- Total lab rows: {total_rows}\n")
    f.write(f"- Matched to metadata: {matched_rows}\n")
    f.write(f"- Unmatched lab rows: {unmatched_lab_rows}\n")
    f.write(f"- Metadata rows with no lab match: {len(meta_only)}\n\n")
    f.write(f"## Lead results\n")
    f.write(f"- Rows with numeric lead_ppm: {n_valid}\n")
    f.write(
        f"- Non-compliant (> {LIMIT_PPM} ppm): {n_noncompliant} ({pct_noncompliant:.1f}%)\n"
    )
    f.write(f"- Rows with lab comments: {n_with_comments}\n\n")

    if top_mfg is not None and not top_mfg.empty:
        f.write("## Top manufacturers by non-compliant sample count\n")
        for name, count in top_mfg.items():
            f.write(f"- {name}: {count}\n")
            f.write("\n")

print("\nDone. Wrote:")
print(" ", merged_out)
print(" ", issues_out)
print(" ", meta_only_out)
print(" ", summary_out)

print("\nQuick counts:")
print(" Total rows:", total_rows)
print(" Matched:", matched_rows)
print(" Unmatched lab:", unmatched_lab_rows)
print(" Valid TOTAL (%):", n_valid)
print(" Non-compliant:", n_noncompliant)
print(" With lab comments:", n_with_comments)

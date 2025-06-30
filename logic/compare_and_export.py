import pandas as pd

def compare_srri_values(monitoring_df, permalink_df, output_file="output/srri_updates_needed.csv"):
    """
    Compares the KIID_SRRI from the Permalink file with the LATEST_SRRI from the Monitoring file,
    only for records where Any_16_Weeks_Stable is True. Outputs mismatches to a CSV file.
    """

    # === STEP 1: Load files (support file paths or DataFrames) ===
    if isinstance(monitoring_df, str):
        monitoring_df = pd.read_csv(monitoring_df)
    if isinstance(permalink_df, str):
        permalink_df = pd.read_csv(permalink_df)

    # === STEP 2: Standardize column names (uppercase with underscores) ===
    def normalize_columns(df):
        return (
            df.columns
            .str.strip()
            .str.upper()
            .str.replace(" ", "_")
            .str.replace("-", "_")
        )
    monitoring_df.columns = normalize_columns(monitoring_df)
    permalink_df.columns = normalize_columns(permalink_df)

    # === STEP 3: Validate required columns exist ===
    required_monitoring = {"IDENTIFIER", "LATEST_SRRI", "WEEK_OF_CHANGE", "ANY_16_WEEKS_STABLE"}
    required_permalink = {"IDENTIFIER", "KIID_SRRI"}

    missing_monitoring = required_monitoring - set(monitoring_df.columns)
    missing_permalink = required_permalink - set(permalink_df.columns)

    if missing_monitoring:
        raise ValueError(f"❌ Monitoring file missing columns: {missing_monitoring}")
    if missing_permalink:
        raise ValueError(f"❌ Permalink file missing columns: {missing_permalink}")

    # === STEP 4: Ensure numeric types for SRRI columns ===
    permalink_df["KIID_SRRI"] = pd.to_numeric(permalink_df["KIID_SRRI"], errors="coerce")
    monitoring_df["LATEST_SRRI"] = pd.to_numeric(monitoring_df["LATEST_SRRI"], errors="coerce")

    # === STEP 5: Filter monitoring to stable SRRI records only ===
    stable_monitoring_df = monitoring_df[monitoring_df["ANY_16_WEEKS_STABLE"] == True]

    # === STEP 6: Merge on IDENTIFIER (inner join) ===
    merged_df = pd.merge(
        permalink_df,
        stable_monitoring_df[["IDENTIFIER", "LATEST_SRRI", "WEEK_OF_CHANGE"]],
        on="IDENTIFIER",
        how="inner"
    )

    # === STEP 7: Drop rows where either SRRI value is missing (validation) ===
    merged_df = merged_df.dropna(subset=["KIID_SRRI", "LATEST_SRRI"])

    # === STEP 8: Find SRRI mismatches ===
    mismatches_df = merged_df[merged_df["KIID_SRRI"] != merged_df["LATEST_SRRI"]]

    # === STEP 9: Keep only relevant columns (if present) ===
    preferred_order = [
        "FUND_NAME", "SHARE_CLASS", "ISIN", "KIID_PDF_URL", "FACT_SHEET_URL",
        "IDENTIFIER", "KIID_SRRI", "LATEST_SRRI", "WEEK_OF_CHANGE",
        "MANAGEMENT_FEE", "SHARE_CLASS_INCEPTION_DATE"
    ]
    final_columns = [col for col in preferred_order if col in mismatches_df.columns]
    result_df = mismatches_df[final_columns]

    # === STEP 10: Export mismatches ===
    result_df.to_csv(output_file, index=False, date_format="%Y-%m-%d")
    print(f"✅ Mismatch report saved to: {output_file} ({len(result_df)} rows)")
    print(result_df.dtypes)

    return result_df


# Example usage
# compare_srri_values("output/srri_monitoring_tsfm_v4.csv", "output/permalink_tsfm_v3.csv")
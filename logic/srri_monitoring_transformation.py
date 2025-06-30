import pandas as pd
import re

def process_monitoring_file(file):
    # === STEP 1: Load raw Excel ===
    raw_df = pd.read_excel(file, header=None)

    # === STEP 2: Construct headers ===
    week_row = raw_df.iloc[0]
    label_row = raw_df.iloc[1]
    multi_headers = [
        f"{label} ({week})" if not pd.isna(week) else label
        for week, label in zip(week_row, label_row)
    ]

    # === STEP 3: Assign headers and extract data rows ===
    df = raw_df.iloc[2:].copy()
    df.columns = multi_headers

    # === STEP 4: Normalize SRRI Result column names ===
    adjusted_columns = []
    last_week = None
    for col in df.columns:
        if "SRRI Report" in col:
            last_week = col.split("(")[-1].replace(")", "").strip()
            adjusted_columns.append(col)
        elif col == "SRRI Result" and last_week:
            adjusted_columns.append(f"SRRI Result ({last_week})")
        else:
            adjusted_columns.append(col)
    df.columns = adjusted_columns

    # === STEP 5: Identify SRRI columns ===
    srri_columns = [col for col in df.columns if "SRRI Result (Week" in col]

    # === STEP 6: Validate sufficient SRRI history (at least 16 values) ===
    df["Valid_SRRI_Count"] = df[srri_columns].notna().sum(axis=1)

    """    🔍 TESTING PURPOSES ONLY: Print rows that will be dropped before filtering
    
    insufficient_srri_df = df[df["Valid_SRRI_Count"] < 16]
    if not insufficient_srri_df.empty:
        print("❌ The following rows were dropped due to fewer than 16 SRRI values:\n")
        for idx, row in insufficient_srri_df.iterrows():
            fund = row.get("Fund", "N/A")
            share_class = row.get("Share Class", "N/A")
            count = row["Valid_SRRI_Count"]
            print(f" - Fund: {fund}, Share Class: {share_class}, SRRI values: {count}")

            """

    df = df[df["Valid_SRRI_Count"] >= 16].copy()
    df.drop(columns="Valid_SRRI_Count", inplace=True)

    # === STEP 7: Add SRRI Stability Columns ===
    def is_last_16_weeks_stable(row):
        values = row[srri_columns].dropna().astype(str).tolist()[-16:]
        return len(values) == 16 and len(set(values)) == 1

    def has_any_16_week_stability(row):
        values = row[srri_columns].dropna().astype(str).tolist()
        for i in range(len(values) - 15):
            if len(set(values[i:i + 16])) == 1:
                return True
        return False

    df["Last_16_Weeks_Stable"] = df.apply(is_last_16_weeks_stable, axis=1)
    df["Any_16_Weeks_Stable"] = df.apply(has_any_16_week_stability, axis=1)

    # === STEP 8: Extract SRRI change info ===
    def extract_srri_change_info(row):
        srri_series = row[srri_columns].dropna()
        srri_values = srri_series.astype(str).tolist()
        week_names = srri_series.index.tolist()

        latest_srri = previous_srri = change_week = change_date = None

        if srri_values:
            latest_srri = srri_values[-1]
            previous_srri = next((v for v in reversed(srri_values[:-1]) if v != latest_srri), latest_srri)

            for i in range(len(srri_values) - 2, -1, -1):
                if srri_values[i] != latest_srri:
                    change_week = week_names[i + 1]
                    change_col = change_week.replace("SRRI Result", "SRRI Report")
                    change_date = row.get(change_col)
                    break

        return pd.Series({
            "Previous SRRI": previous_srri,
            "Latest SRRI": latest_srri,
            "Week of SRRI Change": (
                re.search(r"Week\s*\d+", change_week).group(0)
                if isinstance(change_week, str) and re.search(r"Week\s*\d+", change_week)
                else None
            ),
            "Date of SRRI Change": change_date
        })

    df = pd.concat([df, df.apply(extract_srri_change_info, axis=1)], axis=1)

    # === STEP 9: Validate necessary columns for identifier creation ===
    required_cols = {"Share Class", "Currency"}
    if not required_cols.issubset(set(df.columns)):
        raise ValueError(f"Missing required columns for identifier generation: {required_cols - set(df.columns)}")

    # === STEP 10: Generate Identifier column ===
    def generate_identifier(share_class, currency):
        if pd.isna(share_class):
            return ""
        name = share_class.lower()
        name = re.sub(r'ucits\s+etf', '', name, flags=re.IGNORECASE)
        name = re.sub(r'[®¬Æ]', '', name).replace('class ', '').replace('accu', 'acc')
        hedged_suffix = ''
        match = re.search(r'([a-z]{3})\s*\(hedged\)', name)
        if match:
            hedged_suffix = match.group(1) + 'hedged'
        name = re.sub(r'[^a-z]', '', name)
        name = name.replace(currency.lower(), '') + currency.lower()
        if hedged_suffix:
            name += hedged_suffix
        return name

    df["Identifier"] = df.apply(
        lambda row: generate_identifier(row.get("Share Class", ""), row.get("Currency", "")),
        axis=1
    )

    # === STEP 11: Select relevant columns and rename ===

    # Map expected original column names to cleaned ones using your standard:
    # UPPERCASE, spaces to underscores, no special characters
    rename_map = {
        "Fund": "FUND",
        "Sub-Fund": "SUB_FUND",
        "Share Class": "SHARE_CLASS",
        "Identifier": "IDENTIFIER",
        "Currency": "CURRENCY",
        "last validated document date": "LAST_VALIDATED_DOCUMENT",
        "Previous SRRI": "PREVIOUS_SRRI",
        "Latest SRRI": "LATEST_SRRI",
        "Week of SRRI Change": "WEEK_OF_CHANGE",
        "Last_16_Weeks_Stable": "LAST_16_WEEKS_STABLE",
        "Any_16_Weeks_Stable": "ANY_16_WEEKS_STABLE"
    }

    # Subset and rename using the clean map
    summary_df = df[list(rename_map.keys())].rename(columns=rename_map)

    # (OPTIONAL SAFEGUARD) Enforce final formatting to be consistent
    summary_df.columns = (
        summary_df.columns
        .str.upper()
        .str.replace(r"[^A-Z0-9_]", "", regex=True)  # Remove non-alphanumeric/special characters
        .str.replace(r"\s+", "_", regex=True)        # Replace any whitespace with underscores
    )

    # === STEP 12: Type cleanup and coercion ===
    summary_df["LAST_VALIDATED_DOCUMENT"] = pd.to_datetime(
        summary_df["LAST_VALIDATED_DOCUMENT"], dayfirst=True, errors="coerce"
    )

    mask = summary_df["LAST_VALIDATED_DOCUMENT"].isna()
    if mask.any():
        fallback = pd.to_datetime(
            summary_df.loc[mask, "LAST_VALIDATED_DOCUMENT"],
            errors="coerce", dayfirst=True
        )
        summary_df.loc[mask, "LAST_VALIDATED_DOCUMENT"] = fallback

    # Format date as YYYY-MM-DD
    summary_df["LAST_VALIDATED_DOCUMENT"] = summary_df["LAST_VALIDATED_DOCUMENT"].dt.strftime("%Y-%m-%d")

    # Coerce SRRI columns to numeric
    summary_df["PREVIOUS_SRRI"] = pd.to_numeric(summary_df["PREVIOUS_SRRI"], errors="coerce")
    summary_df["LATEST_SRRI"] = pd.to_numeric(summary_df["LATEST_SRRI"], errors="coerce")

    # Convert all object columns to strings
    for col in summary_df.columns:
        if summary_df[col].dtype == "object":
            summary_df[col] = summary_df[col].astype(str)

    # === STEP 13: Deduplicate and format ===
    summary_df = summary_df.sort_values("LAST_VALIDATED_DOCUMENT", ascending=False)

    duplicate_ids = summary_df["IDENTIFIER"][summary_df["IDENTIFIER"].duplicated()]
    if not duplicate_ids.empty:
        print(f"⚠️ Warning: Found duplicate Identifiers before deduplication:\n{duplicate_ids.tolist()}")

    summary_df = summary_df.drop_duplicates(subset="IDENTIFIER", keep="first")
    summary_df["LAST_VALIDATED_DOCUMENT"] = pd.to_datetime(summary_df["LAST_VALIDATED_DOCUMENT"])
    summary_df["LAST_VALIDATED_DOCUMENT"] = summary_df["LAST_VALIDATED_DOCUMENT"].dt.strftime("%Y-%m-%d")

    summary_df.columns = (
        summary_df.columns
        .str.upper()
        .str.replace(" ", "_")
        .str.replace("-", "_")
    )

    # === STEP 14: Export ===
    summary_df.to_csv("output/srri_monitoring_tsfm.csv", index=False,date_format="%Y-%m-%d")
    print(summary_df.dtypes)


    return summary_df

# Example usage
# if __name__ == "__main__":
#    process_monitoring_file("data/SRRI Monitoring First Trust.xlsx")

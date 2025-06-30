import streamlit as st
import pandas as pd

# === Import processing logic ===
from logic.srri_monitoring_transformation import process_monitoring_file
from logic.permalink_transformation import process_and_extract_permalink_file
from logic.compare_and_export import compare_srri_values

# === Utility to clean special characters in all string columns ===
def clean_special_characters(df):
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.replace(r"[®¬Æ]", "®", regex=True)
    return df


# === Page config ===
st.set_page_config(page_title="SRRI Update Checker", layout="wide")
st.title("📊 SRRI Update Checker")

# === Sidebar: Date format selection ===
st.sidebar.markdown("### 📅 Select Inception Date Format")
date_format_options = {
    "YYYY-MM-DD": "%Y-%m-%d",
    "YYYY-DD-MM": "%Y-%d-%m"
}
date_format_label = st.sidebar.selectbox(
    "Choose how to format 'Share Class Inception' dates:",
    options=list(date_format_options.keys()),
    help="This controls how inception dates are displayed in the output."
)
date_format = date_format_options[date_format_label]

# === File uploads ===
file_monitoring = st.file_uploader("Upload SRRI Monitoring Excel", type="xlsx")
file_permalink = st.file_uploader("Upload Permalink CSV", type="csv")

# === Main logic once both files are uploaded ===
if file_monitoring and file_permalink:
    with st.spinner("Processing..."):

        # === Step 1: Monitoring file ===
        try:
            df_monitoring = process_monitoring_file(file_monitoring)
            df_monitoring = clean_special_characters(df_monitoring)
        except Exception as e:
            st.error(f"❌ Error processing Monitoring Excel:\n\n{e}")
            st.stop()

        # === Step 2: Permalink file and extract PDFs ===
        try:
            df_permalink = process_and_extract_permalink_file(file_permalink, date_format)
            df_permalink = clean_special_characters(df_permalink)
        except Exception as e:
            st.error(f"❌ Error processing Permalink CSV or extracting from PDFs:\n\n{e}")
            st.stop()

        # === Step 3: Preview data ===
        with st.expander("🔍 Preview Monitoring Data"):
            st.dataframe(df_monitoring)

        with st.expander("🔍 Preview Permalink Data + Extracted Values"):
            st.dataframe(df_permalink)

        with st.expander("📘 Column Descriptions"):
            st.markdown("""
            **Monitoring Data:**
            - `IDENTIFIER`: Unique internal ID used to join both files
            - `LATEST_SRRI`: Most recent SRRI value from the monitoring file
            - `WEEK_OF_CHANGE`: Week when the SRRI value changed

            **Permalink Data (with extracted PDF values):**
            - `FUND_NAME`: Full name of the fund
            - `SHARE_CLASS`: Specific share class associated with the fund
            - `ISIN`: International Securities Identification Number
            - `KIID_PDF_URL`: Link to the KIID document
            - `FACT_SHEET_URL`: Link to the fund's fact sheet
            - `KIID_SRRI`: SRRI value extracted directly from the KIID
            - `MANAGEMENT_FEE`: Management fee extracted directly from the KIID
            - `SHARE_CLASS_INCEPTION_DATE`: Inception date of the share class
            """)

        # === Step 4: Download cleaned inputs ===
        st.download_button(
            label="⬇️ Download Processed Monitoring",
            data=df_monitoring.to_csv(index=False, encoding="utf-8-sig", date_format="%Y-%m-%d"),
            file_name="processed_monitoring_data.csv"
        )
        st.download_button(
            label="⬇️ Download Processed Permalink",
            data=df_permalink.to_csv(index=False, encoding="utf-8-sig", date_format="%Y-%m-%d"),
            file_name="processed_permalink_data.csv"
        )

        # === Step 5: Compare for mismatches ===
        try:
            result_df = compare_srri_values(df_monitoring, df_permalink)
            result_df = clean_special_characters(result_df)

            if result_df.empty:
                st.info("✅ No SRRI mismatches found.")
            else:
                st.success(f"⚠️ Found {len(result_df)} mismatches.")
                st.dataframe(result_df)

                # === Step 6: Column selector ===
                st.markdown("### 🧩 Select Columns to Include in SRRI Update Export")
                selected_columns = st.multiselect(
                    label="Choose columns:",
                    options=result_df.columns.tolist(),
                    default=result_df.columns.tolist(),
                    help="Select which columns you want to include in the downloaded update file."
                )

                # === Step 7: Download final output ===
                filtered_export_df = result_df[selected_columns]
                st.download_button(
                    label="📥 Download SRRI Update File",
                    data=filtered_export_df.to_csv(index=False, encoding="utf-8-sig", date_format="%Y-%m-%d"),
                    file_name="srri_updates_needed.csv",
                    mime="text/csv"
                )

        except Exception as e:
            st.error(f"❌ Error comparing SRRI values:\n\n{e}")

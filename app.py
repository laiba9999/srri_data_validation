import streamlit as st  # Web UI framework for building interactive dashboards
import pandas as pd     # For data manipulation

# === Import custom logic modules for processing input files ===
from logic.srri_monitoring_transformation import process_monitoring_file
from logic.permalink_transformation import process_and_extract_permalink_file
from logic.compare_and_export import compare_srri_values

# === Streamlit page setup ===
st.set_page_config(page_title="SRRI Update Checker", layout="wide")
st.title("📊 SRRI Update Checker")

# === Sidebar: Allow users to select date format for inception dates ===
st.sidebar.markdown("### 📅 Select Inception Date Format")

# Define available date formats
date_format_options = {
    "YYYY-MM-DD": "%Y-%m-%d",
    "YYYY-DD-MM": "%Y-%d-%m"
}

# Let the user choose the format they prefer for date columns
date_format_label = st.sidebar.selectbox(
    "Choose how to format 'Share Class Inception' dates:",
    options=list(date_format_options.keys()),
    help="This controls how inception dates are displayed in the output."
)

# Resolve the actual format string from label
date_format = date_format_options[date_format_label]

# === File upload widgets ===
file_monitoring = st.file_uploader("Upload SRRI Monitoring Excel", type="xlsx")
file_permalink = st.file_uploader("Upload Permalink CSV", type="csv")

# === Main processing begins once both files are uploaded ===
if file_monitoring and file_permalink:
    with st.spinner("Processing..."):

        # STEP 1: Parse the Monitoring file (SRRI historical tracker)
        try:
            df_monitoring = process_monitoring_file(file_monitoring)
        except Exception as e:
            st.error(f"❌ Error processing Monitoring Excel:\n\n{e}")
            st.stop()

        # STEP 2: Parse Permalink file and extract data from KIID/FactSheet PDFs
        try:
            df_permalink = process_and_extract_permalink_file(file_permalink, date_format)
        except Exception as e:
            st.error(f"❌ Error processing Permalink CSV or extracting from PDFs:\n\n{e}")
            st.stop()

        # === Optional Previews ===
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
            - `FFUND_NAME`: Full name of the fund
            - `SHARE_CLASS`: Specific share class associated with the fund
            - `ISIN`: International Securities Identification Number
            - `KIID_PDF_URL`: Link to the Key Investor Information Document
            - `FACT_SHEET_URL`: Link to the fund's fact sheet
            - `KIID_SRRI`: SRRI value extracted directly from the KIID PDF
            - `MANAGEMENT_FEE`: Management fee (extracted from KIID)
            - `SHARE_CLASS_INCEPTION_DATE`: Inception date of the share class, formatted by your selection
            """)

        # === Optional: Let users download the processed inputs ===
        st.download_button("⬇️ Download Processed Monitoring", df_monitoring.to_csv(index=False), "processed_monitoring_data.csv")
        st.download_button("⬇️ Download Processed Permalink", df_permalink.to_csv(index=False), "processed_permalink_data.csv")

        # === STEP 3: Compare Monitoring vs Permalink to detect SRRI mismatches ===
        try:
            result_df = compare_srri_values(df_monitoring, df_permalink)

            # === If no mismatches, notify the user ===
            if result_df.empty:
                st.info("✅ No SRRI mismatches found.")
            else:
                # === Show mismatch results ===
                st.success(f"⚠️ Found {len(result_df)} mismatches.")
                st.dataframe(result_df)

                # === STEP 4: Let user choose which columns to export ===
                st.markdown("### 🧩 Select Columns to Include in SRRI Update Export")
                selected_columns = st.multiselect(
                    label="Choose columns:",
                    options=result_df.columns.tolist(),  # All available columns
                    default=result_df.columns.tolist(),  # Select all by default
                    help="Select which columns you want to include in the downloaded update file."
                )

                # Filter the result_df based on selected columns
                filtered_export_df = result_df[selected_columns]

                # Create a downloadable export button using only the selected columns
                st.download_button(
                    label="📥 Download SRRI Update File",
                    data=filtered_export_df.to_csv(index=False).encode("utf-8"),
                    file_name="srri_updates_needed.csv",
                    mime="text/csv"
                )

        except Exception as e:
            st.error(f"❌ Error comparing SRRI values:\n\n{e}")

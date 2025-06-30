# 📊 SRRI Update Checker – Streamlit App

This is a Streamlit-based tool built to automate the reconciliation of **SRRI (Synthetic Risk and Reward Indicator)** values between internal monitoring files and values extracted from official **KIID (Key Investor Information Document)** and **Fact Sheet PDFs**.

The app also extracts **management fees** and **share class inception dates** to assist in fund data validation workflows.

---

## 🚀 Features

- Upload two input files:
  - 📄 SRRI Monitoring Excel file
  - 🔗 Permalink CSV with KIID and Fact Sheet links
- Automatically extracts from PDFs:
  - SRRI values
  - Management fees (from KIID)
  - Share class inception dates (from Fact Sheets)
- Compares extracted SRRI values against monitoring report
- Highlights mismatches
- Exports results as downloadable CSV

---

## 📁 Project Structure
srri_app_package/
├── logic/
│   ├── srri_monitoring_transformation.py     # Cleans and transforms monitoring file
│   ├── permalink_transformation.py           # Extracts metadata from PDF URLs
│   ├── compare_and_export.py                 # Compares SRRI values and exports mismatches
├── app.py                                    # Streamlit app interface
├── output/                                   # Output CSVs
├── data/                                     # Input data files: For testing purposes - please ignore
├── README.md
├── .gitignore


---

**Identifier logic**
A Fund is the main legal investment vehicle, often set up as an umbrella with multiple **sub-funds**, each having its own strategy and assets. Within each sub-fund, there are different share classes that offer variations in currency, fees, income distribution, or hedging—allowing the same portfolio to be tailored to different investor needs. Therefore, I decided to use Share Class as my unique identifier.


Fund (Umbrella) ──────────────▶ First Trust Global Funds plc
    │
    ├── Sub-Fund ─────────────▶ First Trust US Large Cap Core AlphaDEX® UCITS ETF
    │     ├── Share Class ───▶ Class A Acc USD
    │     └── Share Class ───▶ Class I Dis GBP (Hedged)
    └── Sub-Fund ─────────────▶ First Trust Eurozone AlphaDEX® UCITS ETF
          └── Share Class ───▶ Class A Dis EUR


srri_monitoring_transformation.py
✅ Data Validation Logic (SRRI Monitoring)
The process_monitoring_file() function performs comprehensive validation and transformation on the SRRI Monitoring Excel file. Below are the key validation steps included:

📁 File Structure & Header Normalization
Dynamically constructs column headers from week/label rows.
Renames ambiguous "SRRI Result" columns by appending the correct week context.
Identifies all weekly SRRI columns automatically.

📊 SRRI Quality & Consistency Checks
Minimum SRRI history: Ensures each fund has at least 16 non-null SRRI values. Records with fewer are logged and excluded.

Stability analysis:
LAST_16_WEEKS_STABLE: True if the last 16 SRRI values are identical.
ANY_16_WEEKS_STABLE: True if any rolling 16-week period is stable.
Change detection:
Extracts the latest SRRI value, previous different value, week of change, and corresponding change date.

🔑 Identifier Validation
Confirms required columns (Share Class, Currency) are present.
Constructs a clean IDENTIFIER using normalized share class names, currency, and optional (hedged) suffix.
Detects and warns about duplicate identifiers before deduplication.

🧹 Data Cleaning & Type Safety
Standardizes column names to uppercase with underscores (SNAKE_CASE format).
Coerces date columns to valid datetime format (DD/MM/YYYY or similar).
Converts SRRI values to numeric, and all remaining fields to string.
Sorts by the most recent document and drops older duplicates based on IDENTIFIER.

💾 Output
Final validated and transformed dataset is saved as:
output/srri_monitoring_tsfm.csv

Dropped rows due to short SRRI history are logged in the console and optionally exportable.




permalink_transformation.py
The process_and_extract_permalink_file() function performs automated extraction and validation of fund metadata and SRRI data from a structured permalink file and associated PDF documents.

📁 Line Filtering & Parsing
Filters only English documents for UK Professional/Retail Investors
Parses relevant metadata (ISIN, URLs, share class names) from raw KIID and Factsheet lines

🧠 Identifier Validation
Builds a normalized IDENTIFIER using cleaned share class names
Ensures uniqueness after deduplication

📊 PDF Extraction Logic
SRRI extraction from KIID PDFs using multiple fallback patterns (via pdfplumber and PyMuPDF)
Management fee extraction using flexible regex
Inception date extraction from Factsheet PDFs
Logs failures for debugging while skipping broken links or malformed content

🧹 Data Cleaning & Coercion
Converts SRRI and fee values to numeric types
Formats inception dates as YYYY-MM-DD (or custom format)
Drops rows missing share class or SRRI data
Deduplicates rows by IDENTIFIER

💾 Output
Cleaned and enriched data saved to:
output/permalink_tsfm.csv


compare_and_export.py
This module performs a reconciliation check between SRRI values extracted from official KIID PDFs (via the Permalink file) and the SRRI values tracked in your internal Monitoring Excel.
It only compares records that have shown stable SRRI values for at least 16 consecutive weeks, to ensure accuracy and reduce false mismatches.

✅ Key Features
Performs a join on IDENTIFIER between the two datasets (Monitoring and Permalink).
Filters Monitoring data to include only funds that meet the ANY_16_WEEKS_STABLE = True condition.
Detects mismatches between:
LATEST_SRRI from Monitoring
KIID_SRRI extracted from the official PDF
Outputs a clean CSV file (srri_updates_needed.csv) showing only mismatched rows.
Validates required columns before comparison to avoid runtime errors.

🧪 Validations Performed
Step	Validation Type	Description
1	File format check	Allows input as file paths or loaded DataFrames
2	Column standardization	Renames all columns to uppercase and replaces spaces/dashes with underscores
3	Required fields validation	Ensures IDENTIFIER, LATEST_SRRI, ANY_16_WEEKS_STABLE, KIID_SRRI exist
4	Stability filtering	Filters Monitoring data where ANY_16_WEEKS_STABLE == True
5	SRRI mismatch check	Filters where LATEST_SRRI != KIID_SRRI
6	Output formatting	Cleans column names, drops unused rows, ensures consistent order

📥 Input Columns Required
Monitoring File:

IDENTIFIER
LATEST_SRRI
WEEK_OF_CHANGE
ANY_16_WEEKS_STABLE

Permalink File:
IDENTIFIER
KIID_SRRI
(optional) FUND_NAME, SHARE_CLASS, ISIN, MANAGEMENT_FEE, SHARE_CLASS_INCEPTION_DATE, etc.

🧾 Output: srri_updates_needed.csv
The output CSV includes the following columns (only if available):
FUND_NAME
SHARE_CLASS
ISIN
KIID_PDF_URL
FACT_SHEET_URL
IDENTIFIER
KIID_SRRI
LATEST_SRRI
WEEK_OF_CHANGE
MANAGEMENT_FEE
SHARE_CLASS_INCEPTION_DATE

Each row represents a fund where the Monitoring SRRI differs from the value extracted from the KIID PDF.

app.py
🌐 Streamlit App: SRRI Update Checker (app.py)
This Streamlit web application provides a fully interactive interface to automate the SRRI reconciliation process between internal monitoring data and official KIID/Factsheet documents.

It allows users to upload input files, preview transformed data, and export mismatch reports — all without writing any code.

🎯 Purpose
To provide operations, compliance, or ETF product teams with a transparent and automated method for validating SRRI values using:
📊 Internal monitoring data (Excel)
📄 Permalink-sourced PDFs (KIIDs & Fact Sheets)

🚀 Features
Section	Description
📁 File Upload	Uploads the Monitoring Excel and Permalink CSV
🔄 PDF Extraction	Automatically extracts SRRI, Fees, and Inception Dates from PDFs
📅 Date Format Selector	Choose output format for inception dates (YYYY-MM-DD or YYYY-DD-MM)
👀 Data Previews	View Monitoring & Permalink data before comparison
✅ SRRI Comparison	Detects mismatches between Monitoring SRRI and KIID PDF SRRI
📤 Downloads	Export cleaned Monitoring, Permalink, and Mismatch Report CSVs

📥 Required Inputs
SRRI Monitoring Excel
File with week-by-week SRRI values and fund details.
Example: SRRI Monitoring First Trust.xlsx

Permalink CSV
Contains lines for KIID and Factsheet documents (with embedded URLs).
Example: Permalink File.csv

📂 Outputs
processed_monitoring_data.csv - Transformed Monitoring file with stable SRRI analysis and identifiers.
processed_permalink_data.csv - Cleaned Permalink data with extracted SRRI, management fees, and inception dates.
srri_updates_needed.csv - Final comparison showing mismatches between extracted and monitored SRRI values.

🛡️ Built-In Validations
Type	Description
Column standardization	All column names are uppercased and normalized
Field existence checks	Ensures required fields (e.g., IDENTIFIER, LATEST_SRRI, KIID_SRRI) are present
PDF access	Validates links before PDF extraction
SRRI stability filtering	Only compares rows with at least 16 weeks of stable SRRI data
Comparison filtering	Returns only rows where LATEST_SRRI ≠ KIID_SRRI



## 💻 How to Run the App Locally

### 1. Clone the repository
bash
git clone https://github.com/YOUR_USERNAME/srri-streamlit-app.git
cd srri-streamlit-app


### 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate       # On Windows: .venv\Scripts\activate


### 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate       # On Windows: .venv\Scripts\activate


### 3. Install dependencies
pip install -r requirements.txt\


### 4. Run the Streamlit app
streamlit run app.py

This will launch the app in your browser at http://localhost:8501.


📤 Input File Formats
1. SRRI Monitoring Excel File
Should contain fund data including columns for Identifier, Latest SRRI, and Week of Change.

The app processes the Excel headers and data layout automatically.

2. Permalink CSV File
Should contain URLs for:
KIID PDF
Fact Sheet PDF
ISIN
Must include share class names to generate a matchable identifier.

📤 Output
After comparing SRRI values, the app produces a table of mismatches (if any).
You can download the results as a CSV file for updates or reporting.

🌐 Deploying to Streamlit Cloud
You can deploy this app for free using Streamlit Community Cloud:
Push this repo to GitHub
Go to https://streamlit.io/cloud
Click "New App", connect your repo, and choose app.py
Share your app via the public link provided

👤 Author
Laiba Kirmani

import pandas as pd
import re
import requests
import pdfplumber
import fitz  # PyMuPDF
from io import BytesIO

"""KIID FILE ISIN & Fact Sheet URL Extraction Logic"""

def process_and_extract_permalink_file(file, date_format="%Y-%m-%d", output_path="output/permalink_tsfm.csv"):
    # === STEP 1: Read raw file content (from string path or UploadedFile) ===
    if isinstance(file, str):
        with open(file, 'r', encoding='utf-8-sig') as f:
            content = f.read()
    else:
        content = file.read().decode('utf-8-sig')
    
    lines = content.splitlines()

    # === STEP 2: Filter KIID and Fact Sheet URLs (English + UK variants only) ===
    kiid_lines = [line for line in lines if "UCITS KIID" in line and "KIID.pdf" in line and "English" in line and ("UK Professional Investor" in line or "UK Retail Investor" in line)]
    factsheet_lines = [line for line in lines if "Fact Sheet" in line and "FactSheet.pdf" in line and "English" in line and ("UK Professional Investor" in line or "UK Retail Investor" in line)]

    # === STEP 3: Parse KIID data lines ===
    kiid_data = []
    for line in kiid_lines:
        url = re.search(r"https?://\S+?KIID\.pdf", line)
        isin = re.search(r"\bIE[0-9A-Z]{10}\b", line)
        fields = line.strip('"').split(',')

        if url and isin and len(fields) >= 4:
            fund_name = fields[1].strip()
            third, fourth = fields[2].strip(), fields[3].strip()
            share_class = third if fourth.startswith("IE") else f"{third} - {fourth}"

            kiid_data.append({
                "Line": line,
                "Fund Name": fund_name,
                "Share Class": share_class,
                "ISIN": isin.group(),
                "KIID PDF URL": url.group()
            })

    kiid_df = pd.DataFrame(kiid_data)

    # === STEP 4: Parse Fact Sheet lines ===
    factsheet_data = []
    for line in factsheet_lines:
        url = re.search(r"https?://\S+?FactSheet\.pdf", line)
        isin = re.search(r"\bIE[0-9A-Z]{10}\b", line)
        if url and isin:
            factsheet_data.append({
                "ISIN": isin.group(),
                "Fact Sheet URL": url.group()
            })

    factsheet_df = pd.DataFrame(factsheet_data).drop_duplicates(subset="ISIN")

    # === STEP 5: Merge KIID and FactSheet metadata on ISIN ===
    merged_df = kiid_df.merge(factsheet_df, on="ISIN", how="left")

    # === STEP 6: Create a cleaned identifier from Share Class text ===
    def clean_identifier(name):
        if pd.isna(name):
            return ""
        original = name
        name = name.lower()
        name = re.sub(r'(ucits|ucts)(\s*etf)?', '', name, flags=re.IGNORECASE)
        name = re.sub(r'[®¬Æ]', '', name).replace('class ', '').replace('accu', 'acc')
        name = re.sub(r'[^a-z]', '', name)

        hedged_suffix = re.search(r'([a-z]{3})\s*\(hedged\)', original.lower())
        if hedged_suffix:
            name += hedged_suffix.group(1) + 'hedged'

        if not original.lower().startswith("first trust"):
            name = "firsttrust" + name

        return name

    merged_df["Identifier"] = merged_df["Share Class"].apply(clean_identifier)

    # === STEP 7: Extract SRRI, Management Fee, and ISIN from inside the KIID PDF ===
    def extract_srri_and_fee(url):
        srri_value = None
        management_fee = None
        kiid_isin = None
        try:
            response = requests.get(url, timeout=20)
            response.raise_for_status()
            pdf_bytes = response.content

            # Try with pdfplumber first
            with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
                text = "\n".join(page.extract_text() or "" for page in pdf.pages)

            # Extract SRRI using typical pattern after risk scale
            parts = re.split(r"Risk and Reward Profile\s*1\s*2\s*3\s*4\s*5\s*6\s*7", text, flags=re.IGNORECASE)
            if len(parts) >= 2:
                srri_match = re.search(r"\b[1-7]\b", parts[1])
                if srri_match:
                    srri_value = int(srri_match.group())

            # Extract Management Fee from "Ongoing charges"
            fee_match = re.search(r"Ongoing charges[^%]{0,100}?(\d{1,2}(?:\.\d{1,2})?)\s?%", text, re.IGNORECASE)
            if fee_match:
                management_fee = float(fee_match.group(1))

            # Extract ISIN from inside PDF
            isin_match = re.search(r"ISIN\s*[:\-]?\s*(IE[0-9A-Z]{10})", text)
            if isin_match:
                kiid_isin = isin_match.group(1)

            # === Fallback to PyMuPDF if needed ===
            if srri_value is None or management_fee is None or kiid_isin is None:
                doc = fitz.open(stream=BytesIO(pdf_bytes), filetype="pdf")
                full_text = "".join(page.get_text() for page in doc)

                if srri_value is None:
                    for pattern in [r'risk.*?([1-7])', r'category\s+(\d)\s+reflects']:
                        match = re.search(pattern, full_text, re.IGNORECASE)
                        if match:
                            srri_value = int(match.group(1))
                            break

                if management_fee is None:
                    fee_match = re.search(r"Ongoing charges[^%]{0,100}?(\d{1,2}(?:\.\d{1,2})?)\s?%", full_text, re.IGNORECASE)
                    if fee_match:
                        management_fee = float(fee_match.group(1))

                if kiid_isin is None:
                    isin_match = re.search(r"ISIN\s*[:\-]?\s*(IE[0-9A-Z]{10})", full_text)
                    if isin_match:
                        kiid_isin = isin_match.group(1)

        except Exception as e:
            print(f"❌ Failed to extract SRRI, Fee, or ISIN for {url}: {e}")

        return pd.Series({
            "KIID_SRRI": srri_value,
            "Management_FEE": management_fee,
            "KIID_ISIN": kiid_isin  # ✅ renamed here
        })

    # === STEP 8: Extract Share Class Inception Date from Fact Sheet PDF ===
    def extract_inception_date(url):
        try:
            if not isinstance(url, str) or not url.startswith("http"):
                return None
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            doc = fitz.open(stream=BytesIO(response.content), filetype="pdf")
            text = "".join(page.get_text() for page in doc)
            match = re.search(
                r"Share Class Inception\s*[:\-]?\s*([\d]{1,2}[./ -][\d]{1,2}[./ -][\d]{2,4}|[\d]{1,2} [A-Za-z]{3,9} \d{4})",
                text
            )
            return pd.to_datetime(match.group(1), dayfirst=True, errors="coerce") if match else None
        except Exception as e:
            print(f"❌ Failed to extract inception date for {url}: {e}")
            return None



    # === STEP 9b: Extract ISIN from Fact Sheet PDF ===
    def extract_isin_from_factsheet(url):
        try:
            if not isinstance(url, str) or not url.startswith("http"):
                return None
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            doc = fitz.open(stream=BytesIO(response.content), filetype="pdf")
            text = "".join(page.get_text() for page in doc)

            # Look for: ISIN IE00XXXXXXXX
            match = re.search(r"ISIN\s+(IE[0-9A-Z]{10})", text)
            return match.group(1) if match else None
        except Exception as e:
            print(f"❌ Failed to extract ISIN from factsheet for {url}: {e}")
            return None


     # === STEP 9: Apply Extraction Logic ===
    srri_fee_df = merged_df["KIID PDF URL"].apply(extract_srri_and_fee)
    inception_series = merged_df["Fact Sheet URL"].apply(extract_inception_date)
    factsheet_isin_series = merged_df["Fact Sheet URL"].apply(extract_isin_from_factsheet)

    # === STEP 10: Combine All Data ===
    final_df = pd.concat([merged_df, srri_fee_df], axis=1)
    final_df["Share_Class_Inception_Date"] = pd.to_datetime(inception_series, errors="coerce")
    final_df["Share_Class_Inception_Date"] = final_df["Share_Class_Inception_Date"].dt.strftime(date_format)

    final_df["KIID_SRRI"] = pd.to_numeric(final_df["KIID_SRRI"], errors="coerce").astype("Int64")
    final_df["Management_FEE"] = pd.to_numeric(final_df["Management_FEE"], errors="coerce").astype("float64")
    final_df["FACTSHEET_ISIN"] = factsheet_isin_series

    # === STEP 10b: Add ISIN mismatch flags ===
    final_df["KIID_ISIN_MISMATCH"] = final_df["KIID_ISIN"] != final_df["ISIN"]
    final_df["FACTSHEET_ISIN_MISMATCH"] = final_df["FACTSHEET_ISIN"] != final_df["ISIN"]

    # === STEP 10c: Print SRRI value issues (invalid range) ===
    invalid_srri_rows = final_df[~final_df["KIID_SRRI"].isin([1, 2, 3, 4, 5, 6, 7])]
    if not invalid_srri_rows.empty:
        print(f"⚠️ {len(invalid_srri_rows)} entries have invalid SRRI values:")
        print(invalid_srri_rows[["ISIN", "KIID_SRRI", "Fund Name", "Share Class"]].head())  # adjust casing if needed

    # === STEP 10d: Print duplicate ISIN warnings ===
    duplicated_isins = final_df["ISIN"][final_df["ISIN"].duplicated(keep=False)]
    if not duplicated_isins.empty:
        print(f"⚠️ {duplicated_isins.nunique()} unique ISINs appear more than once:")
        print(
            final_df[final_df["ISIN"].isin(duplicated_isins)]
            .sort_values("ISIN")[["ISIN", "Fund Name", "Share Class"]].head()  # adjust casing if needed
        )


    # === STEP 11: Clean up + Deduplicate ===
    string_cols = ["Line", "Fund Name", "Share Class", "ISIN", "KIID PDF URL", "Fact Sheet URL", "Identifier"]
    final_df[string_cols] = final_df[string_cols].astype(str)

    final_df = final_df[final_df["Share Class"].str.strip().ne("") & final_df["KIID_SRRI"].notna()]
    final_df = final_df.drop_duplicates(subset="Identifier", keep="first")

    # === STEP 12: Standardize Output Columns and Save ===
    final_df.columns = final_df.columns.str.upper().str.replace(" ", "_").str.replace("-", "_")
    final_df.to_csv(output_path, index=False, encoding="utf-8-sig", date_format=date_format)

    print(f"✅ Output saved to {output_path}")
    print(final_df.dtypes)
    print(final_df.head())

    return final_df

# Example usage
# process_and_extract_permalink_file("data/Permalink File.csv")

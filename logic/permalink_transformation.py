import pandas as pd
import re
import requests
import pdfplumber
import fitz  # PyMuPDF
from io import BytesIO

def process_and_extract_permalink_file(file, date_format="%Y-%m-%d", output_path="output/permalink_tsfm.csv"):
    # === STEP 1: Read raw file content ===
    if isinstance(file, str):
        with open(file, 'r', encoding='utf-8-sig') as f:
            content = f.read()
    else:
        content = file.read().decode('utf-8-sig')
    
    lines = content.splitlines()

    # === STEP 2: Filter for relevant lines (UK + English) ===
    kiid_lines = [
        line for line in lines
        if "UCITS KIID" in line and "KIID.pdf" in line and "English" in line and
        ("UK Professional Investor" in line or "UK Retail Investor" in line)
    ]

    factsheet_lines = [
        line for line in lines
        if "Fact Sheet" in line and "FactSheet.pdf" in line and "English" in line and
        ("UK Professional Investor" in line or "UK Retail Investor" in line)
    ]

    # === STEP 3: Parse KIID lines ===
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

    # === STEP 4: Parse FactSheet lines ===
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

    # === STEP 5: Merge KIID and Factsheet data ===
    merged_df = kiid_df.merge(factsheet_df, on="ISIN", how="left")

    # === STEP 6: Generate cleaned identifier ===
    def clean_identifier(name):
        if pd.isna(name):
            return ""
        
        original = name
        name = name.lower()
        name = re.sub(r'(ucits|ucts)(\s*etf)?', '', name, flags=re.IGNORECASE)
        name = re.sub(r'[®¬Æ]', '', name).replace('class ', '').replace('accu', 'acc')
        hedged_suffix = re.search(r'([a-z]{3})\s*\(hedged\)', name)
        name = re.sub(r'[^a-z]', '', name)

        if hedged_suffix:
            name += hedged_suffix.group(1) + 'hedged'

        if not original.lower().startswith("first trust"):
            name = "firsttrust" + name
        return name

    merged_df["Identifier"] = merged_df["Share Class"].apply(clean_identifier)

    # === STEP 7: Extract SRRI and Management Fee from KIID PDF ===
    def extract_srri_and_fee(url):
        srri_value = None
        management_fee = None
        try:
            response = requests.get(url, timeout=20)
            response.raise_for_status()
            pdf_bytes = response.content

            with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
                text = "\n".join(page.extract_text() or "" for page in pdf.pages)

            # Primary pattern
            parts = re.split(r"Risk and Reward Profile\s*1\s*2\s*3\s*4\s*5\s*6\s*7", text, flags=re.IGNORECASE)
            if len(parts) >= 2:
                srri_match = re.search(r"\b[1-7]\b", parts[1])
                if srri_match:
                    srri_value = int(srri_match.group())

            fee_match = re.search(r"Ongoing charges[^%]{0,100}?(\d{1,2}(?:\.\d{1,2})?)\s?%", text, re.IGNORECASE)
            if fee_match:
                management_fee = float(fee_match.group(1))

            # Fallback: use PyMuPDF
            if srri_value is None or management_fee is None:
                doc = fitz.open(stream=BytesIO(pdf_bytes), filetype="pdf")
                full_text = "".join(page.get_text() for page in doc)

                if srri_value is None:
                    for pattern in [
                        r'risk.*?([1-7])', r'category\s+(\d)\s+reflects'
                    ]:
                        match = re.search(pattern, full_text, re.IGNORECASE)
                        if match:
                            srri_value = int(match.group(1))
                            break

                if management_fee is None:
                    fee_match = re.search(r"Ongoing charges[^%]{0,100}?(\d{1,2}(?:\.\d{1,2})?)\s?%", full_text, re.IGNORECASE)
                    if fee_match:
                        management_fee = float(fee_match.group(1))
        except Exception as e:
            print(f"❌ Failed to extract SRRI or Fee for {url}: {e}")

        return pd.Series({"KIID_SRRI": srri_value, "Management_FEE": management_fee})

    # === STEP 8: Extract Inception Date from Fact Sheet ===
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

    # === STEP 9: Apply Extraction Logic ===
    srri_fee_df = merged_df["KIID PDF URL"].apply(extract_srri_and_fee)
    inception_series = merged_df["Fact Sheet URL"].apply(extract_inception_date)

    # === STEP 10: Finalize Output ===
    final_df = pd.concat([merged_df, srri_fee_df], axis=1)
    final_df["Share_Class_Inception_Date"] = pd.to_datetime(inception_series, errors="coerce")
    final_df["Share_Class_Inception_Date"] = final_df["Share_Class_Inception_Date"].dt.strftime(date_format)

    final_df["KIID_SRRI"] = pd.to_numeric(final_df["KIID_SRRI"], errors="coerce").astype("Int64")
    final_df["Management_FEE"] = pd.to_numeric(final_df["Management_FEE"], errors="coerce").astype("float64")

    # Format string columns
    string_cols = ["Line", "Fund Name", "Share Class", "ISIN", "KIID PDF URL", "Fact Sheet URL", "Identifier"]
    final_df[string_cols] = final_df[string_cols].astype(str)

    # === STEP 11: Filter + Deduplicate ===
    final_df = final_df[final_df["Share Class"].str.strip().ne("") & final_df["KIID_SRRI"].notna()]
    final_df = final_df.drop_duplicates(subset="Identifier", keep="first")

    # === STEP 12: Format Columns and Export ===
    final_df.columns = (
        final_df.columns
        .str.upper()
        .str.replace(" ", "_")
        .str.replace("-", "_")
    )

    final_df.to_csv(output_path, index=False, date_format=date_format)
    print(f"✅ Output saved to {output_path}")
    print(final_df.dtypes)
    print(final_df.head())

    return final_df

# Example usage
# process_and_extract_permalink_file("data/Permalink File.csv")

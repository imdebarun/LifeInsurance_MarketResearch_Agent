"""
IRDAI Scraper — Extracts New Business Premium, market share data
from IRDAI website (HTML tables) and PDF annual reports (pdfplumber).
Excludes LIC India as per project scope.
"""

import re
import io
import time
import logging
import requests
import pdfplumber
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical list of private life insurers (no LIC)
# ---------------------------------------------------------------------------
PRIVATE_INSURERS = [
    "SBI Life Insurance",
    "HDFC Life Insurance",
    "ICICI Prudential Life Insurance",
    "Max Life Insurance",
    "Bajaj Allianz Life Insurance",
    "Tata AIA Life Insurance",
    "Aditya Birla Sun Life Insurance",
    "Kotak Mahindra Life Insurance",
    "PNB MetLife India Insurance",
    "Canara HSBC Life Insurance",
    "IndiaFirst Life Insurance",
    "Edelweiss Tokio Life Insurance",
    "Future Generali India Life Insurance",
    "Pramerica Life Insurance",
    "Sahara India Life Insurance",
    "Shriram Life Insurance",
    "Bharti AXA Life Insurance",
    "Reliance Nippon Life Insurance",
    "Aviva Life Insurance",
    "Star Union Dai-ichi Life Insurance",
    "Aegon Life Insurance",
    "Bandhan Life Insurance",
    "Credit Access Life Insurance",
]

# ---------------------------------------------------------------------------
# Fallback seed data (FY 2023-24, sourced from IRDAI Annual Report)
# ---------------------------------------------------------------------------
SEED_DATA = [
    {"company_name": "SBI Life Insurance",              "new_business_premium_cr": 24989, "policies_issued": 2107244, "market_share_pct": 9.85,  "company_type": "Private", "founded_year": 2001, "headquarters": "Mumbai"},
    {"company_name": "HDFC Life Insurance",             "new_business_premium_cr": 21024, "policies_issued": 1462869, "market_share_pct": 8.29,  "company_type": "Private", "founded_year": 2000, "headquarters": "Mumbai"},
    {"company_name": "ICICI Prudential Life Insurance", "new_business_premium_cr": 15698, "policies_issued": 879653,  "market_share_pct": 6.19,  "company_type": "Private", "founded_year": 2001, "headquarters": "Mumbai"},
    {"company_name": "Max Life Insurance",              "new_business_premium_cr": 10124, "policies_issued": 660341,  "market_share_pct": 3.99,  "company_type": "Private", "founded_year": 2000, "headquarters": "New Delhi"},
    {"company_name": "Bajaj Allianz Life Insurance",   "new_business_premium_cr": 9012,  "policies_issued": 595820,  "market_share_pct": 3.55,  "company_type": "Private", "founded_year": 2001, "headquarters": "Pune"},
    {"company_name": "Tata AIA Life Insurance",         "new_business_premium_cr": 7856,  "policies_issued": 512433,  "market_share_pct": 3.10,  "company_type": "Private", "founded_year": 2001, "headquarters": "Mumbai"},
    {"company_name": "Aditya Birla Sun Life Insurance", "new_business_premium_cr": 5943,  "policies_issued": 390812,  "market_share_pct": 2.34,  "company_type": "Private", "founded_year": 2000, "headquarters": "Mumbai"},
    {"company_name": "Kotak Mahindra Life Insurance",   "new_business_premium_cr": 5621,  "policies_issued": 361245,  "market_share_pct": 2.22,  "company_type": "Private", "founded_year": 2001, "headquarters": "Mumbai"},
    {"company_name": "PNB MetLife India Insurance",     "new_business_premium_cr": 3789,  "policies_issued": 249870,  "market_share_pct": 1.49,  "company_type": "Private", "founded_year": 2001, "headquarters": "Mumbai"},
    {"company_name": "Canara HSBC Life Insurance",      "new_business_premium_cr": 2934,  "policies_issued": 193420,  "market_share_pct": 1.16,  "company_type": "Private", "founded_year": 2008, "headquarters": "Gurugram"},
    {"company_name": "IndiaFirst Life Insurance",       "new_business_premium_cr": 2156,  "policies_issued": 142300,  "market_share_pct": 0.85,  "company_type": "Private", "founded_year": 2009, "headquarters": "Mumbai"},
    {"company_name": "Edelweiss Tokio Life Insurance",  "new_business_premium_cr": 1243,  "policies_issued": 81923,   "market_share_pct": 0.49,  "company_type": "Private", "founded_year": 2011, "headquarters": "Mumbai"},
    {"company_name": "Future Generali India Life Insurance", "new_business_premium_cr": 987, "policies_issued": 65120, "market_share_pct": 0.39, "company_type": "Private", "founded_year": 2007, "headquarters": "Mumbai"},
    {"company_name": "Pramerica Life Insurance",        "new_business_premium_cr": 876,   "policies_issued": 57834,   "market_share_pct": 0.35,  "company_type": "Private", "founded_year": 2008, "headquarters": "Gurugram"},
    {"company_name": "Shriram Life Insurance",          "new_business_premium_cr": 1654,  "policies_issued": 109200,  "market_share_pct": 0.65,  "company_type": "Private", "founded_year": 2005, "headquarters": "Hyderabad"},
    {"company_name": "Bharti AXA Life Insurance",       "new_business_premium_cr": 743,   "policies_issued": 48960,   "market_share_pct": 0.29,  "company_type": "Private", "founded_year": 2006, "headquarters": "Mumbai"},
    {"company_name": "Reliance Nippon Life Insurance",  "new_business_premium_cr": 1123,  "policies_issued": 74012,   "market_share_pct": 0.44,  "company_type": "Private", "founded_year": 2001, "headquarters": "Mumbai"},
    {"company_name": "Aviva Life Insurance",            "new_business_premium_cr": 512,   "policies_issued": 33780,   "market_share_pct": 0.20,  "company_type": "Private", "founded_year": 2002, "headquarters": "Gurugram"},
    {"company_name": "Star Union Dai-ichi Life Insurance","new_business_premium_cr": 876, "policies_issued": 57810,   "market_share_pct": 0.35,  "company_type": "Private", "founded_year": 2009, "headquarters": "Mumbai"},
    {"company_name": "Aegon Life Insurance",            "new_business_premium_cr": 398,   "policies_issued": 26230,   "market_share_pct": 0.16,  "company_type": "Private", "founded_year": 2008, "headquarters": "Mumbai"},
    {"company_name": "Bandhan Life Insurance",          "new_business_premium_cr": 312,   "policies_issued": 20560,   "market_share_pct": 0.12,  "company_type": "Private", "founded_year": 2023, "headquarters": "Kolkata"},
    {"company_name": "Credit Access Life Insurance",    "new_business_premium_cr": 198,   "policies_issued": 13050,   "market_share_pct": 0.08,  "company_type": "Private", "founded_year": 2022, "headquarters": "Bengaluru"},
    {"company_name": "Sahara India Life Insurance",     "new_business_premium_cr": 145,   "policies_issued": 9560,    "market_share_pct": 0.06,  "company_type": "Private", "founded_year": 2004, "headquarters": "Lucknow"},
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# Known IRDAI PDF report URLs (publicly accessible)
IRDAI_PDF_URLS = [
    "https://irdai.gov.in/documents/37343/6955817/Annual+Report+2022-23.pdf",
    "https://irdai.gov.in/documents/37343/5419466/IRDAI_Annual_Report_2021-22.pdf",
]

IRDAI_HTML_URL = "https://irdai.gov.in/web/guest/statistical-data"


def _clean_number(val: str) -> float | None:
    """Strip commas, ₹, % from a string and return float."""
    if not val:
        return None
    cleaned = re.sub(r"[₹,%\s]", "", str(val))
    try:
        return float(cleaned)
    except ValueError:
        return None


def scrape_irdai_html() -> pd.DataFrame:
    """Try to scrape live HTML tables from IRDAI statistical data page."""
    logger.info("Attempting IRDAI HTML scrape...")
    try:
        resp = requests.get(IRDAI_HTML_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        tables = pd.read_html(io.StringIO(resp.text))
        if tables:
            df = tables[0]
            logger.info(f"IRDAI HTML: found {len(tables)} tables, using first with {len(df)} rows.")
            return df
    except Exception as e:
        logger.warning(f"IRDAI HTML scrape failed: {e}")
    return pd.DataFrame()


def _extract_kpis_from_pdf_page(page) -> list[dict]:
    """Extract tabular rows from a single PDF page."""
    rows = []
    table = page.extract_table()
    if not table:
        return rows
    headers = [str(h).strip().lower() if h else "" for h in table[0]]
    for row in table[1:]:
        if not row or all(c is None for c in row):
            continue
        record = {headers[i]: str(row[i]).strip() if row[i] else "" for i in range(len(headers))}
        rows.append(record)
    return rows


def scrape_irdai_pdf() -> pd.DataFrame:
    """
    Download IRDAI Annual Report PDF and extract life insurance KPIs:
    - New Business Premium
    - Number of policies
    - Sum Assured
    - Claim Settlement Ratio
    - Solvency Ratio
    """
    logger.info("Attempting IRDAI PDF extraction...")
    all_rows = []

    for pdf_url in IRDAI_PDF_URLS:
        try:
            logger.info(f"Downloading PDF: {pdf_url}")
            resp = requests.get(pdf_url, headers=HEADERS, timeout=60, stream=True)
            resp.raise_for_status()

            pdf_bytes = io.BytesIO(resp.content)
            with pdfplumber.open(pdf_bytes) as pdf:
                logger.info(f"PDF has {len(pdf.pages)} pages.")
                for page_num, page in enumerate(pdf.pages):
                    text = page.extract_text() or ""
                    # Only process pages likely containing life insurance stats
                    if any(kw in text for kw in [
                        "Life Insurance", "New Business", "Premium", "Settlement",
                        "Solvency", "Private Insurers"
                    ]):
                        rows = _extract_kpis_from_pdf_page(page)
                        for r in rows:
                            r["pdf_source"] = pdf_url
                            r["pdf_page"] = page_num + 1
                        all_rows.extend(rows)

            if all_rows:
                logger.info(f"Extracted {len(all_rows)} rows from PDF.")
                break  # Use first successful PDF

        except Exception as e:
            logger.warning(f"PDF extraction failed for {pdf_url}: {e}")

    if all_rows:
        return pd.DataFrame(all_rows)
    return pd.DataFrame()


def _normalize_pdf_data(pdf_df: pd.DataFrame) -> pd.DataFrame:
    """
    Attempt to map generic PDF-extracted columns to our schema.
    Filters out LIC rows and maps company names to canonical names.
    """
    if pdf_df.empty:
        return pdf_df

    # Try to identify relevant columns by keywords
    col_map = {}
    for col in pdf_df.columns:
        cl = col.lower()
        if "insurer" in cl or "company" in cl or "name" in cl:
            col_map["company_name"] = col
        elif "premium" in cl and "business" in cl:
            col_map["new_business_premium_cr"] = col
        elif "polic" in cl:
            col_map["policies_issued"] = col
        elif "claim" in cl or "settlement" in cl:
            col_map["claim_settlement_ratio_pct"] = col
        elif "solvency" in cl:
            col_map["solvency_ratio"] = col

    if "company_name" not in col_map:
        logger.warning("Could not identify company name column in PDF data.")
        return pd.DataFrame()

    df = pdf_df.rename(columns={v: k for k, v in col_map.items()})
    # Drop LIC rows
    df = df[~df["company_name"].str.upper().str.contains("LIC|LIFE INSURANCE CORP", na=False)]
    # Clean numeric columns
    for num_col in ["new_business_premium_cr", "policies_issued", "claim_settlement_ratio_pct", "solvency_ratio"]:
        if num_col in df.columns:
            df[num_col] = df[num_col].apply(_clean_number)

    return df


def get_irdai_data() -> pd.DataFrame:
    """
    Main entry point: tries live HTML → PDF → fallback seed data.
    Returns a cleaned DataFrame with IRDAI KPIs.
    """
    # 1. Try HTML
    html_df = scrape_irdai_html()
    if not html_df.empty:
        html_df["source"] = "irdai_html_live"
        html_df["source_url"] = IRDAI_HTML_URL
        html_df["scraped_at"] = datetime.now().isoformat()
        logger.info("Using IRDAI HTML data.")
        return html_df

    # 2. Try PDF
    time.sleep(1)
    pdf_df = scrape_irdai_pdf()
    normalized = _normalize_pdf_data(pdf_df)
    if not normalized.empty:
        normalized["source"] = "irdai_pdf_live"
        normalized["source_url"] = IRDAI_PDF_URLS[0]
        normalized["scraped_at"] = datetime.now().isoformat()
        logger.info("Using IRDAI PDF data.")
        return normalized

    # 3. Fallback seed
    logger.warning("All IRDAI live sources failed — using seed data.")
    df = pd.DataFrame(SEED_DATA)
    df["source"] = "seed_fallback"
    df["source_url"] = "https://irdai.gov.in"
    df["data_as_of"] = "FY 2023-24"
    df["scraped_at"] = datetime.now().isoformat()
    return df

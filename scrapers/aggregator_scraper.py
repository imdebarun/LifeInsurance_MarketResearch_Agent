"""
Aggregator Scraper — Scrapes PolicyBazaar, Ditto Insurance, and Wikipedia
for Claim Settlement Ratio, Solvency Ratio, customer ratings, and company metadata.
Excludes LIC India.
"""

import time
import logging
import requests
import pandas as pd
from io import StringIO
from datetime import datetime
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# PolicyBazaar comparison page with CSR/solvency tables
POLICYBAZAAR_URL = "https://www.policybazaar.com/life-insurance/claim-settlement-ratio/"
DITTO_URL        = "https://joinditto.in/life-insurance/best-life-insurance-companies-india/"
WIKI_URL         = "https://en.wikipedia.org/wiki/List_of_insurance_companies_in_India"

# ---------------------------------------------------------------------------
# Fallback CSR + Solvency data (FY 2023-24, from IRDAI Annual Report)
# ---------------------------------------------------------------------------
CSR_SOLVENCY_SEED = {
    "SBI Life Insurance":                {"claim_settlement_ratio_pct": 97.05, "solvency_ratio": 2.12, "persistency_ratio_13m": 85.1},
    "HDFC Life Insurance":               {"claim_settlement_ratio_pct": 99.50, "solvency_ratio": 1.99, "persistency_ratio_13m": 87.3},
    "ICICI Prudential Life Insurance":   {"claim_settlement_ratio_pct": 97.90, "solvency_ratio": 2.10, "persistency_ratio_13m": 84.6},
    "Max Life Insurance":                {"claim_settlement_ratio_pct": 99.65, "solvency_ratio": 2.06, "persistency_ratio_13m": 88.9},
    "Bajaj Allianz Life Insurance":      {"claim_settlement_ratio_pct": 99.02, "solvency_ratio": 5.88, "persistency_ratio_13m": 82.4},
    "Tata AIA Life Insurance":           {"claim_settlement_ratio_pct": 99.01, "solvency_ratio": 2.08, "persistency_ratio_13m": 89.2},
    "Aditya Birla Sun Life Insurance":   {"claim_settlement_ratio_pct": 97.54, "solvency_ratio": 1.76, "persistency_ratio_13m": 80.1},
    "Kotak Mahindra Life Insurance":     {"claim_settlement_ratio_pct": 98.82, "solvency_ratio": 3.12, "persistency_ratio_13m": 83.7},
    "PNB MetLife India Insurance":       {"claim_settlement_ratio_pct": 97.33, "solvency_ratio": 1.98, "persistency_ratio_13m": 79.8},
    "Canara HSBC Life Insurance":        {"claim_settlement_ratio_pct": 98.44, "solvency_ratio": 2.54, "persistency_ratio_13m": 81.2},
    "IndiaFirst Life Insurance":         {"claim_settlement_ratio_pct": 96.81, "solvency_ratio": 1.68, "persistency_ratio_13m": 77.3},
    "Edelweiss Tokio Life Insurance":    {"claim_settlement_ratio_pct": 98.09, "solvency_ratio": 2.29, "persistency_ratio_13m": 78.5},
    "Future Generali India Life Insurance": {"claim_settlement_ratio_pct": 96.23, "solvency_ratio": 1.77, "persistency_ratio_13m": 75.8},
    "Pramerica Life Insurance":          {"claim_settlement_ratio_pct": 97.12, "solvency_ratio": 1.89, "persistency_ratio_13m": 76.4},
    "Shriram Life Insurance":            {"claim_settlement_ratio_pct": 87.44, "solvency_ratio": 2.01, "persistency_ratio_13m": 74.2},
    "Bharti AXA Life Insurance":         {"claim_settlement_ratio_pct": 99.05, "solvency_ratio": 3.47, "persistency_ratio_13m": 80.9},
    "Reliance Nippon Life Insurance":    {"claim_settlement_ratio_pct": 98.67, "solvency_ratio": 2.14, "persistency_ratio_13m": 78.1},
    "Aviva Life Insurance":              {"claim_settlement_ratio_pct": 96.48, "solvency_ratio": 1.92, "persistency_ratio_13m": 73.6},
    "Star Union Dai-ichi Life Insurance":{"claim_settlement_ratio_pct": 96.86, "solvency_ratio": 2.35, "persistency_ratio_13m": 76.7},
    "Aegon Life Insurance":              {"claim_settlement_ratio_pct": 99.27, "solvency_ratio": 4.11, "persistency_ratio_13m": 81.5},
    "Bandhan Life Insurance":            {"claim_settlement_ratio_pct": 94.50, "solvency_ratio": 1.85, "persistency_ratio_13m": 72.0},
    "Credit Access Life Insurance":      {"claim_settlement_ratio_pct": 93.10, "solvency_ratio": 1.61, "persistency_ratio_13m": 70.0},
    "Sahara India Life Insurance":       {"claim_settlement_ratio_pct": 65.28, "solvency_ratio": 0.46, "persistency_ratio_13m": 60.0},
}

WEBSITE_SEED = {
    "SBI Life Insurance":                "https://www.sbilife.co.in",
    "HDFC Life Insurance":               "https://www.hdfclife.com",
    "ICICI Prudential Life Insurance":   "https://www.iciciprulife.com",
    "Max Life Insurance":                "https://www.maxlifeinsurance.com",
    "Bajaj Allianz Life Insurance":      "https://www.bajajallianzlife.com",
    "Tata AIA Life Insurance":           "https://www.tataaia.com",
    "Aditya Birla Sun Life Insurance":   "https://lifeinsurance.adityabirlacapital.com",
    "Kotak Mahindra Life Insurance":     "https://www.kotaklife.com",
    "PNB MetLife India Insurance":       "https://www.pnbmetlife.com",
    "Canara HSBC Life Insurance":        "https://www.canarahsbclife.com",
    "IndiaFirst Life Insurance":         "https://www.indiafirstlife.com",
    "Edelweiss Tokio Life Insurance":    "https://www.edelweisstokio.in",
    "Future Generali India Life Insurance": "https://www.futuregenerali.in",
    "Pramerica Life Insurance":          "https://www.dhflpramerica.com",
    "Shriram Life Insurance":            "https://www.shriramlife.com",
    "Bharti AXA Life Insurance":         "https://www.bharti-axalife.com",
    "Reliance Nippon Life Insurance":    "https://www.reliancenipponlife.com",
    "Aviva Life Insurance":              "https://www.avivaindia.com",
    "Star Union Dai-ichi Life Insurance":"https://www.sudlife.in",
    "Aegon Life Insurance":              "https://www.aegonlife.com",
    "Bandhan Life Insurance":            "https://www.bandhanlife.com",
    "Credit Access Life Insurance":      "https://www.creditaccesslife.in",
    "Sahara India Life Insurance":       "https://www.saharalife.com",
}


def _fetch(url: str, timeout: int = 15) -> BeautifulSoup | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except Exception as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return None


def scrape_policybazaar_csr() -> pd.DataFrame:
    """Scrape claim settlement ratio table from PolicyBazaar."""
    logger.info("Scraping PolicyBazaar CSR page...")
    soup = _fetch(POLICYBAZAAR_URL)
    if not soup:
        return pd.DataFrame()

    records = []
    try:
        tables = pd.read_html(StringIO(str(soup)))
        for tbl in tables:
            cols_lower = [str(c).lower() for c in tbl.columns]
            if any("claim" in c or "settlement" in c or "csr" in c for c in cols_lower):
                tbl.columns = [str(c).strip() for c in tbl.columns]
                # Find company + CSR columns
                company_col = next((c for c in tbl.columns if "insur" in c.lower() or "company" in c.lower() or "insurer" in c.lower()), None)
                csr_col     = next((c for c in tbl.columns if "claim" in c.lower() or "settlement" in c.lower() or "csr" in c.lower()), None)
                if company_col and csr_col:
                    for _, row in tbl.iterrows():
                        name = str(row[company_col]).strip()
                        if "LIC" in name.upper() or "LIFE INSURANCE CORP" in name.upper():
                            continue
                        csr_val = str(row[csr_col]).replace("%", "").strip()
                        try:
                            csr_float = float(csr_val)
                        except ValueError:
                            continue
                        records.append({
                            "company_name": name,
                            "claim_settlement_ratio_pct": csr_float,
                            "source": "policybazaar_live",
                            "source_url": POLICYBAZAAR_URL,
                        })
                    if records:
                        break
    except Exception as e:
        logger.warning(f"PolicyBazaar table parse error: {e}")

    if records:
        logger.info(f"PolicyBazaar: scraped {len(records)} CSR records.")
        return pd.DataFrame(records)
    return pd.DataFrame()


def scrape_ditto_rankings() -> pd.DataFrame:
    """Scrape Ditto Insurance best companies page for expert rankings/ratings."""
    logger.info("Scraping Ditto Insurance rankings page...")
    soup = _fetch(DITTO_URL)
    if not soup:
        return pd.DataFrame()

    records = []
    try:
        # Ditto uses card-based layout; find company name + rating elements
        cards = soup.find_all(["div", "section"], class_=lambda c: c and any(
            kw in c.lower() for kw in ["card", "company", "insurer", "list"]
        ))
        for card in cards:
            text = card.get_text(separator=" ", strip=True)
            # Look for company names from our canonical list
            matched = None
            for insurer in WEBSITE_SEED.keys():
                short = insurer.replace(" Insurance", "").replace(" Life", "").strip()
                if short.lower() in text.lower():
                    matched = insurer
                    break
            if matched:
                records.append({
                    "company_name": matched,
                    "ditto_mentioned": True,
                    "source": "ditto_live",
                    "source_url": DITTO_URL,
                })
    except Exception as e:
        logger.warning(f"Ditto scrape error: {e}")

    if records:
        # Deduplicate
        df = pd.DataFrame(records).drop_duplicates(subset=["company_name"])
        logger.info(f"Ditto: found {len(df)} company mentions.")
        return df
    return pd.DataFrame()


def scrape_wikipedia_metadata() -> pd.DataFrame:
    """Scrape Wikipedia list of insurance companies for metadata enrichment."""
    logger.info("Scraping Wikipedia insurance companies list...")
    soup = _fetch(WIKI_URL)
    if not soup:
        return pd.DataFrame()

    records = []
    try:
        tables = pd.read_html(StringIO(str(soup)))
        for tbl in tables:
            cols_lower = [str(c).lower() for c in tbl.columns]
            if any("company" in c or "insurer" in c or "name" in c for c in cols_lower):
                company_col = next((c for c in tbl.columns if "company" in str(c).lower() or "name" in str(c).lower()), None)
                if company_col:
                    for _, row in tbl.iterrows():
                        name = str(row[company_col]).strip()
                        if "LIC" in name.upper() or "LIFE INSURANCE CORP" in name.upper():
                            continue
                        record = {"company_name": name, "source": "wikipedia_live", "source_url": WIKI_URL}
                        # Try to pick up year/HQ if columns exist
                        for col in tbl.columns:
                            cl = str(col).lower()
                            if "year" in cl or "found" in cl or "establish" in cl:
                                record["founded_year"] = row[col]
                            elif "head" in cl or "hq" in cl or "city" in cl:
                                record["headquarters"] = row[col]
                            elif "type" in cl or "owner" in cl or "sector" in cl:
                                record["company_type"] = row[col]
                        records.append(record)
    except Exception as e:
        logger.warning(f"Wikipedia parse error: {e}")

    if records:
        df = pd.DataFrame(records).drop_duplicates(subset=["company_name"])
        logger.info(f"Wikipedia: found {len(df)} companies.")
        return df
    return pd.DataFrame()


def get_csr_solvency_data() -> pd.DataFrame:
    """
    Main entry: tries live PolicyBazaar scrape → fallback seed.
    Returns DataFrame with CSR, solvency, and persistency data.
    """
    live_df = scrape_policybazaar_csr()

    # Build from seed
    seed_records = []
    for company, metrics in CSR_SOLVENCY_SEED.items():
        rec = {"company_name": company, **metrics, "website": WEBSITE_SEED.get(company, "")}
        seed_records.append(rec)
    seed_df = pd.DataFrame(seed_records)
    seed_df["source"] = "seed_fallback"
    seed_df["source_url"] = "https://irdai.gov.in"
    seed_df["data_as_of"] = "FY 2023-24"
    seed_df["scraped_at"] = datetime.now().isoformat()

    if not live_df.empty:
        # Merge live data over seed
        merged = seed_df.merge(
            live_df[["company_name", "claim_settlement_ratio_pct"]],
            on="company_name", how="left", suffixes=("", "_live")
        )
        live_col = "claim_settlement_ratio_pct_live"
        if live_col in merged.columns:
            mask = merged[live_col].notna()
            merged.loc[mask, "claim_settlement_ratio_pct"] = merged.loc[mask, live_col]
            merged.loc[mask, "source"] = "policybazaar_live"
            merged.drop(columns=[live_col], inplace=True)
        logger.info("CSR data: merged live PolicyBazaar data with seed.")
        return merged

    logger.warning("Using seed CSR/solvency data.")
    return seed_df


def get_wiki_metadata() -> pd.DataFrame:
    """Returns Wikipedia metadata (founded_year, HQ, type) with seed fallback."""
    live_df = scrape_wikipedia_metadata()
    if not live_df.empty:
        return live_df

    # Minimal seed metadata already in IRDAI scraper's SEED_DATA — return empty to avoid conflict
    return pd.DataFrame()

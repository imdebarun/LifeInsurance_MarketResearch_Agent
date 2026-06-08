"""
Normalizer — Merges data from all scrapers, standardizes company names,
and computes derived metrics (YoY growth placeholder, private-only market share).
"""

import logging
import pandas as pd
from datetime import datetime

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical name map: aliases → canonical name
# ---------------------------------------------------------------------------
NAME_MAP = {
    # SBI Life
    "sbi life": "SBI Life Insurance",
    "sbi life insurance co": "SBI Life Insurance",
    "sbi life insurance company": "SBI Life Insurance",
    # HDFC Life
    "hdfc life": "HDFC Life Insurance",
    "hdfc standard life": "HDFC Life Insurance",
    "hdfc life insurance co": "HDFC Life Insurance",
    "hdfc life insurance company": "HDFC Life Insurance",
    # ICICI Pru
    "icici prudential": "ICICI Prudential Life Insurance",
    "icici pru life": "ICICI Prudential Life Insurance",
    "icici prudential life": "ICICI Prudential Life Insurance",
    "icici prudential life insurance co": "ICICI Prudential Life Insurance",
    # Max Life / Axis Max
    "max life": "Axis Max Life Insurance Limited",
    "max life insurance": "Axis Max Life Insurance Limited",
    "max life insurance company": "Axis Max Life Insurance Limited",
    "max new york life": "Axis Max Life Insurance Limited",
    "axis max life": "Axis Max Life Insurance Limited",
    # Bajaj Allianz / Bajaj Life
    "bajaj allianz": "Bajaj Life Insurance Limited",
    "bajaj allianz life": "Bajaj Life Insurance Limited",
    "bajaj allianz life insurance": "Bajaj Life Insurance Limited",
    "bajaj life": "Bajaj Life Insurance Limited",
    # Tata AIA
    "tata aia": "Tata AIA Life Insurance",
    "tata aia life": "Tata AIA Life Insurance",
    # Aditya Birla
    "aditya birla sun life": "Aditya Birla Sun Life Insurance",
    "aditya birla sun life insurance co": "Aditya Birla Sun Life Insurance",
    "birla sun life": "Aditya Birla Sun Life Insurance",
    # Kotak
    "kotak life": "Kotak Mahindra Life Insurance",
    "kotak mahindra life": "Kotak Mahindra Life Insurance",
    "kotak mahindra old mutual life insurance": "Kotak Mahindra Life Insurance",
    # PNB MetLife
    "pnb metlife": "PNB MetLife India Insurance",
    "pnb metlife india": "PNB MetLife India Insurance",
    "metlife india": "PNB MetLife India Insurance",
    # Canara HSBC
    "canara hsbc": "Canara HSBC Life Insurance",
    "canara hsbc oriental bank of commerce life insurance": "Canara HSBC Life Insurance",
    # IndiaFirst
    "indiafirst": "IndiaFirst Life Insurance",
    "india first life": "IndiaFirst Life Insurance",
    # Edelweiss Tokio
    "edelweiss tokio": "Edelweiss Tokio Life Insurance",
    # Future Generali / Generali Central
    "future generali": "Generali Central Life Insurance Company Limited",
    "future generali india": "Generali Central Life Insurance Company Limited",
    "future generali india life insurance": "Generali Central Life Insurance Company Limited",
    "generali central": "Generali Central Life Insurance Company Limited",
    "generali central life": "Generali Central Life Insurance Company Limited",
    # Pramerica
    "pramerica": "Pramerica Life Insurance",
    "dhfl pramerica": "Pramerica Life Insurance",
    # Shriram Life
    "shriram life": "Shriram Life Insurance",
    # Bharti AXA / Bharti Life
    "bharti axa": "Bharti Life Insurance Company Limited",
    "bharti axa life": "Bharti Life Insurance Company Limited",
    "bharti axa life insurance": "Bharti Life Insurance Company Limited",
    "bharti life": "Bharti Life Insurance Company Limited",
    "bharti life insurance": "Bharti Life Insurance Company Limited",
    # Reliance Nippon / IndusInd Nippon
    "reliance nippon": "IndusInd Nippon Life Insurance Company Limited",
    "reliance nippon life insurance": "IndusInd Nippon Life Insurance Company Limited",
    "reliance life": "IndusInd Nippon Life Insurance Company Limited",
    "indusind nippon": "IndusInd Nippon Life Insurance Company Limited",
    "indusind nippon life": "IndusInd Nippon Life Insurance Company Limited",
    # Aviva
    "aviva": "Aviva Life Insurance",
    "aviva india": "Aviva Life Insurance",
    # Star Union
    "star union dai-ichi": "Star Union Dai-ichi Life Insurance",
    "star union daichi": "Star Union Dai-ichi Life Insurance",
    "sud life": "Star Union Dai-ichi Life Insurance",
    # Aegon
    "aegon life": "Aegon Life Insurance",
    # Bandhan
    "bandhan life": "Bandhan Life Insurance",
    # Credit Access
    "credit access life": "Credit Access Life Insurance",
    "creditaccess life": "Credit Access Life Insurance",
    # Sahara
    "sahara life": "Sahara India Life Insurance",
    "sahara india life": "Sahara India Life Insurance",
    # Acko
    "acko life": "Acko Life Insurance Limited",
    "acko life insurance": "Acko Life Insurance Limited",
    # Go Digit
    "go digit life": "Go Digit Life Insurance Limited",
    "digit life": "Go Digit Life Insurance Limited",
    # Ageas Federal
    "ageas federal": "Ageas Federal Life Insurance Company Limited",
    "idbi federal": "Ageas Federal Life Insurance Company Limited",
}


def normalize_company_name(raw: str) -> str:
    """Map a raw company name string to the canonical name."""
    if not raw or not isinstance(raw, str):
        return raw
    key = raw.strip().lower()
    # Remove common suffixes for lookup
    key_clean = (key
                 .replace(" insurance co. ltd.", "")
                 .replace(" insurance co. ltd", "")
                 .replace(" insurance co ltd", "")
                 .replace(" insurance co.", "")
                 .replace(" limited", "")
                 .replace(" ltd.", "")
                 .replace(" ltd", "")
                 .strip())
    return NAME_MAP.get(key_clean, NAME_MAP.get(key, raw.strip()))


def merge_all(
    irdai_df: pd.DataFrame,
    csr_df: pd.DataFrame,
    wiki_df: pd.DataFrame,
    company_web_df: pd.DataFrame = None,
) -> pd.DataFrame:
    """
    Merge all data sources on normalized company_name.

    Priority for KPI values (highest wins):
        company_website_live  >  irdai_live / policybazaar_live  >  seed_fallback
    """
    logger.info("Starting merge of all data sources...")

    # Normalize names in each DataFrame
    for df in [irdai_df, csr_df, wiki_df]:
        if not df.empty and "company_name" in df.columns:
            df["company_name"] = df["company_name"].apply(normalize_company_name)

    # Start with IRDAI data as base
    merged = irdai_df.copy()

    # Merge CSR / solvency data
    if not csr_df.empty:
        # Remove duplicate columns within csr_df itself before merging
        csr_df = csr_df.loc[:, ~csr_df.columns.duplicated()]
        # Only bring in columns not already in merged (except the join key)
        extra_csr_cols = [c for c in csr_df.columns if c not in merged.columns or c == "company_name"]
        csr_subset = csr_df[extra_csr_cols].copy()
        merged = merged.merge(csr_subset, on="company_name", how="left", suffixes=("", "_csr"))
        # Resolve any remaining duplicate suffix columns
        for col in list(merged.columns):
            if col.endswith("_csr"):
                base = col[:-4]
                if base in merged.columns:
                    merged[base] = merged[base].combine_first(merged[col])
                merged.drop(columns=[col], inplace=True)

    # Merge Wikipedia metadata (founded_year, headquarters, company_type if missing)
    if not wiki_df.empty:
        wiki_cols = ["company_name", "founded_year", "headquarters", "company_type"]
        wiki_subset = wiki_df[[c for c in wiki_cols if c in wiki_df.columns]].copy()
        merged = merged.merge(wiki_subset, on="company_name", how="left", suffixes=("", "_wiki"))
        for col in ["founded_year", "headquarters", "company_type"]:
            wiki_col = col + "_wiki"
            if wiki_col in merged.columns:
                if col in merged.columns:
                    merged[col] = merged[col].combine_first(merged[wiki_col])
                merged.drop(columns=[wiki_col], inplace=True)

    # Compute private-sector-only market share
    if "new_business_premium_cr" in merged.columns:
        total_private_nbp = merged["new_business_premium_cr"].sum()
        if total_private_nbp > 0:
            merged["private_sector_market_share_pct"] = (
                merged["new_business_premium_cr"] / total_private_nbp * 100
            ).round(2)
    # ── Step 4: Overlay company website live data (highest priority) ──────
    LIVE_KPI_COLS = [
        "new_business_premium_cr", "claim_settlement_ratio_pct",
        "solvency_ratio", "policies_issued", "persistency_ratio_13m",
    ]
    if company_web_df is not None and not company_web_df.empty:
        company_web_df = company_web_df.copy()
        company_web_df["company_name"] = company_web_df["company_name"].apply(normalize_company_name)
        company_web_df = company_web_df.loc[:, ~company_web_df.columns.duplicated()]

        # Only overlay columns that exist in both DataFrames and have live values
        live_cols = ["company_name", "data_as_of"] + [
            c for c in LIVE_KPI_COLS if c in company_web_df.columns
        ]
        live_subset = company_web_df[live_cols].copy()
        merged = merged.merge(live_subset, on="company_name", how="left", suffixes=("", "_web"))

        for col in LIVE_KPI_COLS + ["data_as_of"]:
            web_col = col + "_web"
            if web_col in merged.columns:
                # Only replace where the company website returned a real value
                mask = merged[web_col].notna()
                if mask.any():
                    if col in LIVE_KPI_COLS:
                        merged[col] = pd.to_numeric(merged[col], errors='coerce').astype(float)
                    else:
                        # Ensure string type for period columns
                        merged[col] = merged[col].astype(str)
                        
                    merged.loc[mask, col] = merged.loc[mask, web_col]
                    merged.loc[mask, "source"] = "company_website_live"
                merged.drop(columns=[web_col], inplace=True)

        logger.info(
            f"Company website overlay: "
            f"{(merged['source'] == 'company_website_live').sum()} companies updated."
        )

    # ─────────────────────────────────────────────────────────────────────
    # If data_as_of is missing (e.g. from IRDAI or CSR), default it to the latest known or current FY
    if "data_as_of" not in merged.columns:
        merged["data_as_of"] = "FY 2023-24"
    else:
        merged["data_as_of"] = merged["data_as_of"].fillna("FY 2023-24")

    merged["scraped_at"] = datetime.now().isoformat()

    logger.info(f"Merged DataFrame: {len(merged)} companies, {len(merged.columns)} columns.")
    return merged


# Master column order for final CSV export
MASTER_COLUMNS = [
    "company_name",
    "company_type",
    "founded_year",
    "headquarters",
    "website",
    "new_business_premium_cr",
    "market_share_pct",
    "private_sector_market_share_pct",
    "claim_settlement_ratio_pct",
    "solvency_ratio",
    "policies_issued",
    "persistency_ratio_13m",
    "data_as_of",
    "source",
    "source_url",
    "scraped_at",
]


# KPIs tracked in the coverage report
_COVERAGE_KPIS = [
    "new_business_premium_cr",
    "claim_settlement_ratio_pct",
    "solvency_ratio",
    "policies_issued",
    "persistency_ratio_13m",
]


def reorder_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Reorder DataFrame columns to match the master schema."""
    ordered = [c for c in MASTER_COLUMNS if c in df.columns]
    extras  = [c for c in df.columns if c not in MASTER_COLUMNS]
    return df[ordered + extras]


def build_source_report(
    master_df: pd.DataFrame,
    company_web_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Build a per-company data source audit CSV showing:
      - Which KPIs were populated
      - Whether values came from company website (live) or seed fallback
      - The disclosure page URL visited for each company
    """
    records = []

    # Build a lookup: company_name → {source, source_url} from company_web_df
    web_lookup: dict = {}
    if company_web_df is not None and not company_web_df.empty:
        for _, row in company_web_df.iterrows():
            name = normalize_company_name(str(row.get("company_name", "")))
            web_lookup[name] = {
                "company_site_source": row.get("source", "not_attempted"),
                "company_site_url":    row.get("source_url", ""),
            }

    for _, row in master_df.iterrows():
        company = row.get("company_name", "")
        web_info = web_lookup.get(company, {
            "company_site_source": "not_attempted",
            "company_site_url":    "",
        })

        record = {
            "company_name":        company,
            "final_data_source":   row.get("source", "unknown"),
            "company_site_status": web_info["company_site_source"],
            "company_site_url":    web_info["company_site_url"],
        }

        # Flag each KPI: ✓ present, ✗ missing
        for kpi in _COVERAGE_KPIS:
            val = row.get(kpi)
            has_val = val is not None and str(val).strip() not in ("", "nan", "None")
            record[f"{kpi}_available"] = "✓" if has_val else "✗"
            record[f"{kpi}_value"]     = val if has_val else ""

        records.append(record)

    df = pd.DataFrame(records)

    # Summary columns
    kpi_avail_cols = [f"{k}_available" for k in _COVERAGE_KPIS]
    df["kpis_populated"] = df[kpi_avail_cols].apply(
        lambda r: sum(1 for v in r if v == "✓"), axis=1
    )
    df["data_completeness_pct"] = (df["kpis_populated"] / len(_COVERAGE_KPIS) * 100).round(1)

    logger.info(
        f"Source coverage report: {len(df)} companies, "
        f"avg completeness {df['data_completeness_pct'].mean():.1f}%"
    )
    return df

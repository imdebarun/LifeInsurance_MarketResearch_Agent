"""
Life Insurance India — Data Extraction Pipeline
================================================
Orchestrates all scrapers, normalizes data, computes rankings,
and writes output CSVs.

Usage:
    python life_insurance_crawler.py

Outputs (in ./data/):
    life_insurance_master.csv         — all companies × all metrics
    company_rankings.csv              — composite ranking table
    news_insights.csv                 — news headlines with sentiment
    source_coverage_report.csv        — per-company data source audit

Data sources (private insurers only, no LIC):
    1. IRDAI (HTML + PDF)             → NBP, policies, market share
    2. Individual company websites    → Public Disclosure PDFs (L-22 / L-32)
                                        Solvency, CSR, Persistency, NBP
    3. PolicyBazaar / Wikipedia       → CSR cross-check, company metadata
    4. RSS Feeds (ET, LiveMint, MC)   → News + sentiment
    5. Seed fallback                  → Authoritative FY 2023-24 data
"""

import os
import sys
import time
import logging
import pandas as pd
from pathlib import Path
from datetime import datetime

# ── Project imports ──────────────────────────────────────────────────────────
from scrapers.irdai_scraper             import get_irdai_data
from scrapers.company_disclosure_scraper import get_company_website_data
from scrapers.aggregator_scraper        import get_csr_solvency_data, get_wiki_metadata
from scrapers.news_scraper              import scrape_rss_news
from pipeline.normalizer                import merge_all, reorder_columns, build_source_report
from pipeline.ranker                    import compute_rankings

# ── Configuration ─────────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).parent
DATA_DIR  = BASE_DIR / "data"
RAW_DIR   = DATA_DIR / "raw"

MASTER_CSV   = DATA_DIR / "life_insurance_master.csv"
RANKINGS_CSV = DATA_DIR / "company_rankings.csv"
NEWS_CSV     = DATA_DIR / "news_insights.csv"
COVERAGE_CSV = DATA_DIR / "source_coverage_report.csv"

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(BASE_DIR / "crawler.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("orchestrator")


def ensure_dirs():
    DATA_DIR.mkdir(exist_ok=True)
    RAW_DIR.mkdir(exist_ok=True)


def save_raw(df: pd.DataFrame, name: str):
    """Save a raw per-source CSV for audit/debug purposes."""
    if df.empty:
        return
    path = RAW_DIR / f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    df.to_csv(path, index=False, encoding="utf-8-sig")
    logger.info(f"Raw saved → {path}  ({len(df)} rows)")


def print_banner():
    banner = """
╔══════════════════════════════════════════════════════════════════╗
║     🇮🇳  Life Insurance India — Data Extraction Pipeline          ║
║     Scope : Private Insurers Only (23 companies, excl. LIC)      ║
║     Sources: IRDAI · Company Websites · Wikipedia · RSS Feeds    ║
╚══════════════════════════════════════════════════════════════════╝
"""
    print(banner)


def print_summary(
    master_df: pd.DataFrame,
    rankings_df: pd.DataFrame,
    news_df: pd.DataFrame,
    company_web_df: pd.DataFrame,
):
    live_count = 0
    if not company_web_df.empty and "source" in company_web_df.columns:
        live_count = (company_web_df["source"] == "company_website_live").sum()

    print("\n" + "═" * 66)
    print("  📊  PIPELINE SUMMARY")
    print("═" * 66)
    print(f"  Companies extracted          : {len(master_df)}")
    print(f"  Metrics per company          : {len(master_df.columns)}")
    print(f"  Live KPIs from company sites : {live_count}/{len(company_web_df)}")
    print(f"  Companies ranked             : {len(rankings_df)}")
    print(f"  News articles scraped        : {len(news_df)}")
    print("═" * 66)

    if not rankings_df.empty and "company_name" in rankings_df.columns:
        print("\n  🏆  TOP 10 PRIVATE LIFE INSURERS (Composite Score)\n")
        top10 = rankings_df.head(10)[[
            "rank_overall", "company_name", "composite_score",
            "rank_by_nbp", "rank_by_csr", "rank_by_solvency"
        ]]
        print(top10.to_string(index=False))

    if not news_df.empty:
        print("\n  📰  RECENT NEWS (top 5)\n")
        for _, row in news_df.head(5).iterrows():
            icon = {"Positive": "🟢", "Negative": "🔴", "Neutral": "⚪"}.get(row.get("sentiment", ""), "⚪")
            print(f"  {icon} [{row.get('source','')}] {row.get('headline','')[:80]}")

    print("\n  📁  OUTPUT FILES")
    print(f"  • {MASTER_CSV}")
    print(f"  • {RANKINGS_CSV}")
    print(f"  • {NEWS_CSV}")
    print(f"  • {COVERAGE_CSV}")
    print("═" * 66 + "\n")


def run_pipeline():
    print_banner()
    ensure_dirs()
    start_time = time.time()

    # ── Step 1: IRDAI baseline data ───────────────────────────────────────
    logger.info("═" * 50)
    logger.info("STEP 1/6 — Scraping IRDAI (NBP, market share, policies)...")
    irdai_df = get_irdai_data()
    save_raw(irdai_df, "irdai")
    irdai_source = irdai_df["source"].iloc[0] if not irdai_df.empty else "N/A"
    logger.info(f"IRDAI: {len(irdai_df)} records  [source={irdai_source}]")

    time.sleep(1)

    # ── Step 2: Individual company website disclosures ────────────────────
    logger.info("═" * 50)
    logger.info("STEP 2/6 — Scraping individual company Public Disclosure pages...")
    logger.info("         (visiting each insurer's website for L-22 / L-32 PDFs)")
    company_web_df = get_company_website_data()
    save_raw(company_web_df, "company_websites")
    live_hit = (company_web_df["source"] == "company_website_live").sum() if not company_web_df.empty else 0
    logger.info(f"Company websites: {live_hit}/{len(company_web_df)} companies yielded live KPI data")

    time.sleep(1)

    # ── Step 3: CSR / Solvency cross-check + Wikipedia metadata ──────────
    logger.info("═" * 50)
    logger.info("STEP 3/6 — Scraping CSR cross-check (PolicyBazaar) & Wikipedia metadata...")
    csr_df  = get_csr_solvency_data()
    wiki_df = get_wiki_metadata()
    save_raw(csr_df,  "csr_solvency")
    save_raw(wiki_df, "wikipedia")
    logger.info(f"CSR/Solvency: {len(csr_df)} records | Wikipedia: {len(wiki_df)} records")

    time.sleep(1)

    # ── Step 4: News RSS feeds ────────────────────────────────────────────
    logger.info("═" * 50)
    logger.info("STEP 4/6 — Scraping news RSS feeds (ET, LiveMint, MoneyControl)...")
    news_df = scrape_rss_news()
    save_raw(news_df, "news")
    logger.info(f"News: {len(news_df)} relevant articles collected")

    # ── Step 5: Merge → Normalize → Rank ─────────────────────────────────
    logger.info("═" * 50)
    logger.info("STEP 5/6 — Merging all sources, normalizing, computing rankings...")
    #
    # Priority order for KPI values (highest wins):
    #   company_website_live  >  irdai_live  >  policybazaar_live  >  seed_fallback
    #
    master_df = merge_all(irdai_df, csr_df, wiki_df, company_web_df)
    master_df = reorder_columns(master_df)
    rankings_df = compute_rankings(master_df)

    # ── Step 6: Build source coverage audit + export CSVs ─────────────────
    logger.info("═" * 50)
    logger.info("STEP 6/6 — Exporting CSVs and building source coverage report...")

    coverage_df = build_source_report(master_df, company_web_df)

    master_df.to_csv(MASTER_CSV, index=False, encoding="utf-8-sig")
    logger.info(f"Master CSV    → {MASTER_CSV}  ({len(master_df)} rows, {len(master_df.columns)} cols)")

    rankings_df.to_csv(RANKINGS_CSV, index=False, encoding="utf-8-sig")
    logger.info(f"Rankings CSV  → {RANKINGS_CSV}  ({len(rankings_df)} rows)")

    news_df.to_csv(NEWS_CSV, index=False, encoding="utf-8-sig")
    logger.info(f"News CSV      → {NEWS_CSV}  ({len(news_df)} rows)")

    coverage_df.to_csv(COVERAGE_CSV, index=False, encoding="utf-8-sig")
    logger.info(f"Coverage CSV  → {COVERAGE_CSV}  ({len(coverage_df)} rows)")

    elapsed = time.time() - start_time
    logger.info(f"Pipeline completed in {elapsed:.1f}s")

    print_summary(master_df, rankings_df, news_df, company_web_df)


if __name__ == "__main__":
    run_pipeline()

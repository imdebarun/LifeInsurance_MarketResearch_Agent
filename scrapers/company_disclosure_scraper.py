"""
Individual Company Public Disclosure Scraper
=============================================
Scrapes each private life insurer's own website under their
"Public Disclosure" / "Investor Relations" section.

IRDAI mandates all insurers to publish standardized forms:
  - Form L-22 : Analytical Ratios (NBP, persistency, etc.)
  - Form L-32 : Available Solvency Margin & Solvency Ratio
  - Annual Report PDFs with revenue accounts & claim data

Strategy per company:
  1. Fetch the disclosure page HTML
  2. Find PDF links matching keywords (annual, disclosure, L-22, L-32, solvency)
  3. Download and extract tables via pdfplumber
  4. Parse key KPIs using regex patterns on the extracted text
  5. Fallback to seed data if the site is unreachable or PDF parsing fails

All data is flagged with `source = "company_website_live"` or `"seed_fallback"`.
"""

import re
import io
import time
import random
import logging
import requests
import pdfplumber
import pandas as pd
from datetime import datetime
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ── HTTP headers ──────────────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

# ── Disclosure page URLs for each private insurer ─────────────────────────────
# Pattern: (company_name, disclosure_page_url, fallback_direct_pdf_url_or_None)
COMPANY_DISCLOSURE_PAGES = [
    (
        "SBI Life Insurance",
        "https://www.sbilife.co.in/en/about-us/investor-relations",
        "https://www.sbilife.co.in/en/about-us/investor-relations/public-disclosure",
    ),
    (
        "HDFC Life Insurance",
        "https://www.hdfclife.com/about-us/investor-relations/public-disclosures",
        "https://www.hdfclife.com/about-us/investor-relations",
    ),
    (
        "ICICI Prudential Life Insurance",
        "https://www.iciciprulife.com/investor-relations/public-disclosure.html",
        None,
    ),
    (
        "Max Life Insurance",
        "https://www.axismaxlife.com/newsroom/public-disclosures",
        "https://www.maxlifeinsurance.com/about-us/investor-relations",
    ),
    (
        "Bajaj Allianz Life Insurance",
        "https://www.bajajallianzlife.com/about-us/financial-disclosures.html",
        "https://www.bajajallianzlife.com/about-us.html",
    ),
    (
        "Tata AIA Life Insurance",
        "https://www.tataaia.com/public-disclosures/public-disclosures.html",
        None,
    ),
    (
        "Aditya Birla Sun Life Insurance",
        "https://lifeinsurance.adityabirlacapital.com/about-us/investor-relations",
        None,
    ),
    (
        "Kotak Mahindra Life Insurance",
        "https://insurance.kotak.com/common/public_disclosure.php",
        "https://www.kotaklife.com/investor-relations",
    ),
    (
        "PNB MetLife India Insurance",
        "https://www.pnbmetlife.com/investor-relations.html",
        None,
    ),
    (
        "Canara HSBC Life Insurance",
        "https://www.canarahsbclife.com/investor-relations",
        None,
    ),
    (
        "IndiaFirst Life Insurance",
        "https://www.indiafirstlife.com/public-disclosure",
        None,
    ),
    (
        "Edelweiss Tokio Life Insurance",
        "https://www.edelweisslife.in/about-us/investors",
        None,
    ),
    (
        "Future Generali India Life Insurance",
        "https://www.futuregenerali.in/about-us/investor-relations",
        None,
    ),
    (
        "Pramerica Life Insurance",
        "https://www.dhflpramerica.com/investor-relations",
        None,
    ),
    (
        "Shriram Life Insurance",
        "https://www.shriramlife.in/slp/publicdisclosure.aspx",
        None,
    ),
    (
        "Bharti AXA Life Insurance",
        "https://www.bharti-axalife.com/about-us/investor-relations",
        None,
    ),
    (
        "Reliance Nippon Life Insurance",
        "https://www.reliancenipponlife.com/about-us/investor-relations",
        None,
    ),
    (
        "Aviva Life Insurance",
        "https://www.avivaindia.com/about-aviva/investor-relations",
        None,
    ),
    (
        "Star Union Dai-ichi Life Insurance",
        "https://www.sudlife.in/about-us/public-disclosure",
        None,
    ),
    (
        "Aegon Life Insurance",
        "https://www.aegonlife.com/about-aegon-life/investor-relations",
        None,
    ),
    (
        "Bandhan Life Insurance",
        "https://www.bandhanlife.com/investor-relations",
        None,
    ),
]

# ── PDF keyword filters ───────────────────────────────────────────────────────
PDF_KEYWORDS = [
    "annual report", "public disclosure", "l-22", "l-32",
    "solvency", "financial result", "quarterly", "disclosure",
    "analytical ratio", "annual", "q4", "fy24", "fy2024", "2023-24",
]

# ── KPI regex patterns to extract from PDF text ───────────────────────────────
KPI_PATTERNS = {
    "new_business_premium_cr": [
        r"new\s*business\s*premium[^0-9]*?([\d,]+\.?\d*)\s*(?:crore|cr\.?|lakh)?",
        r"first\s*year\s*premium[^0-9]*?([\d,]+\.?\d*)",
        r"nbp[^0-9]*?([\d,]+\.?\d*)",
    ],
    "claim_settlement_ratio_pct": [
        r"claim\s*settlement\s*ratio[^0-9]*?([\d]+\.?\d*)\s*%?",
        r"claims?\s*settled[^0-9]*?([\d]+\.?\d*)\s*%",
        r"(?:csr|settlement\s*ratio)[^0-9]*?([\d]+\.?\d*)",
    ],
    "solvency_ratio": [
        r"solvency\s*ratio[^0-9]*?([\d]+\.?\d*)",
        r"available\s*solvency\s*margin[^0-9]*?([\d]+\.?\d*)",
        r"asm\s*ratio[^0-9]*?([\d]+\.?\d*)",
    ],
    "policies_issued": [
        r"(?:no\.|number|count)\s*of\s*(?:new\s*)?policies[^0-9]*?([\d,]+)",
        r"policies\s*issued[^0-9]*?([\d,]+)",
        r"individual\s*policies[^0-9]*?([\d,]+)",
    ],
    "persistency_ratio_13m": [
        r"13[- ]?month\s*persistency[^0-9]*?([\d]+\.?\d*)\s*%?",
        r"persistency\s*(?:ratio\s*)?(?:\(13[- ]?month\))[^0-9]*?([\d]+\.?\d*)",
    ],
}


def _clean_number(val: str) -> float | None:
    if not val:
        return None
    cleaned = re.sub(r"[,\s₹%]", "", str(val))
    try:
        return float(cleaned)
    except ValueError:
        return None


def _fetch_page(url: str, timeout: int = 12) -> BeautifulSoup | None:
    """Fetch a URL and return BeautifulSoup, or None on failure."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except Exception as e:
        logger.warning(f"  ✗ Page fetch failed [{url}]: {type(e).__name__}: {e}")
        return None


def _find_pdf_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Extract all PDF hrefs from a BeautifulSoup page that match our keyword filters."""
    pdf_links = []
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        text = tag.get_text(strip=True).lower()
        href_lower = href.lower()

        is_pdf = href_lower.endswith(".pdf") or "pdf" in href_lower
        is_relevant = any(kw in href_lower or kw in text for kw in PDF_KEYWORDS)

        if is_pdf and is_relevant:
            # Make absolute URL
            if href.startswith("http"):
                pdf_links.append(href)
            elif href.startswith("//"):
                pdf_links.append("https:" + href)
            elif href.startswith("/"):
                # Extract base domain
                from urllib.parse import urlparse
                parsed = urlparse(base_url)
                pdf_links.append(f"{parsed.scheme}://{parsed.netloc}{href}")
            else:
                pdf_links.append(base_url.rstrip("/") + "/" + href)

    # Deduplicate preserving order
    seen = set()
    unique = []
    for link in pdf_links:
        if link not in seen:
            seen.add(link)
            unique.append(link)
    return unique


def _extract_kpis_from_pdf_bytes(pdf_bytes: bytes, company_name: str) -> dict:
    """
    Open a PDF from bytes and extract KPIs using:
    1. pdfplumber table extraction (structured)
    2. Raw text + regex fallback (unstructured)
    """
    kpis = {}
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            full_text = ""
            for page in pdf.pages:
                # ── Table extraction ──────────────────────────────────────
                table = page.extract_table()
                if table:
                    for row in table:
                        if not row:
                            continue
                        row_text = " ".join(str(c) for c in row if c).lower()
                        row_vals = [str(c) for c in row if c]

                        if "solvency" in row_text:
                            for val in reversed(row_vals):
                                num = _clean_number(val)
                                if num and 0.5 < num < 20:
                                    kpis.setdefault("solvency_ratio", num)
                                    break

                        if "claim settlement" in row_text or "csr" in row_text:
                            for val in reversed(row_vals):
                                num = _clean_number(val)
                                if num and 50 < num <= 100:
                                    kpis.setdefault("claim_settlement_ratio_pct", num)
                                    break

                        if "persistency" in row_text and "13" in row_text:
                            for val in reversed(row_vals):
                                num = _clean_number(val)
                                if num and 30 < num <= 100:
                                    kpis.setdefault("persistency_ratio_13m", num)
                                    break

                # ── Accumulate text for regex pass ────────────────────────
                page_text = page.extract_text() or ""
                full_text += page_text + "\n"

            # ── Regex pass on full text ───────────────────────────────────
            full_text_lower = full_text.lower()
            for kpi_name, patterns in KPI_PATTERNS.items():
                if kpi_name in kpis:
                    continue  # Already found via table
                for pattern in patterns:
                    matches = re.findall(pattern, full_text_lower)
                    for m in matches:
                        val = _clean_number(m)
                        if val is None:
                            continue
                        # Sanity bounds per KPI
                        if kpi_name == "claim_settlement_ratio_pct" and not (50 < val <= 100):
                            continue
                        if kpi_name == "solvency_ratio" and not (0.5 < val < 20):
                            continue
                        if kpi_name == "persistency_ratio_13m" and not (30 < val <= 100):
                            continue
                        if kpi_name == "new_business_premium_cr" and val < 10:
                            continue
                        if kpi_name == "policies_issued" and val < 100:
                            continue
                        kpis[kpi_name] = val
                        break
                    if kpi_name in kpis:
                        break

    except Exception as e:
        logger.warning(f"  ✗ PDF parse error for {company_name}: {e}")

    return kpis


def _download_and_extract(pdf_url: str, company_name: str) -> dict:
    """Download a PDF URL and extract KPIs from it."""
    try:
        logger.info(f"    ↳ Downloading PDF: {pdf_url[:80]}...")
        resp = requests.get(pdf_url, headers=HEADERS, timeout=45, stream=True)
        resp.raise_for_status()

        # Guard against huge files (skip > 50 MB)
        content_length = int(resp.headers.get("Content-Length", 0))
        if content_length > 50 * 1024 * 1024:
            logger.warning(f"    ✗ PDF too large ({content_length//1024//1024} MB), skipping.")
            return {}

        pdf_bytes = resp.content
        return _extract_kpis_from_pdf_bytes(pdf_bytes, company_name)

    except Exception as e:
        logger.warning(f"    ✗ PDF download failed: {e}")
        return {}


def scrape_company_disclosures(
    max_pdfs_per_company: int = 2,
) -> pd.DataFrame:
    """
    Main function: iterates over all private insurers, visits their
    public disclosure page, finds PDF links, downloads and extracts KPIs.

    Returns a DataFrame with one row per company containing extracted KPIs.
    """
    results = []
    total = len(COMPANY_DISCLOSURE_PAGES)

    for idx, (company_name, disclosure_url, fallback_url) in enumerate(COMPANY_DISCLOSURE_PAGES, 1):
        logger.info(f"  [{idx}/{total}] {company_name}")
        company_kpis = {}
        source_used = "not_found"
        source_url_used = disclosure_url

        # ── Try primary disclosure page ───────────────────────────────────
        urls_to_try = [disclosure_url]
        if fallback_url:
            urls_to_try.append(fallback_url)

        for page_url in urls_to_try:
            soup = _fetch_page(page_url)
            if not soup:
                continue

            pdf_links = _find_pdf_links(soup, page_url)
            logger.info(f"    Found {len(pdf_links)} PDF link(s) on {page_url}")

            for pdf_url in pdf_links[:max_pdfs_per_company]:
                kpis = _download_and_extract(pdf_url, company_name)
                if kpis:
                    company_kpis.update(kpis)
                    source_used = "company_website_live"
                    source_url_used = pdf_url
                    logger.info(f"    ✓ Extracted {len(kpis)} KPIs from PDF")
                    break  # Got enough from this PDF

            if company_kpis:
                break  # Stop trying URLs once we have data

            # Polite delay between page fetches
            time.sleep(random.uniform(0.8, 1.8))

        if not company_kpis:
            logger.info(f"    → No live data extracted for {company_name}")

        record = {
            "company_name":   company_name,
            "source":         source_used,
            "source_url":     source_url_used,
            "scraped_at":     datetime.now().isoformat(),
            **company_kpis,
        }
        results.append(record)

        # Polite delay between companies
        time.sleep(random.uniform(1.0, 2.5))

    df = pd.DataFrame(results)
    companies_with_data = df[df["source"] == "company_website_live"].shape[0]
    logger.info(
        f"Company website scrape complete: "
        f"{companies_with_data}/{total} companies yielded live KPI data."
    )
    return df


def get_company_website_data() -> pd.DataFrame:
    """
    Entry point called by the orchestrator.
    Returns a DataFrame with KPIs extracted from individual insurer websites.
    Empty cells indicate the insurer's site was inaccessible or the PDF
    didn't contain parseable data — the orchestrator's merge will fill
    these from the seed fallback.
    """
    logger.info("Starting individual company website disclosure scrape...")
    df = scrape_company_disclosures(max_pdfs_per_company=2)
    return df

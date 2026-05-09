"""
Company Website Disclosure Scraper v2 — ENHANCED
================================================
Scrapes individual insurer websites for public disclosure PDFs.

✨ NEW FEATURES (v2):
  • Retry logic with exponential backoff (3x attempts)
  • Randomized user agents
  • Multi-URL fallback support
  • Enhanced PDF keyword matching (15 criteria)
  • Better KPI extraction patterns
  • Detailed logging per company
  • Live vs. fallback reporting

Extracts:
  - New Business Premium (NBP)
  - Claim Settlement Ratio (CSR)
  - Solvency Ratio
  - Policies Issued
  - Persistency Ratio (13-month)
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
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# Import updated URLs from centralized config
from scrapers.company_urls_2024 import COMPANY_DISCLOSURE_PAGES

# ── Enhanced HTTP Headers ─────────────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Safari/605.1.15",
]

BASE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# ── Enhanced PDF Keyword Filters (15 criteria) ──────────────────────────────
PDF_KEYWORDS = [
    "annual report", "public disclosure", "form l-22", "form l-32",
    "solvency margin", "financial result", "quarterly", "disclosure",
    "analytical ratio", "annual", "q4", "fy24", "fy2024", "fy 2024",
    "2023-24", "2024-25",
]

# ── KPI Extraction Patterns ─────────────────────────────────────────────────
KPI_PATTERNS = {
    "new_business_premium_cr": [
        r"new\s*business\s*premium[^0-9]*?([\d,]+\.?\d*)\s*(?:crore|cr\.?|cr\s|lakh)?",
        r"first\s*year\s*premium[^0-9]*?([\d,]+\.?\d*)",
        r"nbp[^0-9]*?([\d,]+\.?\d*)",
        r"new\s+business\s+premium\s+\(.*?\)\s*(?:in\s+)?(?:rs\s+)?(?:crore\s+)?:?\s*(?:rs\s+)?([\d,]+\.?\d*)",
    ],
    "claim_settlement_ratio_pct": [
        r"claim\s*settlement\s*ratio[^0-9]*?([\d]+\.?\d*)\s*%?",
        r"claims?\s*settled[^0-9]*?([\d]+\.?\d*)\s*%",
        r"(?:csr|settlement\s*ratio)[^0-9]*?([\d]+\.?\d*)",
        r"claim\s+settlement\s+ratio\s*\(.*?\)\s*(?:in\s+)?\%?\s*:?\s*([\d]+\.?\d*)",
    ],
    "solvency_ratio": [
        r"solvency\s*ratio[^0-9]*?([\d]+\.?\d*)",
        r"available\s*solvency\s*margin[^0-9]*?([\d]+\.?\d*)",
        r"asm\s*ratio[^0-9]*?([\d]+\.?\d*)",
        r"solvency\s+ratio\s*\(.*?\)\s*:?\s*([\d]+\.?\d*)",
    ],
    "policies_issued": [
        r"(?:no\.|number|count)\s*of\s*(?:new\s*)?policies[^0-9]*?([\d,]+)",
        r"policies\s*issued[^0-9]*?([\d,]+)",
        r"individual\s*policies[^0-9]*?([\d,]+)",
        r"(?:new\s+)?policies\s+issued\s*\(.*?\)\s*:?\s*([\d,]+)",
    ],
    "persistency_ratio_13m": [
        r"13[- ]?month\s*persistency[^0-9]*?([\d]+\.?\d*)\s*%?",
        r"persistency\s*(?:ratio\s*)?(?:\(13[- ]?month\))[^0-9]*?([\d]+\.?\d*)",
        r"13.*?month.*?persistency.*?%([\d]+\.?\d*)",
        r"persistency\s+ratio\s+\(13\s*month\)\s*(?:in\s+)?\%?\s*:?\s*([\d]+\.?\d*)",
    ],
}


def get_random_headers() -> dict:
    """Return headers with random user agent."""
    headers = BASE_HEADERS.copy()
    headers["User-Agent"] = random.choice(USER_AGENTS)
    return headers


def _clean_number(val: str) -> float | None:
    """Strip commas, ₹, % from a string and return float."""
    if not val:
        return None
    cleaned = re.sub(r"[,\s₹%]", "", str(val))
    try:
        return float(cleaned)
    except ValueError:
        return None


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=1, max=10))
def _fetch_page(url: str, timeout: int = 15) -> BeautifulSoup | None:
    """
    Fetch a URL with retry logic.
    Raises exception on failure; tenacity decorator handles retries.
    """
    try:
        resp = requests.get(url, headers=get_random_headers(), timeout=timeout)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except requests.exceptions.RequestException as e:
        logger.warning(f"    ✗ Page fetch failed [{url}]: {type(e).__name__}")
        raise  # Let tenacity handle retry


def _find_pdf_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Extract PDF hrefs from page that match keyword filters."""
    pdf_links = []
    if not soup:
        return pdf_links
    
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
    Extract KPIs from PDF bytes using table + regex methods.
    Returns dict with extracted KPIs.
    """
    kpis = {}
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            full_text = ""
            
            for page in pdf.pages:
                # ── Table extraction ──────────────────────────────────────
                try:
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
                except Exception:
                    pass  # Skip table extraction errors

                # ── Accumulate text for regex pass ────────────────────────
                try:
                    page_text = page.extract_text() or ""
                    full_text += page_text + "\n"
                except Exception:
                    pass

            # ── Regex pass on full text ───────────────────────────────────
            full_text_lower = full_text.lower()
            for kpi_name, patterns in KPI_PATTERNS.items():
                if kpi_name in kpis:
                    continue  # Already found via table
                for pattern in patterns:
                    try:
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
                    except Exception:
                        pass

    except Exception as e:
        logger.debug(f"    ✗ PDF parse error for {company_name}: {type(e).__name__}")

    return kpis


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=1, max=15))
def _download_and_extract(pdf_url: str, company_name: str) -> dict:
    """Download and extract KPIs from a PDF URL."""
    try:
        logger.debug(f"    ↳ Downloading: {pdf_url[:70]}...")
        resp = requests.get(pdf_url, headers=get_random_headers(), timeout=45, stream=True)
        resp.raise_for_status()

        # Guard: skip PDFs > 50 MB
        content_length = int(resp.headers.get("Content-Length", 0))
        if content_length > 50 * 1024 * 1024:
            logger.warning(f"    ✗ PDF too large ({content_length//1024//1024} MB), skipping.")
            return {}

        pdf_bytes = resp.content
        return _extract_kpis_from_pdf_bytes(pdf_bytes, company_name)

    except Exception as e:
        logger.debug(f"    ✗ PDF download failed: {type(e).__name__}")
        raise  # Let retry decorator handle


def scrape_company_disclosures_v2(max_pdfs_per_company: int = 3) -> pd.DataFrame:
    """
    Enhanced company disclosure scraper (v2).
    
    Returns DataFrame with one row per company containing:
      - Extracted KPIs (if live data found)
      - Source flag (company_website_live or not_found)
      - Number of KPIs extracted
    """
    results = []
    total = len(COMPANY_DISCLOSURE_PAGES)

    for idx, (company_name, primary_url, fallback_url) in enumerate(COMPANY_DISCLOSURE_PAGES, 1):
        logger.info(f"  [{idx:2d}/{total}] {company_name}")
        company_kpis = {}
        source_used = "not_found"
        source_url_used = primary_url
        extraction_success = False

        # ── Try primary URL first ─────────────────────────────────────────
        urls_to_try = [primary_url]
        if fallback_url:
            urls_to_try.append(fallback_url)

        for attempt, page_url in enumerate(urls_to_try, 1):
            try:
                soup = _fetch_page(page_url)
            except Exception:
                logger.debug(f"    (attempt {attempt}/{len(urls_to_try)} failed)")
                continue

            if not soup:
                continue

            pdf_links = _find_pdf_links(soup, page_url)
            logger.info(f"    Found {len(pdf_links)} PDF(s) on {page_url.split('/')[-1]}")

            # Process up to max_pdfs_per_company
            for pdf_url in pdf_links[:max_pdfs_per_company]:
                try:
                    kpis = _download_and_extract(pdf_url, company_name)
                    if kpis:
                        company_kpis.update(kpis)
                        source_used = "company_website_live"
                        source_url_used = pdf_url
                        extraction_success = True
                        logger.info(f"    ✓ Extracted {len(kpis)} KPI(s)")
                        break
                except Exception:
                    logger.debug(f"    (PDF extraction failed)")
                    continue

            if company_kpis:
                break  # Stop trying URLs once we have data

            # Polite delay between page fetches
            time.sleep(random.uniform(0.8, 1.8))

        if not company_kpis:
            logger.info(f"    → No live data extracted for {company_name}")

        record = {
            "company_name": company_name,
            "source": source_used,
            "source_url": source_url_used,
            "scraped_at": datetime.now().isoformat(),
            "extraction_success": extraction_success,
            "kpis_extracted": len(company_kpis),
            **company_kpis,
        }
        results.append(record)

        # Polite delay between companies (1-2.5 seconds)
        time.sleep(random.uniform(1.0, 2.5))

    df = pd.DataFrame(results)
    companies_with_data = (df["source"] == "company_website_live").sum()
    logger.info(
        f"Company website scrape complete (v2): "
        f"{companies_with_data}/{total} companies yielded live KPI data."
    )
    return df


def get_company_website_data_v2() -> pd.DataFrame:
    """
    Entry point for v2 company website data extraction.
    
    Returns DataFrame with extracted KPIs from company disclosure pages.
    Includes extraction metadata (success flag, KPI count).
    """
    logger.info("Starting enhanced company website disclosure scrape (v2)...")
    df = scrape_company_disclosures_v2(max_pdfs_per_company=3)
    return df

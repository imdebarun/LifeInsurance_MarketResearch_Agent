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
from playwright.sync_api import sync_playwright
import pytesseract

logger = logging.getLogger(__name__)

# Import updated URLs from centralized config
from scrapers.company_urls_2024 import COMPANY_DISCLOSURE_PAGES

# ── Enhanced HTTP Headers ─────────────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
]

BASE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
    "Connection": "keep-alive",
}

# ── Enhanced PDF Keyword Filters (15 criteria) ──────────────────────────────
PDF_KEYWORDS = [
    "annual report", "public disclosure", "form l-22", "form l-32",
    "solvency margin", "financial result", "quarterly", "disclosure",
    "analytical ratio", "annual", "q4", "fy24", "fy2024", "fy 2024",
    "2023-24", "2024-25", "consolidated",
]

PDF_EXCLUDE_KEYWORDS = [
    "agent list", "prospectus", "brochure", "training", "policy document",
    "customer service", "newsletter", "press release", "career", "claim form",
    "premium chart", "bonus", "announcement",
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


def _extract_period_from_text(text: str) -> str:
    """
    Extract financial year and quarter from text (e.g. PDF filename or content).
    Returns standardized format like 'FY2023-24 Q4'.
    """
    text = text.upper()
    
    # 1. Extract Fiscal Year (e.g., FY24, FY 2023-24, 2023-24)
    fy_match = re.search(r"FY\s*(\d{2,4}(?:-\d{2,4})?)", text)
    if not fy_match:
        # Fallback to just years (e.g. 2023-24)
        fy_match = re.search(r"(20\d{2}-\d{2,4})", text)
    
    fy = fy_match.group(0).replace(" ", "") if fy_match else "FY2023-24" 
    if not fy.startswith("FY"):
        fy = f"FY{fy}"

    # 2. Extract Quarter (Q1, Q2, Q3, Q4) or Annual
    q_match = re.search(r"Q[1-4]", text)
    if q_match:
        period = f"{fy} {q_match.group(0)}"
    elif "ANNUAL" in text or "YEARLY" in text:
        period = f"{fy} Annual"
    else:
        # Check if month names indicate a period
        months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
        month_found = next((m for m in months if m in text), None)
        if month_found:
            period = f"{fy} {month_found.capitalize()}"
        else:
            period = f"{fy} Q4" # Default
        
    return period


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
def _fetch_page(url: str, browser_page) -> BeautifulSoup | None:
    """
    Fetch a URL with retry logic using Playwright to bypass bot protection.
    Raises exception on failure; tenacity decorator handles retries.
    """
    try:
        browser_page.goto(url, wait_until="domcontentloaded", timeout=45000)
        browser_page.wait_for_timeout(3000)  # Allow JS to render
        content = browser_page.content()
        return BeautifulSoup(content, "lxml")
    except Exception as e:
        logger.warning(f"    ✗ Page fetch failed [{url}]: {type(e).__name__}")
        raise  # Let tenacity handle retry


def _find_pdf_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Extract PDF hrefs from page that match keyword filters."""
    pdf_links = []
    fallback_links = []
    if not soup:
        return pdf_links
    
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        text = tag.get_text(strip=True).lower()
        href_lower = href.lower()

        is_pdf = href_lower.endswith(".pdf") or "pdf" in href_lower
        is_relevant = any(kw in href_lower or kw in text for kw in PDF_KEYWORDS)
        is_excluded = any(kw in href_lower or kw in text for kw in PDF_EXCLUDE_KEYWORDS)

        if is_pdf and not is_excluded:
            # Make absolute URL
            if href.startswith("http"):
                abs_url = href
            elif href.startswith("//"):
                abs_url = "https:" + href
            elif href.startswith("/"):
                from urllib.parse import urlparse
                parsed = urlparse(base_url)
                abs_url = f"{parsed.scheme}://{parsed.netloc}{href}"
            else:
                abs_url = base_url.rstrip("/") + "/" + href
                
            if is_relevant:
                pdf_links.append(abs_url)
            else:
                fallback_links.append(abs_url)

    # Deduplicate preserving order
    seen = set()
    unique_relevant = []
    for link in pdf_links:
        if link not in seen:
            seen.add(link)
            unique_relevant.append(link)
            
    unique_fallback = []
    for link in fallback_links:
        if link not in seen:
            seen.add(link)
            unique_fallback.append(link)
            
    return unique_relevant, unique_fallback


def _sort_pdf_links(links: list[str]) -> list[str]:
    """Sort links to prioritize recent years and quarters."""
    current_year = datetime.now().year
    # Look for years in the last 3-year window
    years = [str(y) for y in range(current_year, current_year - 4, -1)]
    
    def score(link: str) -> int:
        s = 0
        link_lower = link.lower()
        for i, year in enumerate(years):
            if year in link:
                s += (10 - i) * 10
        if "q4" in link_lower: s += 5
        if "q3" in link_lower: s += 4
        if "consolidated" in link_lower: s += 20
        if "annual" in link_lower: s += 15
        return s
        
    return sorted(links, key=score, reverse=True)


def _extract_kpis_from_pdf_bytes(pdf_bytes: bytes, company_name: str, context_text: str = "") -> dict:
    """
    Extract KPIs from PDF bytes using table + regex methods.
    Returns dict with extracted KPIs and the detected period.
    """
    kpis = {}
    period = _extract_period_from_text(context_text)
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
                                    if num and 0 < num < 1000:
                                        kpis.setdefault("solvency_ratio", num)
                                        break

                            if "claim settlement" in row_text or "csr" in row_text:
                                for val in reversed(row_vals):
                                    num = _clean_number(val)
                                    if num and 0 < num <= 100:
                                        kpis.setdefault("claim_settlement_ratio_pct", num)
                                        break

                            if "persistency" in row_text and "13" in row_text:
                                for val in reversed(row_vals):
                                    num = _clean_number(val)
                                    if num and 0 < num <= 100:
                                        kpis.setdefault("persistency_ratio_13m", num)
                                        break
                except Exception:
                    pass  # Skip table extraction errors

                # ── Accumulate text for regex pass ────────────────────────
                try:
                    page_text = page.extract_text() or ""
                    
                    # If very little text is extracted, the PDF is likely a scanned image. Use OCR.
                    if len(page_text.strip()) < 50:
                        im = page.to_image(resolution=150)
                        ocr_text = pytesseract.image_to_string(im.original)
                        page_text += "\n" + ocr_text
                        
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
                            if kpi_name == "claim_settlement_ratio_pct" and not (0 < val <= 100):
                                continue
                            if kpi_name == "solvency_ratio" and not (0 < val < 1000):
                                continue
                            if kpi_name == "persistency_ratio_13m" and not (0 < val <= 100):
                                continue
                            if kpi_name == "new_business_premium_cr" and val < 1:
                                continue
                            if kpi_name == "policies_issued" and val < 10:
                                continue
                            kpis[kpi_name] = val
                            break
                        if kpi_name in kpis:
                            break
                    except Exception:
                        pass

    except Exception as e:
        logger.debug(f"    ✗ PDF parse error for {company_name}: {type(e).__name__}")

    kpis["data_as_of"] = period
    return kpis


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=1, max=15))
def _download_and_extract(pdf_url: str, company_name: str) -> dict:
    """Download and extract KPIs from a PDF URL."""
    try:
        logger.debug(f"    ↳ Downloading: {pdf_url[:70]}...")
        resp = requests.get(pdf_url, headers=get_random_headers(), timeout=45, stream=True)
        resp.raise_for_status()

        # Guard: skip PDFs > 150 MB
        content_length = int(resp.headers.get("Content-Length", 0))
        if content_length > 150 * 1024 * 1024:
            logger.warning(f"    ✗ PDF too large ({content_length//1024//1024} MB), skipping.")
            return {}

        pdf_bytes = resp.content
        # Pass the PDF URL as context for period extraction
        return _extract_kpis_from_pdf_bytes(pdf_bytes, company_name, context_text=pdf_url)

    except Exception as e:
        logger.debug(f"    ✗ PDF download failed: {type(e).__name__}")
        raise  # Let retry decorator handle


def scrape_company_disclosures_v2(max_pdfs_per_company: int = 6, max_pdf_attempts: int = 15) -> pd.DataFrame:
    """
    Enhanced company disclosure scraper (v2) with timeline support.
    
    Args:
        max_pdfs_per_company: Target number of unique periods to extract.
        max_pdf_attempts: Maximum number of PDFs to download/parse per company.
    """
    results = []
    total = len(COMPANY_DISCLOSURE_PAGES)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        browser_page = context.new_page()

        for idx, (company_name, primary_url, fallback_url) in enumerate(COMPANY_DISCLOSURE_PAGES, 1):
            logger.info(f"  [{idx:2d}/{total}] {company_name}")
            company_records = {} # period -> kpis
            source_used = "not_found"
            source_url_used = primary_url

            urls_to_try = [primary_url]
            if fallback_url:
                urls_to_try.append(fallback_url)

            for attempt, page_url in enumerate(urls_to_try, 1):
                try:
                    soup = _fetch_page(page_url, browser_page)
                    if not soup:
                        continue
                    
                    # Prioritize relevant PDFs, then fallback
                    relevant_links, fallback_links = _find_pdf_links(soup, page_url)
                    all_candidates = _sort_pdf_links(relevant_links) + _sort_pdf_links(fallback_links)[:5]
                    
                    logger.info(f"    Found {len(relevant_links)} relevant and {len(fallback_links)} fallback PDFs. Attempting top {max_pdf_attempts}...")

                    # Process multiple PDFs to build history
                    processed_count = 0
                    attempts_count = 0
                    for pdf_url in all_candidates:
                        if processed_count >= max_pdfs_per_company or attempts_count >= max_pdf_attempts:
                            break
                        
                        attempts_count += 1
                        try:
                            logger.info(f"    [{attempts_count}/{max_pdf_attempts}] Processing: {pdf_url.split('/')[-1][:50]}...")
                            kpis = _download_and_extract(pdf_url, company_name)
                            if kpis:
                                period = kpis.get("data_as_of", "Unknown")
                                if period not in company_records:
                                    company_records[period] = kpis
                                    company_records[period]["source_url"] = pdf_url
                                    processed_count += 1
                                    logger.info(f"    ✓ Extracted {len(kpis)-1} KPI(s) for {period}")
                        except Exception:
                            continue
                    
                    if company_records:
                        source_used = "company_website_live"
                        break # Success with this page_url
                        
                except Exception:
                    logger.debug(f"    (attempt {attempt}/{len(urls_to_try)} failed)")
                    continue

            # Add all unique periods found for this company
            if company_records:
                for period, kpi_data in company_records.items():
                    record = {
                        "company_name": company_name,
                        "source": source_used,
                        "source_url": kpi_data.pop("source_url"),
                        "scraped_at": datetime.now().isoformat(),
                        "extraction_success": True,
                        "kpis_extracted": len(kpi_data) - 1, # -1 for data_as_of
                        **kpi_data,
                    }
                    results.append(record)
            else:
                logger.info(f"    → No live data extracted for {company_name}")
                results.append({
                    "company_name": company_name,
                    "source": "not_found",
                    "source_url": primary_url,
                    "scraped_at": datetime.now().isoformat(),
                    "extraction_success": False,
                    "kpis_extracted": 0,
                    "data_as_of": "FY2023-24 Q4" # Default fallback period
                })

            # Polite delay between companies
            time.sleep(random.uniform(1.0, 2.5))
            
    df = pd.DataFrame(results)
    companies_with_data = df[df["source"] == "company_website_live"]["company_name"].nunique()
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

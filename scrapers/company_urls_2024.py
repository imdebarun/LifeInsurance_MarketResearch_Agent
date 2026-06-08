"""
Company Disclosure URLs Configuration (Updated May 2026)
=========================================================
Centralized configuration for all 26 private life insurers in India.

Each company has:
  - Primary disclosure URL (main page to try first)
  - Fallback URL (alternative if primary fails)
  
Sources: Verified via official company websites and Life Insurance Council
Tested: May 2026
"""

# (company_name, primary_disclosure_url, fallback_url)
COMPANY_DISCLOSURE_PAGES = [
    (
        "SBI Life Insurance",
        "https://www.sbilife.co.in/en/about-us/investor-relations/public-disclosure",
        "https://www.sbilife.co.in/en/about-us/investor-relations",
    ),
    (
        "HDFC Life Insurance",
        "https://www.hdfclife.com/about-us/investor-relations/public-disclosure",
        "https://www.hdfclife.com/about-us/investor-relations",
    ),
    (
        "ICICI Prudential Life Insurance",
        "https://www.iciciprulife.com/about-us/investor-relations/yearly-public-disclosures.html",
        "https://www.iciciprulife.com/about-us/investor-relations.html",
    ),
    (
        "Axis Max Life Insurance Limited",
        "https://www.axismaxlife.com/newsroom/public-disclosures",
        "https://www.maxfinancialservices.com/investor-relations",
    ),
    (
        "Bajaj Life Insurance Limited",
        "https://www.bajajlifeinsurance.com/about-us.html",
        "https://www.bajajlifeinsurance.com/public-notice.html",
    ),
    (
        "Tata AIA Life Insurance",
        "https://www.tataaia.com/public-disclosures/public-disclosures.html",
        "https://www.tataaia.com/investor-relations",
    ),
    (
        "Aditya Birla Sun Life Insurance",
        "https://lifeinsurance.adityabirlacapital.com/about-us/public-disclosure",
        "https://lifeinsurance.adityabirlacapital.com/about-us/investors",
    ),
    (
        "Kotak Mahindra Life Insurance",
        "https://insurance.kotak.com/about-us/corporate-governance/public-disclosures",
        "https://www.kotaklife.com/why-kotak-life/corporate-governance",
    ),
    (
        "PNB MetLife India Insurance",
        "https://www.pnbmetlife.com/investor-relations/public-disclosures.html",
        "https://newsite.pnbmetlife.com/investor-relations",
    ),
    (
        "Canara HSBC Life Insurance",
        "https://www.canarahsbclife.com/public-disclosures.html",
        "https://onlineinsurance.canarahsbclife.com/lifeinsurance/portal/canh/home/public-disclosures",
    ),
    (
        "IndiaFirst Life Insurance",
        "https://www.indiafirstlife.com/about-us/public-disclosure",
        "https://www.indiafirstlife.com/public-disclosure",
    ),
    (
        "Edelweiss Tokio Life Insurance",
        "https://www.edelweisslife.in/public-disclosure",
        "https://www.edelweisslife.in/about-us/investors",
    ),
    (
        "Generali Central Life Insurance Company Limited",
        "https://www.generalicentrallife.com/documents/about-us/public-disclosures",
        "https://life2.futuregenerali.in/about-us/public-disclosures/2024-2025",
    ),
    (
        "Pramerica Life Insurance",
        "https://www.pramericalife.in/Public_Disclosure",
        "https://www.pramericalife.in/investor-relations",
    ),
    (
        "Shriram Life Insurance",
        "https://www.shriramlife.in/slp/publicdisclosure.aspx",
        "https://www.shriramlife.in/investor-relations",
    ),
    (
        "Bharti Life Insurance Company Limited",
        "https://www.bhartiaxa.com/about-us/public-disclosure",
        "https://www.bhartiaxa.com/public-disclosure",
    ),
    (
        "IndusInd Nippon Life Insurance Company Limited",
        "https://www.indusindnipponlife.com/about-us/public-disclosure",
        "https://www.indusindnipponlife.com/about-us/investor-relations",
    ),
    (
        "Aviva Life Insurance",
        "https://www.avivaindia.com/public-disclosure",
        "https://www.aviva.com/investors",
    ),
    (
        "Star Union Dai-ichi Life Insurance",
        "https://www.sudlife.in/public-disclosure",
        "https://www.sudlife.in/investor-relations",
    ),
    (
        "Aegon Life Insurance",
        "https://www.aegonlife.com/about-aegon-life/investor-relations",
        "https://www.aegon.com/investors",
    ),
    (
        "Bandhan Life Insurance",
        "https://www.bandhanlife.com/public-disclosure",
        "https://www.bandhanlife.com/investor-relations",
    ),
    (
        "Credit Access Life Insurance",
        "https://calife.in/public-disclosures/",
        "https://creditaccesslife.in/Public_Disclosure",
    ),
    (
        "Sahara India Life Insurance",
        "https://www.saharalife.com/AnnualReport.html",
        "http://saharalife.com/temp/viewreport.asp",
    ),
    (
        "Acko Life Insurance Limited",
        "https://www.acko.com/life/public-disclosure/",
        "https://www.acko.com/public-disclosure/",
    ),
    (
        "Go Digit Life Insurance Limited",
        "https://www.godigit.com/life/financials",
        "https://www.godigit.com/public-disclosures",
    ),
    (
        "Ageas Federal Life Insurance Company Limited",
        "https://www.ageasfederal.com/public-disclosures",
        "https://www.ageasfederal.com/investor-relations",
    ),
]


def get_company_urls(company_name: str) -> tuple[str, str] | None:
    """
    Lookup URLs for a specific company.
    
    Args:
        company_name: Name of the insurer (must match COMPANY_DISCLOSURE_PAGES)
    
    Returns:
        Tuple of (primary_url, fallback_url) or None if not found
    """
    for name, primary, fallback in COMPANY_DISCLOSURE_PAGES:
        if name.lower() == company_name.lower():
            return (primary, fallback)
    return None


def get_all_companies() -> list[str]:
    """Return list of all 26 company names."""
    return [name for name, _, _ in COMPANY_DISCLOSURE_PAGES]


def get_company_count() -> int:
    """Return total number of companies (26)."""
    return len(COMPANY_DISCLOSURE_PAGES)

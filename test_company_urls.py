"""
Company Disclosure URLs Verification Tool
==========================================
Standalone utility to test all 23 company disclosure URLs for accessibility.

Usage:
    python test_company_urls.py              # Test all 23 URLs
    python test_company_urls.py --quick      # Test first 5 only

Output:
    url_verification_report.txt
"""

import sys
import time
import requests
from pathlib import Path
from bs4 import BeautifulSoup
from datetime import datetime
from scrapers.company_urls_2024 import COMPANY_DISCLOSURE_PAGES


def get_headers():
    """Return standard HTTP headers."""
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }


def test_url(url: str, timeout: int = 15) -> dict:
    """
    Test a single URL for accessibility and PDF links.
    
    Returns:
        {
            'url': str,
            'status_code': int,
            'accessible': bool,
            'pdf_count': int,
            'error': str or None,
            'response_time_ms': float,
        }
    """
    result = {
        "url": url,
        "status_code": None,
        "accessible": False,
        "pdf_count": 0,
        "error": None,
        "response_time_ms": 0,
    }

    try:
        start = time.time()
        resp = requests.get(url, headers=get_headers(), timeout=timeout)
        response_time = (time.time() - start) * 1000

        result["status_code"] = resp.status_code
        result["response_time_ms"] = round(response_time, 2)

        if resp.status_code == 200:
            result["accessible"] = True
            # Count PDF links
            soup = BeautifulSoup(resp.text, "html.parser")
            pdf_links = [
                a.get("href")
                for a in soup.find_all("a", href=True)
                if "pdf" in a.get("href", "").lower()
            ]
            result["pdf_count"] = len(pdf_links)
        else:
            result["error"] = f"HTTP {resp.status_code}"

    except requests.exceptions.Timeout:
        result["error"] = "Timeout"
    except requests.exceptions.ConnectionError:
        result["error"] = "Connection Error"
    except Exception as e:
        result["error"] = type(e).__name__

    return result


def main():
    """Run URL verification tests."""
    quick_mode = "--quick" in sys.argv
    
    print("\n" + "=" * 80)
    print("🔍 Life Insurance Company Disclosure URLs Verification")
    print("=" * 80)
    print(f"Testing {len(COMPANY_DISCLOSURE_PAGES)} companies...")
    print(f"Mode: {'Quick (5 companies)' if quick_mode else 'Full (all 23)'}\n")

    results = []
    companies_to_test = COMPANY_DISCLOSURE_PAGES[:5] if quick_mode else COMPANY_DISCLOSURE_PAGES

    for idx, (company_name, primary_url, fallback_url) in enumerate(companies_to_test, 1):
        print(f"[{idx:2d}] {company_name:<35} ", end="", flush=True)

        # Test primary URL
        primary_result = test_url(primary_url)

        if primary_result["accessible"]:
            status = "✅ OK"
            pdfs = primary_result["pdf_count"]
            print(f"{status} (Primary, {pdfs} PDFs, {primary_result['response_time_ms']}ms)")
        else:
            # Try fallback URL
            fallback_result = test_url(fallback_url) if fallback_url else {"accessible": False}

            if fallback_result.get("accessible"):
                status = "⚠️  FALLBACK"
                pdfs = fallback_result.get("pdf_count", 0)
                print(f"{status} ({pdfs} PDFs, {fallback_result.get('response_time_ms', 0)}ms)")
                primary_result = fallback_result
            else:
                error_msg = (
                    primary_result.get("error") or "Unknown"
                )
                print(f"❌ FAILED ({error_msg})")

        results.append({
            "company_name": company_name,
            "primary_url": primary_url,
            "fallback_url": fallback_url,
            "status_code": primary_result["status_code"],
            "accessible": primary_result["accessible"],
            "pdf_count": primary_result["pdf_count"],
            "error": primary_result["error"],
            "response_time_ms": primary_result["response_time_ms"],
        })

        time.sleep(0.5)  # Polite delay

    # Print summary
    print("\n" + "=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)

    accessible_count = sum(1 for r in results if r["accessible"])
    print(f"Accessible URLs:       {accessible_count}/{len(results)} ({round(accessible_count/len(results)*100, 1)}%)")
    print(f"Failed URLs:           {len(results) - accessible_count}")
    print(f"Total PDFs found:      {sum(r['pdf_count'] for r in results)}")

    # Save report
    report_path = Path("url_verification_report.txt")
    with open(report_path, "w") as f:
        f.write("=" * 80 + "\n")
        f.write("Life Insurance Company Disclosure URLs Verification Report\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 80 + "\n\n")

        for r in results:
            f.write(f"Company: {r['company_name']}\n")
            f.write(f"Primary URL: {r['primary_url']}\n")
            f.write(f"Status: {'✅ ACCESSIBLE' if r['accessible'] else '❌ FAILED'}\n")
            if r["status_code"]:
                f.write(f"HTTP Status: {r['status_code']}\n")
            if r["error"]:
                f.write(f"Error: {r['error']}\n")
            f.write(f"PDFs Found: {r['pdf_count']}\n")
            f.write(f"Response Time: {r['response_time_ms']}ms\n")
            f.write("-" * 80 + "\n\n")

        f.write("=" * 80 + "\n")
        f.write("SUMMARY\n")
        f.write("=" * 80 + "\n")
        f.write(f"Total Companies: {len(results)}\n")
        f.write(f"Accessible: {accessible_count}\n")
        f.write(f"Failed: {len(results) - accessible_count}\n")
        f.write(f"Success Rate: {round(accessible_count/len(results)*100, 1)}%\n")

    print(f"\n✅ Report saved to: {report_path}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()

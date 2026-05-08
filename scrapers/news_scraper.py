"""
News Scraper — Collects recent life insurance headlines from RSS feeds
(Economic Times, Business Standard, Money Control) and applies
rule-based sentiment analysis using TextBlob.
"""

import re
import logging
import feedparser
import pandas as pd
from datetime import datetime
from textblob import TextBlob

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# RSS feed sources (no auth required, publicly available)
# ---------------------------------------------------------------------------
RSS_FEEDS = {
    "Economic Times - Insurance": "https://economictimes.indiatimes.com/industry/banking/insurance/rssfeeds/1181454541.cms",
    "Economic Times - Finance":   "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
    "Business Standard - Insurance": "https://www.business-standard.com/rss/finance/insurance-news.rss",
    "Money Control - Insurance":  "https://www.moneycontrol.com/rss/MCtopnews.xml",
    "LiveMint - Insurance":       "https://www.livemint.com/rss/insurance",
}

# Canonical private insurer names for entity matching (no LIC)
INSURER_NAMES = [
    "SBI Life", "HDFC Life", "ICICI Prudential", "Max Life",
    "Bajaj Allianz", "Tata AIA", "Aditya Birla Sun Life", "Kotak Mahindra Life",
    "PNB MetLife", "Canara HSBC", "IndiaFirst Life", "Edelweiss Tokio",
    "Future Generali", "Pramerica Life", "Shriram Life", "Bharti AXA",
    "Reliance Nippon Life", "Aviva Life", "Star Union Dai-ichi", "Aegon Life",
    "Bandhan Life", "Credit Access Life", "Sahara Life",
]

# Keywords that signal insurance-relevance for filtering
INSURANCE_KEYWORDS = [
    "insurance", "insurer", "life insurance", "term plan", "premium",
    "irdai", "claim", "policy", "policyholder", "annuity", "ulip",
    "solvency", "actuarial", "endowment", "whole life", "rider",
]

CATEGORY_RULES = {
    "Regulatory": ["irdai", "regulation", "guideline", "circular", "compliance", "rbc", "framework", "mandate"],
    "Claims":     ["claim", "settlement", "claimant", "payout", "repudiat", "dispute"],
    "Product":    ["launch", "plan", "product", "ulip", "term plan", "annuity", "endowment", "rider", "feature"],
    "M&A":        ["merger", "acquisition", "takeover", "stake", "partnership", "joint venture", "jv"],
    "Performance":["premium", "market share", "growth", "profit", "loss", "quarterly", "results", "revenue"],
}


def _classify_category(text: str) -> str:
    text_lower = text.lower()
    for category, keywords in CATEGORY_RULES.items():
        if any(kw in text_lower for kw in keywords):
            return category
    return "General"


def _get_sentiment(text: str) -> str:
    try:
        polarity = TextBlob(text).sentiment.polarity
        if polarity > 0.05:
            return "Positive"
        elif polarity < -0.05:
            return "Negative"
        return "Neutral"
    except Exception:
        return "Neutral"


def _match_company(text: str) -> str:
    text_lower = text.lower()
    for name in INSURER_NAMES:
        if name.lower() in text_lower:
            return name
    return ""


def _parse_date(entry) -> str:
    for attr in ["published", "updated", "created"]:
        val = getattr(entry, attr, None)
        if val:
            return str(val)
    return datetime.now().isoformat()


def _is_relevant(title: str, summary: str) -> bool:
    combined = (title + " " + summary).lower()
    return any(kw in combined for kw in INSURANCE_KEYWORDS)


def scrape_rss_news() -> pd.DataFrame:
    """Parse all configured RSS feeds and return a structured news DataFrame."""
    records = []
    seen_urls = set()

    for source_name, feed_url in RSS_FEEDS.items():
        logger.info(f"Fetching RSS feed: {source_name}")
        try:
            feed = feedparser.parse(feed_url)
            if feed.bozo:
                logger.warning(f"Feed parse warning for {source_name}: {feed.bozo_exception}")

            for entry in feed.entries:
                title   = getattr(entry, "title",   "").strip()
                summary = getattr(entry, "summary", "").strip()
                url     = getattr(entry, "link",    "").strip()

                if url in seen_urls:
                    continue
                if not _is_relevant(title, summary):
                    continue

                seen_urls.add(url)
                combined_text = f"{title}. {summary}"

                records.append({
                    "headline":          title,
                    "summary":           summary[:500],
                    "source":            source_name,
                    "published_at":      _parse_date(entry),
                    "url":               url,
                    "company_mentioned": _match_company(combined_text),
                    "sentiment":         _get_sentiment(combined_text),
                    "category":          _classify_category(combined_text),
                    "scraped_at":        datetime.now().isoformat(),
                })

        except Exception as e:
            logger.warning(f"RSS feed error for {source_name}: {e}")

    if records:
        df = pd.DataFrame(records).sort_values("published_at", ascending=False)
        logger.info(f"News scraper: collected {len(df)} relevant articles.")
        return df

    # Fallback — return empty with correct schema so pipeline doesn't break
    logger.warning("No news articles collected from RSS feeds.")
    return pd.DataFrame(columns=[
        "headline", "summary", "source", "published_at", "url",
        "company_mentioned", "sentiment", "category", "scraped_at",
    ])

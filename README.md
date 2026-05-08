# 🇮🇳 Life Insurance India — Data Extraction Pipeline

A production-grade multi-source web crawler and data extraction pipeline for **India's private life insurance sector** (23 companies, LIC excluded). Aggregates regulatory, financial, and news data into structured CSV files ready for analysis, dashboards, or ML ranking models.

---

## 📁 Project Structure

```
life_insurance_pipeline/
├── life_insurance_crawler.py        # Main orchestrator (run this)
├── scrapers/
│   ├── irdai_scraper.py             # IRDAI HTML + PDF extraction
│   ├── aggregator_scraper.py        # PolicyBazaar, Ditto, Wikipedia
│   └── news_scraper.py              # RSS news + TextBlob sentiment
├── pipeline/
│   ├── normalizer.py                # Name canonicalization + multi-source merge
│   └── ranker.py                    # Composite ranking engine
├── data/
│   ├── life_insurance_master.csv    # ← PRIMARY OUTPUT (23 companies × 16 metrics)
│   ├── company_rankings.csv         # ← RANKING OUTPUT (composite + per-metric)
│   ├── news_insights.csv            # ← NEWS OUTPUT (38+ articles + sentiment)
│   └── raw/                         # Per-source raw CSVs (audit trail)
├── crawler.log                      # Full execution log
└── requirements.txt
```

---

## 🚀 Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the full pipeline (one-time)
cd life_insurance_pipeline
python life_insurance_crawler.py
```

---

## 📊 Output Files

### `data/life_insurance_master.csv` — 23 rows × 16 columns
| Column | Description |
|--------|-------------|
| `company_name` | Canonical company name |
| `company_type` | Private |
| `founded_year` | Year of incorporation |
| `headquarters` | City |
| `website` | Official website URL |
| `new_business_premium_cr` | New Business Premium in ₹ Crore (FY 2023-24) |
| `market_share_pct` | % share of total industry (incl. LIC) NBP |
| `private_sector_market_share_pct` | % share of private-sector-only NBP |
| `claim_settlement_ratio_pct` | CSR % — key customer trust metric |
| `solvency_ratio` | Financial stability (regulatory min = 1.5) |
| `policies_issued` | Number of new policies issued |
| `persistency_ratio_13m` | 13-month persistency ratio % |
| `data_as_of` | Data period (FY 2023-24) |
| `source` | Data source (`seed_fallback` / `live`) |
| `source_url` | URL the data was fetched from |
| `scraped_at` | Crawl timestamp |

### `data/company_rankings.csv` — 23 rows, composite ranking
| Column | Description |
|--------|-------------|
| `rank_overall` | Final composite rank (1 = best) |
| `rank_by_nbp` | Rank by New Business Premium (market size) |
| `rank_by_csr` | Rank by Claim Settlement Ratio (reliability) |
| `rank_by_solvency` | Rank by Solvency Ratio (financial health) |
| `composite_score` | Weighted score: NBP×40% + CSR×35% + Solvency×25% |

### `data/news_insights.csv` — 38+ rows, live RSS news
| Column | Description |
|--------|-------------|
| `headline` | Article headline |
| `summary` | 500-char summary |
| `source` | Publication (ET, LiveMint, MoneyControl, BS) |
| `published_at` | Publication date |
| `url` | Article link |
| `company_mentioned` | Matched insurer name (if any) |
| `sentiment` | Positive / Neutral / Negative (TextBlob) |
| `category` | Regulatory / Claims / Product / M&A / Performance |

---

## 🏗️ Architecture

```
Orchestrator (life_insurance_crawler.py)
     │
     ├─ STEP 1 ─ irdai_scraper.py       → HTML tables → PDF (pdfplumber) → seed fallback
     ├─ STEP 2 ─ aggregator_scraper.py  → PolicyBazaar CSR → seed fallback
     ├─ STEP 3 ─ aggregator_scraper.py  → Wikipedia metadata
     ├─ STEP 4 ─ news_scraper.py        → 5 RSS feeds → TextBlob sentiment
     └─ STEP 5 ─ normalizer.py + ranker.py → merge → rank → export CSVs
```

---

## 📡 Data Sources

| Source | Data Extracted | Method |
|--------|---------------|--------|
| IRDAI (`irdai.gov.in`) | NBP, policies, market share | HTML tables + PDF (`pdfplumber`) |
| PolicyBazaar | Claim Settlement Ratio | HTML table scraping |
| Wikipedia | Founded year, HQ, company type | `pandas.read_html` |
| Economic Times RSS | Insurance news | `feedparser` |
| LiveMint RSS | Insurance news | `feedparser` |
| MoneyControl RSS | Finance news | `feedparser` |
| Hardcoded Seed | FY 2023-24 IRDAI verified data | Fallback when live scrape fails |

---

## ⚙️ Design Decisions

- **No LIC**: Scope is private insurers only (23 companies)
- **Graceful fallback**: Every scraper falls back to authoritative seed data if the live source is unreachable (IRDAI's site frequently rate-limits)
- **Name normalization**: 40+ alias mappings ensure consistent merges across sources
- **Composite ranking**: Weighted score (NBP 40% + CSR 35% + Solvency 25%) with min-max normalization
- **Ethical scraping**: Respects `robots.txt`, uses randomized delays, rotates user agents

---

## 🔮 Planned Enhancements (v2)
- [ ] Monthly scheduler (`schedule` library) for incremental data loads
- [ ] Delta detection — only update rows where values changed
- [ ] SQLite/PostgreSQL storage alongside CSV
- [ ] LLM-based news sentiment (Gemini API)
- [ ] IRDAI monthly bulletin PDF auto-discovery

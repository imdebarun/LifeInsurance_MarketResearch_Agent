import os
import json
import logging
from datetime import datetime
import pandas as pd
from pathlib import Path
from db.manager import upsert_performance_metric, upsert_news, init_db

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DASHBOARD_PUBLIC_DIR = BASE_DIR / "dashboard" / "public"

HISTORICAL_DATA_FILE = DATA_DIR / "historical_data.csv"

def save_and_export_dashboard_data(master_df: pd.DataFrame, rankings_df: pd.DataFrame, news_df: pd.DataFrame):
    """
    Appends the latest run to historical data, and exports JSONs for the dashboard.
    """
    logger.info("Starting historical storage and dashboard export...")
    
    # Ensure directories exist
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DASHBOARD_PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    
    # Initialize DB
    init_db()
    
    current_time = datetime.now().isoformat()
    
    # 1. Update Historical CSV
    if not master_df.empty:
        new_records = master_df.copy()
        new_records["snapshot_time"] = current_time
        
        if HISTORICAL_DATA_FILE.exists():
            try:
                old_history = pd.read_csv(HISTORICAL_DATA_FILE)
                combined = pd.concat([old_history, new_records], ignore_index=True)
                
                # Deduplicate based on company and period (data_as_of)
                # Keep the last one (the newest snapshot)
                combined = combined.drop_duplicates(subset=["company_name", "data_as_of"], keep="last")
                
                # Sort by company and then data_as_of (this is tricky with strings like FY24 Q4, 
                # but better than nothing; ideally we'd have a sortable date column)
                combined = combined.sort_values(by=["company_name", "data_as_of"])
                
                combined.to_csv(HISTORICAL_DATA_FILE, index=False)
                logger.info(f"Updated {HISTORICAL_DATA_FILE.name} (total {len(combined)} records)")
            except Exception as e:
                logger.error(f"Error updating historical CSV: {e}")
                new_records.to_csv(HISTORICAL_DATA_FILE, index=False)
        else:
            new_records.to_csv(HISTORICAL_DATA_FILE, index=False)
            logger.info(f"Created new {HISTORICAL_DATA_FILE.name}")
            
        # ── DB Sync ──────────────────────────────────────────────────────────
        logger.info("Syncing historical metrics to Database...")
        for _, row in master_df.iterrows():
            data = row.to_dict()
            data = {k: (None if pd.isna(v) else v) for k, v in data.items()}
            if 'scraped_at' not in data or not data['scraped_at']:
                data['scraped_at'] = datetime.now()
            elif isinstance(data['scraped_at'], str):
                try:
                    data['scraped_at'] = pd.to_datetime(data['scraped_at']).to_pydatetime()
                except:
                    data['scraped_at'] = datetime.now()
            upsert_performance_metric(data)
    
    # 2. Export Latest Snapshot JSON
    # Replace NaN with None for valid JSON
    latest_json = master_df.fillna("").to_dict(orient="records")
    latest_json_path = DASHBOARD_PUBLIC_DIR / "latest_data.json"
    with open(latest_json_path, "w", encoding="utf-8") as f:
        json.dump(latest_json, f, indent=2)
        
    # 3. Sync News to DB
    if not news_df.empty:
        logger.info("Syncing news insights to Database...")
        for _, row in news_df.iterrows():
            data = row.to_dict()
            data = {k: (None if pd.isna(v) else v) for k, v in data.items()}
            if 'scraped_at' not in data or not data['scraped_at']:
                data['scraped_at'] = datetime.now()
            elif isinstance(data['scraped_at'], str):
                try:
                    data['scraped_at'] = pd.to_datetime(data['scraped_at']).to_pydatetime()
                except:
                    data['scraped_at'] = datetime.now()
            upsert_news(data)
        
    # 4. Export Rankings JSON
    rankings_json = rankings_df.fillna("").to_dict(orient="records")
    rankings_json_path = DASHBOARD_PUBLIC_DIR / "rankings_data.json"
    with open(rankings_json_path, "w", encoding="utf-8") as f:
        json.dump(rankings_json, f, indent=2)
        
    # 5. Export News JSON
    news_json = news_df.fillna("").to_dict(orient="records") if not news_df.empty else []
    news_json_path = DASHBOARD_PUBLIC_DIR / "news_data.json"
    with open(news_json_path, "w", encoding="utf-8") as f:
        json.dump(news_json, f, indent=2)
        
    # 6. Export Historical JSON (for time-series charts)
    if HISTORICAL_DATA_FILE.exists():
        full_hist_df = pd.read_csv(HISTORICAL_DATA_FILE)
        hist_json = full_hist_df.fillna("").to_dict(orient="records")
        hist_json_path = DASHBOARD_PUBLIC_DIR / "historical_data.json"
        with open(hist_json_path, "w", encoding="utf-8") as f:
            json.dump(hist_json, f, indent=2)
            
    logger.info(f"Dashboard JSONs exported to {DASHBOARD_PUBLIC_DIR}")

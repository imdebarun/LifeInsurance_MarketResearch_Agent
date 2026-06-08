import pandas as pd
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from db.manager import init_db, upsert_performance_metric, upsert_news
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migration")

def migrate_csv_to_db():
    init_db()
    
    base_path = Path(__file__).resolve().parent / "data"
    
    # 1. Migrate Historical Metrics
    hist_path = base_path / "historical_data.csv"
    if hist_path.exists():
        logger.info("Migrating historical metrics...")
        df_hist = pd.read_csv(hist_path)
        for _, row in df_hist.iterrows():
            data = row.to_dict()
            # Clean data (NaN to None for SQLAlchemy)
            data = {k: (None if pd.isna(v) else v) for k, v in data.items()}
            
            # Convert timestamps
            if data.get('scraped_at'):
                try:
                    data['scraped_at'] = pd.to_datetime(data['scraped_at']).to_pydatetime()
                except:
                    data['scraped_at'] = datetime.utcnow()
            
            upsert_performance_metric(data)
        logger.info(f"Successfully migrated {len(df_hist)} metric records.")
    
    # 2. Migrate News
    news_path = base_path / "news_insights.csv"
    if news_path.exists():
        logger.info("Migrating news insights...")
        df_news = pd.read_csv(news_path)
        for _, row in df_news.iterrows():
            data = row.to_dict()
            data = {k: (None if pd.isna(v) else v) for k, v in data.items()}
            
            if data.get('scraped_at'):
                try:
                    data['scraped_at'] = pd.to_datetime(data['scraped_at']).to_pydatetime()
                except:
                    data['scraped_at'] = datetime.utcnow()
                    
            upsert_news(data)
        logger.info(f"Successfully migrated {len(df_news)} news records.")

if __name__ == "__main__":
    migrate_csv_to_db()

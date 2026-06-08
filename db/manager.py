from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base, User, Insurer, PerformanceMetric, NewsArticle
import bcrypt
import os
from datetime import datetime
from pathlib import Path

# Use SQLite for portability, can be easily switched to PostgreSQL
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "insurance_intelligence.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """Initialize the database tables."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    Base.metadata.create_all(bind=engine)

# ── User Auth ───────────────────────────────────────────────────────────────

def create_user(username, email, password):
    session = SessionLocal()
    try:
        # Check if user already exists
        existing = session.query(User).filter((User.username == username) | (User.email == email)).first()
        if existing:
            return False
            
        # Salt and hash password using native bcrypt
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        
        new_user = User(username=username, email=email, password_hash=hashed.decode('utf-8'))
        session.add(new_user)
        session.commit()
        return True
    except Exception as e:
        session.rollback()
        print(f"Error creating user: {e}")
        return False
    finally:
        session.close()

def authenticate_user(username, password):
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.username == username).first()
        if user and bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')):
            return user
        return None
    finally:
        session.close()

# ── Data Upsert ─────────────────────────────────────────────────────────────

def upsert_insurer(company_info):
    session = SessionLocal()
    try:
        name = company_info['company_name']
        insurer = session.query(Insurer).filter(Insurer.company_name == name).first()
        if not insurer:
            insurer = Insurer(
                company_name=name,
                company_type=company_info.get('company_type'),
                founded_year=company_info.get('founded_year'),
                headquarters=company_info.get('headquarters'),
                website=company_info.get('website')
            )
            session.add(insurer)
            session.commit()
            session.refresh(insurer)
        return insurer.id
    finally:
        session.close()

def upsert_performance_metric(metric_data):
    session = SessionLocal()
    try:
        # First ensure insurer exists
        insurer_id = upsert_insurer(metric_data)
        
        # Check if metric for this period exists
        period = metric_data['data_as_of']
        existing = session.query(PerformanceMetric).filter(
            PerformanceMetric.insurer_id == insurer_id,
            PerformanceMetric.data_as_of == period
        ).first()
        
        if existing:
            # Update
            for key, value in metric_data.items():
                if hasattr(existing, key) and key not in ['id', 'insurer_id']:
                    setattr(existing, key, value)
        else:
            # Insert
            new_metric = PerformanceMetric(insurer_id=insurer_id, **{
                k: v for k, v in metric_data.items() if hasattr(PerformanceMetric, k) and k != 'id'
            })
            session.add(new_metric)
        
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

def upsert_news(news_data):
    session = SessionLocal()
    try:
        url = news_data.get('url')
        existing = session.query(NewsArticle).filter(NewsArticle.url == url).first()
        
        if existing:
            for key, value in news_data.items():
                if hasattr(existing, key) and key != 'id':
                    setattr(existing, key, value)
        else:
            new_art = NewsArticle(**{
                k: v for k, v in news_data.items() if hasattr(NewsArticle, k) and k != 'id'
            })
            session.add(new_art)
        
        session.commit()
    except Exception as e:
        session.rollback()
    finally:
        session.close()

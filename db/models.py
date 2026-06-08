from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Insurer(Base):
    __tablename__ = 'insurers'
    id = Column(Integer, primary_key=True)
    company_name = Column(String(200), unique=True, nullable=False)
    company_type = Column(String(50))
    founded_year = Column(Float)
    headquarters = Column(String(200))
    website = Column(String(500))
    
    metrics = relationship("PerformanceMetric", back_populates="insurer")

class PerformanceMetric(Base):
    __tablename__ = 'performance_metrics'
    id = Column(Integer, primary_key=True)
    insurer_id = Column(Integer, ForeignKey('insurers.id'))
    data_as_of = Column(String(50), nullable=False) # e.g., FY2023-24 Q4
    
    new_business_premium_cr = Column(Float)
    market_share_pct = Column(Float)
    private_sector_market_share_pct = Column(Float)
    claim_settlement_ratio_pct = Column(Float)
    solvency_ratio = Column(Float)
    policies_issued = Column(Float)
    persistency_ratio_13m = Column(Float)
    
    source = Column(String(100))
    source_url = Column(String(500))
    scraped_at = Column(DateTime, default=datetime.utcnow)
    
    insurer = relationship("Insurer", back_populates="metrics")

class NewsArticle(Base):
    __tablename__ = 'news_articles'
    id = Column(Integer, primary_key=True)
    headline = Column(String(500), nullable=False)
    summary = Column(Text)
    full_text = Column(Text) # For LLM application
    source = Column(String(100))
    published_at = Column(String(100))
    url = Column(String(500), unique=True)
    company_mentioned = Column(String(200))
    sentiment = Column(String(50))
    category = Column(String(50))
    scraped_at = Column(DateTime, default=datetime.utcnow)
    embedding = Column(JSON) # To store vector embeddings if needed later

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from pathlib import Path
import os
import sys

# Add project root to path for DB imports
sys.path.append(str(Path(__file__).resolve().parent.parent))
from db.manager import SessionLocal, authenticate_user, create_user, init_db
from db.models import PerformanceMetric, NewsArticle, Insurer, User

# Page Config
st.set_page_config(
    page_title="India Life Insurance Intelligence Dashboard",
    page_icon="🇮🇳",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Premium Look
st.markdown("""
<style>
    .main { background-color: #0e1117; color: #ffffff; }
    .stMetric { 
        background-color: #1e2130; 
        padding: 20px; 
        border-radius: 10px; 
        border-left: 5px solid #00d4ff;
        transition: transform 0.3s ease;
    }
    .stMetric:hover {
        transform: translateY(-5px);
        background-color: #252a3d;
    }
    [data-testid="stMetricLabel"] {
        color: #00d4ff !important;
        font-weight: 600 !important;
    }
    [data-testid="stMetricValue"] {
        color: #ffffff !important;
        font-weight: 700 !important;
    }
    .stSidebar { background-color: #161b22; }
    h1, h2, h3 { font-family: 'Inter', sans-serif; font-weight: 700; color: #00d4ff; }
    .sentiment-tag {
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: bold;
        font-size: 0.8rem;
    }
    .sentiment-positive { background-color: #1a472a; color: #2ecc71; }
    .sentiment-negative { background-color: #4c1d1d; color: #e74c3c; }
    .sentiment-neutral { background-color: #2c3e50; color: #bdc3c7; }
</style>
""", unsafe_allow_html=True)

# Initialize DB on start
init_db()

# ── Session State for Auth ──────────────────────────────────────────────────
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user' not in st.session_state:
    st.session_state.user = None

def login_ui():
    st.markdown("<h1 style='text-align: center;'>🔐 Intelligence Portal</h1>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab1, tab2 = st.tabs(["Login", "Sign Up"])
        
        with tab1:
            username = st.text_input("Username", key="login_user")
            password = st.text_input("Password", type="password", key="login_pass")
            if st.button("Login"):
                user = authenticate_user(username, password)
                if user:
                    st.session_state.logged_in = True
                    st.session_state.user = user.username
                    st.success(f"Welcome back, {user.username}!")
                    st.rerun()
                else:
                    st.error("Invalid username or password")
                    
        with tab2:
            new_username = st.text_input("Username", key="reg_user")
            new_email = st.text_input("Email", key="reg_email")
            new_pass = st.text_input("Password", type="password", key="reg_pass")
            confirm_pass = st.text_input("Confirm Password", type="password", key="reg_confirm")
            
            if st.button("Register"):
                if new_pass != confirm_pass:
                    st.error("Passwords do not match")
                elif not new_username or not new_email:
                    st.error("All fields are required")
                else:
                    if create_user(new_username, new_email, new_pass):
                        st.success("Account created! Please login.")
                    else:
                        st.error("Username or email already exists")

# ── Data Loading from DB ───────────────────────────────────────────────────
@st.cache_data
def load_data_from_db():
    session = SessionLocal()
    try:
        # Load Metrics and Join with Insurers
        query = session.query(
            Insurer.company_name,
            Insurer.company_type,
            PerformanceMetric.new_business_premium_cr,
            PerformanceMetric.market_share_pct,
            PerformanceMetric.private_sector_market_share_pct,
            PerformanceMetric.claim_settlement_ratio_pct,
            PerformanceMetric.solvency_ratio,
            PerformanceMetric.policies_issued,
            PerformanceMetric.persistency_ratio_13m,
            PerformanceMetric.data_as_of,
            PerformanceMetric.source,
            PerformanceMetric.scraped_at
        ).join(PerformanceMetric, Insurer.id == PerformanceMetric.insurer_id)
        
        df_hist = pd.read_sql(query.statement, session.bind)
        
        # Load News
        df_news = pd.read_sql(session.query(NewsArticle).statement, session.bind)
        
        return df_hist, df_news
    finally:
        session.close()

# ── Main Dashboard UI ───────────────────────────────────────────────────────
def main_dashboard():
    df_hist, df_news = load_data_from_db()
    
    # Sidebar
    st.sidebar.title(f"👋 Hello, {st.session_state.user}")
    
    if not df_hist.empty:
        last_sync = df_hist['scraped_at'].max()
        if isinstance(last_sync, str):
            last_sync = pd.to_datetime(last_sync).strftime("%Y-%m-%d %H:%M")
        else:
            last_sync = last_sync.strftime("%Y-%m-%d %H:%M")
        st.sidebar.caption(f"Last DB Sync: {last_sync}")
        
    st.sidebar.markdown("---")
    
    all_companies = sorted(df_hist['company_name'].unique().tolist()) if not df_hist.empty else []
    selected_company = st.sidebar.selectbox("Select Insurer", ["All Insurers"] + all_companies)
    
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.user = None
        st.rerun()

    # Header
    st.title("🇮🇳 Life Insurance India Intelligence")
    st.markdown("### Connected Database Analysis & Sentiment Tracker")

    if df_hist.empty:
        st.warning("Database is empty. Please run the extraction pipeline.")
        st.stop()

    # Metrics Section
    if selected_company == "All Insurers":
        latest_data = df_hist.sort_values('scraped_at', ascending=False).drop_duplicates('company_name')
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            total_nbp = latest_data['new_business_premium_cr'].sum()
            st.metric("Total Market NBP (Cr)", f"₹{total_nbp:,.0f}")
        with col2:
            avg_solvency = latest_data['solvency_ratio'].mean()
            st.metric("Avg. Solvency Ratio", f"{avg_solvency:.2f}")
        with col3:
            avg_csr = latest_data['claim_settlement_ratio_pct'].mean()
            st.metric("Avg. Claim Settlement", f"{avg_csr:.2f}%")
        with col4:
            total_policies = latest_data['policies_issued'].sum()
            st.metric("Total Policies Issued", f"{total_policies:,.0f}")
    else:
        company_data = df_hist[df_hist['company_name'] == selected_company].sort_values('scraped_at', ascending=False)
        latest = company_data.iloc[0]
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("New Business Premium (Cr)", f"₹{latest['new_business_premium_cr']:,.0f}")
        with col2:
            st.metric("Solvency Ratio", f"{latest['solvency_ratio']:.2f}")
        with col3:
            st.metric("Claim Settlement Ratio", f"{latest['claim_settlement_ratio_pct']:.2f}%")
        with col4:
            st.metric("13M Persistency", f"{latest['persistency_ratio_13m']:.1f}%")

    # Tabs
    tab1, tab2, tab3 = st.tabs(["📊 Performance Trends", "📰 Market Intelligence", "🏆 Leaderboard"])

    with tab1:
        st.subheader("Historical Performance Analysis")
        trend_metric = st.selectbox("Select Trend Metric", 
                                  ["new_business_premium_cr", "solvency_ratio", "claim_settlement_ratio_pct", "policies_issued"])
        metric_label = trend_metric.replace('_', ' ').title()
        
        if selected_company == "All Insurers":
            fig = px.line(df_hist, x="data_as_of", y=trend_metric, color="company_name",
                          title=f"Industry-wide {metric_label} Trends",
                          template="plotly_dark")
        else:
            comp_hist = df_hist[df_hist['company_name'] == selected_company].sort_values('data_as_of')
            fig = px.line(comp_hist, x="data_as_of", y=trend_metric, 
                          title=f"{selected_company}: {metric_label} Timeline",
                          template="plotly_dark", markers=True)
            fig.update_traces(line_color='#00d4ff')
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        st.subheader("News & Market Sentiment")
        if not df_news.empty:
            display_news = df_news
            if selected_company != "All Insurers":
                # Simple keyword match for the selected company
                display_news = df_news[df_news['headline'].str.contains(selected_company.split()[0], case=False)]
            
            # Sentiment Donut Chart
            col_a, col_b = st.columns([1, 2])
            with col_a:
                sentiment_counts = display_news['sentiment'].value_counts()
                fig_donut = px.pie(names=sentiment_counts.index, values=sentiment_counts.values,
                                 hole=0.6, title="Sentiment Mix",
                                 color=sentiment_counts.index,
                                 color_discrete_map={"Positive": "#2ecc71", "Negative": "#e74c3c", "Neutral": "#bdc3c7"},
                                 template="plotly_dark")
                fig_donut.update_layout(showlegend=False, margin=dict(t=30, b=0, l=0, r=0))
                st.plotly_chart(fig_donut, use_container_width=True)
            
            with col_b:
                st.markdown("#### Latest Headlines")
                for _, row in display_news.head(8).iterrows():
                    sentiment = row['sentiment']
                    sent_class = f"sentiment-{sentiment.lower() if sentiment else 'neutral'}"
                    st.markdown(f"""
                    **{row['headline']}**  
                    <span class="sentiment-tag {sent_class}">{sentiment}</span> | *{row['published_at']}*  
                    {row['summary'][:150]}... [Read More]({row['url']})
                    <hr style="margin: 8px 0; border: 0.5px solid #2d333b;">
                    """, unsafe_allow_html=True)
        else:
            st.info("No news articles found in the database.")

    with tab3:
        st.subheader("Market Rankings")
        latest_data = df_hist.sort_values('scraped_at', ascending=False).drop_duplicates('company_name')
        st.dataframe(latest_data[["company_name", "new_business_premium_cr", "solvency_ratio", "claim_settlement_ratio_pct", "data_as_of"]], 
                     use_container_width=True, hide_index=True)

# ── App Logic ──────────────────────────────────────────────────────────────
if not st.session_state.logged_in:
    login_ui()
else:
    main_dashboard()

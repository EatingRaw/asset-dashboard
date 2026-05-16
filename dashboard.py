import streamlit as st
import pandas as pd
import os
import plotly.express as px
import yfinance as yf
from datetime import datetime
import pytz

st.set_page_config(page_title="NONE DASHBOARD", page_icon="📈", layout="wide")

# Configuration
BASELINE_DATE = pd.Timestamp("2026-05-15")

st.title("🎢 None Festival")
st.subheader("Leaderboard: Who is the Growth King? :)")

import sqlite3

# Helper to determine market close + 1 hour in KST
def get_market_close_time_kst(dt):
    try:
        et_tz = pytz.timezone('US/Eastern')
        kst_tz = pytz.timezone('Asia/Seoul')
        # dt is naive or UTC from yfinance, treat as the trading day
        et_time = et_tz.localize(datetime(dt.year, dt.month, dt.day, 17, 0, 0))
        kst_time = et_time.astimezone(kst_tz)
        return kst_time
    except:
        return dt

# Fetch User Data
try:
    if os.path.exists("assets.db"):
        conn = sqlite3.connect("assets.db")
        df_user = pd.read_sql_query("SELECT * FROM assets", conn)
        conn.close()
    else:
        df_user = pd.DataFrame()
except:
    df_user = pd.DataFrame()

# Helper to fetch comparison data
def fetch_comparison(ticker, name, start_date):
    try:
        # Fetch a bit more to ensure we have the baseline
        fetch_start = start_date - pd.Timedelta(days=5)
        raw = yf.download(ticker, start=fetch_start.strftime("%Y-%m-%d"), progress=False, auto_adjust=True)
        if raw.empty: return pd.DataFrame()
        
        data = raw[["Close"]].copy()
        new_rows = []
        for dt, row in data.iterrows():
            kst_close = get_market_close_time_kst(dt)
            new_rows.append({"amount": float(row["Close"]), "name": name, "date": kst_close})
        
        res = pd.DataFrame(new_rows)
        # Today's live price
        last_price = yf.Ticker(ticker).fast_info.last_price
        if last_price:
            today_close = get_market_close_time_kst(datetime.now())
            if today_close > res["date"].max():
                res = pd.concat([res, pd.DataFrame([{"amount": float(last_price), "name": name, "date": today_close}])])
        return res
    except: return pd.DataFrame()

# Load all data
comparison_list = [
    ("VOO", "S&P 500 (VOO)"),
    ("BTC-USD", "Bitcoin"),
    ("USDKRW=X", "USD/KRW")
]

all_dfs = []
if not df_user.empty:
    df_user['date_dt'] = pd.to_datetime(df_user['date'])
    df_user['date'] = df_user['date_dt'].apply(lambda x: get_market_close_time_kst(x))
    df_user = df_user.sort_values('date').drop_duplicates(subset=['name', 'date'], keep='last')
    all_dfs.append(df_user[['name', 'date', 'amount']])

for ticker, name in comparison_list:
    comp_df = fetch_comparison(ticker, name, BASELINE_DATE)
    if not comp_df.empty:
        all_dfs.append(comp_df[['name', 'date', 'amount']])

if all_dfs:
    df = pd.concat(all_dfs, ignore_index=True)
    # Ensure all names are strings and no trailing spaces
    df['name'] = df['name'].astype(str).str.strip()
    
    # Filter by BASELINE_DATE
    df = df[df['date'].dt.tz_localize(None) >= BASELINE_DATE].copy()
    
    if df.empty:
        st.warning("기준일 이후 데이터가 없습니다.")
    else:
        baselines = {}
        for name in df['name'].unique():
            user_df_sub = df[df['name'] == name].sort_values('date')
            if not user_df_sub.empty:
                baselines[name] = user_df_sub.iloc[0]['amount']
        
        df['growth_rate'] = df.apply(
            lambda r: r['amount'] / baselines[r['name']] if baselines.get(r['name']) else 1.0,
            axis=1,
        )
        df['growth_rate_pct'] = (df['growth_rate'] - 1) * 100

        # Current snapshot
        latest_all = df.sort_values(by='date').groupby('name').tail(1).sort_values(by='growth_rate_pct', ascending=False)
        
        # Emojis
        crown_name = latest_all.iloc[0]['name']
        turtle_name = latest_all.iloc[-1]['name']
        
        def get_display_name(n):
            if n == crown_name: return f"👑 {n}"
            if n == turtle_name: return f"🐢 {n}"
            return n

        # 1. Metrics
        st.subheader("Leaderboard")
        cols = st.columns(len(latest_all))
        for i, (idx, row) in enumerate(latest_all.iterrows()):
            with cols[i]:
                baseline = baselines.get(row['name'], row['amount'])
                net_change = row['amount'] - baseline
                
                label = get_display_name(row['name'])
                
                if "S&P 500" in row['name'] or "Bitcoin" in row['name']:
                    delta_val = f"{net_change:+.2f} USD"
                elif "USD/KRW" in row['name']:
                    delta_val = f"{net_change:+.2f} KRW"
                else:
                    delta_val = f"${net_change:+.2f} USD"
                
                st.metric(
                    label=label,
                    value=f"{row['growth_rate_pct']:.2f}%",
                    delta=delta_val,
                    help=f"기록시간: {row['date'].strftime('%m/%d %H:%M')}"
                )

        st.divider()

        # 2. Graph
        st.subheader("Growth Race 🏎️")
        df_chart_data = df.copy()
        start_date = df_chart_data['date'].min() - pd.Timedelta(days=1)
        start_points = []
        for name in df_chart_data['name'].unique():
            start_points.append({'name': name, 'date': start_date, 'amount': baselines.get(name, 0), 'growth_rate': 1.0, 'growth_rate_pct': 0.0})
        
        df_chart = pd.concat([pd.DataFrame(start_points), df_chart_data], ignore_index=True).sort_values(by='date')
        df_chart['display_name'] = df_chart['name'].apply(get_display_name)

        fig = px.line(
            df_chart, x='date', y='growth_rate_pct', color='display_name', markers=True,
            title="Comparison of Growth Rates", labels={'growth_rate_pct': 'Growth (%)', 'display_name': 'Participant'}
        )
        fig.update_layout(yaxis_ticksuffix="%")
        st.plotly_chart(fig, use_container_width=True)

        # 3. Table
        st.subheader("Volatility Analysis 📊")
        vol_rows = []
        for name in latest_all['name']:
            sub = df[df['name'] == name].sort_values('date')
            display = get_display_name(name)
            if len(sub) < 2:
                vol_rows.append({"이름": display, "수익률": f"{sub.iloc[-1]['growth_rate_pct']:+.2f}%", "일일수익": "N/A", "변동성": "N/A", "MDD": "N/A"})
                continue
            
            d_ret = (sub.iloc[-1]['amount'] / sub.iloc[-2]['amount'] - 1) * 100
            vol = sub['growth_rate'].pct_change().std() * 100
            mdd = ((sub['growth_rate'] - sub['growth_rate'].cummax()) / sub['growth_rate'].cummax()).min() * 100
            
            vol_rows.append({
                "이름": display,
                "수익률": f"{sub.iloc[-1]['growth_rate_pct']:+.2f}%",
                "일일수익": f"{d_ret:+.2f}%",
                "변동성": f"{vol:.2f}%",
                "MDD": f"{mdd:.2f}%"
            })
        st.table(pd.DataFrame(vol_rows))

else:
    st.info("데이터를 불러오는 중입니다...")

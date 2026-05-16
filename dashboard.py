import streamlit as st
import pandas as pd
import os
import plotly.express as px
import yfinance as yf

st.set_page_config(page_title="NONE DASHBOARD", page_icon="📈")

# Configuration - 미국 주식 시스템 시작일로 기준점 변경
BASELINE_DATE = pd.Timestamp("2026-05-16")

st.title("🎢 None Festival")
st.subheader("Leaderboard: Who is the Growth King? :)")

import sqlite3

# Fetch Data
try:
    if os.path.exists("assets.db"):
        conn = sqlite3.connect("assets.db")
        df = pd.read_sql_query("SELECT * FROM assets", conn)
        conn.close()
    else:
        st.warning("데이터베이스 파일(assets.db)이 아직 생성되지 않았습니다.")
        df = pd.DataFrame()
except Exception as e:
    st.error(f"Database Error: {e}")
    df = pd.DataFrame()

if not df.empty:
    # Process Data
    df['date'] = pd.to_datetime(df['date']).dt.normalize() + pd.Timedelta(hours=16, minutes=30)
    
    # Keep only the latest entry per user per day
    if 'id' in df.columns:
        df = df.sort_values('id').drop_duplicates(subset=['name', 'date'], keep='last')
    else:
        df = df.drop_duplicates(subset=['name', 'date'], keep='last')

    # Rebase to BASELINE_DATE
    df = df[df['date'] >= BASELINE_DATE].copy()

    if df.empty:
        st.info("오늘 데이터가 아직 집계되지 않았거나 BASELINE_DATE 이후 데이터가 없습니다.")
    else:
        baselines = {}
        for name in df['name'].unique():
            user_df = df[df['name'] == name].sort_values('date')
            if not user_df.empty:
                baselines[name] = user_df.iloc[0]['amount']

        df['growth_rate'] = df.apply(
            lambda r: r['amount'] / baselines[r['name']] if baselines.get(r['name']) else 1.0,
            axis=1,
        )

        # 1. Leaderboard (Latest Data)
        latest_df = df.sort_values(by='date').groupby('name').tail(1)
        latest_df = latest_df.sort_values(by='growth_rate', ascending=False)
        
        # Display Metrics
        cols = st.columns(len(latest_df))
        for i, (index, row) in enumerate(latest_df.iterrows()):
            with cols[i]:
                baseline = baselines.get(row['name'], row['amount'])
                net_profit = row['amount'] - baseline
                # USD -> KRW conversion
                try:
                    usd_rate = yf.Ticker("USDKRW=X").fast_info.last_price or 1350
                    net_profit_krw = net_profit * usd_rate
                except:
                    net_profit_krw = net_profit * 1350

                st.metric(
                    label=f"{i+1}위 {row['name']}",
                    value=f"{(row['growth_rate']-1)*100:.1f}%",
                    delta=f"${net_profit:,.2f} USD",
                    help=f"약 {net_profit_krw:,.0f} KRW (실시간 환율 반영)"
                )

        st.divider()

        # 2. Growth Chart
        st.subheader("Growth Race 🏎️")
        df_sorted = df.sort_values(by='date')
        
        # Add "Start" point
        start_date = df_sorted['date'].min() - pd.Timedelta(days=1)
        start_points = []
        for name in df['name'].unique():
            start_points.append({
                'name': name,
                'date': start_date,
                'amount': baselines.get(name, 0),
                'growth_rate': 1.0
            })
        
        df_start = pd.DataFrame(start_points)
        df_chart = pd.concat([df_start, df_sorted], ignore_index=True).sort_values(by='date')
        df_chart['growth_rate_pct'] = (df_chart['growth_rate'] - 1) * 100

        fig = px.line(
            df_chart,
            x='date',
            y='growth_rate_pct',
            color='name',
            markers=True,
            title="Asset Growth Rate Over Time",
            labels={'growth_rate_pct': 'Growth (%)'}
        )
        fig.update_layout(yaxis_ticksuffix="%")
        fig.add_hline(y=0.0, line_dash="dash", line_color="lightgray")
        st.plotly_chart(fig, use_container_width=True)
else:
    st.info("데이터가 없습니다. 메인 시스템에서 잔고를 DB에 저장해야 합니다.")

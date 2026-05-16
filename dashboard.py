import streamlit as st
import pandas as pd
import os
import plotly.express as px
import yfinance as yf

st.set_page_config(page_title="NONE DASHBOARD", page_icon="📈")

# Configuration - 미국 주식 시스템 시작일로 기준점 변경
BASELINE_DATE = pd.Timestamp("2026-05-15")

st.title("🎢 None Festival")
st.subheader("Leaderboard: Who is the Growth King? :)")

import sqlite3

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
        raw = yf.download(ticker, start=start_date.strftime("%Y-%m-%d"), progress=False, auto_adjust=True)
        if raw.empty: return pd.DataFrame()
        data = raw[["Close"]].copy()
        data.index = pd.to_datetime(data.index).tz_localize(None).normalize() + pd.Timedelta(hours=16, minutes=30)
        data.columns = ["amount"]
        data["name"] = name
        data["date"] = data.index
        # Ensure today's price is included
        today_1630 = pd.Timestamp.now().normalize() + pd.Timedelta(hours=16, minutes=30)
        if today_1630 not in data.index:
            last_price = yf.Ticker(ticker).fast_info.last_price
            if last_price:
                patch = pd.DataFrame([{"amount": float(last_price), "name": name, "date": today_1630}], index=[today_1630])
                data = pd.concat([data, patch]).sort_index()
        return data
    except: return pd.DataFrame()

# Load all data (VOO instead of ^GSPC)
comparison_list = [
    ("VOO", "S&P 500 (VOO)"),
    ("BTC-USD", "Bitcoin"),
    ("USDKRW=X", "USD/KRW")
]

all_dfs = []
if not df_user.empty:
    df_user['date'] = pd.to_datetime(df_user['date']).dt.normalize() + pd.Timedelta(hours=16, minutes=30)
    df_user = df_user.sort_values('date').drop_duplicates(subset=['name', 'date'], keep='last')
    all_dfs.append(df_user[['name', 'date', 'amount']])

for ticker, name in comparison_list:
    comp_df = fetch_comparison(ticker, name, BASELINE_DATE)
    if not comp_df.empty:
        all_dfs.append(comp_df[['name', 'date', 'amount']])

if all_dfs:
    df = pd.concat(all_dfs, ignore_index=True)
    df = df[df['date'] >= BASELINE_DATE].copy()
    
    # Calculate Growth
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

    # 1. Leaderboard Metrics - SHOW ONLY USER
    st.markdown("### 👤 User Status")
    user_names = [n for n in df['name'].unique() if n not in ["S&P 500 (VOO)", "Bitcoin", "USD/KRW"]]
    if user_names:
        latest_user_df = df[df['name'].isin(user_names)].sort_values(by='date').groupby('name').tail(1)
        cols = st.columns(len(latest_user_df))
        for i, (idx, row) in enumerate(latest_user_df.iterrows()):
            with cols[i]:
                baseline = baselines.get(row['name'], row['amount'])
                net_change = row['amount'] - baseline
                try:
                    usd_rate = yf.Ticker("USDKRW=X").fast_info.last_price or 1350
                    net_profit_krw = net_change * usd_rate
                except: net_profit_krw = net_change * 1350
                
                st.metric(
                    label=row['name'],
                    value=f"{row['growth_rate_pct']:.2f}%",
                    delta=f"${net_change:,.2f} USD",
                    help=f"약 {net_profit_krw:,.0f} KRW"
                )
    else:
        st.info("사용자 데이터가 없습니다.")

    st.divider()

    # 2. Growth Chart - SHOW 4 ITEMS WITH CROWN/TURTLE
    st.subheader("Growth Race 🏎️")
    latest_all = df.sort_values(by='date').groupby('name').tail(1).sort_values(by='growth_rate_pct', ascending=False)
    crown_name = latest_all.iloc[0]['name']
    turtle_name = latest_all.iloc[-1]['name']
    
    def get_display_name(n):
        if n == crown_name: return f"👑 {n}"
        if n == turtle_name: return f"🐢 {n}"
        return n

    df_chart_data = df.copy()
    start_date = df_chart_data['date'].min() - pd.Timedelta(days=1)
    start_points = []
    for name in df_chart_data['name'].unique():
        start_points.append({'name': name, 'date': start_date, 'amount': baselines.get(name, 0), 'growth_rate': 1.0, 'growth_rate_pct': 0.0})
    
    df_chart = pd.concat([pd.DataFrame(start_points), df_chart_data], ignore_index=True).sort_values(by='date')
    df_chart['display_name'] = df_chart['name'].apply(get_display_name)

    fig = px.line(
        df_chart, x='date', y='growth_rate_pct', color='display_name', markers=True,
        title="Asset Growth Rate Over Time (Comparison)", labels={'growth_rate_pct': 'Growth (%)', 'display_name': 'Participant'}
    )
    fig.update_layout(yaxis_ticksuffix="%")
    fig.add_hline(y=0.0, line_dash="dash", line_color="lightgray")
    st.plotly_chart(fig, use_container_width=True)

    # 3. Volatility Table - SHOW ONLY USER
    st.divider()
    st.subheader("사용자 변동성 분석 📊")
    volatility_rows = []
    for name in user_names:
        user_df_sub = df[df['name'] == name].sort_values('date')
        latest_pct = (user_df_sub.iloc[-1]['growth_rate'] - 1) * 100
        if len(user_df_sub) < 2:
            volatility_rows.append({"이름": name, "수익률(USD)": f"{latest_pct:+.2f}%", "일일수익률": "N/A", "변동성": "N/A", "MDD": "N/A"})
            continue
        daily_returns = user_df_sub['growth_rate'].pct_change().dropna()
        volatility = daily_returns.std() * 100
        cumulative = user_df_sub['growth_rate']
        mdd = ((cumulative - cumulative.cummax()) / cumulative.cummax()).min() * 100
        daily_ret = (user_df_sub.iloc[-1]['amount'] / user_df_sub.iloc[-2]['amount'] - 1) * 100
        volatility_rows.append({
            "이름": name,
            "수익률(USD)": f"{latest_pct:+.2f}%",
            "일일수익률": f"{daily_ret:+.2f}%",
            "변동성": f"{volatility:.2f}%",
            "MDD": f"{mdd:.2f}%"
        })

    if volatility_rows:
        st.table(pd.DataFrame(volatility_rows))

else:
    st.info("데이터가 없습니다.")

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
        st.info("지정된 기준일(BASELINE_DATE) 이후의 데이터가 없습니다.")
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
        
        # Add "Start" point for visualization
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

        # Rankings for emoji
        non_sp500_latest = df_chart[~df_chart['name'].str.contains('S&P 500|Bitcoin|USD/KRW')].sort_values('date').groupby('name').tail(1)
        if not non_sp500_latest.empty:
            crown_name = non_sp500_latest.sort_values('growth_rate_pct', ascending=False).iloc[0]['name']
            turtle_name = non_sp500_latest.sort_values('growth_rate_pct', ascending=True).iloc[0]['name']
            df_chart['name_display'] = df_chart['name'].apply(
                lambda n: f"👑 {n}" if n == crown_name else (f"🐢 {n}" if n == turtle_name else n)
            )
        else:
            df_chart['name_display'] = df_chart['name']

        fig = px.line(
            df_chart,
            x='date',
            y='growth_rate_pct',
            color='name_display',
            markers=True,
            title="Asset Growth Rate Over Time",
            labels={'growth_rate_pct': 'Growth (%)', 'name_display': 'Participant'}
        )
        fig.update_layout(yaxis_ticksuffix="%")

        # Add External Comparison Lines
        SP500_START_DATE = BASELINE_DATE.strftime("%Y-%m-%d")
        TODAY_1630 = pd.Timestamp.now().normalize() + pd.Timedelta(hours=16, minutes=30)

        def ensure_today_bar(close_df, ticker):
            if TODAY_1630 in close_df.index: return close_df
            try:
                last_price = yf.Ticker(ticker).fast_info.last_price
                if last_price is None or pd.isna(last_price): return close_df
                patch = pd.DataFrame({"close": [float(last_price)]}, index=[TODAY_1630])
                return pd.concat([close_df, patch]).sort_index()
            except: return close_df

        # S&P 500
        try:
            sp500_raw = yf.download("^GSPC", start=SP500_START_DATE, progress=False, auto_adjust=True)
            if not sp500_raw.empty:
                sp500 = sp500_raw[["Close"]].copy()
                sp500.index = pd.to_datetime(sp500.index).tz_localize(None).normalize() + pd.Timedelta(hours=16, minutes=30)
                sp500.columns = ["close"]
                sp500 = ensure_today_bar(sp500, "^GSPC")
                start_price = sp500.iloc[0]["close"]
                sp500["growth"] = (sp500["close"] / start_price - 1) * 100
                fig.add_scatter(x=sp500.index, y=sp500["growth"], mode="lines", name="S&P 500", line=dict(color="gray", dash="dot", width=2))
        except: pass

        # Bitcoin
        try:
            btc_raw = yf.download("BTC-USD", start=SP500_START_DATE, progress=False, auto_adjust=True)
            if not btc_raw.empty:
                btc = btc_raw[["Close"]].copy()
                btc.index = pd.to_datetime(btc.index).tz_localize(None).normalize() + pd.Timedelta(hours=16, minutes=30)
                btc.columns = ["close"]
                btc = ensure_today_bar(btc, "BTC-USD")
                start_price = btc.iloc[0]["close"]
                btc["growth"] = (btc["close"] / start_price - 1) * 100
                fig.add_scatter(x=btc.index, y=btc["growth"], mode="lines", name="Bitcoin", line=dict(color="orange", dash="dot", width=2))
        except: pass

        # USD/KRW
        try:
            usd_raw = yf.download("USDKRW=X", start=SP500_START_DATE, progress=False, auto_adjust=True)
            if not usd_raw.empty:
                usd = usd_raw[["Close"]].copy()
                usd.index = pd.to_datetime(usd.index).tz_localize(None).normalize() + pd.Timedelta(hours=16, minutes=30)
                usd.columns = ["close"]
                usd = ensure_today_bar(usd, "USDKRW=X")
                start_price = usd.iloc[0]["close"]
                usd["growth"] = (usd["close"] / start_price - 1) * 100
                fig.add_scatter(x=usd.index, y=usd["growth"], mode="lines", name="USD/KRW", line=dict(color="green", dash="dot", width=2))
        except: pass

        fig.add_hline(y=0.0, line_dash="dash", line_color="lightgray")
        st.plotly_chart(fig, use_container_width=True)

        # 3. Volatility Comparison Table
        st.divider()
        st.subheader("변동성 비교 📊")
        volatility_rows = []

        for name in df['name'].unique():
            user_df = df[df['name'] == name].sort_values('date')
            latest_growth = (user_df.iloc[-1]['growth_rate'] - 1) * 100
            if len(user_df) < 2:
                volatility_rows.append({"이름": name, "현재 수익률": f"{latest_growth:+.2f}%", "일일수익률": "N/A", "변동성 (std)": "N/A", "MDD": "N/A", "_growth": latest_growth})
                continue
            daily_returns = user_df['growth_rate'].pct_change().dropna()
            volatility = daily_returns.std() * 100
            cumulative = user_df['growth_rate']
            mdd = ((cumulative - cumulative.cummax()) / cumulative.cummax()).min() * 100
            daily_return = (user_df.iloc[-1]['amount'] / user_df.iloc[-2]['amount'] - 1) * 100
            volatility_rows.append({"이름": name, "현재 수익률": f"{latest_growth:+.2f}%", "일일수익률": f"{daily_return:+.2f}%", "변동성 (std)": f"{volatility:.2f}%", "MDD": f"{mdd:.2f}%", "_growth": latest_growth})

        if volatility_rows:
            vol_df = pd.DataFrame(volatility_rows).sort_values("_growth", ascending=False)
            vol_df = vol_df.drop(columns=["_growth"])
            st.table(vol_df.reset_index(drop=True))
else:
    st.info("데이터가 없습니다.")

import streamlit as st
import pandas as pd
import os
import plotly.express as px
import yfinance as yf
from datetime import datetime
import pytz

# 페이지 설정
st.set_page_config(page_title="수익률 대시보드", page_icon="📈", layout="wide")

# 기준일 설정 (5/15)
BASELINE_DATE = pd.Timestamp("2026-05-15")

st.title("🎢 수익률 페스티벌")
st.subheader("누가 가장 많이 벌었을까요? :)")

import sqlite3

# 날짜 표시 변환 함수 (DB의 'YYYY-MM-DD'를 해당 거래일의 KST 장마감 시간으로 변환)
def convert_to_kst_morning(date_str):
    try:
        dt = pd.to_datetime(date_str)
        et_tz = pytz.timezone('US/Eastern')
        kst_tz = pytz.timezone('Asia/Seoul')
        # 미국 장 마감 16:00 + 1시간 = 17:00 (ET)
        # 이 시간은 한국 시간으로 다음 날 오전 6시(서머타임) 또는 7시임
        et_time = et_tz.localize(datetime(dt.year, dt.month, dt.day, 17, 0, 0))
        return et_time.astimezone(kst_tz)
    except:
        return pd.to_datetime(date_str)

# 사용자 데이터 불러오기
try:
    if os.path.exists("assets.db"):
        conn = sqlite3.connect("assets.db")
        df_user = pd.read_sql_query("SELECT * FROM assets", conn)
        conn.close()
    else:
        df_user = pd.DataFrame()
except:
    df_user = pd.DataFrame()

# 비교 데이터 불러오기 함수
@st.cache_data(ttl=600)
def fetch_comparison(ticker, name, start_date):
    try:
        # 기준일 이전 데이터부터 가져와서 기준일 시점의 종가를 확보
        fetch_start = start_date - pd.Timedelta(days=5)
        raw = yf.download(ticker, start=fetch_start.strftime("%Y-%m-%d"), progress=False, auto_adjust=True)
        if raw.empty: return pd.DataFrame()
        
        data = raw["Close"]
        if not isinstance(data, pd.Series):
            data = data.iloc[:, 0]
            
        new_rows = []
        for dt, price in data.items():
            # US 거래일 dt의 마감 시간 -> KST 오전
            kst_time = convert_to_kst_morning(dt)
            new_rows.append({"amount": float(price), "name": name, "date": kst_time})
        
        return pd.DataFrame(new_rows)
    except:
        return pd.DataFrame()

# 데이터 로드
comparison_list = [
    ("VOO", "S&P 500 (VOO)"),
    ("BTC-USD", "비트코인"),
    ("USDKRW=X", "USD/KRW 환율")
]

all_dfs = []

# 1. 사용자 데이터 처리
if not df_user.empty:
    # 5/15일 데이터는 사용자가 현금을 보유한 '시작 시점'이므로 
    # 5/15 06:00 (목요일 장마감 결과)가 아니라 5/15 저녁으로 간주해야 함
    # 하지만 단순화를 위해 DB 날짜를 거래일로 보고 KST 오전으로 변환
    df_user['date'] = df_user['date'].apply(convert_to_kst_morning)
    df_user = df_user.sort_values('date').drop_duplicates(subset=['name', 'date'], keep='last')
    all_dfs.append(df_user[['name', 'date', 'amount']])

# 2. 비교 데이터 처리
for ticker, name in comparison_list:
    comp_df = fetch_comparison(ticker, name, BASELINE_DATE)
    if not comp_df.empty:
        all_dfs.append(comp_df[['name', 'date', 'amount']])

if all_dfs:
    df = pd.concat(all_dfs, ignore_index=True)
    df['name'] = df['name'].astype(str).str.strip()
    
    # KST 오전 시간 기준으로 5/15 06:00 이후 데이터 필터링
    # 5/15 데이터(목요일 장 결과)가 기준점이 됨
    df = df[df['date'].dt.tz_localize(None) >= BASELINE_DATE].copy()
    
    if df.empty:
        st.warning("데이터가 없습니다.")
    else:
        # 수익률 계산 (각 항목의 가장 빠른 데이터를 1.0으로 설정)
        baselines = {}
        for name in df['name'].unique():
            sub = df[df['name'] == name].sort_values('date')
            baselines[name] = sub.iloc[0]['amount']
        
        df['growth_rate'] = df.apply(lambda r: r['amount'] / baselines[r['name']], axis=1)
        df['growth_rate_pct'] = (df['growth_rate'] - 1) * 100

        # 최신 데이터 정렬
        latest_all = df.sort_values(by='date').groupby('name').tail(1).sort_values(by='growth_rate_pct', ascending=False)
        crown_name = latest_all.iloc[0]['name']
        turtle_name = latest_all.iloc[-1]['name']
        
        def get_display_name(n):
            if n == crown_name: return f"👑 {n}"
            if n == turtle_name: return f"🐢 {n}"
            return n

        # 1. 리더보드
        st.subheader("🏆 리더보드")
        cols = st.columns(len(latest_all))
        for i, (idx, row) in enumerate(latest_all.iterrows()):
            with cols[i]:
                baseline = baselines.get(row['name'], row['amount'])
                net_change = row['amount'] - baseline
                label = get_display_name(row['name'])
                
                if "S&P 500" in row['name'] or "비트코인" in row['name']:
                    delta_val = f"{net_change:+.2f} USD"
                elif "USD/KRW" in row['name']:
                    delta_val = f"{net_change:+.2f} KRW"
                else:
                    delta_val = f"${net_change:+.2f} USD"
                
                st.metric(label=label, value=f"{row['growth_rate_pct']:.2f}%", delta=delta_val, help=f"최종 기록: {row['date'].strftime('%m/%d %H:%M')}")

        st.divider()

        # 2. 그래프
        st.subheader("🏎️ 수익률 레이스")
        df_chart = df.sort_values(by='date')
        df_chart['참가자'] = df_chart['name'].apply(get_display_name)
        
        fig = px.line(
            df_chart, x='date', y='growth_rate_pct', color='참가자', markers=True,
            title="수익률 추이 (기준: 5/15)",
            labels={'growth_rate_pct': '수익률 (%)', 'date': '날짜'}
        )
        fig.update_layout(yaxis_ticksuffix="%")
        st.plotly_chart(fig, use_container_width=True)

        # 3. 테이블
        st.subheader("📊 종합 변동성 분석")
        vol_rows = []
        for name in latest_all['name']:
            sub = df[df['name'] == name].sort_values('date')
            display = get_display_name(name)
            if len(sub) < 2:
                vol_rows.append({"이름": display, "수익률": f"{sub.iloc[-1]['growth_rate_pct']:+.2f}%", "일일 수익": "0.00%", "변동성": "0.00%", "MDD": "0.00%"})
                continue
            
            d_ret = (sub.iloc[-1]['amount'] / sub.iloc[-2]['amount'] - 1) * 100
            vol = sub['growth_rate'].pct_change().std() * 100
            mdd = ((sub['growth_rate'] - sub['growth_rate'].cummax()) / sub['growth_rate'].cummax()).min() * 100
            vol_rows.append({"이름": display, "현재 수익률": f"{sub.iloc[-1]['growth_rate_pct']:+.2f}%", "일일 수익": f"{d_ret:+.2f}%", "변동성": f"{vol:.2f}%", "MDD": f"{mdd:.2f}%"})
        st.table(pd.DataFrame(vol_rows))

else:
    st.info("데이터를 불러오는 중입니다...")

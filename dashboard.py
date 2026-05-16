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

# 날짜 표시 변환 함수 (거래일 -> KST 오전)
def convert_to_kst_morning(date_dt):
    try:
        et_tz = pytz.timezone('US/Eastern')
        kst_tz = pytz.timezone('Asia/Seoul')
        # 미국 장 마감 16:00 + 1시간 = 17:00 (ET)
        et_time = et_tz.localize(datetime(date_dt.year, date_dt.month, date_dt.day, 17, 0, 0))
        return et_time.astimezone(kst_tz)
    except:
        return date_dt

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
        fetch_start = start_date - pd.Timedelta(days=5)
        raw = yf.download(ticker, start=fetch_start.strftime("%Y-%m-%d"), progress=False, auto_adjust=True)
        if raw.empty: return pd.DataFrame()
        
        data = raw["Close"]
        if not isinstance(data, pd.Series):
            data = data.iloc[:, 0]
            
        new_rows = []
        now_kst = datetime.now(pytz.timezone('Asia/Seoul'))
        
        for dt, price in data.items():
            kst_time = convert_to_kst_morning(dt)
            # 현재 시간보다 미래(내일 아침 등)는 제외
            if kst_time > now_kst:
                continue
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
    df_user['date_dt'] = pd.to_datetime(df_user['date'])
    df_user['date'] = df_user['date_dt'].apply(convert_to_kst_morning)
    
    # 미래 데이터 제외
    now_kst = datetime.now(pytz.timezone('Asia/Seoul'))
    df_user = df_user[df_user['date'] <= now_kst]
    
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
    
    # 기준일(5/15) 이후 데이터 필터링
    df = df[df['date'].dt.tz_localize(None) >= BASELINE_DATE].copy()
    
    if df.empty:
        st.warning("데이터가 없습니다.")
    else:
        # 수익률 계산
        baselines = {}
        for name in df['name'].unique():
            sub = df[df['name'] == name].sort_values('date')
            baselines[name] = sub.iloc[0]['amount']
        
        df['growth_rate'] = df.apply(lambda r: r['amount'] / baselines[r['name']], axis=1)
        df['growth_rate_pct'] = (df['growth_rate'] - 1) * 100

        # 최신 데이터
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
            title="수익률 추이 (5/15 ~ 현재)",
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
                vol_rows.append({"이름": display, "현재 수익률": f"{sub.iloc[-1]['growth_rate_pct']:+.2f}%", "일일 수익": "0.00%", "변동성": "0.00%", "MDD": "0.00%"})
                continue
            
            d_ret = (sub.iloc[-1]['amount'] / sub.iloc[-2]['amount'] - 1) * 100
            vol = sub['growth_rate'].pct_change().std() * 100
            mdd = ((sub['growth_rate'] - sub['growth_rate'].cummax()) / sub['growth_rate'].cummax()).min() * 100
            vol_rows.append({"이름": display, "현재 수익률": f"{sub.iloc[-1]['growth_rate_pct']:+.2f}%", "일일 수익": f"{d_ret:+.2f}%", "변동성": f"{vol:.2f}%", "MDD": f"{mdd:.2f}%"})
        st.table(pd.DataFrame(vol_rows))

else:
    st.info("데이터를 불러오는 중입니다...")

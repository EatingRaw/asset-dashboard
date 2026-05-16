import streamlit as st
import pandas as pd
import os
import plotly.express as px
import yfinance as yf
from datetime import datetime, timedelta
import pytz

# 페이지 설정
st.set_page_config(page_title="수익률 대시보드", page_icon="📈", layout="wide")

# 설정 - 사용자가 지정한 첫 기록일(5/16)로 기준점 변경
BASELINE_DATE = pd.Timestamp("2026-05-16")

st.title("🎢 수익률 페스티벌")
st.subheader("누가 가장 많이 벌었을까요? :)")

import sqlite3

# 장 마감 시간 + 1시간 (KST) 계산 함수
def get_market_close_time_kst(dt):
    try:
        et_tz = pytz.timezone('US/Eastern')
        kst_tz = pytz.timezone('Asia/Seoul')
        # 미국 장 마감 16:00 + 1시간 = 17:00 (ET)
        et_time = et_tz.localize(datetime(dt.year, dt.month, dt.day, 17, 0, 0))
        kst_time = et_time.astimezone(kst_tz)
        return kst_time
    except:
        return dt

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
@st.cache_data(ttl=3600)
def fetch_comparison(ticker, name, start_date):
    try:
        # 기준일보다 며칠 전부터 가져와서 기준일 데이터를 확보
        fetch_start = start_date - pd.Timedelta(days=5)
        raw = yf.download(ticker, start=fetch_start.strftime("%Y-%m-%d"), progress=False, auto_adjust=True)
        if raw.empty: return pd.DataFrame()
        
        # 'Close' 데이터 추출
        if "Close" in raw.columns:
            data = raw["Close"]
        else:
            data = raw.xs('Close', axis=1, level=0)
            
        if isinstance(data, pd.Series):
            data = data.to_frame()
            
        close_prices = data.iloc[:, 0]
        
        new_rows = []
        for dt, price in close_prices.items():
            # US 날짜 dt의 장 마감 + 1시간 KST 계산
            kst_close = get_market_close_time_kst(dt)
            # 미래 날짜는 제외 (주말 등 처리)
            if kst_close.tz_localize(None) > datetime.now():
                continue
            new_rows.append({"amount": float(price), "name": name, "date": kst_close})
        
        res = pd.DataFrame(new_rows)
        
        # 현재 장 중인 경우 실시간 가격 추가 (주말 제외)
        now = datetime.now()
        # 주말(토, 일) 체크 - 토요일 오전까지는 금요일 장 데이터가 최신임
        if now.weekday() < 5 or (now.weekday() == 5 and now.hour < 7): # 월~금 또는 토요일 새벽
            ticker_obj = yf.Ticker(ticker)
            last_price = ticker_obj.fast_info.last_price
            if last_price:
                # 가장 최근 ET 영업일 기준 KST 장마감 시간
                today_close = get_market_close_time_kst(now)
                # 이미 리스트에 있는 시간보다 나중이고, 현재 시간보다는 전일 때만 추가
                if today_close > res["date"].max() and today_close.tz_localize(None) <= now:
                    res = pd.concat([res, pd.DataFrame([{"amount": float(last_price), "name": name, "date": today_close}])])
        
        return res
    except Exception as e:
        return pd.DataFrame()

# 데이터 로드
comparison_list = [
    ("VOO", "S&P 500 (VOO)"),
    ("BTC-USD", "비트코인"),
    ("USDKRW=X", "USD/KRW 환율")
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
    df['name'] = df['name'].astype(str).str.strip()
    
    # 기준일(5/16) 이후 데이터만 사용
    df = df[df['date'].dt.tz_localize(None) >= BASELINE_DATE].copy()
    
    if df.empty:
        st.warning("기준일(2026-05-16) 이후의 데이터가 없습니다.")
    else:
        # 수익률 계산
        baselines = {}
        for name in df['name'].unique():
            sub = df[df['name'] == name].sort_values('date')
            if not sub.empty:
                baselines[name] = sub.iloc[0]['amount']
        
        df['growth_rate'] = df.apply(
            lambda r: r['amount'] / baselines[r['name']] if baselines.get(r['name']) else 1.0,
            axis=1,
        )
        df['growth_rate_pct'] = (df['growth_rate'] - 1) * 100

        latest_all = df.sort_values(by='date').groupby('name').tail(1).sort_values(by='growth_rate_pct', ascending=False)
        crown_name = latest_all.iloc[0]['name']
        turtle_name = latest_all.iloc[-1]['name']
        
        def get_display_name(n):
            if n == crown_name: return f"👑 {n}"
            if n == turtle_name: return f"🐢 {n}"
            return n

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
                st.metric(label=label, value=f"{row['growth_rate_pct']:.2f}%", delta=delta_val, help=f"기록시간: {row['date'].strftime('%m/%d %H:%M')}")

        st.divider()
        st.subheader("🏎️ 수익률 레이스")
        df_chart_data = df.copy()
        
        # 시작점 설정
        first_date = df_chart_data['date'].min()
        start_points = []
        for name in df_chart_data['name'].unique():
            start_points.append({'name': name, 'date': first_date - pd.Timedelta(minutes=1), 'amount': baselines.get(name, 0), 'growth_rate': 1.0, 'growth_rate_pct': 0.0})
        
        df_chart = pd.concat([pd.DataFrame(start_points), df_chart_data], ignore_index=True).sort_values(by='date')
        df_chart['이름'] = df_chart['name'].apply(get_display_name)
        fig = px.line(df_chart, x='date', y='growth_rate_pct', color='이름', markers=True, title="시간 경과에 따른 수익률 비교", labels={'growth_rate_pct': '수익률 (%)', 'date': '날짜', '이름': '참가자'})
        fig.update_layout(yaxis_ticksuffix="%")
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("📊 종합 변동성 분석")
        vol_rows = []
        for name in latest_all['name']:
            sub = df[df['name'] == name].sort_values('date')
            display = get_display_name(name)
            if len(sub) < 2:
                vol_rows.append({"이름": display, "현재 수익률": f"{sub.iloc[-1]['growth_rate_pct']:+.2f}%", "일일 수익": "N/A", "변동성": "N/A", "MDD": "N/A"})
                continue
            d_ret = (sub.iloc[-1]['amount'] / sub.iloc[-2]['amount'] - 1) * 100
            vol = sub['growth_rate'].pct_change().std() * 100
            mdd = ((sub['growth_rate'] - sub['growth_rate'].cummax()) / sub['growth_rate'].cummax()).min() * 100
            vol_rows.append({"이름": display, "현재 수익률": f"{sub.iloc[-1]['growth_rate_pct']:+.2f}%", "일일 수익": f"{d_ret:+.2f}%", "변동성": f"{vol:.2f}%", "MDD": f"{mdd:.2f}%"})
        st.table(pd.DataFrame(vol_rows))
else:
    st.info("데이터를 불러오는 중입니다... 잠시만 기다려주세요.")

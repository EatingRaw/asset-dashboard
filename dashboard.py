import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import os
import plotly.express as px
import yfinance as yf
from datetime import datetime
import pytz

# 페이지 설정
st.set_page_config(page_title="수익률 대시보드", page_icon="📈", layout="wide")

# 절전모드 방지: Wake Lock + 자동 새로고침
components.html("""
<script>
    // 5분마다 자동 새로고침 (Streamlit Cloud 절전 방지)
    setTimeout(function() {
        window.parent.location.reload();
    }, 300000);

    // Wake Lock API (브라우저 탭 절전/화면 꺼짐 방지)
    let wakeLock = null;
    async function requestWakeLock() {
        try {
            if ('wakeLock' in navigator) {
                wakeLock = await navigator.wakeLock.request('screen');
            }
        } catch (err) {}
    }
    requestWakeLock();
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') requestWakeLock();
    });
</script>
""", height=0)

# 기준일 설정
BASELINE_DATE = pd.Timestamp("2026-05-15")

st.title("🎢 수익률 페스티벌")
st.subheader("누가 가장 많이 벌었을까요? :)")

import sqlite3

# 달러 delta 포맷 (부호를 $ 앞에 배치: -$53.13)
def fmt_delta(val):
    if val >= 0:
        return f"+${val:,.2f}"
    else:
        return f"-${abs(val):,.2f}"

# US 거래일을 KST 오전 시간으로 변환 (거래일 + 1일 오전 6시)
def convert_us_date_to_kst(us_date):
    try:
        kst_date = pd.to_datetime(us_date) + pd.Timedelta(hours=6)
        return kst_date
    except:
        return us_date

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
        now_kst = datetime.now(pytz.timezone('Asia/Seoul')).replace(tzinfo=None)
        
        for dt, price in data.items():
            # US 거래일 dt -> KST 다음날 오전 6시
            kst_time = pd.to_datetime(dt) + pd.Timedelta(days=1, hours=6)
            if kst_time > now_kst:
                continue
            new_rows.append({"amount": float(price), "name": name, "date": kst_time})
        
        return pd.DataFrame(new_rows)
    except:
        return pd.DataFrame()

# 데이터 로드 (원화 비교 항목 제거)
comparison_list = [
    ("VOO", "S&P 500 (VOO)"),
    ("BTC-USD", "비트코인"),
]

all_dfs = []

# 1. 사용자 데이터 처리 (DB 날짜를 그대로 사용하되 오전 6시로 설정)
if not df_user.empty:
    df_user['date'] = pd.to_datetime(df_user['date']) + pd.Timedelta(hours=6)
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
    df = df[df['date'] >= BASELINE_DATE].copy()
    
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

        # 시작 자산 / 계좌 수익률 표시 (사용자 데이터가 있을 경우)
        user_names = df_user['name'].unique() if not df_user.empty else []
        for uname in user_names:
            uname = str(uname).strip()
            if uname in baselines:
                initial_amount = baselines[uname]
                # 최신 금액
                user_latest = latest_all[latest_all['name'] == uname]
                if not user_latest.empty:
                    current_amount = user_latest.iloc[0]['amount']
                    growth_pct = user_latest.iloc[0]['growth_rate_pct']
                    net_change = current_amount - initial_amount
                    
                    info_cols = st.columns(3)
                    with info_cols[0]:
                        st.metric(
                            label="💰 시작 자산",
                            value=f"${initial_amount:,.2f}",
                            help=f"기준일: {BASELINE_DATE.strftime('%Y/%m/%d')}"
                        )
                    with info_cols[1]:
                        st.metric(
                            label="📊 현재 자산",
                            value=f"${current_amount:,.2f}",
                            delta=fmt_delta(net_change)
                        )
                    with info_cols[2]:
                        st.metric(
                            label="📈 계좌 수익률",
                            value=f"{growth_pct:+.2f}%",
                            delta=fmt_delta(net_change),
                            help=f"기준일({BASELINE_DATE.strftime('%m/%d')}) 대비"
                        )
                    st.divider()

        st.subheader("🏆 리더보드")
        cols = st.columns(len(latest_all))
        for i, (idx, row) in enumerate(latest_all.iterrows()):
            with cols[i]:
                baseline = baselines.get(row['name'], row['amount'])
                net_change = row['amount'] - baseline
                label = get_display_name(row['name'])
                delta_val = fmt_delta(net_change)
                st.metric(label=label, value=f"{row['growth_rate_pct']:.2f}%", delta=delta_val, help=f"최종 기록: {row['date'].strftime('%m/%d %H:%M')}")

        st.divider()
        st.subheader("🏎️ 수익률 레이스")
        df_chart = df.sort_values(by='date')
        df_chart['참가자'] = df_chart['name'].apply(get_display_name)
        
        # 차트 제목 동적 생성
        min_date = df_chart['date'].min()
        max_date = df_chart['date'].max()
        start_date_str = min_date.strftime('%m/%d') if not pd.isna(min_date) else ""
        end_date_str = max_date.strftime('%m/%d') if not pd.isna(max_date) else ""
        chart_title = f"수익률 추이 ({start_date_str} ~ {end_date_str})"
        
        fig = px.line(df_chart, x='date', y='growth_rate_pct', color='참가자', markers=True, title=chart_title, labels={'growth_rate_pct': '수익률 (%)', 'date': '날짜'})
        fig.update_layout(yaxis_ticksuffix="%")
        st.plotly_chart(fig, use_container_width=True)

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

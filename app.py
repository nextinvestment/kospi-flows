"""KOSPI 수급 분석 대시보드."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import store
from config import WATCHLIST, KOSPI200_PROXY_CODE, KOSPI200_PROXY_NAME

st.set_page_config(page_title="KOSPI 수급 분석", layout="wide")
st.title("KOSPI 수급 분석")


@st.cache_data(ttl=600)
def _market(market: str = "KOSPI") -> pd.DataFrame:
    df = store.load_market(market)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


@st.cache_data(ttl=600)
def _stocks() -> pd.DataFrame:
    df = store.load_stocks()
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        df["foreign_value"] = df["foreign_net"] * df["close"] / 1e8  # 억원
        df["inst_value"] = df["inst_net"] * df["close"] / 1e8
    return df


market = _market("KOSPI")
stocks = _stocks()

if market.empty:
    st.error("데이터가 없습니다. `python run_daily.py backfill` 먼저 실행하세요.")
    st.stop()

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["오늘의 수급", "일별·누적 (KOSPI)", "종목별 추적", "종목 랭킹", "KOSPI200 proxy"]
)


# --------------------------------------------------------------------- TAB 1
with tab1:
    latest = market.iloc[-1]
    st.subheader(f"{latest['date'].date()} KOSPI 투자자별 순매수 (단위: 억원)")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("외국인", f"{latest['외국인']:+,.0f}")
    c2.metric("기관계", f"{latest['기관계']:+,.0f}")
    c3.metric("개인", f"{latest['개인']:+,.0f}")
    c4.metric("기타법인", f"{latest['기타법인']:+,.0f}")

    st.markdown("### 기관 세부")
    inst_cols = ["금융투자", "보험", "투신", "은행", "기타금융", "연기금등"]
    cols = st.columns(len(inst_cols))
    for col, name in zip(cols, inst_cols):
        col.metric(name, f"{latest[name]:+,.0f}")

    st.markdown("### 최근 10거래일")
    recent = market.tail(10).iloc[::-1].copy()
    recent["date"] = recent["date"].dt.strftime("%Y-%m-%d")
    st.dataframe(
        recent[["date", "외국인", "기관계", "개인", "금융투자", "연기금등", "기타법인"]],
        use_container_width=True,
        hide_index=True,
    )


# --------------------------------------------------------------------- TAB 2
with tab2:
    st.subheader("KOSPI 일별 + 누적 순매수")
    lookback = st.slider("조회 기간 (일)", 30, min(800, len(market)), 180, key="lb_market")
    df = market.tail(lookback).copy()

    fig = go.Figure()
    for col, color in [("외국인", "crimson"), ("기관계", "royalblue"), ("개인", "darkorange")]:
        fig.add_bar(x=df["date"], y=df[col], name=col, marker_color=color, opacity=0.6)
    fig.update_layout(barmode="group", height=400, title="일별 순매수 (억원)", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### 누적 순매수")
    cum = df.copy()
    for c in ["외국인", "기관계", "개인"]:
        cum[c] = cum[c].cumsum()
    fig2 = go.Figure()
    for col, color in [("외국인", "crimson"), ("기관계", "royalblue"), ("개인", "darkorange")]:
        fig2.add_scatter(x=cum["date"], y=cum[col], mode="lines", name=col, line=dict(color=color, width=2))
    fig2.add_hline(y=0, line_dash="dash", line_color="gray")
    fig2.update_layout(height=400, title=f"기간 누적 (직전 {lookback} 거래일)", hovermode="x unified")
    st.plotly_chart(fig2, use_container_width=True)

    st.markdown("#### 월별 누적")
    monthly = market.copy()
    monthly["월"] = monthly["date"].dt.to_period("M").astype(str)
    agg = monthly.groupby("월")[["외국인", "기관계", "개인"]].sum().reset_index().tail(18)
    fig3 = go.Figure()
    for col, color in [("외국인", "crimson"), ("기관계", "royalblue"), ("개인", "darkorange")]:
        fig3.add_bar(x=agg["월"], y=agg[col], name=col, marker_color=color)
    fig3.update_layout(barmode="group", height=400, title="월별 순매수 합계 (억원)")
    st.plotly_chart(fig3, use_container_width=True)


# --------------------------------------------------------------------- TAB 3
with tab3:
    st.subheader("종목별 외국인·기관 매매 추적")
    if stocks.empty:
        st.info("종목 데이터가 없습니다. backfill을 먼저 실행하세요.")
    else:
        options = {f"{name} ({code})": code for code, name in WATCHLIST.items() if code in stocks["code"].unique()}
        pick = st.selectbox("종목 선택", options.keys())
        code = options[pick]
        s = stocks[stocks["code"] == code].sort_values("date")

        # Price + foreign holding pct
        fig = go.Figure()
        fig.add_scatter(x=s["date"], y=s["close"], name="종가", yaxis="y1", line=dict(color="black"))
        fig.add_scatter(x=s["date"], y=s["foreign_pct"], name="외국인 보유율 (%)",
                        yaxis="y2", line=dict(color="green", dash="dot"))
        fig.update_layout(
            height=380, title=f"{pick} 가격 · 외국인 보유율",
            yaxis=dict(title="종가"),
            yaxis2=dict(title="외국인 보유율 (%)", overlaying="y", side="right"),
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)

        # Daily net (shares converted to 억원)
        fig2 = go.Figure()
        fig2.add_bar(x=s["date"], y=s["foreign_value"], name="외국인 순매수 (억원)", marker_color="crimson", opacity=0.7)
        fig2.add_bar(x=s["date"], y=s["inst_value"], name="기관 순매수 (억원)", marker_color="royalblue", opacity=0.7)
        fig2.update_layout(barmode="group", height=350, title="일별 외국인·기관 순매수 (종가환산 억원)", hovermode="x unified")
        st.plotly_chart(fig2, use_container_width=True)

        # Cumulative
        cs = s.copy()
        cs["외국인 누적"] = cs["foreign_value"].cumsum()
        cs["기관 누적"] = cs["inst_value"].cumsum()
        fig3 = go.Figure()
        fig3.add_scatter(x=cs["date"], y=cs["외국인 누적"], name="외국인 누적", line=dict(color="crimson"))
        fig3.add_scatter(x=cs["date"], y=cs["기관 누적"], name="기관 누적", line=dict(color="royalblue"))
        fig3.add_hline(y=0, line_dash="dash", line_color="gray")
        fig3.update_layout(height=350, title="기간 누적 (억원)", hovermode="x unified")
        st.plotly_chart(fig3, use_container_width=True)


# --------------------------------------------------------------------- TAB 4
with tab4:
    st.subheader("일별 종목 랭킹 (워치리스트 내)")
    if stocks.empty:
        st.info("종목 데이터가 없습니다.")
    else:
        dates = sorted(stocks["date"].unique(), reverse=True)
        d_sel = st.selectbox("날짜", dates, format_func=lambda x: pd.Timestamp(x).strftime("%Y-%m-%d"))
        day = stocks[stocks["date"] == d_sel].copy()
        day["종목명"] = day["code"].map(WATCHLIST)
        day = day[["종목명", "code", "close", "ret_pct", "foreign_value", "inst_value", "foreign_pct"]]
        day = day.rename(columns={
            "code": "코드", "close": "종가", "ret_pct": "등락률(%)",
            "foreign_value": "외국인순매수(억)", "inst_value": "기관순매수(억)",
            "foreign_pct": "외국인보유율(%)",
        })

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### 외국인 순매수 상위")
            st.dataframe(day.sort_values("외국인순매수(억)", ascending=False).head(10),
                         hide_index=True, use_container_width=True)
        with c2:
            st.markdown("#### 외국인 순매도 상위")
            st.dataframe(day.sort_values("외국인순매수(억)", ascending=True).head(10),
                         hide_index=True, use_container_width=True)

        # Cumulative ranking over a window
        st.markdown("#### N일 누적 외국인 순매수 (워치리스트)")
        window = st.slider("기간 (거래일)", 5, 60, 20, key="cum_window")
        recent_dates = sorted(stocks["date"].unique(), reverse=True)[:window]
        w = stocks[stocks["date"].isin(recent_dates)].copy()
        w["종목명"] = w["code"].map(WATCHLIST)
        cum = w.groupby(["code", "종목명"])[["foreign_value", "inst_value"]].sum().reset_index()
        cum = cum.rename(columns={"foreign_value": "외국인누적(억)", "inst_value": "기관누적(억)"})
        cum = cum.sort_values("외국인누적(억)", ascending=False)
        st.dataframe(cum, hide_index=True, use_container_width=True)


# --------------------------------------------------------------------- TAB 5
with tab5:
    st.subheader(f"{KOSPI200_PROXY_NAME}")
    st.caption(
        "네이버에서 KOSPI 200 선물 투자자별 데이터는 제공되지 않아, "
        "KODEX 200 ETF (069500)의 외국인·기관 매매를 선물 수급의 proxy로 사용합니다."
    )
    if stocks.empty or KOSPI200_PROXY_CODE not in stocks["code"].unique():
        st.warning(f"{KOSPI200_PROXY_CODE} 데이터가 없습니다. backfill 실행 필요.")
    else:
        s = stocks[stocks["code"] == KOSPI200_PROXY_CODE].sort_values("date")
        # 5 + 20 + 60 day cumulative for foreign
        latest_row = s.iloc[-1]
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("종가", f"{latest_row['close']:,.0f}")
        c2.metric("최근 5일 외국인 누적(억)", f"{s.tail(5)['foreign_value'].sum():+,.0f}")
        c3.metric("최근 20일 외국인 누적(억)", f"{s.tail(20)['foreign_value'].sum():+,.0f}")
        c4.metric("최근 60일 외국인 누적(억)", f"{s.tail(60)['foreign_value'].sum():+,.0f}")

        fig = go.Figure()
        fig.add_scatter(x=s["date"], y=s["close"], name="069500 종가", yaxis="y1", line=dict(color="black"))
        cum_f = s["foreign_value"].cumsum()
        fig.add_scatter(x=s["date"], y=cum_f, name="외국인 누적 (억원)", yaxis="y2", line=dict(color="crimson"))
        fig.update_layout(
            height=420, title="069500 가격 vs 외국인 누적 순매수",
            yaxis=dict(title="종가"),
            yaxis2=dict(title="외국인 누적 (억원)", overlaying="y", side="right"),
            hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)


st.divider()
st.caption(
    f"데이터 출처: Naver Finance · 최근 갱신: {market['date'].max().strftime('%Y-%m-%d')} · "
    f"`python run_daily.py` 로 갱신"
)

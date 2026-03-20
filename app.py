"""
NewsFlow Day Trading Scanner
=============================
Momentum pullback strategy — find news-driven stocks,
wait for the pullback, enter when momentum resumes.

Optimised for:
  • Small accounts ($500–$2,000)
  • Intraday only — no overnight holds
  • Momentum pullback entries
  • Tight ATR-based stops on 15min chart

Deploy: push to GitHub → share.streamlit.io
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import datetime
import time
import pytz

# ─────────────────────────────────────────────
#  PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="NewsFlow Day Trader",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.block-container { padding-top: 1.2rem; }
.buy-pill   { background:#0d6b45; color:#d4f0e4; padding:3px 12px; border-radius:12px; font-weight:700; font-size:14px; }
.wait-pill  { background:#7a4e00; color:#fff3d4; padding:3px 12px; border-radius:12px; font-weight:700; font-size:14px; }
.avoid-pill { background:#8b1a1a; color:#fde0e0; padding:3px 12px; border-radius:12px; font-weight:700; font-size:14px; }
.conf-bar   { height:8px; border-radius:6px; margin-top:4px; }
.news-hl    { font-size:12px; color:#bbb; font-style:italic; margin:2px 0; }
.rule-box   { background:#1a1a2e; border:1px solid #2a2a4e; border-radius:8px; padding:12px 16px; font-size:13px; }
.tag        { display:inline-block; padding:2px 8px; border-radius:10px; font-size:11px; font-weight:600; margin:1px; }
.tag-gap    { background:#1a3a5c; color:#60b4ff; }
.tag-vol    { background:#1a5c2a; color:#60ff8a; }
.tag-mom    { background:#3a1a5c; color:#c060ff; }
.tag-news   { background:#5c3a1a; color:#ffb060; }
div[data-testid="stMetricValue"] { font-size:1.6rem; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
#  WATCHLISTS
# ─────────────────────────────────────────────
WATCHLISTS = {
    "⚡ Day Trading Favorites (50)": [
        "AAPL","MSFT","NVDA","AMD","META","TSLA","AMZN","GOOGL","NFLX","COIN",
        "PLTR","SOFI","HOOD","RIVN","NIO","UBER","SNAP","RBLX","SHOP","PYPL",
        "SQ","ROKU","TWLO","NET","DDOG","CRWD","ZS","OKTA","SNOW","ABNB",
        "LYFT","SPOT","PINS","WISH","GME","AMC","BB","SPCE","SNDL","TLRY",
        "F","GM","INTC","BAC","GS","JPM","XOM","CVX","SPY","QQQ",
    ],
    "💻 Tech (20)": [
        "AAPL","MSFT","NVDA","AMD","INTC","AVGO","QCOM","ORCL","CRM","ADBE",
        "SHOP","NET","TWLO","SNOW","DDOG","ZS","CRWD","OKTA","PLTR","COIN",
    ],
    "🚀 High Vol / Meme (20)": [
        "GME","AMC","SPCE","CLOV","NKLA","SNDL","TLRY","BB","NOK","WISH",
        "CTRM","SENS","GNUS","BBIG","ATER","PROG","MVIS","WKHS","RIVN","LCID",
    ],
    "🏦 Finance (15)": [
        "JPM","BAC","GS","MS","V","MA","PYPL","SQ","HOOD","SOFI",
        "C","WFC","AXP","COF","COIN",
    ],
}

# ─────────────────────────────────────────────
#  NEWS SCORING  (same engine as v2)
# ─────────────────────────────────────────────
BULLISH_KW = [
    "beat","beats","exceeds","record","surge","soar","rally","upgrade",
    "raised","raise","growth","profit","bullish","breakout","buy",
    "outperform","strong","positive","boost","deal","acquisition",
    "contract","partnership","launch","approval","dividend","buyback",
    "guidance raised","revenue growth","topped estimates","better than expected",
    "raises forecast","price target raised","analyst upgrade","strong demand",
]
BEARISH_KW = [
    "miss","misses","below","decline","drop","fall","downgrade","cut",
    "loss","bearish","lawsuit","investigation","recall","warning","layoff",
    "layoffs","bankruptcy","debt","sell","underperform","weak","negative",
    "concern","probe","fine","guidance cut","guidance lowered","disappointing",
    "missed estimates","worse than expected","lowers forecast","analyst downgrade",
    "revenue decline","faces pressure","regulatory risk",
]

def score_news(news_items):
    if not news_items:
        return {"score": 50, "direction": "neutral", "confidence": 0,
                "headlines": [], "reason": "No news found.", "count": 0, "fresh": False}

    now = datetime.datetime.now(datetime.timezone.utc).timestamp()
    bull, bear = 0.0, 0.0
    scored, fresh = [], False

    for item in news_items[:20]:
        content   = item.get("content", {})
        title_raw = content.get("title") or item.get("title") or ""
        title     = title_raw.lower()
        pub       = content.get("pubDate") or item.get("providerPublishTime") or 0
        if isinstance(pub, str):
            try:
                pub = datetime.datetime.fromisoformat(pub.replace("Z","+00:00")).timestamp()
            except Exception:
                pub = 0

        age_h = (now - pub) / 3600 if pub else 48
        rec   = 1.0 if age_h <= 1 else 0.8 if age_h <= 3 else 0.5 if age_h <= 8 else 0.2
        if age_h <= 3:
            fresh = True

        bh = sum(1 for kw in BULLISH_KW if kw in title)
        brh= sum(1 for kw in BEARISH_KW if kw in title)
        bull += bh  * rec
        bear += brh * rec
        if (bh > 0 or brh > 0) and title_raw:
            scored.append((rec * (bh + brh), title_raw))

    scored.sort(reverse=True)
    headlines = [h[1] for h in scored[:3]]
    total     = bull + bear
    count     = len(news_items)

    if total == 0:
        return {"score": 50, "direction": "neutral", "confidence": 5,
                "headlines": headlines, "reason": f"{count} articles, no strong keywords.", "count": count, "fresh": fresh}

    ratio = bull / total
    if ratio >= 0.65:
        direction  = "bull"
        score      = round(50 + (ratio - 0.5) * 90, 1)
        confidence = round(ratio * 75)
        reason     = f"{round(ratio*100)}% bullish news weight · {count} articles"
    elif ratio <= 0.35:
        direction  = "bear"
        score      = round(50 - (0.5 - ratio) * 90, 1)
        confidence = round((1 - ratio) * 75)
        reason     = f"{round((1-ratio)*100)}% bearish news weight · {count} articles"
    else:
        direction  = "neutral"
        score      = 50.0
        confidence = 10
        reason     = f"Mixed signals · {count} articles"

    if fresh:
        confidence = min(confidence + 15, 95)
        reason    += " · fresh news"
    confidence = min(confidence + min(count * 2, 10), 98)

    return {"score": min(max(score,0),100), "direction": direction,
            "confidence": confidence, "headlines": headlines,
            "reason": reason, "count": count, "fresh": fresh}


# ─────────────────────────────────────────────
#  INTRADAY PRICE ANALYSIS
#  Uses 5-min and 15-min data for day trading
# ─────────────────────────────────────────────
def intraday_analysis(ticker: str):
    """
    Fetches 5-min and 15-min intraday data.
    Returns momentum pullback setup quality + tight ATR stop.
    """
    try:
        t = yf.Ticker(ticker)

        # 5-min data — last 2 days
        df5  = t.history(period="2d", interval="5m")
        # 15-min data — last 5 days
        df15 = t.history(period="5d", interval="15m")

        if df5 is None or len(df5) < 10:
            return None
        if df15 is None or len(df15) < 10:
            return None

        # ── 15-min ATR (tight stop for day trading) ──
        tr15 = pd.concat([
            df15["High"] - df15["Low"],
            (df15["High"] - df15["Close"].shift(1)).abs(),
            (df15["Low"]  - df15["Close"].shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr15 = float(tr15.tail(14).mean())

        # ── Current price from 5-min ──
        price = float(df5["Close"].iloc[-1])

        # ── Today's open and high ──
        today     = datetime.date.today()
        df5_today = df5[df5.index.date == today] if len(df5) > 0 else df5
        if len(df5_today) == 0:
            df5_today = df5

        day_open  = float(df5_today["Open"].iloc[0])
        day_high  = float(df5_today["High"].max())
        day_low   = float(df5_today["Low"].min())
        day_vol   = int(df5_today["Volume"].sum())

        # ── Gap from yesterday close ──
        df_daily  = t.history(period="5d", interval="1d")
        prev_close= float(df_daily["Close"].iloc[-2]) if len(df_daily) >= 2 else day_open
        gap_pct   = round((day_open - prev_close) / prev_close * 100, 2)

        # ── Volume surge (today vs avg daily volume from info) ──
        info      = t.fast_info
        avg_vol   = getattr(info, "three_month_average_volume", None) or 1
        vol_ratio = round(day_vol / (avg_vol / 6.5), 2)  # normalise to per-hour

        # ── Momentum pullback detection ──
        # Look for: initial surge (5-min high > open + ATR),
        # then pullback (price came back toward VWAP / open),
        # then resumption signal (last candle green + above open)
        close5    = df5_today["Close"]
        open5     = df5_today["Open"]
        high5     = df5_today["High"]

        # Initial surge: any 5-min candle made a big move up
        surged    = any((high5 - open5) > atr15 * 0.5)

        # Pullback: price has retraced at least 30% from day high
        hl_range  = day_high - day_low
        pullback_pct = round((day_high - price) / hl_range * 100, 1) if hl_range > 0 else 0
        pulled_back  = 20 <= pullback_pct <= 65  # healthy retracement

        # Resumption: last 5-min candle is bullish and above open
        last_bull = float(close5.iloc[-1]) > float(open5.iloc[-1]) and float(close5.iloc[-1]) > day_open

        # ── 15-min trend (simple: close > EMA9) ──
        ema9_15   = df15["Close"].ewm(span=9).mean()
        above_ema = float(df15["Close"].iloc[-1]) > float(ema9_15.iloc[-1])

        # ── RSI 14 on 15-min ──
        delta15   = df15["Close"].diff()
        gain15    = delta15.clip(lower=0).rolling(14).mean()
        loss15    = (-delta15.clip(upper=0)).rolling(14).mean()
        rs15      = gain15 / loss15.replace(0, 1e-9)
        rsi15     = round(float(100 - 100 / (1 + rs15.iloc[-1])), 1)

        # ── Setup score (0–100) ──
        setup_score = 0
        if gap_pct >= 2:          setup_score += 25
        elif gap_pct >= 1:        setup_score += 15
        if vol_ratio >= 2.0:      setup_score += 25
        elif vol_ratio >= 1.5:    setup_score += 15
        if surged:                setup_score += 15
        if pulled_back:           setup_score += 20
        if last_bull:             setup_score += 10
        if above_ema:             setup_score += 10
        if 40 <= rsi15 <= 65:     setup_score += 10  # not overbought
        elif rsi15 > 75:          setup_score -= 15  # overbought — risky entry
        setup_score = min(setup_score, 100)

        # ── Setup label ──
        if pulled_back and last_bull and surged:
            setup_label = "Pullback ready"
        elif surged and not pulled_back:
            setup_label = "Wait — no pullback yet"
        elif gap_pct >= 2 and vol_ratio >= 1.5:
            setup_label = "Gap setup"
        else:
            setup_label = "Watching"

        # ── Tight stop / target for day trade ──
        stop   = round(price - atr15 * 1.5, 2)
        target = round(price + atr15 * 3.0, 2)   # 2:1 R/R on 15-min ATR
        risk_pct = round(abs(price - stop) / price * 100, 1)

        # ── Position size for $500–$2000 account ──
        # Risk max 1% of $1,250 midpoint = $12.50 per trade
        risk_dollars  = 12.50
        stop_distance = abs(price - stop)
        shares        = int(risk_dollars / stop_distance) if stop_distance > 0 else 1
        shares        = max(1, min(shares, 50))  # cap at 50 shares for small account
        trade_cost    = round(shares * price, 2)

        return {
            "price":        round(price, 2),
            "prev_close":   round(prev_close, 2),
            "day_open":     round(day_open, 2),
            "day_high":     round(day_high, 2),
            "gap_pct":      gap_pct,
            "vol_ratio":    vol_ratio,
            "atr15":        round(atr15, 3),
            "rsi15":        rsi15,
            "above_ema":    above_ema,
            "surged":       surged,
            "pulled_back":  pulled_back,
            "pullback_pct": pullback_pct,
            "last_bull":    last_bull,
            "setup_score":  setup_score,
            "setup_label":  setup_label,
            "stop":         stop,
            "target":       target,
            "risk_pct":     risk_pct,
            "shares":       shares,
            "trade_cost":   trade_cost,
        }

    except Exception:
        return None


# ─────────────────────────────────────────────
#  COMBINED RECOMMENDATION
# ─────────────────────────────────────────────
def recommend(news: dict, intraday: dict) -> dict:
    if news["direction"] == "bear":
        return {"action": "AVOID", "confidence": news["confidence"],
                "reason": f"Bearish news. {news['reason']}"}

    if intraday is None:
        return {"action": "AVOID", "confidence": 0,
                "reason": "Could not fetch intraday data."}

    # Daily trend check — gap direction must match news
    if news["direction"] == "bull" and intraday["gap_pct"] < -1:
        return {"action": "AVOID", "confidence": 20,
                "reason": "Bullish news but stock gapped DOWN — conflicting signal."}

    # Combined score: news 60% + intraday setup 40%
    combined = round(news["confidence"] * 0.6 + intraday["setup_score"] * 0.4)

    if intraday["setup_label"] == "Pullback ready" and news["direction"] == "bull" and combined >= 55:
        action = "BUY NOW"
        reason = f"Momentum pullback setup ready. {news['reason']}. {intraday['setup_label']}."
    elif intraday["setup_label"] == "Wait — no pullback yet" and news["direction"] == "bull":
        action = "WAIT"
        reason = f"Good news catalyst but price hasn't pulled back yet — wait for retracement before entry."
    elif combined >= 55 and news["direction"] == "bull":
        action = "BUY NOW"
        reason = f"{news['reason']}. Setup: {intraday['setup_label']}."
    elif combined >= 35:
        action = "WAIT"
        reason = f"Moderate signal. {news['reason']}. Setup not fully formed yet."
    else:
        action = "AVOID"
        reason = f"Signal too weak. {news['reason']}"

    return {"action": action, "confidence": combined, "reason": reason}


# ─────────────────────────────────────────────
#  FULL SCAN
# ─────────────────────────────────────────────
def scan(ticker: str) -> dict | None:
    try:
        t    = yf.Ticker(ticker)
        info = t.info
        news = t.news or []

        price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
        if not price or price < 1:
            return None

        news_result     = score_news(news)
        intraday_result = intraday_analysis(ticker)
        rec             = recommend(news_result, intraday_result)

        if rec["action"] == "AVOID":
            return None

        return {
            "ticker":     ticker,
            "company":    (info.get("longName") or info.get("shortName") or ticker)[:28],
            "sector":     info.get("sector") or "—",
            "action":     rec["action"],
            "confidence": rec["confidence"],
            "reason":     rec["reason"],
            "news":       news_result,
            "intraday":   intraday_result,
        }
    except Exception:
        return None


# ─────────────────────────────────────────────
#  SIDEBAR
# ─────────────────────────────────────────────
with st.sidebar:
    st.title("⚡ NewsFlow Day Trader")
    st.caption("Momentum pullback · Intraday only · Small account")
    st.divider()

    watchlist_name = st.selectbox("Watchlist", list(WATCHLISTS.keys()))
    tickers        = WATCHLISTS[watchlist_name]
    st.caption(f"{len(tickers)} tickers")

    st.divider()
    st.subheader("Filters")
    min_conf = st.slider("Min Confidence %", 0, 90, 50)
    show_wait= st.checkbox("Show WAIT signals too", value=True)

    st.divider()
    st.markdown("**Account size: $500–$2,000**")
    st.caption("Position sizes are calculated risking max $12.50 per trade (1% of $1,250 midpoint). Adjust in code if needed.")

    st.divider()
    run = st.button("⚡ Scan Now", use_container_width=True, type="primary")

    st.divider()
    st.markdown("**Your trading flow:**")
    st.caption("1. Run scanner during market hours")
    st.caption("2. Open BUY NOW picks in TradingView")
    st.caption("3. Apply NewsFlow v3 Pine Script")
    st.caption("4. Confirm Daily trend is bullish")
    st.caption("5. On 15min — wait for pullback candle")
    st.caption("6. Enter when momentum resumes")
    st.caption("7. Close before market close (4 PM)")
    st.divider()
    st.caption("⚠ Not financial advice.")


# ─────────────────────────────────────────────
#  HEADER
# ─────────────────────────────────────────────
eastern = pytz.timezone("America/New_York")
now_et  = datetime.datetime.now(eastern)
st.title("⚡ NewsFlow Day Trader")
st.caption(f"Momentum pullback scanner · {now_et.strftime('%Y-%m-%d %H:%M')} ET · Intraday only — close all positions by 4 PM ET")

# Market hours warning — correct US Eastern time
hour = now_et.hour
mkt_open   = (hour > 9 or (hour == 9 and now_et.minute >= 30)) and hour < 16
pre_market = hour < 9 or (hour == 9 and now_et.minute < 30)
closing    = hour == 15 and now_et.minute >= 30
closed     = hour >= 16 or hour < 4

if pre_market:
    st.warning("⏰ Pre-market. Market opens at 9:30 AM ET — signals will sharpen once trading begins.")
elif closing:
    st.error("🔔 Market closes in under 30 minutes. Close any open positions before 4 PM ET.")
elif closed:
    st.error("🔴 Market is closed. Run this scanner when market opens at 9:30 AM ET tomorrow.")

if not run:
    st.info("👈 Click **Scan Now** to find momentum pullback setups right now.")

    st.markdown("### How the momentum pullback works")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown("**1. News catalyst**")
        st.caption("Stock gets a bullish headline — earnings beat, upgrade, deal announcement.")
    with c2:
        st.markdown("**2. Initial surge**")
        st.caption("Price spikes up on heavy volume. Don't chase this — wait.")
    with c3:
        st.markdown("**3. Pullback**")
        st.caption("Price retraces 20–65% of the move. This is your entry zone.")
    with c4:
        st.markdown("**4. Resumption**")
        st.caption("Price turns back up on a 5-min or 15-min bullish candle. Enter here.")
    st.stop()


# ─────────────────────────────────────────────
#  SCAN
# ─────────────────────────────────────────────
results = []
progress = st.progress(0, text="Starting scan…")
status   = st.empty()

for i, ticker in enumerate(tickers):
    progress.progress((i + 1) / len(tickers), text=f"Scanning {ticker}… ({i+1}/{len(tickers)})")
    status.caption(f"Fetching intraday data for **{ticker}**…")
    r = scan(ticker)
    if r and r["confidence"] >= min_conf:
        if r["action"] == "BUY NOW" or (show_wait and r["action"] == "WAIT"):
            results.append(r)
    time.sleep(0.4)

progress.empty()
status.empty()

results.sort(key=lambda x: (x["action"] == "BUY NOW", x["confidence"]), reverse=True)

# ─────────────────────────────────────────────
#  SUMMARY
# ─────────────────────────────────────────────
buy_now = [r for r in results if r["action"] == "BUY NOW"]
waiting = [r for r in results if r["action"] == "WAIT"]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Scanned",    len(tickers))
c2.metric("BUY NOW",    len(buy_now), delta=f"{len(buy_now)} ready to enter")
c3.metric("WAIT",       len(waiting), delta="pullback pending")
c4.metric("Avg Conf",   f"{round(sum(r['confidence'] for r in results)/len(results),1)}%" if results else "—")

st.divider()

if not results:
    st.warning("No setups found right now. The market may be quiet or no stocks have pulled back yet. Try again in 15–30 minutes.")
    st.stop()


# ─────────────────────────────────────────────
#  RESULT CARDS
# ─────────────────────────────────────────────
def render_card(r):
    intra = r["intraday"]
    news  = r["news"]
    conf  = r["confidence"]
    action= r["action"]

    conf_col  = "#00cc66" if conf >= 70 else "#ffaa00" if conf >= 50 else "#ff8c00"
    pill_cls  = "buy-pill" if action == "BUY NOW" else "wait-pill"
    tv_url    = f"https://www.tradingview.com/chart/?symbol={r['ticker']}"
    yf_url    = f"https://finance.yahoo.com/quote/{r['ticker']}"

    with st.container(border=True):
        h1, h2, h3 = st.columns([2, 3, 3])

        with h1:
            st.markdown(f"### {r['ticker']}")
            st.caption(f"{r['company']}")
            st.caption(f"{r['sector']}")

        with h2:
            st.markdown(
                f'<span class="{pill_cls}">{action}</span> &nbsp;'
                f'<span style="font-size:22px;font-weight:600;color:{conf_col}">{conf}%</span> '
                f'<span style="font-size:12px;color:#888">confidence</span>',
                unsafe_allow_html=True)
            st.markdown(
                f'<div style="height:8px;width:{conf}%;background:{conf_col};border-radius:6px;margin-top:4px"></div>',
                unsafe_allow_html=True)
            st.caption(r["reason"])

        with h3:
            if intra:
                gap_col = "green" if intra["gap_pct"] >= 0 else "red"
                st.markdown(f"**${intra['price']}** &nbsp; "
                            f"<span style='color:{gap_col}'>Gap {'+' if intra['gap_pct']>=0 else ''}{intra['gap_pct']}%</span>",
                            unsafe_allow_html=True)
                st.caption(f"Setup: **{intra['setup_label']}** · Pullback: {intra['pullback_pct']}%")

        if intra:
            st.markdown("")
            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("Entry",   f"${intra['price']}")
            col2.metric("Stop",    f"${intra['stop']}",   delta=f"-{intra['risk_pct']}%", delta_color="inverse")
            col3.metric("Target",  f"${intra['target']}", delta=f"+{round(abs(intra['target']-intra['price'])/intra['price']*100,1)}%")
            col4.metric("Shares",  intra["shares"],        help="Based on $12.50 max risk (1% of $1,250)")
            col5.metric("Cost",    f"${intra['trade_cost']}")

            # Intraday signal tags
            tags = ""
            if intra["gap_pct"] >= 1:       tags += '<span class="tag tag-gap">GAP</span>'
            if intra["vol_ratio"] >= 1.5:   tags += f'<span class="tag tag-vol">VOL {intra["vol_ratio"]}×</span>'
            if intra["surged"]:             tags += '<span class="tag tag-mom">SURGE</span>'
            if intra["pulled_back"]:        tags += '<span class="tag tag-mom">PULLBACK</span>'
            if news["fresh"]:               tags += '<span class="tag tag-news">FRESH NEWS</span>'
            if tags:
                st.markdown(tags, unsafe_allow_html=True)

            # 15-min stats
            st.markdown("")
            sc1, sc2, sc3, sc4 = st.columns(4)
            sc1.caption(f"15m ATR: **{intra['atr15']}**")
            sc2.caption(f"15m RSI: **{intra['rsi15']}**")
            sc3.caption(f"Above EMA9: **{'Yes' if intra['above_ema'] else 'No'}**")
            sc4.caption(f"News articles: **{news['count']}**")

        # Headlines
        if news["headlines"]:
            st.markdown("**Yahoo Finance headlines:**")
            for hl in news["headlines"]:
                st.markdown(f'<div class="news-hl">📰 {hl}</div>', unsafe_allow_html=True)

        st.markdown("")
        st.markdown(
            f'<a href="{tv_url}" target="_blank" style="background:#2962ff;color:white;padding:4px 12px;border-radius:6px;font-size:12px;text-decoration:none;font-weight:500">📈 TradingView</a> &nbsp;'
            f'<a href="{yf_url}" target="_blank" style="background:#6c3fc0;color:white;padding:4px 12px;border-radius:6px;font-size:12px;text-decoration:none;font-weight:500">📰 Yahoo Finance</a>',
            unsafe_allow_html=True)


# BUY NOW section
if buy_now:
    st.subheader(f"✅ {len(buy_now)} Ready to Enter")
    st.caption("Pullback is in place — momentum resuming. Enter on next bullish 15-min candle.")
    for r in buy_now:
        render_card(r)

# WAIT section
if waiting and show_wait:
    st.divider()
    st.subheader(f"⏳ {len(waiting)} Waiting for Pullback")
    st.caption("Good setups but price hasn't pulled back yet. Set an alert and check back in 15–30 min.")
    for r in waiting:
        render_card(r)

# ─────────────────────────────────────────────
#  DAY TRADING RULES REMINDER
# ─────────────────────────────────────────────
st.divider()
with st.expander("📋 Day Trading Rules — read before every session"):
    st.markdown("""
**Entry rules (all must be true):**
- Scanner shows BUY NOW
- TradingView Pine Script shows Daily trend = Bullish or Neutral
- 15-min chart shows a pullback candle followed by a green candle
- RSI on 15-min is between 40–65 (not overbought)

**Exit rules:**
- Hit target → close the trade
- Hit stop loss → close immediately, no hesitation
- 3:30 PM ET → close everything regardless of P&L

**Small account rules ($500–$2,000):**
- Max 1–2 trades open at the same time
- Risk max $12.50 per trade (1% of $1,250)
- Never add to a losing position
- If you lose 2 trades in a row → stop for the day

**Pattern Day Trader (PDT) rule:**
- If your account is under $25,000 on a US margin account, you are limited to 3 day trades per rolling 5-day period
- Use a cash account to avoid PDT restrictions
    """)

st.caption("⚠ NewsFlow is a research tool, not financial advice. Day trading involves significant risk of loss.")

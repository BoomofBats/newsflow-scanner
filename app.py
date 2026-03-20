"""
NewsFlow Scanner v2 — Yahoo Finance Edition
============================================
News-first stock scanner. BUY recommendations driven by
Yahoo Finance news sentiment + price/volume confirmation.

Deploy to Streamlit Cloud:
  1. Push app.py + requirements.txt to GitHub
  2. Connect at share.streamlit.io
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import datetime
import time

# ─────────────────────────────────────────────
#  PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="NewsFlow Scanner",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.block-container { padding-top: 1.2rem; }
.buy-pill  { background:#0d6b45; color:#d4f0e4; padding:3px 10px; border-radius:12px; font-weight:600; font-size:13px; }
.hold-pill { background:#7a4e00; color:#fff3d4; padding:3px 10px; border-radius:12px; font-weight:600; font-size:13px; }
.avoid-pill{ background:#8b1a1a; color:#fde0e0; padding:3px 10px; border-radius:12px; font-weight:600; font-size:13px; }
.conf-bar-wrap { background:#2a2a2a; border-radius:6px; height:8px; width:100%; }
.reason-text { font-size:12px; color:#aaa; font-style:italic; }
.headline-text { font-size:12px; color:#ccc; }
.tv-btn { background:#2962ff; color:white; padding:4px 12px; border-radius:6px; font-size:12px; text-decoration:none; font-weight:500; }
div[data-testid="stMetricValue"] { font-size:1.8rem; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
#  WATCHLISTS
# ─────────────────────────────────────────────
WATCHLISTS = {
    "🔥 Major US Stocks (67)": [
        "AAPL","MSFT","NVDA","AMZN","META","GOOGL","TSLA","AVGO","JPM","V",
        "UNH","LLY","XOM","MA","JNJ","PG","HD","MRK","ABBV","CVX",
        "BAC","COST","NFLX","AMD","ADBE","CRM","TMO","PEP","ORCL","ACN",
        "MCD","QCOM","INTC","WMT","DIS","GS","MS","AMGN","IBM","CAT",
        "BA","GE","F","GM","RIVN","PLTR","SOFI","HOOD","COIN","RBLX",
        "SNAP","UBER","LYFT","SPOT","PINS","TWLO","SQ","PYPL","SHOP","NET",
        "SPY","QQQ","IWM","XLF","XLE","XLK","ARKK",
    ],
    "💻 Tech (20)": [
        "AAPL","MSFT","NVDA","AMD","INTC","AVGO","QCOM","ORCL","IBM","CRM",
        "ADBE","SHOP","NET","TWLO","SNOW","DDOG","ZS","CRWD","OKTA","PLTR",
    ],
    "🏦 Finance (20)": [
        "JPM","BAC","GS","MS","V","MA","PYPL","SQ","HOOD","SOFI",
        "C","WFC","AXP","COF","BLK","SCHW","IBKR","CME","ICE","NDAQ",
    ],
    "🚗 EV & Auto (12)": [
        "TSLA","RIVN","LCID","NIO","LI","XPEV","GM","F","STLA","TM","HMC","SONY",
    ],
    "🚀 High Volatility (18)": [
        "GME","AMC","SPCE","CLOV","NKLA","SNDL","TLRY","BB","NOK",
        "WISH","CTRM","SENS","GNUS","BBIG","ATER","PROG","MVIS","WKHS",
    ],
}

# ─────────────────────────────────────────────
#  NEWS SENTIMENT ENGINE
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

def score_news(news_items: list) -> dict:
    """
    Full news scoring. Returns a dict with:
      - sentiment_score  0–100
      - direction        bull / bear / neutral
      - confidence       how strong the signal is (0–100)
      - top_headlines    list of up to 3 most relevant headlines
      - reason           human-readable explanation
      - news_count
      - recency_bonus    were there very recent articles?
    """
    if not news_items:
        return {
            "sentiment_score": 50, "direction": "neutral",
            "confidence": 0, "top_headlines": [],
            "reason": "No recent news found on Yahoo Finance.",
            "news_count": 0, "recency_bonus": False,
        }

    now = datetime.datetime.now(datetime.timezone.utc).timestamp()
    bull_score = 0.0
    bear_score = 0.0
    headlines_scored = []  # (recency, bull_hits, bear_hits, title)
    recency_bonus = False

    for item in news_items[:20]:
        content = item.get("content", {})
        title_raw = content.get("title") or item.get("title") or ""
        title = title_raw.lower()

        pub = content.get("pubDate") or item.get("providerPublishTime") or 0
        if isinstance(pub, str):
            try:
                pub = datetime.datetime.fromisoformat(
                    pub.replace("Z", "+00:00")).timestamp()
            except Exception:
                pub = 0

        age_h = (now - pub) / 3600 if pub else 48
        if age_h <= 2:
            rec = 1.0
            recency_bonus = True
        elif age_h <= 6:
            rec = 0.8
        elif age_h <= 24:
            rec = 0.5
        else:
            rec = 0.15

        bull_hits = sum(1 for kw in BULLISH_KW if kw in title)
        bear_hits = sum(1 for kw in BEARISH_KW if kw in title)

        bull_score += bull_hits * rec
        bear_score += bear_hits * rec

        if (bull_hits > 0 or bear_hits > 0) and title_raw:
            headlines_scored.append((rec, bull_hits, bear_hits, title_raw))

    # Sort headlines by recency × relevance
    headlines_scored.sort(key=lambda x: x[0] * (x[1] + x[2]), reverse=True)
    top_headlines = [h[3] for h in headlines_scored[:3]]

    total = bull_score + bear_score
    news_count = len(news_items)

    if total == 0:
        # No keyword matches — neutral, low confidence
        direction = "neutral"
        sentiment_score = 50
        raw_confidence = 5
        reason = f"Found {news_count} articles but none contained strong bullish or bearish signals."
    else:
        bull_ratio = bull_score / total
        if bull_ratio >= 0.70:
            direction = "bull"
            sentiment_score = round(50 + (bull_ratio - 0.5) * 90, 1)
            raw_confidence = round(bull_ratio * 80)
            reason = _build_reason("bull", bull_score, bear_score, news_count, recency_bonus, headlines_scored)
        elif bull_ratio <= 0.30:
            direction = "bear"
            sentiment_score = round(50 - (0.5 - bull_ratio) * 90, 1)
            raw_confidence = round((1 - bull_ratio) * 80)
            reason = _build_reason("bear", bull_score, bear_score, news_count, recency_bonus, headlines_scored)
        else:
            direction = "neutral"
            sentiment_score = 50
            raw_confidence = round(30 - abs(bull_ratio - 0.5) * 60)
            reason = f"Mixed signals — {round(bull_ratio*100)}% of news weight is bullish, {round((1-bull_ratio)*100)}% bearish. No clear edge."

    # Recency boost: very fresh news = stronger conviction
    if recency_bonus:
        raw_confidence = min(raw_confidence + 15, 95)

    # Volume of coverage boost
    coverage_boost = min(news_count * 2, 10)
    confidence = min(raw_confidence + coverage_boost, 98)

    return {
        "sentiment_score": min(max(sentiment_score, 0), 100),
        "direction":       direction,
        "confidence":      confidence,
        "top_headlines":   top_headlines,
        "reason":          reason,
        "news_count":      news_count,
        "recency_bonus":   recency_bonus,
    }


def _build_reason(direction, bull_score, bear_score, news_count, recency, headlines_scored):
    total = bull_score + bear_score
    bull_pct = round(bull_score / total * 100)
    bear_pct = 100 - bull_pct
    freshness = "including very recent articles" if recency else "mostly older articles"
    kw_examples = []
    for _, bh, brh, title in headlines_scored[:2]:
        if direction == "bull" and bh > 0:
            for kw in BULLISH_KW:
                if kw in title.lower() and kw not in kw_examples:
                    kw_examples.append(kw)
                    break
        elif direction == "bear" and brh > 0:
            for kw in BEARISH_KW:
                if kw in title.lower() and kw not in kw_examples:
                    kw_examples.append(kw)
                    break

    kw_str = f" (keywords: {', '.join(kw_examples[:2])})" if kw_examples else ""
    if direction == "bull":
        return f"{bull_pct}% of news weight is bullish{kw_str}. {news_count} articles scanned, {freshness}."
    else:
        return f"{bear_pct}% of news weight is bearish{kw_str}. {news_count} articles scanned, {freshness}."


# ─────────────────────────────────────────────
#  PRICE CONFIRMATION ENGINE
# ─────────────────────────────────────────────
def price_confirmation(info: dict, hist: pd.DataFrame) -> dict:
    """
    Secondary check — does price/volume action confirm the news?
    Returns a dict with score 0–100 and a short reason.
    """
    score = 0
    reasons = []

    price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
    prev  = info.get("regularMarketPreviousClose") or info.get("previousClose") or price
    open_ = info.get("regularMarketOpen") or price
    vol   = info.get("regularMarketVolume") or 0
    avg_v = info.get("averageVolume") or 1

    change_pct  = ((price - prev) / prev * 100) if prev else 0
    vol_ratio   = vol / avg_v if avg_v else 1
    gap_pct     = ((open_ - prev) / prev * 100) if prev else 0

    # Volume spike
    if vol_ratio >= 3.0:
        score += 35
        reasons.append(f"vol {vol_ratio:.1f}× avg")
    elif vol_ratio >= 2.0:
        score += 25
        reasons.append(f"vol {vol_ratio:.1f}× avg")
    elif vol_ratio >= 1.5:
        score += 15
        reasons.append(f"vol {vol_ratio:.1f}× avg")

    # Price momentum
    if change_pct >= 3:
        score += 30
        reasons.append(f"+{change_pct:.1f}% today")
    elif change_pct >= 1:
        score += 15
        reasons.append(f"+{change_pct:.1f}% today")
    elif change_pct > 0:
        score += 5

    # Gap up
    if gap_pct >= 2:
        score += 20
        reasons.append(f"gap +{gap_pct:.1f}%")
    elif gap_pct >= 1:
        score += 10

    # Momentum breakout (close > 20-day high)
    if hist is not None and len(hist) > 21:
        high_20 = float(hist["High"].iloc[:-1].tail(20).max())
        if price > high_20:
            score += 15
            reasons.append("20d breakout")

    # RSI not overbought (above 70 is a warning)
    if hist is not None and len(hist) >= 15:
        delta = hist["Close"].diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        rs    = gain / loss.replace(0, 1e-9)
        rsi   = float(100 - 100 / (1 + rs.iloc[-1]))
        if rsi > 75:
            score -= 10
            reasons.append(f"RSI {rsi:.0f} overbought")
        elif rsi < 40:
            score += 5
            reasons.append(f"RSI {rsi:.0f} oversold")

    summary = ", ".join(reasons) if reasons else "no strong price confirmation"
    return {
        "score":       min(max(score, 0), 100),
        "summary":     summary,
        "change_pct":  round(change_pct, 2),
        "vol_ratio":   round(vol_ratio, 2),
        "gap_pct":     round(gap_pct, 2),
        "price":       round(price, 2),
    }


# ─────────────────────────────────────────────
#  BUY DECISION ENGINE
# ─────────────────────────────────────────────
def make_recommendation(news: dict, price: dict) -> dict:
    """
    Combines news sentiment (70% weight) + price confirmation (30% weight)
    into a final BUY / HOLD / AVOID recommendation with confidence % and reason.
    """
    if news["direction"] == "bear":
        return {
            "action":     "AVOID",
            "confidence": news["confidence"],
            "reason":     f"Bearish news. {news['reason']}",
        }

    if news["direction"] == "neutral" or news["confidence"] < 20:
        return {
            "action":     "HOLD",
            "confidence": news["confidence"],
            "reason":     f"Unclear news signal. {news['reason']}",
        }

    # Bullish news — now check price confirmation
    news_weight  = 0.70
    price_weight = 0.30
    combined = (news["confidence"] * news_weight) + (price["score"] * price_weight)
    combined = round(combined)

    if combined >= 60:
        action = "BUY"
        if price["score"] >= 40:
            reason = f"{news['reason']} Price confirms: {price['summary']}."
        else:
            reason = f"{news['reason']} Price action is weak — consider waiting for volume confirmation."
    elif combined >= 35:
        action = "HOLD"
        reason = f"Mildly bullish news but not strong enough conviction. {news['reason']}"
    else:
        action = "HOLD"
        reason = f"News signal too weak to act on. {news['reason']}"

    return {
        "action":     action,
        "confidence": combined,
        "reason":     reason,
    }


# ─────────────────────────────────────────────
#  ATR STOP / TARGET
# ─────────────────────────────────────────────
def compute_levels(price: float, hist: pd.DataFrame, atr_mult: float) -> dict:
    if hist is None or len(hist) < 2:
        stop_dist = price * 0.02
    else:
        tr = pd.concat([
            hist["High"] - hist["Low"],
            (hist["High"] - hist["Close"].shift(1)).abs(),
            (hist["Low"]  - hist["Close"].shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr = float(tr.tail(14).mean())
        stop_dist = atr * atr_mult

    stop   = round(price - stop_dist, 2)
    target = round(price + stop_dist * 2, 2)
    risk   = round(stop_dist / price * 100, 1)
    return {"stop": stop, "target": target, "risk_pct": risk}


# ─────────────────────────────────────────────
#  MAIN SCANNER
# ─────────────────────────────────────────────
def scan_ticker(ticker: str, atr_mult: float) -> dict | None:
    try:
        t    = yf.Ticker(ticker)
        info = t.info
        hist = t.history(period="30d")
        news = t.news or []

        price_val = info.get("currentPrice") or info.get("regularMarketPrice") or 0
        if not price_val or price_val < 1:
            return None

        news_result  = score_news(news)
        price_result = price_confirmation(info, hist)
        rec          = make_recommendation(news_result, price_result)
        levels       = compute_levels(price_val, hist, atr_mult)

        return {
            "ticker":      ticker,
            "company":     (info.get("longName") or info.get("shortName") or ticker)[:30],
            "sector":      info.get("sector") or "—",
            "price":       price_result["price"],
            "change_pct":  price_result["change_pct"],
            "vol_ratio":   price_result["vol_ratio"],
            "action":      rec["action"],
            "confidence":  rec["confidence"],
            "reason":      rec["reason"],
            "headlines":   news_result["top_headlines"],
            "news_count":  news_result["news_count"],
            "recency":     news_result["recency_bonus"],
            "news_score":  news_result["sentiment_score"],
            "price_score": price_result["score"],
            "stop":        levels["stop"],
            "target":      levels["target"],
            "risk_pct":    levels["risk_pct"],
        }
    except Exception:
        return None


# ─────────────────────────────────────────────
#  SIDEBAR
# ─────────────────────────────────────────────
with st.sidebar:
    st.title("📰 NewsFlow Scanner")
    st.caption("News-first stock scanner · Yahoo Finance")
    st.divider()

    watchlist_name = st.selectbox("Watchlist", list(WATCHLISTS.keys()))
    tickers = WATCHLISTS[watchlist_name]
    st.caption(f"{len(tickers)} tickers")

    st.divider()
    st.subheader("Settings")
    atr_mult = st.slider("Stop Loss ATR Multiplier", 0.5, 3.0, 1.5, 0.25,
        help="Higher = wider stop, more room to breathe")
    min_confidence = st.slider("Min Confidence % to show", 0, 90, 50,
        help="Only show BUY signals above this confidence level")

    st.divider()
    run = st.button("🔍 Scan for BUY signals", use_container_width=True, type="primary")

    st.divider()
    st.caption("💡 Best run after 4 PM market close for next-day picks.")
    st.caption("⚠ Not financial advice. Always do your own research.")


# ─────────────────────────────────────────────
#  HEADER
# ─────────────────────────────────────────────
st.title("📰 NewsFlow Scanner")
st.caption(f"Scans Yahoo Finance news · recommends stocks to buy tomorrow · {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")

if not run:
    st.info("👈 Select a watchlist and click **Scan for BUY signals** to begin.")

    st.markdown("### How it works")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**1. News scan**")
        st.caption("Fetches Yahoo Finance headlines for each stock. Scores them by keyword sentiment weighted by how recent they are.")
    with c2:
        st.markdown("**2. Price confirmation**")
        st.caption("Checks if volume, price momentum, and gaps confirm the news signal. News drives the decision — price is a secondary check.")
    with c3:
        st.markdown("**3. BUY recommendation**")
        st.caption("Combines both signals into a BUY / HOLD / AVOID call with a confidence %, a plain-English reason, and entry/stop/target levels.")
    st.stop()


# ─────────────────────────────────────────────
#  SCAN
# ─────────────────────────────────────────────
all_results = []
buy_results = []

progress = st.progress(0, text="Starting scan…")
status   = st.empty()

for i, ticker in enumerate(tickers):
    progress.progress((i + 1) / len(tickers), text=f"Scanning {ticker}… ({i+1}/{len(tickers)})")
    status.caption(f"Fetching news and price data for **{ticker}**…")
    result = scan_ticker(ticker, atr_mult)
    if result:
        all_results.append(result)
        if result["action"] == "BUY" and result["confidence"] >= min_confidence:
            buy_results.append(result)
    time.sleep(0.3)

progress.empty()
status.empty()

# Sort BUY results by confidence descending
buy_results.sort(key=lambda x: x["confidence"], reverse=True)
all_results.sort(key=lambda x: x["confidence"], reverse=True)

# ─────────────────────────────────────────────
#  SUMMARY METRICS
# ─────────────────────────────────────────────
total_scanned = len(all_results)
buy_count     = len(buy_results)
hold_count    = sum(1 for r in all_results if r["action"] == "HOLD")
avoid_count   = sum(1 for r in all_results if r["action"] == "AVOID")
avg_conf      = round(sum(r["confidence"] for r in buy_results) / buy_count, 1) if buy_count else 0

col1, col2, col3, col4 = st.columns(4)
col1.metric("Stocks Scanned", total_scanned)
col2.metric("BUY Signals",    buy_count,    delta=f"{buy_count} actionable")
col3.metric("Avg Confidence", f"{avg_conf}%")
col4.metric("Hold / Avoid",   f"{hold_count} / {avoid_count}")

st.divider()

# ─────────────────────────────────────────────
#  RESULTS
# ─────────────────────────────────────────────
if not buy_results:
    st.warning("No BUY signals found with the current settings. Try lowering the Min Confidence slider, or run again after market close when more news is available.")
    st.stop()

st.subheader(f"📈 {buy_count} BUY Signal{'s' if buy_count != 1 else ''} Found")
st.caption("Sorted by confidence · News sentiment is the primary driver · Price action is a secondary confirmation")

for r in buy_results:
    conf     = r["confidence"]
    conf_col = "#00cc66" if conf >= 70 else "#ffaa00" if conf >= 50 else "#ff8c00"
    chg_col  = "green" if r["change_pct"] >= 0 else "red"
    chg_str  = f"+{r['change_pct']}%" if r["change_pct"] >= 0 else f"{r['change_pct']}%"
    tv_url   = f"https://finance.yahoo.com/quote/{r['ticker']}"
    tv_chart = f"https://www.tradingview.com/chart/?symbol={r['ticker']}"

    with st.container(border=True):
        # ── Row 1: ticker + recommendation ──
        h1, h2, h3 = st.columns([3, 4, 3])

        with h1:
            st.markdown(f"### {r['ticker']}")
            st.caption(f"{r['company']} · {r['sector']}")

        with h2:
            st.markdown(
                f'<span class="buy-pill">BUY</span> &nbsp; '
                f'<span style="font-size:22px; font-weight:600; color:{conf_col}">{conf}%</span> '
                f'<span style="font-size:13px; color:#888">confidence</span>',
                unsafe_allow_html=True
            )
            # Confidence bar
            st.markdown(
                f'<div class="conf-bar-wrap">'
                f'<div style="height:8px;width:{conf}%;background:{conf_col};border-radius:6px"></div>'
                f'</div>',
                unsafe_allow_html=True
            )

        with h3:
            st.metric("Price",  f"${r['price']}", chg_str)

        # ── Row 2: reason ──
        st.markdown(
            f'<div class="reason-text">💬 {r["reason"]}</div>',
            unsafe_allow_html=True
        )

        st.markdown("")

        # ── Row 3: trade levels + news details ──
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Entry",  f"${r['price']}")
        d2.metric("Stop",   f"${r['stop']}",   delta=f"-{r['risk_pct']}% risk", delta_color="inverse")
        d3.metric("Target", f"${r['target']}", delta=f"+{round(abs(r['target']-r['price'])/r['price']*100,1)}%")
        d4.metric("Vol Spike", f"{r['vol_ratio']}×")

        # ── Headlines ──
        if r["headlines"]:
            st.markdown("**Recent headlines from Yahoo Finance:**")
            for hl in r["headlines"]:
                st.markdown(
                    f'<div class="headline-text">📰 {hl}</div>',
                    unsafe_allow_html=True
                )
        else:
            st.caption("No specific headlines matched — signal based on general news volume.")

        # ── Score breakdown + links ──
        st.markdown("")
        sb1, sb2, sb3, sb4 = st.columns(4)
        sb1.caption(f"News score: **{r['news_score']}/100**")
        sb2.caption(f"Price score: **{r['price_score']}/100**")
        sb3.caption(f"Articles scanned: **{r['news_count']}**")
        recency_label = "🟢 Fresh news" if r["recency"] else "🟡 Older news"
        sb4.caption(recency_label)

        st.markdown(
            f'<a href="{tv_chart}" target="_blank" class="tv-btn">📈 Open in TradingView</a> &nbsp; '
            f'<a href="{tv_url}"   target="_blank" class="tv-btn" style="background:#6c3fc0">📰 Yahoo Finance</a>',
            unsafe_allow_html=True
        )

# ─────────────────────────────────────────────
#  EXPORT
# ─────────────────────────────────────────────
st.divider()
st.subheader("📥 Export")

df_export = pd.DataFrame([{
    "Ticker":      r["ticker"],
    "Company":     r["company"],
    "Action":      r["action"],
    "Confidence%": r["confidence"],
    "Price":       r["price"],
    "Change%":     r["change_pct"],
    "VolSpike":    r["vol_ratio"],
    "NewsScore":   r["news_score"],
    "PriceScore":  r["price_score"],
    "Stop":        r["stop"],
    "Target":      r["target"],
    "Risk%":       r["risk_pct"],
    "Reason":      r["reason"],
    "Headlines":   " | ".join(r["headlines"]),
} for r in buy_results])

col_a, col_b = st.columns(2)
with col_a:
    st.download_button(
        "⬇ Download BUY list as CSV",
        df_export.to_csv(index=False).encode(),
        file_name=f"newsflow_buys_{datetime.date.today()}.csv",
        mime="text/csv",
        use_container_width=True,
    )
with col_b:
    tv_list = "\n".join(r["ticker"] for r in buy_results)
    st.download_button(
        "📈 Download TradingView Watchlist",
        tv_list.encode(),
        file_name=f"newsflow_watchlist_{datetime.date.today()}.txt",
        mime="text/plain",
        use_container_width=True,
        help="One ticker per line — importable into TradingView watchlist"
    )

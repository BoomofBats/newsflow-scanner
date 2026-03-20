"""
NewsFlow Scanner — Streamlit Web App
=====================================
Deploys to Streamlit Cloud for free.
Just push to GitHub and connect at share.streamlit.io
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
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
#  CUSTOM CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; }
    .metric-card {
        background: #1e1e2e;
        border-radius: 10px;
        padding: 16px 20px;
        border: 1px solid #2a2a3e;
    }
    .signal-tag {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 11px;
        font-weight: 600;
        margin: 1px;
    }
    .tag-vol  { background:#1a3a5c; color:#60b4ff; }
    .tag-gap  { background:#3a1a5c; color:#c060ff; }
    .tag-mom  { background:#1a5c2a; color:#60ff8a; }
    .tag-rev  { background:#5c3a1a; color:#ffb060; }
    .buy-badge  { color:#00cc66; font-weight:700; font-size:15px; }
    .watch-badge { color:#ffaa00; font-weight:700; font-size:15px; }
    .avoid-badge { color:#ff4444; font-weight:700; font-size:15px; }
    .tv-link {
        display: inline-block;
        background: #2962ff;
        color: white !important;
        padding: 3px 10px;
        border-radius: 6px;
        font-size: 12px;
        text-decoration: none;
        font-weight: 500;
    }
    .tv-link:hover { background: #1a4fd6; }
    div[data-testid="stMetricValue"] { font-size: 2rem; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
#  WATCHLISTS
# ─────────────────────────────────────────────
WATCHLISTS = {
    "🔥 High Movers (67 stocks)": [
        "AAPL","MSFT","NVDA","AMZN","META","GOOGL","TSLA","AVGO","JPM","V",
        "UNH","LLY","XOM","MA","JNJ","PG","HD","MRK","ABBV","CVX",
        "BAC","COST","NFLX","AMD","ADBE","CRM","TMO","PEP","ORCL","ACN",
        "MCD","QCOM","INTC","WMT","DIS","GS","MS","AMGN","IBM","CAT",
        "BA","GE","F","GM","RIVN","PLTR","SOFI","HOOD","COIN","RBLX",
        "SNAP","UBER","LYFT","SPOT","PINS","TWLO","SQ","PYPL","SHOP","NET",
        "SPY","QQQ","IWM","XLF","XLE","XLK","ARKK",
    ],
    "🚀 Meme / High Volatility": [
        "GME","AMC","SPCE","CLOV","WKHS","NKLA","SNDL","TLRY",
        "BB","NOK","WISH","CTRM","SENS","GNUS","XELA","BBIG","ATER","PROG",
    ],
    "💻 Tech Focus": [
        "AAPL","MSFT","NVDA","AMD","INTC","AVGO","QCOM","ORCL","IBM","CRM",
        "ADBE","SHOP","NET","TWLO","SNOW","DDOG","ZS","CRWD","OKTA","PLTR",
    ],
    "🏦 Finance Focus": [
        "JPM","BAC","GS","MS","V","MA","PYPL","SQ","HOOD","SOFI",
        "C","WFC","AXP","COF","BLK","SCHW","IBKR","CME","ICE","NDAQ",
    ],
}

# ─────────────────────────────────────────────
#  SCORING ENGINE (same logic as news_scanner.py)
# ─────────────────────────────────────────────
BULLISH_KW = [
    "beat","beats","exceeds","record","surge","soar","rally","upgrade",
    "raised","raise","growth","profit","bullish","breakout","buy",
    "outperform","strong","positive","boost","deal","acquisition",
    "contract","partnership","launch","approval","dividend","buyback",
    "guidance raised",
]
BEARISH_KW = [
    "miss","misses","below","decline","drop","fall","downgrade","cut",
    "loss","bearish","lawsuit","investigation","recall","warning","layoff",
    "bankruptcy","debt","sell","underperform","weak","negative","concern",
    "probe","fine","guidance cut","guidance lowered","disappointing",
]

def score_news(news_items):
    if not news_items:
        return 0.0, "neutral", "", 0

    now = datetime.datetime.now(datetime.timezone.utc).timestamp()
    bull, bear = 0.0, 0.0
    top_headline, top_recency = "", 0

    for item in news_items[:15]:
        content = item.get("content", {})
        title = (content.get("title") or item.get("title") or "").lower()
        pub = content.get("pubDate") or item.get("providerPublishTime") or 0
        if isinstance(pub, str):
            try:
                pub = datetime.datetime.fromisoformat(
                    pub.replace("Z", "+00:00")).timestamp()
            except Exception:
                pub = 0

        age_h = (now - pub) / 3600 if pub else 24
        rec = 1.0 if age_h <= 2 else 0.7 if age_h <= 6 else 0.4 if age_h <= 24 else 0.1

        bull += sum(1 for kw in BULLISH_KW if kw in title) * rec
        bear += sum(1 for kw in BEARISH_KW if kw in title) * rec

        if rec > top_recency and title:
            top_recency = rec
            top_headline = content.get("title") or item.get("title") or title

    total = bull + bear
    if total == 0:
        score, sentiment = 50.0, "neutral"
    else:
        ratio = bull / total
        if ratio >= 0.65:
            score, sentiment = 50 + (ratio - 0.5) * 100, "bull"
        elif ratio <= 0.35:
            score, sentiment = 50 - (0.5 - ratio) * 100, "bear"
        else:
            score, sentiment = 50.0, "neutral"

    score = min(score + min(len(news_items), 10), 100)
    return round(score, 1), sentiment, top_headline, len(news_items)


def compute_atr(hist, period=14):
    if hist is None or len(hist) < 2:
        return 0.0
    tr = pd.concat([
        hist["High"] - hist["Low"],
        (hist["High"] - hist["Close"].shift(1)).abs(),
        (hist["Low"]  - hist["Close"].shift(1)).abs(),
    ], axis=1).max(axis=1)
    return round(float(tr.tail(period).mean()), 4)


def scan_ticker(ticker, cfg):
    try:
        t = yf.Ticker(ticker)
        info = t.info

        price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
        if not price or price < cfg["min_price"]:
            return None

        prev  = info.get("regularMarketPreviousClose") or info.get("previousClose") or price
        chg   = round((price - prev) / prev * 100, 2) if prev else 0
        open_ = info.get("regularMarketOpen") or info.get("open") or price
        gap_up_pct  = round((open_ - prev) / prev * 100, 2) if prev else 0
        gap_dn_pct  = round((prev - open_) / prev * 100, 2) if prev else 0

        vol     = info.get("regularMarketVolume") or info.get("volume") or 0
        avg_vol = info.get("averageVolume") or 1
        vol_ratio = round(vol / avg_vol, 2)

        hist = t.history(period="30d")
        atr  = compute_atr(hist)

        # RSI (14)
        close_s = hist["Close"]
        delta = close_s.diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        rs    = gain / loss.replace(0, 1e-9)
        rsi   = round(float(100 - 100 / (1 + rs.iloc[-1])), 1) if len(rs) else 50

        # Momentum: close > highest high of last 20 bars
        highest = float(hist["High"].iloc[:-1].tail(20).max()) if len(hist) > 20 else price
        mom_break = price > highest and vol_ratio >= cfg["mom_vol_mult"]

        # Signals
        vol_spike  = vol_ratio >= cfg["vol_spike_mult"]
        gap_up     = gap_up_pct >= cfg["gap_pct"]
        gap_down   = gap_dn_pct >= cfg["gap_pct"]
        reversal   = rsi < cfg["rsi_oversold"] and chg > 0 and vol_ratio >= 1.3

        # Scores
        v_score = min(round((vol_ratio - cfg["vol_spike_mult"] + 1) * 20), 30) if vol_spike else 0
        g_score = min(round(max(gap_up_pct, gap_dn_pct) * 6), 25) if (gap_up or gap_down) else 0
        m_score = 25 if mom_break else 0
        r_score = 20 if reversal  else 0

        # News scoring
        news = t.news or []
        n_score, sentiment, headline, n_count = score_news(news)

        # Composite
        price_score = min(v_score + g_score + m_score + r_score, 60)
        composite   = round((price_score * 0.5) + (n_score * 0.5), 1)

        if composite < cfg["min_score"]:
            return None

        # Trade levels
        stop_dist   = atr * cfg["atr_mult"] if atr else price * 0.02
        bull_signal = sentiment == "bull" or gap_up or mom_break or reversal
        entry       = round(price, 2)
        stop        = round(entry - stop_dist, 2) if bull_signal else round(entry + stop_dist, 2)
        target      = round(entry + stop_dist * 2, 2) if bull_signal else round(entry - stop_dist * 2, 2)
        risk_pct    = round(abs(entry - stop) / entry * 100, 1)

        rating = "BUY" if composite >= 65 else "WATCH" if composite >= 40 else "AVOID"

        active_signals = []
        if vol_spike:  active_signals.append("VOL")
        if gap_up:     active_signals.append("GAP↑")
        if gap_down:   active_signals.append("GAP↓")
        if mom_break:  active_signals.append("BRK")
        if reversal:   active_signals.append("REV")

        return {
            "ticker":    ticker,
            "company":   (info.get("longName") or info.get("shortName") or ticker)[:28],
            "sector":    info.get("sector") or "—",
            "price":     entry,
            "change":    chg,
            "vol_ratio": vol_ratio,
            "rsi":       rsi,
            "news_score":n_score,
            "composite": composite,
            "sentiment": sentiment,
            "rating":    rating,
            "signals":   active_signals,
            "headline":  headline or "No recent headline",
            "n_count":   n_count,
            "entry":     entry,
            "stop":      stop,
            "target":    target,
            "risk_pct":  risk_pct,
            "atr":       round(atr, 2),
        }
    except Exception:
        return None


# ─────────────────────────────────────────────
#  SIDEBAR
# ─────────────────────────────────────────────
with st.sidebar:
    st.title("⚡ NewsFlow Scanner")
    st.caption("News-proxy signal scanner using Yahoo Finance")
    st.divider()

    watchlist_name = st.selectbox("Watchlist", list(WATCHLISTS.keys()))
    tickers = WATCHLISTS[watchlist_name]
    st.caption(f"{len(tickers)} tickers in this list")

    st.divider()
    st.subheader("Signal Filters")
    min_score     = st.slider("Min Composite Score", 0, 100, 50)
    vol_spike_mult= st.slider("Vol Spike Multiplier (×avg)", 1.0, 5.0, 2.0, 0.1)
    gap_pct       = st.slider("Min Gap %", 0.5, 5.0, 1.5, 0.25)
    rsi_oversold  = st.slider("RSI Oversold Level", 10, 50, 35)
    mom_vol_mult  = st.slider("Momentum Vol Confirm (×avg)", 1.0, 3.0, 1.5, 0.1)
    atr_mult      = st.slider("ATR Stop Multiplier", 0.5, 3.0, 1.5, 0.25)
    min_price     = st.number_input("Min Stock Price ($)", 1.0, 500.0, 5.0)

    st.divider()
    run = st.button("🔍 Run Scan", use_container_width=True, type="primary")

    st.divider()
    st.caption("💡 Tip: Run after 4 PM for tomorrow's picks. Yahoo Finance has a ~15 min delay — fine for EOD analysis.")

cfg = {
    "min_score":      min_score,
    "vol_spike_mult": vol_spike_mult,
    "gap_pct":        gap_pct,
    "rsi_oversold":   rsi_oversold,
    "mom_vol_mult":   mom_vol_mult,
    "atr_mult":       atr_mult,
    "min_price":      min_price,
}

# ─────────────────────────────────────────────
#  MAIN CONTENT
# ─────────────────────────────────────────────
st.title("⚡ NewsFlow Stock Scanner")
st.caption(f"Last run: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}  •  Powered by Yahoo Finance")

if not run:
    st.info("👈 Configure your filters in the sidebar and click **Run Scan** to find tomorrow's picks.")
    st.stop()

# ── Scan ──────────────────────────────────────
results = []
progress_bar = st.progress(0, text="Starting scan…")
status_text  = st.empty()

for i, ticker in enumerate(tickers):
    status_text.caption(f"Scanning {ticker}… ({i+1}/{len(tickers)})")
    progress_bar.progress((i + 1) / len(tickers), text=f"Scanning {ticker}…")
    result = scan_ticker(ticker, cfg)
    if result:
        results.append(result)
    time.sleep(0.25)

progress_bar.empty()
status_text.empty()

if not results:
    st.warning("No stocks matched your criteria. Try lowering the Min Score or Vol Spike filters.")
    st.stop()

# Sort by composite score
results.sort(key=lambda x: x["composite"], reverse=True)

# ── Summary Metrics ───────────────────────────
buy_ct   = sum(1 for r in results if r["rating"] == "BUY")
watch_ct = sum(1 for r in results if r["rating"] == "WATCH")
avg_sc   = round(sum(r["composite"] for r in results) / len(results), 1)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Stocks Found",    len(results))
c2.metric("BUY Signals",     buy_ct,   delta=f"{buy_ct} actionable")
c3.metric("WATCH Signals",   watch_ct)
c4.metric("Avg Score",       avg_sc)

st.divider()

# ── Rating filter tabs ────────────────────────
tab_all, tab_buy, tab_watch = st.tabs([
    f"All ({len(results)})",
    f"⬆ BUY ({buy_ct})",
    f"👀 WATCH ({watch_ct})",
])

def signal_tags_html(signals):
    color_map = {"VOL":"tag-vol","GAP↑":"tag-mom","GAP↓":"tag-gap","BRK":"tag-mom","REV":"tag-rev"}
    return " ".join(
        f'<span class="signal-tag {color_map.get(s,"tag-vol")}">{s}</span>'
        for s in signals
    ) or "<span style='color:#555'>—</span>"

def rating_html(r):
    cls = {"BUY":"buy-badge","WATCH":"watch-badge","AVOID":"avoid-badge"}.get(r, "")
    return f'<span class="{cls}">{r}</span>'

def render_table(data):
    if not data:
        st.info("No results in this category.")
        return

    # Build display dataframe
    rows = []
    for r in data:
        chg_arrow = "▲" if r["change"] >= 0 else "▼"
        chg_str   = f"{chg_arrow} {abs(r['change']):.1f}%"
        tv_url    = f"https://www.tradingview.com/chart/?symbol={r['ticker']}"
        rows.append({
            "Ticker":     r["ticker"],
            "Company":    r["company"],
            "Score":      r["composite"],
            "Rating":     r["rating"],
            "Signals":    ", ".join(r["signals"]) if r["signals"] else "—",
            "Price":      f"${r['price']:.2f}",
            "Change":     chg_str,
            "Vol ×":      f"{r['vol_ratio']:.1f}×",
            "RSI":        r["rsi"],
            "Entry":      f"${r['entry']:.2f}",
            "Stop":       f"${r['stop']:.2f}",
            "Target":     f"${r['target']:.2f}",
            "Risk %":     f"{r['risk_pct']}%",
            "Sector":     r["sector"],
        })

    df = pd.DataFrame(rows)

    # Color-coded rating column
    def color_rating(val):
        colors = {"BUY": "color: #00cc66; font-weight:700",
                  "WATCH": "color: #ffaa00; font-weight:700",
                  "AVOID": "color: #ff4444; font-weight:700"}
        return colors.get(val, "")

    def color_change(val):
        return "color: #00cc66" if "▲" in str(val) else "color: #ff4444"

    styled = df.style\
        .applymap(color_rating, subset=["Rating"])\
        .applymap(color_change, subset=["Change"])\
        .set_properties(**{"font-size": "13px"})\
        .hide(axis="index")

    st.dataframe(styled, use_container_width=True, height=min(50 + len(data) * 38, 600))

    # ── Expandable detail cards ───────────────
    st.subheader("📋 Signal Details")
    for r in data:
        tv_url = f"https://www.tradingview.com/chart/?symbol={r['ticker']}"
        with st.expander(f"**{r['ticker']}** — {r['company']}  |  Score: {r['composite']}  |  {r['rating']}"):
            col1, col2, col3 = st.columns(3)
            col1.metric("Entry",   f"${r['entry']:.2f}")
            col2.metric("Stop",    f"${r['stop']:.2f}",   delta=f"-{r['risk_pct']}% risk", delta_color="inverse")
            col3.metric("Target",  f"${r['target']:.2f}", delta=f"+{round(abs(r['target']-r['entry'])/r['entry']*100,1)}%")

            st.markdown(f"""
            | Field | Value |
            |---|---|
            | Sector | {r['sector']} |
            | RSI | {r['rsi']} |
            | Volume Spike | {r['vol_ratio']}× avg |
            | News Score | {r['news_score']} / 100 |
            | News Articles | {r['n_count']} recent items |
            | ATR | {r['atr']} |
            | Signals | {", ".join(r["signals"]) if r["signals"] else "—"} |
            """)

            st.caption(f"📰 {r['headline']}")
            st.markdown(f'<a href="{tv_url}" target="_blank" class="tv-link">📈 Open in TradingView</a>', unsafe_allow_html=True)

with tab_all:
    render_table(results)

with tab_buy:
    render_table([r for r in results if r["rating"] == "BUY"])

with tab_watch:
    render_table([r for r in results if r["rating"] == "WATCH"])

# ── Export ────────────────────────────────────
st.divider()
st.subheader("📥 Export Results")

df_export = pd.DataFrame([{
    "Ticker":    r["ticker"],
    "Company":   r["company"],
    "Score":     r["composite"],
    "Rating":    r["rating"],
    "Signals":   ", ".join(r["signals"]),
    "Price":     r["price"],
    "Change%":   r["change"],
    "VolSpike":  r["vol_ratio"],
    "RSI":       r["rsi"],
    "NewsScore": r["news_score"],
    "Entry":     r["entry"],
    "Stop":      r["stop"],
    "Target":    r["target"],
    "Risk%":     r["risk_pct"],
    "Sector":    r["sector"],
    "Headline":  r["headline"],
} for r in results])

col_dl1, col_dl2 = st.columns(2)
with col_dl1:
    st.download_button(
        "⬇ Download CSV",
        df_export.to_csv(index=False).encode(),
        file_name=f"newsflow_{datetime.date.today()}.csv",
        mime="text/csv",
        use_container_width=True,
    )
with col_dl2:
    # TradingView watchlist format: one ticker per line
    tv_watchlist = "\n".join(r["ticker"] for r in results if r["rating"] == "BUY")
    st.download_button(
        "📈 Download TradingView Watchlist (BUY only)",
        tv_watchlist.encode(),
        file_name=f"newsflow_watchlist_{datetime.date.today()}.txt",
        mime="text/plain",
        use_container_width=True,
        help="Import this file into TradingView's watchlist manager"
    )

st.divider()
st.caption("⚠ NewsFlow is a research tool, not financial advice. Always do your own analysis before trading.")

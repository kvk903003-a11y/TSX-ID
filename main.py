import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import ta
import time
import plotly.graph_objects as go

st.set_page_config(page_title="TSX Advanced Alerts Engine", layout="wide")
st.title("🇨🇦 TSX Semi-Automated Intraday Engine with Alerts")

# --- SETTINGS ---
INITIAL_CAPITAL = 100000
TOP_N = 3
REFRESH_INTERVAL = 60
STOP_LOSS = 0.5
TAKE_PROFIT = 1.0
TRAILING_STOP = True

# --- SESSION STATE ---
if "equity_curve" not in st.session_state:
    st.session_state.equity_curve = [INITIAL_CAPITAL]
if "capital" not in st.session_state:
    st.session_state.capital = INITIAL_CAPITAL
if "positions" not in st.session_state:
    st.session_state.positions = {}
if "alerts" not in st.session_state:
    st.session_state.alerts = []

# --- TSX STOCKS ---
stocks = [
    "SHOP.TO","SU.TO","RY.TO","TD.TO","BNS.TO",
    "ENB.TO","CNQ.TO","CP.TO","CNR.TO","BAM.TO",
    "TRP.TO","MFC.TO","WCN.TO","ATD.TO","CM.TO"
]

# --- SIGNAL GENERATION ---
def generate_signal(df):
    df["EMA10"] = ta.trend.ema_indicator(df["Close"], 10)
    df["EMA30"] = ta.trend.ema_indicator(df["Close"], 30)
    df["RSI7"] = ta.momentum.rsi(df["Close"], 7)
    last = df.iloc[-1]
    signal = 0
    score = 0
    if last["EMA10"] > last["EMA30"] and last["RSI7"] < 70:
        signal = 1
        score = ((last["EMA10"] - last["EMA30"]) / last["EMA30"]) * 100 + (70 - last["RSI7"])
    elif last["EMA10"] < last["EMA30"] and last["RSI7"] > 30:
        signal = -1
        score = ((last["EMA30"] - last["EMA10"]) / last["EMA10"]) * 100 + (last["RSI7"] - 30)
    return signal, last["Close"], score, df

# --- FETCH DATA & GENERATE SIGNALS ---
results = []
for ticker in stocks:
    df = yf.download(ticker, period="7d", interval="15m")
    if df.empty:
        continue
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    signal, price, score, df = generate_signal(df)
    results.append({"Stock": ticker, "Signal": signal, "Price": price, "Score": score, "DF": df})

df_signals = pd.DataFrame(results)

# --- TOP BUY SIGNALS ---
buy_signals = df_signals[df_signals["Signal"]==1].sort_values(by="Score", ascending=False)
top_buys = buy_signals.head(TOP_N)

st.subheader("🏆 Top Intraday Buy Signals")
st.dataframe(top_buys[["Stock","Price","Score"]])

# --- OPEN POSITIONS ---
total_score = top_buys["Score"].sum() if not top_buys.empty else 1
for _, row in top_buys.iterrows():
    ticker = row["Stock"]
    price = row["Price"]
    score = row["Score"]
    allocation = st.session_state.capital * (score / total_score)
    shares = allocation // price
    if ticker not in st.session_state.positions:
        st.session_state.positions[ticker] = []
    st.session_state.positions[ticker].append({
        "entry": price,
        "shares": shares,
        "status": "open",
        "stop_loss": price * (1 - STOP_LOSS/100),
        "take_profit": price * (1 + TAKE_PROFIT/100),
        "trailing_stop": price * (1 - STOP_LOSS/100)
    })
    # ALERT
    st.session_state.alerts.append(f"🔔 New BUY position for {ticker} at ${price:.2f}")

# --- CHECK POSITIONS ---
for ticker, pos_list in st.session_state.positions.items():
    df_price = df_signals[df_signals["Stock"]==ticker]["Price"].values[0]
    for pos in pos_list:
        if pos["status"]=="open":
            if TRAILING_STOP:
                pos["trailing_stop"] = max(pos["trailing_stop"], df_price * (1 - STOP_LOSS/100))
            if df_price <= pos["trailing_stop"]:
                pos["status"]="closed"
                st.session_state.capital += pos["shares"] * df_price
                alert_text = f"⚠️ {ticker} closed by Trailing Stop at ${df_price:.2f}"
                st.session_state.alerts.append(alert_text)
                st.toast(alert_text)
            elif df_price >= pos["take_profit"]:
                pos["status"]="closed"
                st.session_state.capital += pos["shares"] * df_price
                alert_text = f"✅ {ticker} closed by Take-Profit at ${df_price:.2f}"
                st.session_state.alerts.append(alert_text)
                st.toast(alert_text)

# --- UPDATE EQUITY CURVE ---
total_value = st.session_state.capital
for ticker, pos_list in st.session_state.positions.items():
    for pos in pos_list:
        if pos["status"]=="open":
            df_price = df_signals[df_signals["Stock"]==ticker]["Price"].values[0]
            total_value += pos["shares"] * df_price
st.session_state.equity_curve.append(total_value)

st.subheader("📈 Intraday Portfolio Equity Curve")
st.line_chart(st.session_state.equity_curve)

# --- ALERT LOG ---
st.subheader("📋 Alert Log")
alerts_df = pd.DataFrame({"Time": pd.Timestamp.now(), "Alert": st.session_state.alerts})
st.dataframe(alerts_df)

# --- RISK METRICS ---
equity_array = np.array(st.session_state.equity_curve)
returns = pd.Series(equity_array).pct_change().dropna()
if len(returns)>0:
    sharpe = np.sqrt(252*6.5*4) * returns.mean() / returns.std() if returns.std()!=0 else 0
    drawdown = (equity_array / np.maximum.accumulate(equity_array) - 1).min()
    st.write(f"Sharpe Ratio: {round(sharpe,2)}")
    st.write(f"Max Drawdown: {round(drawdown*100,2)}%")

# --- NEXT REFRESH ---
st.info(f"Next refresh in {REFRESH_INTERVAL} seconds...")
time.sleep(REFRESH_INTERVAL)
st.experimental_rerun()

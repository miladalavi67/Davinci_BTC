# -*- coding: utf-8 -*-
"""
موتور تحلیل تکنیکال — هسته اصلی
اندیکاتورها، روند، الگو، Order Block برای همه تایم‌فریم‌ها
"""
import numpy as np
import pandas as pd
import requests

BASE = "https://fapi.binance.com"


# ═══════════ دریافت داده ═══════════
def get_klines(symbol, interval, limit=200):
    """دریافت کندل از Binance Futures"""
    try:
        url = f"{BASE}/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
        r = requests.get(url, timeout=15, headers={"User-Agent": "btc-analyzer"})
        if not r.ok:
            return None
        data = r.json()
        df = pd.DataFrame(data, columns=[
            "ts", "open", "high", "low", "close", "vol",
            "ct", "qav", "trades", "tb", "tq", "ig"])
        for col in ["open", "high", "low", "close", "vol", "tb"]:
            df[col] = df[col].astype(float)
        df["ts"] = pd.to_datetime(df["ts"], unit="ms")
        return df
    except Exception as e:
        print(f"[!] خطای دریافت {symbol} {interval}: {e}")
        return None


def get_funding(symbol):
    try:
        r = requests.get(f"{BASE}/fapi/v1/premiumIndex?symbol={symbol}", timeout=10)
        if r.ok:
            return float(r.json().get("lastFundingRate", 0)) * 100
    except Exception:
        pass
    return None


def get_oi(symbol):
    try:
        r = requests.get(f"{BASE}/futures/data/openInterestHist?symbol={symbol}&period=1h&limit=24", timeout=10)
        if r.ok:
            data = r.json()
            if len(data) >= 2:
                first = float(data[0]["sumOpenInterest"])
                last = float(data[-1]["sumOpenInterest"])
                chg = (last - first) / first * 100 if first > 0 else 0
                return {"current": last, "chg_24h": round(chg, 2)}
    except Exception:
        pass
    return None


# ═══════════ اندیکاتورها ═══════════
def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()


def rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = -delta.where(delta < 0, 0).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def macd(series, fast=12, slow=26, signal=9):
    ef = ema(series, fast)
    es = ema(series, slow)
    line = ef - es
    sig = ema(line, signal)
    return line, sig, line - sig


def bollinger(series, period=20, std=2):
    mid = series.rolling(period).mean()
    sd = series.rolling(period).std()
    return mid + std * sd, mid, mid - std * sd


def vwap(df):
    tp = (df["high"] + df["low"] + df["close"]) / 3
    return (tp * df["vol"]).cumsum() / df["vol"].cumsum()


def atr(df, period=14):
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def stoch_rsi(series, period=14):
    r = rsi(series, period)
    mn = r.rolling(period).min()
    mx = r.rolling(period).max()
    return ((r - mn) / (mx - mn).replace(0, np.nan) * 100).fillna(50)


def ichimoku(df):
    high, low = df["high"], df["low"]
    tenkan = (high.rolling(9).max() + low.rolling(9).min()) / 2
    kijun = (high.rolling(26).max() + low.rolling(26).min()) / 2
    span_a = ((tenkan + kijun) / 2)
    span_b = (high.rolling(52).max() + low.rolling(52).min()) / 2
    price = df["close"].iloc[-1]
    # ابر فعلی (۲۶ دوره قبل)
    cloud_top = max(span_a.iloc[-27] if len(span_a) > 27 else span_a.iloc[-1],
                    span_b.iloc[-27] if len(span_b) > 27 else span_b.iloc[-1])
    cloud_bot = min(span_a.iloc[-27] if len(span_a) > 27 else span_a.iloc[-1],
                    span_b.iloc[-27] if len(span_b) > 27 else span_b.iloc[-1])
    pos = "above" if price > cloud_top else "below" if price < cloud_bot else "inside"
    tk_cross = "bull" if tenkan.iloc[-1] > kijun.iloc[-1] else "bear"
    return {"cloud_pos": pos, "tk_cross": tk_cross,
            "tenkan": round(tenkan.iloc[-1], 2), "kijun": round(kijun.iloc[-1], 2)}


# ═══════════ روند ═══════════
def detect_trend(df):
    """تشخیص روند با EMA + ساختار"""
    close = df["close"]
    e50 = ema(close, 50).iloc[-1]
    e200 = ema(close, 200).iloc[-1] if len(close) >= 200 else ema(close, 100).iloc[-1]
    price = close.iloc[-1]
    # ساختار HH/HL
    recent = df.tail(20)
    highs = recent["high"].values
    lows = recent["low"].values
    hh = sum(1 for i in range(1, len(highs)) if highs[i] > highs[i-1])
    hl = sum(1 for i in range(1, len(lows)) if lows[i] > lows[i-1])
    struct = "bull" if (hh > 10 and hl > 10) else "bear" if (hh < 10 and hl < 10) else "range"
    # ترکیب
    if price > e50 > e200 and struct == "bull":
        return {"trend": "strong_bull", "label": "صعودی قوی", "ema50": round(e50, 2), "ema200": round(e200, 2)}
    elif price < e50 < e200 and struct == "bear":
        return {"trend": "strong_bear", "label": "نزولی قوی", "ema50": round(e50, 2), "ema200": round(e200, 2)}
    elif price > e50:
        return {"trend": "bull", "label": "صعودی", "ema50": round(e50, 2), "ema200": round(e200, 2)}
    elif price < e50:
        return {"trend": "bear", "label": "نزولی", "ema50": round(e50, 2), "ema200": round(e200, 2)}
    return {"trend": "range", "label": "رنج", "ema50": round(e50, 2), "ema200": round(e200, 2)}


# ═══════════ الگو (کانال / مثلث) ═══════════
def detect_pattern(df, lookback=40):
    seg = df.tail(lookback).reset_index(drop=True)
    if len(seg) < lookback:
        return {"pattern": "none", "label": "—"}
    x = np.arange(len(seg))
    # رگرسیون روی high و low
    ph = np.polyfit(x, seg["high"], 1)
    pl = np.polyfit(x, seg["low"], 1)
    pc = np.polyfit(x, seg["close"], 1)
    # R²
    pred = np.polyval(pc, x)
    ss_res = np.sum((seg["close"] - pred)**2)
    ss_tot = np.sum((seg["close"] - seg["close"].mean())**2)
    r2 = 1 - ss_res/ss_tot if ss_tot > 0 else 0
    avg = seg["close"].mean()
    slope_norm = pc[0] / avg * 100
    # عرض (همگرایی؟)
    w_start = np.polyval(ph, 0) - np.polyval(pl, 0)
    w_end = np.polyval(ph, len(seg)-1) - np.polyval(pl, len(seg)-1)
    converging = w_end < w_start * 0.7
    if converging and r2 < 0.6:
        return {"pattern": "triangle", "label": "مثلث (همگرا)", "r2": round(r2, 2)}
    if slope_norm > 0.08 and r2 > 0.4:
        return {"pattern": "channel_up", "label": "کانال صعودی", "r2": round(r2, 2)}
    if slope_norm < -0.08 and r2 > 0.4:
        return {"pattern": "channel_down", "label": "کانال نزولی", "r2": round(r2, 2)}
    return {"pattern": "range", "label": "رنج", "r2": round(r2, 2)}


# ═══════════ Order Block + FVG ═══════════
def detect_order_blocks(df, max_look=30):
    """تشخیص Order Block با FVG و mitigation"""
    C = df.tail(max_look + 3).reset_index(drop=True)
    price = C["close"].iloc[-1]
    bull_obs, bear_obs = [], []
    for i in range(len(C) - 3, max(0, len(C) - max_look), -1):
        nxt = C.iloc[i+1]
        move = abs(nxt["close"] - nxt["open"]) / nxt["open"]
        nb = abs(nxt["close"] - nxt["open"])
        nr = nxt["high"] - nxt["low"]
        strong = move > 0.006 and nr > 0 and nb/nr > 0.55
        if not strong:
            continue
        cur = C.iloc[i]
        # OB صعودی
        if cur["close"] < cur["open"] and nxt["close"] > nxt["open"]:
            after = C.iloc[i+2] if i+2 < len(C) else None
            fvg = bool(after is not None and after["low"] > cur["high"])
            mid = (cur["low"] + cur["high"]) / 2
            bull_obs.append({"lo": round(cur["low"], 2), "hi": round(cur["high"], 2),
                             "mid": round(mid, 2), "fvg": fvg,
                             "dist": round((mid - price)/price*100, 2)})
        # OB نزولی
        if cur["close"] > cur["open"] and nxt["close"] < nxt["open"]:
            after = C.iloc[i+2] if i+2 < len(C) else None
            fvg = bool(after is not None and after["high"] < cur["low"])
            mid = (cur["low"] + cur["high"]) / 2
            bear_obs.append({"lo": round(cur["low"], 2), "hi": round(cur["high"], 2),
                             "mid": round(mid, 2), "fvg": fvg,
                             "dist": round((mid - price)/price*100, 2)})
    bull_obs.sort(key=lambda o: abs(o["dist"]))
    bear_obs.sort(key=lambda o: abs(o["dist"]))
    return {"bull": bull_obs[:3], "bear": bear_obs[:3]}


def rsi_divergence(df):
    close = df["close"]
    r = rsi(close)
    if len(close) < 20:
        return None
    p_now, p_prev = close.iloc[-1], close.iloc[-6]
    r_now, r_prev = r.iloc[-1], r.iloc[-6]
    if p_now < p_prev and r_now > r_prev and r_now < 48:
        return "bull"
    if p_now > p_prev and r_now < r_prev and r_now > 52:
        return "bear"
    return None


# ═══════════ تحلیل کامل یک تایم‌فریم ═══════════
def analyze_timeframe(symbol, interval):
    df = get_klines(symbol, interval, 200)
    if df is None or len(df) < 60:
        return None
    close = df["close"]
    price = close.iloc[-1]
    macd_line, macd_sig, macd_hist = macd(close)
    bb_up, bb_mid, bb_low = bollinger(close)
    trend = detect_trend(df)
    pattern = detect_pattern(df)
    obs = detect_order_blocks(df)
    ichi = ichimoku(df)
    div = rsi_divergence(df)
    # CVD
    delta = df["tb"] - (df["vol"] - df["tb"])
    cvd = float(delta.tail(10).sum())
    return {
        "interval": interval,
        "price": round(price, 2),
        "trend": trend,
        "pattern": pattern,
        "rsi": round(float(rsi(close).iloc[-1]), 1),
        "rsi_div": div,
        "macd": "bull" if macd_line.iloc[-1] > macd_sig.iloc[-1] else "bear",
        "macd_hist": round(float(macd_hist.iloc[-1]), 2),
        "stoch_rsi": round(float(stoch_rsi(close).iloc[-1]), 1),
        "bb_pos": "upper" if price > bb_up.iloc[-1] else "lower" if price < bb_low.iloc[-1] else "mid",
        "vwap": round(float(vwap(df).iloc[-1]), 2),
        "atr": round(float(atr(df).iloc[-1]), 2),
        "ichimoku": ichi,
        "order_blocks": obs,
        "cvd": round(cvd, 1),
        "cvd_dir": "in" if cvd > 0 else "out",
    }

# -*- coding: utf-8 -*-
"""
نوار خلاصه بیت‌کوین (شبیه v17)
─────────────────────────────────
همه متریک‌های کلیدی را فشرده و یکجا برمی‌گرداند:
4H | 1H | RSI | FIB | US session | SCORE
"""
from datetime import datetime, timezone
from analysis import get_klines, rsi, ema, macd
from advanced import ichimoku_full, important_zones


def us_session_label():
    """وضعیت سشن آمریکا (UTC)"""
    t = datetime.now(timezone.utc)
    m = t.hour * 60 + t.minute
    if 12 * 60 <= m < 13 * 60 + 30:
        return "Pre-Market"
    if 13 * 60 + 30 <= m < 20 * 60:
        return "باز (US)"
    if 20 * 60 <= m < 21 * 60:
        return "Power Hour"
    return "بسته"


def _trend_of(df):
    """روند ساده یک تایم‌فریم بر اساس EMA"""
    close = df["close"]
    price = float(close.iloc[-1])
    e50 = ema(close, 50); e200 = ema(close, 200)
    e50v = float(e50.iloc[-1]); e200v = float(e200.iloc[-1])
    if price > e50v > e200v:
        return "صعودی قوی", "strong_bull", 2
    elif price > e50v:
        return "صعودی", "bull", 1
    elif price < e50v < e200v:
        return "نزولی قوی", "strong_bear", -2
    elif price < e50v:
        return "نزولی", "bear", -1
    return "خنثی", "range", 0


def btc_summary(symbol="BTCUSDT"):
    df4 = get_klines(symbol, "4h", 200)
    df1 = get_klines(symbol, "1h", 200)
    df15 = get_klines(symbol, "15m", 200)
    if df1 is None or df4 is None:
        return {"error": "داده در دسترس نیست"}

    price = float(df1["close"].iloc[-1])

    # روند ۴H و ۱H
    t4_label, t4_cls, t4_score = _trend_of(df4)
    t1_label, t1_cls, t1_score = _trend_of(df1)

    # RSI روی ۱H
    rsi1 = round(float(rsi(df1["close"]).iloc[-1]), 1)
    rsi_state = "اشباع خرید" if rsi1 >= 70 else "اشباع فروش" if rsi1 <= 30 else "نرمال"

    # ایچیموکو ۱H
    ich = ichimoku_full(df1)

    # نزدیک‌ترین سطح فیبو/محدوده مهم (۱۵M یا ۱H)
    fib_txt = "—"
    zsrc = df15 if df15 is not None else df1
    zinfo = important_zones(zsrc)
    if zinfo["zones"]:
        z = min(zinfo["zones"], key=lambda x: abs(x["dist"]))
        side = "حمایت" if z["direction"] == "support" else "مقاومت"
        fib_txt = f"{z['fib']} ({side} {z['dist']:+.1f}٪)"

    # MACD ۴H
    ml, ms, mh = macd(df4["close"])
    macd4 = "صعودی" if float(ml.iloc[-1]) > float(ms.iloc[-1]) else "نزولی"

    # SCORE کلی (ترکیب همه، -۱۰ تا +۱۰ نرمال به ۰-۱۰۰)
    raw = t4_score * 2 + t1_score * 2 + ich["score"]
    if rsi1 >= 70: raw -= 1
    elif rsi1 <= 30: raw += 1
    if macd4 == "صعودی": raw += 1
    else: raw -= 1
    # نرمال‌سازی به ۰-۱۰۰
    score = max(0, min(100, round(50 + raw * 5)))

    if score >= 65:
        bias = "صعودی"; bias_cls = "bull"
    elif score <= 35:
        bias = "نزولی"; bias_cls = "bear"
    else:
        bias = "خنثی"; bias_cls = "range"

    return {
        "symbol": symbol,
        "price": round(price, 2),
        "us_session": us_session_label(),
        "tf4": {"label": t4_label, "cls": t4_cls},
        "tf1": {"label": t1_label, "cls": t1_cls},
        "rsi1": rsi1, "rsi_state": rsi_state,
        "ichimoku": ich["verdict"],
        "macd4": macd4,
        "fib": fib_txt,
        "score": score, "bias": bias, "bias_cls": bias_cls,
        "ts": datetime.now(timezone.utc).strftime("%H:%M UTC"),
    }

# -*- coding: utf-8 -*-
"""
تحلیل پیشرفته (مرحله ۱ و ۲) — روی تایم‌فریم ۱ ساعته
─────────────────────────────────────────────────────
۱. ایچیموکو کامل (سیگنال، نه فقط موقعیت ابر)
۲. RSI: واگرایی + مناطق اشباع
۳. فیبوناچی + هم‌پوشانی با Order Block → محدوده مهم (صعودی/نزولی)
"""
import numpy as np
import pandas as pd
from analysis import get_klines, ema, rsi, detect_order_blocks


# ═══════════ ۱. ایچیموکو کامل ═══════════
def ichimoku_full(df):
    """تحلیل کامل ایچیموکو با سیگنال نهایی"""
    high, low, close = df["high"], df["low"], df["close"]
    tenkan = (high.rolling(9).max() + low.rolling(9).min()) / 2
    kijun = (high.rolling(26).max() + low.rolling(26).min()) / 2
    span_a = ((tenkan + kijun) / 2)
    span_b = (high.rolling(52).max() + low.rolling(52).min()) / 2
    price = close.iloc[-1]

    # ابر فعلی (۲۶ دوره جلوتر projection → استفاده از ۲۶ قبل)
    idx = -27 if len(span_a) > 27 else -1
    cloud_top = max(span_a.iloc[idx], span_b.iloc[idx])
    cloud_bot = min(span_a.iloc[idx], span_b.iloc[idx])

    # اجزای سیگنال
    signals = []
    score = 0  # مثبت=صعودی، منفی=نزولی

    # موقعیت نسبت به ابر
    if price > cloud_top:
        pos = "above"; score += 2; signals.append("بالای ابر (صعودی)")
    elif price < cloud_bot:
        pos = "below"; score -= 2; signals.append("زیر ابر (نزولی)")
    else:
        pos = "inside"; signals.append("داخل ابر (بلاتکلیف)")

    # تقاطع تنکان/کیجون (TK Cross)
    tk = tenkan.iloc[-1]; kj = kijun.iloc[-1]
    if tk > kj:
        score += 1; signals.append("تنکان بالای کیجون")
    else:
        score -= 1; signals.append("تنکان زیر کیجون")

    # رنگ ابر آینده (span_a vs span_b فعلی)
    if span_a.iloc[-1] > span_b.iloc[-1]:
        score += 1; signals.append("ابر آینده سبز")
    else:
        score -= 1; signals.append("ابر آینده قرمز")

    # قیمت نسبت به کیجون (خط پایه)
    if price > kj:
        score += 1
    else:
        score -= 1

    # جمع‌بندی
    if score >= 3:
        verdict = "صعودی قوی"; bias = "bull"
    elif score >= 1:
        verdict = "صعودی"; bias = "bull"
    elif score <= -3:
        verdict = "نزولی قوی"; bias = "bear"
    elif score <= -1:
        verdict = "نزولی"; bias = "bear"
    else:
        verdict = "خنثی"; bias = "neutral"

    return {
        "verdict": verdict, "bias": bias, "score": score,
        "cloud_pos": pos, "signals": signals,
        "tenkan": round(float(tk), 2), "kijun": round(float(kj), 2),
        "cloud_top": round(float(cloud_top), 2), "cloud_bot": round(float(cloud_bot), 2),
    }


# ═══════════ ۲. RSI: واگرایی + اشباع ═══════════
def rsi_analysis(df):
    """RSI با تشخیص اشباع و واگرایی"""
    close = df["close"]
    r = rsi(close)
    cur = float(r.iloc[-1])

    # منطقه اشباع
    if cur >= 70:
        zone = "overbought"; zone_fa = "اشباع خرید 🔴"
    elif cur <= 30:
        zone = "oversold"; zone_fa = "اشباع فروش 🟢"
    else:
        zone = "neutral"; zone_fa = "خنثی"

    # واگرایی (مقایسه دو قله/دره اخیر)
    div = None; div_fa = None
    if len(close) >= 20:
        p_now, p_prev = close.iloc[-1], close.iloc[-7]
        r_now, r_prev = r.iloc[-1], r.iloc[-7]
        # واگرایی صعودی: قیمت کف پایین‌تر، RSI کف بالاتر
        if p_now < p_prev and r_now > r_prev and r_now < 50:
            div = "bull"; div_fa = "واگرایی صعودی 🟢 (احتمال برگشت بالا)"
        # واگرایی نزولی: قیمت سقف بالاتر، RSI سقف پایین‌تر
        elif p_now > p_prev and r_now < r_prev and r_now > 50:
            div = "bear"; div_fa = "واگرایی نزولی 🔴 (احتمال برگشت پایین)"

    return {"value": round(cur, 1), "zone": zone, "zone_fa": zone_fa,
            "divergence": div, "divergence_fa": div_fa}


# ═══════════ ۳. فیبوناچی + Order Block → محدوده مهم ═══════════
def find_swing(df, lookback=60):
    """آخرین swing high و low مهم را پیدا می‌کند"""
    seg = df.tail(lookback)
    hi_idx = seg["high"].idxmax()
    lo_idx = seg["low"].idxmin()
    hi = float(seg["high"].max())
    lo = float(seg["low"].min())
    # جهت موج: اگر high بعد از low بود → صعودی، برعکس → نزولی
    swing_up = hi_idx > lo_idx
    return {"hi": hi, "lo": lo, "swing_up": swing_up}


def fib_levels(hi, lo, swing_up):
    """سطوح فیبوناچی اصلاحی"""
    diff = hi - lo
    ratios = {"0.236": 0.236, "0.382": 0.382, "0.5": 0.5,
              "0.618": 0.618, "0.705": 0.705, "0.786": 0.786}
    levels = {}
    for name, r in ratios.items():
        if swing_up:
            # موج صعودی → اصلاح از بالا به پایین
            levels[name] = round(hi - diff * r, 2)
        else:
            # موج نزولی → اصلاح از پایین به بالا
            levels[name] = round(lo + diff * r, 2)
    return levels


def important_zones(df):
    """
    محدوده مهم = هم‌پوشانی سطح فیبوناچی با Order Block
    (جایی که هم فیبو مهمه، هم سفارش واقعی هست → قوی‌تر)
    """
    price = float(df["close"].iloc[-1])
    swing = find_swing(df)
    fib = fib_levels(swing["hi"], swing["lo"], swing["swing_up"])
    obs = detect_order_blocks(df)
    all_obs = [(o, "bull") for o in obs["bull"]] + [(o, "bear") for o in obs["bear"]]

    zones = []
    # ناحیه طلایی فیبو معمولاً 0.618 تا 0.705
    golden = ["0.5", "0.618", "0.705", "0.786"]

    for fname, flevel in fib.items():
        # آیا یه Order Block نزدیک این سطح فیبو هست؟ (±0.7%)
        matched_ob = None
        for ob, obtype in all_obs:
            if abs(ob["mid"] - flevel) / flevel < 0.007:
                matched_ob = (ob, obtype)
                break
        importance = 1  # پایه
        reasons = [f"فیبو {fname}"]
        if fname in golden:
            importance += 1; reasons.append("ناحیه طلایی")
        if matched_ob:
            importance += 2; reasons.append(f"Order Block ({'صعودی' if matched_ob[1]=='bull' else 'نزولی'})")
            if matched_ob[0].get("fvg"):
                importance += 1; reasons.append("FVG")
        dist = round((flevel - price) / price * 100, 2)
        # جهت ناحیه: زیر قیمت = حمایت (صعودی)، بالای قیمت = مقاومت (نزولی)
        zone_dir = "support" if flevel < price else "resistance"
        zones.append({
            "level": flevel, "fib": fname, "importance": importance,
            "reasons": reasons, "dist": dist, "direction": zone_dir,
            "has_ob": matched_ob is not None,
        })

    # مرتب بر اساس اهمیت، بعد نزدیکی
    zones.sort(key=lambda z: (-z["importance"], abs(z["dist"])))
    # فقط محدوده‌های مهم (اهمیت ۲+)
    important = [z for z in zones if z["importance"] >= 2][:5]
    return {
        "swing_hi": swing["hi"], "swing_lo": swing["lo"],
        "swing_up": swing["swing_up"], "zones": important, "price": price,
    }


# ═══════════ تحلیل کامل پیشرفته ═══════════
def advanced_analysis(symbol, interval="1h"):
    df = get_klines(symbol, interval, 200)
    if df is None or len(df) < 60:
        return None
    return {
        "symbol": symbol,
        "interval": interval,
        "price": round(float(df["close"].iloc[-1]), 2),
        "ichimoku": ichimoku_full(df),
        "rsi": rsi_analysis(df),
        "zones": important_zones(df),
    }

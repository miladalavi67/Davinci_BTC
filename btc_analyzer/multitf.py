# -*- coding: utf-8 -*-
"""
تحلیل چندمرحله‌ای بیت‌کوین + سناریوهای سشن آمریکا
──────────────────────────────────────────────────
مرحله ۱: ۱ ساعته → ایچیموکو کامل (روند اصلی)
مرحله ۲: ۴ ساعته → RSI + MACD (مومنتوم)
مرحله ۳: ۱۵ دقیقه → محدوده‌های ورود (سطوح دقیق)
مرحله ۴: ترکیب → سناریوهای محتمل برای سشن US
"""
import numpy as np
from datetime import datetime, timezone
from analysis import get_klines, ema, rsi, macd, atr, detect_order_blocks
from advanced import ichimoku_full, important_zones


def _last(series):
    try:
        return float(series.iloc[-1])
    except Exception:
        return None


# ═══════════ مرحله ۱: ۱ ساعته — ایچیموکو ═══════════
def step1_ichimoku_1h(df1h):
    ich = ichimoku_full(df1h)
    return {
        "tf": "1H", "verdict": ich["verdict"], "bias": ich["bias"],
        "score": ich["score"], "signals": ich["signals"],
        "tenkan": ich["tenkan"], "kijun": ich["kijun"],
        "cloud_top": ich["cloud_top"], "cloud_bot": ich["cloud_bot"],
    }


# ═══════════ مرحله ۲: ۴ ساعته — RSI + MACD ═══════════
def step2_momentum_4h(df4h):
    close = df4h["close"]
    r = rsi(close)
    rsi_val = _last(r)
    macd_line, macd_sig, macd_hist = macd(close)
    ml = _last(macd_line); ms = _last(macd_sig); mh = _last(macd_hist)

    # وضعیت RSI
    if rsi_val >= 70:
        rsi_state = "اشباع خرید"; rsi_bias = "bear"
    elif rsi_val <= 30:
        rsi_state = "اشباع فروش"; rsi_bias = "bull"
    elif rsi_val >= 55:
        rsi_state = "مایل به صعود"; rsi_bias = "bull"
    elif rsi_val <= 45:
        rsi_state = "مایل به نزول"; rsi_bias = "bear"
    else:
        rsi_state = "خنثی"; rsi_bias = "neutral"

    # وضعیت MACD
    if ml > ms and mh > 0:
        macd_state = "صعودی (بالای سیگنال)"; macd_bias = "bull"
    elif ml < ms and mh < 0:
        macd_state = "نزولی (زیر سیگنال)"; macd_bias = "bear"
    else:
        macd_state = "در حال تغییر"; macd_bias = "neutral"

    # جمع‌بندی مومنتوم
    score = 0
    if rsi_bias == "bull": score += 1
    elif rsi_bias == "bear": score -= 1
    if macd_bias == "bull": score += 1
    elif macd_bias == "bear": score -= 1

    if score >= 2: verdict = "مومنتوم صعودی"; bias = "bull"
    elif score <= -2: verdict = "مومنتوم نزولی"; bias = "bear"
    else: verdict = "مومنتوم خنثی"; bias = "neutral"

    return {
        "tf": "4H", "verdict": verdict, "bias": bias, "score": score,
        "rsi": round(rsi_val, 1), "rsi_state": rsi_state,
        "macd_state": macd_state,
        "macd_hist": round(mh, 4) if mh is not None else None,
    }


# ═══════════ مرحله ۳: ۱۵ دقیقه — محدوده‌های ورود ═══════════
def step3_zones_15m(df15):
    price = float(df15["close"].iloc[-1])
    zinfo = important_zones(df15)
    zones = zinfo["zones"]

    # نزدیک‌ترین حمایت و مقاومت
    supports = [z for z in zones if z["direction"] == "support"]
    resistances = [z for z in zones if z["direction"] == "resistance"]
    nearest_sup = min(supports, key=lambda z: abs(z["dist"])) if supports else None
    nearest_res = min(resistances, key=lambda z: abs(z["dist"])) if resistances else None

    return {
        "tf": "15M", "price": round(price, 2),
        "zones": zones[:5],
        "nearest_support": nearest_sup,
        "nearest_resistance": nearest_res,
    }


# ═══════════ مرحله ۴: سناریوهای سشن US ═══════════
def build_scenarios(s1, s2, s3):
    """
    بر اساس ۳ تایم‌فریم، سناریوهای محتمل برای سشن US می‌سازد.
    هر سناریو: شرط محرک + جهت + هدف + احتمال نسبی.
    """
    price = s3["price"]
    sup = s3["nearest_support"]
    res = s3["nearest_resistance"]
    scenarios = []

    # هم‌سویی تایم‌فریم‌ها
    biases = [s1["bias"], s2["bias"]]
    bull_count = biases.count("bull")
    bear_count = biases.count("bear")

    # ── سناریو صعودی ──
    if bull_count >= 1:
        prob = "بالا" if bull_count == 2 else "متوسط"
        trigger = f"شکست مقاومت ${res['level']}" if res else "ادامه روند صعودی"
        target = res["level"] if res else round(price * 1.015, 2)
        # هدف بعدی
        next_target = round(target * 1.01, 2)
        scenarios.append({
            "type": "bull", "title": "سناریو صعودی", "prob": prob,
            "trigger": trigger,
            "entry": round(price, 2),
            "target": next_target,
            "stop": sup["level"] if sup else round(price * 0.99, 2),
            "logic": f"۱H {s1['verdict']} + ۴H {s2['verdict']}",
        })

    # ── سناریو نزولی ──
    if bear_count >= 1:
        prob = "بالا" if bear_count == 2 else "متوسط"
        trigger = f"شکست حمایت ${sup['level']}" if sup else "ادامه روند نزولی"
        target = sup["level"] if sup else round(price * 0.985, 2)
        next_target = round(target * 0.99, 2)
        scenarios.append({
            "type": "bear", "title": "سناریو نزولی", "prob": prob,
            "trigger": trigger,
            "entry": round(price, 2),
            "target": next_target,
            "stop": res["level"] if res else round(price * 1.01, 2),
            "logic": f"۱H {s1['verdict']} + ۴H {s2['verdict']}",
        })

    # ── سناریو خنثی/رنج (اگر تایم‌فریم‌ها متناقض) ──
    if bull_count == bear_count or (bull_count == 0 and bear_count == 0):
        rng_low = sup["level"] if sup else round(price * 0.99, 2)
        rng_high = res["level"] if res else round(price * 1.01, 2)
        scenarios.append({
            "type": "range", "title": "سناریو رنج (احتیاط)", "prob": "متوسط",
            "trigger": f"نوسان بین ${rng_low} و ${rng_high}",
            "entry": None, "target": None, "stop": None,
            "logic": "تایم‌فریم‌ها هم‌سو نیستند — صبر تا شکست واضح",
        })

    # جهت کلی پیشنهادی
    if bull_count > bear_count:
        overall = "تمایل صعودی"
    elif bear_count > bull_count:
        overall = "تمایل نزولی"
    else:
        overall = "بلاتکلیف (رنج)"

    return {"overall": overall, "scenarios": scenarios}


# ═══════════ تحلیل کامل ═══════════
def multi_tf_analysis(symbol="BTCUSDT"):
    df1h = get_klines(symbol, "1h", 200)
    df4h = get_klines(symbol, "4h", 200)
    df15 = get_klines(symbol, "15m", 200)
    if df1h is None or df4h is None or df15 is None:
        return {"error": "داده در دسترس نیست"}
    if len(df1h) < 60 or len(df4h) < 40 or len(df15) < 60:
        return {"error": "داده کافی نیست"}

    s1 = step1_ichimoku_1h(df1h)
    s2 = step2_momentum_4h(df4h)
    s3 = step3_zones_15m(df15)
    scen = build_scenarios(s1, s2, s3)

    price = float(df1h["close"].iloc[-1])
    return {
        "symbol": symbol,
        "price": round(price, 2),
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "step1": s1,
        "step2": s2,
        "step3": s3,
        "scenarios": scen,
    }

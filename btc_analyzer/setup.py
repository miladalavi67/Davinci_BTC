# -*- coding: utf-8 -*-
"""
تشخیص ستاپ — ترکیب ML + Confluence
ستاپ معتبر = ML ≥ ۷۰٪ هم‌جهت + حداقل چند فاکتور Confluence هم‌جهت
"""
from analysis import (get_klines, analyze_timeframe, ema, rsi, macd,
                      detect_order_blocks)
from ml_model import train_and_backtest


def count_confluence(a, direction):
    """شمارش فاکتورهای هم‌جهت با direction در یک تحلیل تایم‌فریم"""
    if not a:
        return 0, []
    score = 0
    factors = []
    is_bull = direction == "bull"

    # روند
    t = a["trend"]["trend"]
    if (is_bull and "bull" in t) or (not is_bull and "bear" in t):
        score += 2 if "strong" in t else 1
        factors.append("روند")

    # MACD
    if (is_bull and a["macd"] == "bull") or (not is_bull and a["macd"] == "bear"):
        score += 1
        factors.append("MACD")

    # RSI (نه اشباع مخالف)
    if is_bull and a["rsi"] < 60:
        score += 1; factors.append("RSI")
    elif not is_bull and a["rsi"] > 40:
        score += 1; factors.append("RSI")

    # واگرایی RSI
    if a.get("rsi_div") == direction:
        score += 2; factors.append("واگرایی RSI")

    # StochRSI
    if is_bull and a["stoch_rsi"] < 30:
        score += 1; factors.append("StochRSI")
    elif not is_bull and a["stoch_rsi"] > 70:
        score += 1; factors.append("StochRSI")

    # ایچیموکو
    ic = a["ichimoku"]["cloud_pos"]
    if (is_bull and ic == "above") or (not is_bull and ic == "below"):
        score += 1; factors.append("ایچیموکو")

    # CVD
    if (is_bull and a["cvd_dir"] == "in") or (not is_bull and a["cvd_dir"] == "out"):
        score += 1; factors.append("CVD")

    # بولینگر (نزدیک باند مخالف = فرصت)
    if is_bull and a["bb_pos"] == "lower":
        score += 1; factors.append("بولینگر")
    elif not is_bull and a["bb_pos"] == "upper":
        score += 1; factors.append("بولینگر")

    return score, factors


def detect_setup(symbol, interval="1h"):
    """
    ستاپ معتبر وقتی:
      - ML احتمال یک جهت ≥ ۷۰٪
      - و Confluence همان جهت ≥ ۵ امتیاز
    """
    # تحلیل تکنیکال
    a = analyze_timeframe(symbol, interval)
    if not a:
        return None

    # ML
    ml = train_and_backtest(symbol, interval)
    if "error" in ml:
        ml_bull = None
    else:
        ml_bull = ml["bull_prob"]

    if ml_bull is None:
        return None

    # تعیین جهت غالب ML
    if ml_bull >= 70:
        direction = "bull"; ml_prob = ml_bull
    elif ml_bull <= 30:
        direction = "bear"; ml_prob = 100 - ml_bull
    else:
        return {"has_setup": False, "ml_prob": ml_bull,
                "reason": "ML زیر آستانه ۷۰٪"}

    # Confluence همان جهت
    conf_score, factors = count_confluence(a, direction)
    CONF_MIN = 5

    has_setup = conf_score >= CONF_MIN

    # نقطه ستاپ = قیمت فعلی، نزدیک‌ترین OB هم‌جهت برای ورود
    obs = a["order_blocks"]
    entry_zone = None
    if direction == "bull" and obs["bull"]:
        entry_zone = obs["bull"][0]
    elif direction == "bear" and obs["bear"]:
        entry_zone = obs["bear"][0]

    return {
        "has_setup": has_setup,
        "direction": direction,
        "ml_prob": ml_prob,
        "ml_bull_raw": ml_bull,
        "conf_score": conf_score,
        "conf_min": CONF_MIN,
        "factors": factors,
        "price": a["price"],
        "entry_zone": entry_zone,
        "backtest_acc": ml.get("backtest_acc"),
    }


def get_chart_data(symbol, interval="1h", limit=150):
    """داده کندل برای رسم چارت + سطوح ستاپ"""
    df = get_klines(symbol, interval, limit)
    if df is None or len(df) < 30:
        return None
    candles = []
    for _, row in df.iterrows():
        candles.append({
            "time": int(row["ts"].timestamp()),
            "open": round(row["open"], 2),
            "high": round(row["high"], 2),
            "low": round(row["low"], 2),
            "close": round(row["close"], 2),
        })
    # EMA برای overlay
    e50 = ema(df["close"], 50)
    e200 = ema(df["close"], 200) if len(df) >= 200 else ema(df["close"], 100)
    ema50 = [{"time": int(df["ts"].iloc[i].timestamp()), "value": round(float(e50.iloc[i]), 2)}
             for i in range(len(df)) if not (e50.iloc[i] != e50.iloc[i])]
    ema200 = [{"time": int(df["ts"].iloc[i].timestamp()), "value": round(float(e200.iloc[i]), 2)}
              for i in range(len(df)) if not (e200.iloc[i] != e200.iloc[i])]
    # اوردر بلاک‌ها
    obs = detect_order_blocks(df)
    return {
        "candles": candles,
        "ema50": ema50,
        "ema200": ema200,
        "order_blocks": obs,
    }

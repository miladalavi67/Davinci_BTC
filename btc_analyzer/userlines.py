# -*- coding: utf-8 -*-
"""
تحلیل خط‌های دستی کاربر (فقط ادمین)
─────────────────────────────────────
کاربر روی چارت خط می‌کشد. سیستم هر خط را با داده واقعی می‌سنجد:
  • خط افقی → آیا واقعاً حمایت/مقاومت معتبری است؟ (لمس‌های گذشته)
  • خط مورب → آیا خط روند معتبری است؟ (لمس‌های واقعی)
سیستم چشم‌بسته قبول نمی‌کند:
  • اگر خط معتبر بود → تأیید + در سناریوی US دخیل می‌شود
  • اگر معتبر نبود → دلیل می‌آورد چرا

ورودی هر خط: دو نقطه {time, price} از چارت (مختصات واقعی).
"""
from analysis import get_klines, detect_order_blocks, ema, atr
from advanced import important_zones


def _slope_norm(p1, p2, price):
    """شیب نرمال‌شده خط (نسبت به قیمت)"""
    t1, v1 = p1["time"], p1["price"]
    t2, v2 = p2["time"], p2["price"]
    if t2 == t1:
        return 0
    # شیب به ازای هر کندل (نه ثانیه) — نرمال به قیمت
    dt = (t2 - t1)
    return ((v2 - v1) / dt) / price * 3600  # تقریب به ساعت


def classify_line(p1, p2, price):
    """نوع خط را تشخیص می‌دهد: افقی / صعودی / نزولی"""
    v1, v2 = p1["price"], p2["price"]
    avg = (v1 + v2) / 2
    change = abs(v2 - v1) / avg
    if change < 0.005:  # کمتر از ۰.۵٪ → افقی
        return "horizontal"
    return "rising" if v2 > v1 else "falling"


def line_price_at(p1, p2, t):
    """قیمت خط در زمان t (درون‌یابی خطی)"""
    t1, v1 = p1["time"], p1["price"]
    t2, v2 = p2["time"], p2["price"]
    if t2 == t1:
        return v1
    return v1 + (v2 - v1) * (t - t1) / (t2 - t1)


def validate_line(df, p1, p2):
    """
    یک خط را با داده واقعی می‌سنجد و نتیجه + دلیل برمی‌گرداند.
    p1/p2 دارای time (ثانیه یونیکس، مثل چارت) و price هستند.
    """
    price = float(df["close"].iloc[-1])
    line_type = classify_line(p1, p2, price)
    atr_val = float(atr(df).iloc[-1])
    tol = atr_val * 0.6  # تلورانس لمس = ۰.۶ ATR

    # زمان کندل‌ها به ثانیه یونیکس (مثل چارت Lightweight)
    df_times = (df["ts"].astype("int64") // 10**9).tolist()
    highs = df["high"].tolist(); lows = df["low"].tolist(); closes = df["close"].tolist()

    t_start = min(p1["time"], p2["time"])
    t_end = max(p1["time"], p2["time"])
    touches = 0

    for i, t in enumerate(df_times):
        # در بازه خط (با کمی امتداد به جلو)
        if t < t_start or t > t_end + (t_end - t_start) * 0.3:
            continue
        lp = line_price_at(p1, p2, t)
        hi, lo = highs[i], lows[i]
        if lo - tol <= lp <= hi + tol:
            touches += 1

    # ── ارزیابی اعتبار ──
    reasons = []
    valid = False
    strength = 0

    if touches >= 3:
        valid = True; strength = 3
        reasons.append(f"خط با {touches} بار لمس واقعی تأیید می‌شود (معتبر)")
    elif touches == 2:
        valid = True; strength = 2
        reasons.append(f"خط با {touches} لمس نسبتاً معتبر است")
    elif touches == 1:
        valid = False; strength = 1
        reasons.append("فقط ۱ لمس پیدا شد — برای خط معتبر حداقل ۲ لمس لازم است")
    else:
        valid = False; strength = 0
        reasons.append("هیچ لمس واقعی پیدا نشد — این خط با حرکت واقعی قیمت هم‌خوان نیست")

    # ── مقایسه با سطوح سیستم (Order Block / فیبوناچی) ──
    sys_match = None
    line_price_now = line_price_at(p1, p2, df_times[-1])
    obs = detect_order_blocks(df)
    all_obs = [o["mid"] for o in obs.get("bull", [])] + [o["mid"] for o in obs.get("bear", [])]
    for ob in all_obs:
        if abs(ob - line_price_now) / line_price_now < 0.008:
            sys_match = "order_block"
            reasons.append(f"با یک Order Block سیستم (${round(ob,1)}) هم‌پوشانی دارد — تأیید قوی")
            strength += 1
            break

    if not sys_match:
        zinfo = important_zones(df)
        for z in zinfo["zones"]:
            if abs(z["level"] - line_price_now) / line_price_now < 0.008:
                sys_match = "fib"
                reasons.append(f"نزدیک سطح فیبوناچی {z['fib']} است — هم‌خوان با سیستم")
                strength += 1
                break

    # ── نقش خط ──
    if line_type == "horizontal":
        role = "support" if line_price_now < price else "resistance"
    elif line_type == "rising":
        role = "trend_up"
    else:
        role = "trend_down"

    return {
        "type": line_type,
        "role": role,
        "valid": valid,
        "strength": min(strength, 5),
        "touches": touches,
        "line_price_now": round(line_price_now, 2),
        "sys_match": sys_match,
        "reasons": reasons,
    }


def analyze_user_lines(symbol, lines, interval="1h"):
    """
    همه خط‌های کاربر را تحلیل می‌کند.
    lines: لیست [{"p1":{"time","price"}, "p2":{"time","price"}}, ...]
    """
    df = get_klines(symbol, interval, 300)
    if df is None or len(df) < 60:
        return {"error": "داده در دسترس نیست"}
    if not lines:
        return {"error": "هیچ خطی کشیده نشده"}

    price = float(df["close"].iloc[-1])
    results = []
    valid_count = 0
    bull_signals = 0
    bear_signals = 0

    for ln in lines:
        try:
            res = validate_line(df, ln["p1"], ln["p2"])
            results.append(res)
            if res["valid"]:
                valid_count += 1
                # جهت‌گیری: حمایت معتبر زیر قیمت = صعودی، مقاومت بالای قیمت شکسته = ...
                if res["role"] == "support" or res["role"] == "trend_up":
                    bull_signals += res["strength"]
                elif res["role"] == "resistance" or res["role"] == "trend_down":
                    bear_signals += res["strength"]
        except Exception as e:
            results.append({"error": str(e), "valid": False, "reasons": ["خطا در تحلیل این خط"]})

    # ── وزن نهایی برای SCORE سشن US ──
    # فقط خط‌های معتبر وزن می‌گیرند (چشم‌بسته قبول نمی‌شود)
    net = bull_signals - bear_signals
    if valid_count == 0:
        score_weight = 0
        verdict = "هیچ خط معتبری نبود — در تحلیل دخیل نمی‌شود"
    elif net > 0:
        score_weight = min(net * 3, 20)  # حداکثر +۲۰
        verdict = f"خط‌های معتبر تو تمایل صعودی نشان می‌دهند (+{score_weight} به SCORE)"
    elif net < 0:
        score_weight = max(net * 3, -20)
        verdict = f"خط‌های معتبر تو تمایل نزولی نشان می‌دهند ({score_weight} به SCORE)"
    else:
        score_weight = 0
        verdict = "خط‌های معتبر متعادل‌اند — اثر خنثی"

    return {
        "symbol": symbol,
        "price": round(price, 2),
        "lines": results,
        "valid_count": valid_count,
        "total_count": len(lines),
        "score_weight": score_weight,
        "verdict": verdict,
        "net_direction": "bull" if net > 0 else "bear" if net < 0 else "neutral",
    }

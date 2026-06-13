# -*- coding: utf-8 -*-
"""
ماژول هوش مصنوعی — RandomForest + Backtesting
─────────────────────────────────────────────
از الگوهای گذشته بیت‌کوین یاد می‌گیرد و احتمال جهت حرکت بعدی را تخمین می‌زند.

⚠️ مهم: این مدل آماری است، نه پیشگویی قطعی.
   خروجی = "بر اساس شرایط مشابه گذشته، X% مواقع صعودی بوده"
   نه "قیمت بالا می‌رود".

Backtesting: مدل روی داده گذشته آموزش می‌بیند و روی داده‌ای که ندیده
   تست می‌شود تا دقت واقعی‌اش سنجیده شود (نه دقت توهمی).
"""
import numpy as np
import pandas as pd

try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import TimeSeriesSplit
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

from analysis import get_klines, ema, rsi, macd, bollinger, atr, stoch_rsi


# ═══════════ ساخت ویژگی‌ها (Features) ═══════════
def build_features(df):
    """از کندل‌ها، ویژگی‌های آماری برای مدل می‌سازد"""
    close = df["close"]
    feat = pd.DataFrame(index=df.index)

    # اندیکاتورها به‌صورت نرمال‌شده
    feat["rsi"] = rsi(close) / 100
    feat["stoch"] = stoch_rsi(close) / 100
    macd_line, macd_sig, macd_hist = macd(close)
    feat["macd_hist"] = macd_hist / close
    e50 = ema(close, 50)
    e200 = ema(close, 200)
    feat["dist_ema50"] = (close - e50) / close
    feat["dist_ema200"] = (close - e200) / close
    feat["ema_cross"] = (e50 - e200) / close
    bb_up, bb_mid, bb_low = bollinger(close)
    feat["bb_pos"] = (close - bb_low) / (bb_up - bb_low).replace(0, np.nan)
    feat["atr_pct"] = atr(df) / close
    # مومنتوم
    feat["ret_1"] = close.pct_change(1)
    feat["ret_3"] = close.pct_change(3)
    feat["ret_6"] = close.pct_change(6)
    # حجم
    feat["vol_ratio"] = df["vol"] / df["vol"].rolling(20).mean()
    # CVD
    delta = df["tb"] - (df["vol"] - df["tb"])
    feat["cvd"] = delta.rolling(5).sum() / df["vol"].rolling(5).sum().replace(0, np.nan)

    return feat


def build_labels(df, horizon=4, threshold=0.005):
    """برچسب: آیا قیمت بعد از horizon کندل بیش از threshold بالا رفته؟
       1 = صعودی، 0 = نزولی/خنثی"""
    future = df["close"].shift(-horizon)
    change = (future - df["close"]) / df["close"]
    return (change > threshold).astype(int)


# ═══════════ آموزش + Backtesting ═══════════
def train_and_backtest(symbol, interval="1h", limit=1000, horizon=4):
    """
    مدل را آموزش می‌دهد و با backtesting اعتبارسنجی می‌کند.
    خروجی: مدل آموزش‌دیده + دقت backtest + پیش‌بینی فعلی
    """
    if not HAS_SKLEARN:
        return {"error": "scikit-learn نصب نیست. pip install scikit-learn"}

    df = get_klines(symbol, interval, limit)
    if df is None or len(df) < 200:
        return {"error": "داده کافی نیست"}

    feat = build_features(df)
    labels = build_labels(df, horizon=horizon)

    # حذف ردیف‌های ناقص
    data = feat.copy()
    data["label"] = labels
    data = data.dropna()
    if len(data) < 150:
        return {"error": "داده پاک کافی نیست"}

    X = data.drop(columns=["label"]).values
    y = data["label"].values

    # ── Backtesting با TimeSeriesSplit (واقع‌بینانه، بدون نشت داده) ──
    tscv = TimeSeriesSplit(n_splits=5)
    accuracies = []
    for train_idx, test_idx in tscv.split(X):
        if len(np.unique(y[train_idx])) < 2:
            continue
        m = RandomForestClassifier(n_estimators=80, max_depth=6,
                                    min_samples_leaf=10, random_state=42, n_jobs=1)
        m.fit(X[train_idx], y[train_idx])
        acc = m.score(X[test_idx], y[test_idx])
        accuracies.append(acc)

    backtest_acc = round(float(np.mean(accuracies)) * 100, 1) if accuracies else None

    # ── مدل نهایی روی همه داده ──
    final = RandomForestClassifier(n_estimators=80, max_depth=6,
                                    min_samples_leaf=10, random_state=42, n_jobs=1)
    final.fit(X, y)

    # ── پیش‌بینی وضعیت فعلی ──
    last_feat = feat.dropna().iloc[-1:].values
    if len(last_feat) == 0:
        return {"error": "ویژگی فعلی ناقص"}
    proba = final.predict_proba(last_feat)[0]
    # proba[1] = احتمال صعود
    bull_prob = round(float(proba[1]) * 100) if len(proba) > 1 else 50

    # اهمیت ویژگی‌ها (کدوم اندیکاتورها مهم‌تر بودن)
    importances = dict(zip(data.drop(columns=["label"]).columns,
                           final.feature_importances_))
    top_features = sorted(importances.items(), key=lambda x: -x[1])[:3]

    # نرخ پایه (چند درصد مواقع صعودی بوده — برای مقایسه)
    base_rate = round(float(y.mean()) * 100, 1)

    return {
        "symbol": symbol,
        "interval": interval,
        "horizon": horizon,
        "bull_prob": bull_prob,
        "bear_prob": 100 - bull_prob,
        "backtest_acc": backtest_acc,
        "base_rate": base_rate,
        "samples": len(data),
        "top_features": [{"name": fa_feature_name(f), "weight": round(w, 3)} for f, w in top_features],
        "reliable": backtest_acc is not None and backtest_acc > 52,  # بهتر از شانس؟
    }


def fa_feature_name(key):
    """نام فارسی ویژگی‌ها"""
    names = {
        "rsi": "RSI", "stoch": "StochRSI", "macd_hist": "MACD",
        "dist_ema50": "فاصله از EMA50", "dist_ema200": "فاصله از EMA200",
        "ema_cross": "تقاطع EMA", "bb_pos": "موقعیت بولینگر",
        "atr_pct": "نوسان (ATR)", "ret_1": "بازده ۱ کندل",
        "ret_3": "بازده ۳ کندل", "ret_6": "بازده ۶ کندل",
        "vol_ratio": "نسبت حجم", "cvd": "جریان سفارش (CVD)",
    }
    return names.get(key, key)


# ═══════════ ترکیب سناریو (چند تایم‌فریم) ═══════════
def ml_scenario(symbol, intervals=("1h", "4h")):
    """مدل را روی چند تایم‌فریم اجرا و ترکیب می‌کند"""
    results = {}
    for itv in intervals:
        res = train_and_backtest(symbol, itv)
        if "error" not in res:
            results[itv] = res
    if not results:
        return None

    # میانگین وزنی (تایم بالاتر وزن بیشتر)
    weights = {"1h": 1, "4h": 2, "1d": 3}
    total_w = sum(weights.get(itv, 1) for itv in results)
    weighted_bull = sum(r["bull_prob"] * weights.get(itv, 1) for itv, r in results.items()) / total_w

    return {
        "combined_bull": round(weighted_bull),
        "combined_bear": round(100 - weighted_bull),
        "timeframes": results,
    }

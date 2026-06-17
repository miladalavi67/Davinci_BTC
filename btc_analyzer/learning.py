# -*- coding: utf-8 -*-
"""
سیستم یادگیری — ثبت پیش‌بینی‌ها و سنجش نتایج واقعی
────────────────────────────────────────────────────
۱. record_prediction: وقتی ستاپ/محدوده اعلام می‌شود، ثبت می‌کند
۲. evaluate_pending: پیش‌بینی‌های گذشته را با قیمت فعلی می‌سنجد
۳. get_stats: نرخ موفقیت هر نوع را برمی‌گرداند

روش: آمار واقعی (نه جعبه سیاه) — ربات یاد می‌گیرد کدام
نوع سیگنال‌ها در گذشته درست بوده‌اند.
"""
import os
import time
import sqlite3
from analysis import get_klines

LEARN_DB = os.environ.get("LEARN_DB_PATH", "learning.db")

# افق ارزیابی: چند ساعت بعد چک کنیم نتیجه چه شد
EVAL_HORIZON_H = 24
# حداقل حرکت برای «موفق» محسوب شدن (٪)
SUCCESS_MOVE = 0.01  # ۱٪


def _db():
    conn = sqlite3.connect(LEARN_DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_learning():
    conn = _db(); c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS predictions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT,
        kind TEXT,           -- 'setup' یا 'zone'
        subtype TEXT,        -- جزئیات: 'bull'/'bear' یا 'fib_ob'/'fib'/'ema'...
        direction TEXT,      -- 'bull'/'bear'
        price REAL,          -- قیمت موقع پیش‌بینی
        target REAL,         -- سطح هدف (برای محدوده)
        created_ts REAL,
        eval_ts REAL,        -- کِی ارزیابی شد (NULL = هنوز نه)
        result TEXT,         -- 'success'/'fail'/'neutral'/NULL
        move_pct REAL        -- چقدر حرکت کرد
    )""")
    conn.commit(); conn.close()


def record_prediction(symbol, kind, subtype, direction, price, target=None):
    """یک پیش‌بینی جدید ثبت می‌کند (اگر تکراری اخیر نباشد)"""
    conn = _db(); c = conn.cursor()
    # جلوگیری از ثبت تکراری: همان symbol+kind+direction در ۶ ساعت اخیر
    cutoff = time.time() - 6 * 3600
    c.execute("""SELECT COUNT(*) AS n FROM predictions
        WHERE symbol=? AND kind=? AND direction=? AND created_ts>?""",
        (symbol, kind, direction, cutoff))
    if c.fetchone()["n"] > 0:
        conn.close(); return False
    c.execute("""INSERT INTO predictions
        (symbol,kind,subtype,direction,price,target,created_ts,eval_ts,result,move_pct)
        VALUES(?,?,?,?,?,?,?,NULL,NULL,NULL)""",
        (symbol, kind, subtype, direction, price, target, time.time()))
    conn.commit(); conn.close()
    return True


def evaluate_pending():
    """
    پیش‌بینی‌هایی که افق‌شان (۲۴ساعت) گذشته را می‌سنجد.
    قیمت فعلی را با قیمت پیش‌بینی مقایسه می‌کند.
    """
    conn = _db(); c = conn.cursor()
    cutoff = time.time() - EVAL_HORIZON_H * 3600
    c.execute("""SELECT * FROM predictions
        WHERE eval_ts IS NULL AND created_ts<=?""", (cutoff,))
    rows = c.fetchall()
    if not rows:
        conn.close(); return 0

    # قیمت فعلی هر نماد را یک‌بار بگیر (کش ساده)
    price_cache = {}
    evaluated = 0
    for row in rows:
        sym = row["symbol"]
        if sym not in price_cache:
            df = get_klines(sym, "1h", 2)
            price_cache[sym] = float(df["close"].iloc[-1]) if df is not None and len(df) else None
        cur = price_cache[sym]
        if cur is None:
            continue
        old = row["price"]
        move = (cur - old) / old  # حرکت واقعی
        direction = row["direction"]

        # آیا در جهت پیش‌بینی حرکت کرد؟
        if direction == "bull":
            if move >= SUCCESS_MOVE:
                result = "success"
            elif move <= -SUCCESS_MOVE:
                result = "fail"
            else:
                result = "neutral"
        else:  # bear
            if move <= -SUCCESS_MOVE:
                result = "success"
            elif move >= SUCCESS_MOVE:
                result = "fail"
            else:
                result = "neutral"

        c.execute("""UPDATE predictions SET eval_ts=?,result=?,move_pct=? WHERE id=?""",
            (time.time(), result, round(move * 100, 2), row["id"]))
        evaluated += 1

    conn.commit(); conn.close()
    return evaluated


def get_stats():
    """آمار نرخ موفقیت بر اساس نوع سیگنال"""
    conn = _db(); c = conn.cursor()

    def rate(where, params=()):
        c.execute(f"""SELECT
            SUM(CASE WHEN result='success' THEN 1 ELSE 0 END) AS s,
            SUM(CASE WHEN result='fail' THEN 1 ELSE 0 END) AS f,
            SUM(CASE WHEN result='neutral' THEN 1 ELSE 0 END) AS n,
            COUNT(*) AS total
            FROM predictions WHERE result IS NOT NULL {where}""", params)
        r = c.fetchone()
        s, f, n, total = r["s"] or 0, r["f"] or 0, r["n"] or 0, r["total"] or 0
        decided = s + f  # خنثی‌ها در نرخ حساب نمی‌شوند
        win_rate = round(s / decided * 100, 1) if decided > 0 else None
        return {"success": s, "fail": f, "neutral": n, "total": total, "win_rate": win_rate}

    # کلی
    overall = rate("")
    # ستاپ‌ها
    setups = rate("AND kind='setup'")
    setup_bull = rate("AND kind='setup' AND direction='bull'")
    setup_bear = rate("AND kind='setup' AND direction='bear'")
    # محدوده‌ها
    zones = rate("AND kind='zone'")
    # محدوده‌های با OB
    zones_ob = rate("AND kind='zone' AND subtype LIKE '%ob%'")

    # تعداد در انتظار ارزیابی
    c.execute("SELECT COUNT(*) AS n FROM predictions WHERE eval_ts IS NULL")
    pending = c.fetchone()["n"]
    conn.close()

    return {
        "overall": overall,
        "setups": setups,
        "setup_bull": setup_bull,
        "setup_bear": setup_bear,
        "zones": zones,
        "zones_ob": zones_ob,
        "pending": pending,
    }


def get_confidence(kind, direction=None, has_ob=False):
    """
    بر اساس آمار گذشته، یک ضریب اعتماد برمی‌گرداند (۰ تا ۱).
    این همان «یادگیری» است: اگر نوعی در گذشته خوب بوده، اعتماد بالاتر.
    """
    stats = get_stats()
    if kind == "setup":
        if direction == "bull":
            wr = stats["setup_bull"]["win_rate"]
        elif direction == "bear":
            wr = stats["setup_bear"]["win_rate"]
        else:
            wr = stats["setups"]["win_rate"]
    elif kind == "zone":
        wr = stats["zones_ob"]["win_rate"] if has_ob else stats["zones"]["win_rate"]
    else:
        wr = None
    # اگر داده کافی نیست (None)، اعتماد خنثی = ۰.۵
    if wr is None:
        return {"confidence": 0.5, "win_rate": None, "enough_data": False}
    return {"confidence": round(wr / 100, 2), "win_rate": wr, "enough_data": True}

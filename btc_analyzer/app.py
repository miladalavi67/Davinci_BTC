# -*- coding: utf-8 -*-
"""
وب‌سرور Flask — داشبورد تحلیل بیت‌کوین و ۱۰ ارز اول
مسیرها:
  /                → داشبورد (تک‌صفحه)
  /api/analyze     → تحلیل کامل یک ارز در چند تایم‌فریم
  /api/ml          → سناریو ML با backtesting
  /api/overview    → خلاصه همه ارزها
"""
from flask import Flask, render_template, jsonify, request, session, redirect, url_for
import threading
import time
import os
import secrets

from analysis import analyze_timeframe, get_funding, get_oi
from ml_model import ml_scenario, HAS_SKLEARN
from setup import detect_setup, get_chart_data
from notify import notify_setup
from auth import (init_auth, verify_user, create_user, change_password,
                 delete_user, list_users, login_required, admin_required)

app = Flask(__name__)
# کلید نشست — از env var یا تصادفی (برای امنیت کوکی‌ها)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
init_auth()

# ۱۱ ارز: بیت‌کوین + ۱۰ ارز اول
COINS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
         "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT", "TRXUSDT"]

TIMEFRAMES = ["15m", "1h", "4h", "1d"]

# کش ساده (برای کاهش فشار روی API و سرعت)
_cache = {}
CACHE_TTL = 120  # ثانیه


def cached(key, fn):
    now = time.time()
    if key in _cache and now - _cache[key]["ts"] < CACHE_TTL:
        return _cache[key]["data"]
    data = fn()
    _cache[key] = {"ts": now, "data": data}
    return data


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        u = verify_user(username, password)
        if u:
            session["user"] = u["username"]
            session["role"] = u["role"]
            return redirect(url_for("index"))
        return render_template("login.html", error="نام کاربری یا رمز اشتباه است")
    if "user" in session:
        return redirect(url_for("index"))
    return render_template("login.html", error=None)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    return render_template("index.html", coins=COINS, timeframes=TIMEFRAMES,
                           user=session.get("user"), role=session.get("role"))


# ── مدیریت کاربران (فقط ادمین) ──
@app.route("/api/users", methods=["GET"])
@admin_required
def api_users():
    return jsonify(list_users())


@app.route("/api/users/add", methods=["POST"])
@admin_required
def api_add_user():
    d = request.get_json(force=True)
    un = (d.get("username") or "").strip()
    pw = d.get("password") or ""
    if len(un) < 3 or len(pw) < 6:
        return jsonify({"error": "یوزرنیم حداقل ۳ و رمز حداقل ۶ کاراکتر"}), 400
    if create_user(un, pw, d.get("role", "user")):
        return jsonify({"ok": True})
    return jsonify({"error": "این یوزرنیم قبلاً وجود دارد"}), 400


@app.route("/api/users/delete", methods=["POST"])
@admin_required
def api_del_user():
    d = request.get_json(force=True)
    if delete_user(d.get("username", "")):
        return jsonify({"ok": True})
    return jsonify({"error": "حذف نشد (ادمین قابل حذف نیست)"}), 400


@app.route("/api/password", methods=["POST"])
@login_required
def api_change_pw():
    d = request.get_json(force=True)
    new_pw = d.get("new_password") or ""
    if len(new_pw) < 6:
        return jsonify({"error": "رمز حداقل ۶ کاراکتر"}), 400
    change_password(session["user"], new_pw)
    return jsonify({"ok": True})


@app.route("/api/analyze")
@login_required
def api_analyze():
    """تحلیل کامل یک ارز در همه تایم‌فریم‌ها"""
    symbol = request.args.get("symbol", "BTCUSDT").upper()
    if symbol not in COINS:
        return jsonify({"error": "ارز نامعتبر"}), 400

    def do():
        from concurrent.futures import ThreadPoolExecutor
        result = {"symbol": symbol, "timeframes": {}}
        # تایم‌فریم‌ها را موازی بگیر (سریع‌تر)
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = {tf: ex.submit(analyze_timeframe, symbol, tf) for tf in TIMEFRAMES}
            for tf, fut in futs.items():
                a = fut.result()
                if a:
                    result["timeframes"][tf] = a
        result["funding"] = get_funding(symbol)
        result["oi"] = get_oi(symbol)
        result["bias"] = compute_bias(result["timeframes"])
        return result

    return jsonify(cached(f"analyze_{symbol}", do))


@app.route("/api/ml")
@login_required
def api_ml():
    """سناریو ML با backtesting (سنگین‌تر، کش طولانی‌تر)"""
    symbol = request.args.get("symbol", "BTCUSDT").upper()
    if symbol not in COINS:
        return jsonify({"error": "ارز نامعتبر"}), 400
    if not HAS_SKLEARN:
        return jsonify({"error": "scikit-learn روی سرور نصب نیست"}), 503

    def do():
        return ml_scenario(symbol, intervals=("1h", "4h")) or {"error": "تحلیل ناموفق"}

    # کش ML طولانی‌تر چون سنگینه
    key = f"ml_{symbol}"
    now = time.time()
    if key in _cache and now - _cache[key]["ts"] < 600:  # ۱۰ دقیقه
        return jsonify(_cache[key]["data"])
    data = do()
    _cache[key] = {"ts": now, "data": data}
    return jsonify(data)


@app.route("/api/overview")
@login_required
def api_overview():
    """خلاصه روند همه ارزها (برای نمای کلی)"""
    def do():
        out = []
        for sym in COINS:
            a = analyze_timeframe(sym, "1h")
            if a:
                out.append({
                    "symbol": sym,
                    "coin": sym.replace("USDT", ""),
                    "price": a["price"],
                    "trend": a["trend"]["trend"],
                    "trend_label": a["trend"]["label"],
                    "rsi": a["rsi"],
                    "pattern": a["pattern"]["label"],
                    "cvd_dir": a["cvd_dir"],
                })
        return out

    return jsonify(cached("overview", do))


@app.route("/api/chart")
@login_required
def api_chart():
    """داده کندل برای چارت ۱ ساعته + اوردر بلاک"""
    symbol = request.args.get("symbol", "BTCUSDT").upper()
    if symbol not in COINS:
        return jsonify({"error": "ارز نامعتبر"}), 400

    def do():
        data = get_chart_data(symbol, "1h", 150)
        return data or {"error": "داده در دسترس نیست"}

    return jsonify(cached(f"chart_{symbol}", do))


@app.route("/api/setup")
@login_required
def api_setup():
    """تشخیص ستاپ (ML ≥۷۰٪ + Confluence) روی ۱ ساعته"""
    symbol = request.args.get("symbol", "BTCUSDT").upper()
    if symbol not in COINS:
        return jsonify({"error": "ارز نامعتبر"}), 400

    key = f"setup_{symbol}"
    now = time.time()
    if key in _cache and now - _cache[key]["ts"] < 600:  # کش ۱۰ دقیقه (سنگین)
        return jsonify(_cache[key]["data"])
    data = detect_setup(symbol, "1h") or {"error": "تحلیل ناموفق"}
    _cache[key] = {"ts": now, "data": data}
    return jsonify(data)


# اسکن پس‌زمینه همه ارزها برای ستاپ
_setup_scan = {"ts": 0, "results": {}}

def background_setup_scan():
    """هر ۱۰ دقیقه همه ارزها را برای ستاپ چک می‌کند (در ترد جدا)"""
    while True:
        try:
            for sym in COINS:
                try:
                    res = detect_setup(sym, "1h")
                    if res:
                        _setup_scan["results"][sym] = res
                        # کش فردی هم به‌روز شود
                        _cache[f"setup_{sym}"] = {"ts": time.time(), "data": res}
                        # اگر ستاپ معتبر بود، به اعضای ربات تلگرام خبر بده
                        try:
                            notify_setup(sym, res)
                        except Exception as e:
                            print(f"[!] notify: {e}")
                    time.sleep(2)  # فاصله بین ارزها (فشار کمتر)
                except Exception:
                    pass
            _setup_scan["ts"] = time.time()
        except Exception as e:
            print(f"[!] background scan: {e}")
        time.sleep(600)  # هر ۱۰ دقیقه


@app.route("/api/setups")
@login_required
def api_setups():
    """خلاصه ستاپ همه ارزها (از اسکن پس‌زمینه)"""
    out = []
    for sym, res in _setup_scan["results"].items():
        if res and res.get("has_setup"):
            out.append({
                "symbol": sym,
                "coin": sym.replace("USDT", ""),
                "direction": res["direction"],
                "ml_prob": res["ml_prob"],
                "conf_score": res["conf_score"],
            })
    return jsonify({"setups": out, "scan_ts": _setup_scan["ts"]})


def compute_bias(timeframes):
    """رأی‌گیری وزن‌دار روند بین تایم‌فریم‌ها"""
    weights = {"15m": 1, "1h": 2, "4h": 3, "1d": 4}
    bull = bear = 0
    for tf, data in timeframes.items():
        w = weights.get(tf, 1)
        t = data["trend"]["trend"]
        if "bull" in t:
            bull += w * (2 if "strong" in t else 1)
        elif "bear" in t:
            bear += w * (2 if "strong" in t else 1)
    total = bull + bear
    if total == 0:
        return {"direction": "range", "bull_pct": 50, "bear_pct": 50}
    bull_pct = round(bull / total * 100)
    return {
        "direction": "bull" if bull_pct >= 60 else "bear" if bull_pct <= 40 else "range",
        "bull_pct": bull_pct,
        "bear_pct": 100 - bull_pct,
    }


def start_background():
    """ترد اسکن پس‌زمینه ستاپ را روشن می‌کند (یک‌بار)"""
    if not getattr(start_background, "_started", False):
        start_background._started = True
        if HAS_SKLEARN:
            threading.Thread(target=background_setup_scan, daemon=True).start()
            print("[+] اسکن پس‌زمینه ستاپ روشن شد (هر ۱۰ دقیقه)")


# روشن کردن خودکار هنگام import (برای serve.py / waitress)
start_background()


if __name__ == "__main__":
    print("="*50)
    print("داشبورد تحلیل بیت‌کوین + ۱۰ ارز اول")
    print(f"scikit-learn: {'فعال ✅' if HAS_SKLEARN else 'غیرفعال ❌ (pip install scikit-learn)'}")
    print("باز کن: http://localhost:5000")
    print("="*50)
    app.run(host="0.0.0.0", port=5000, debug=False)

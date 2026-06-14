# -*- coding: utf-8 -*-
"""
اعلان تلگرام برای سایت — وقتی ستاپ تشکیل شد به اعضای ربات پیام می‌دهد.
از همان توکن ربات و دیتابیس اعضای ربات استفاده می‌کند.

Env Vars:
  TELEGRAM_TOKEN  = توکن همان ربات
  BOT_DB_PATH     = مسیر کامل دیتابیس ربات (cycle_bot.db)
"""
import os
import time
import sqlite3
import requests

TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
BOT_DB = os.environ.get("BOT_DB_PATH", "")
TG = f"https://api.telegram.org/bot{TOKEN}"

# جلوگیری از ارسال تکراری: هر ستاپ فقط یک‌بار (تا وقتی جهتش عوض نشده)
_last_setup = {}   # symbol -> direction


def _members():
    """لیست اعضای فعال را از دیتابیس ربات می‌خواند"""
    if not BOT_DB or not os.path.exists(BOT_DB):
        return []
    try:
        conn = sqlite3.connect(BOT_DB)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT chat_id FROM members WHERE active=1")
        rows = [r["chat_id"] for r in c.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        print(f"[!] خطای خواندن اعضای ربات: {e}")
        return []


def _send(chat_id, text):
    try:
        requests.post(f"{TG}/sendMessage", json={
            "chat_id": chat_id, "text": text,
            "parse_mode": "HTML", "disable_web_page_preview": True
        }, timeout=15)
    except Exception as e:
        print(f"[!] خطای ارسال تلگرام: {e}")


def notify_setup(symbol, setup):
    """
    اگر ستاپ جدید (نسبت به آخرین بار) بود، به همه اعضای ربات پیام می‌دهد.
    setup: خروجی detect_setup با has_setup=True
    """
    if not TOKEN:
        return
    if not setup or not setup.get("has_setup"):
        # اگر ستاپ از بین رفت، حافظه را پاک کن تا دفعه بعد دوباره خبر بدهد
        _last_setup.pop(symbol, None)
        return

    direction = setup["direction"]
    # اگر همین جهت قبلاً خبر داده شده، دوباره نفرست
    if _last_setup.get(symbol) == direction:
        return
    _last_setup[symbol] = direction

    coin = symbol.replace("USDT", "")
    is_bull = direction == "bull"
    icon = "🟢" if is_bull else "🔴"
    dir_fa = "صعودی" if is_bull else "نزولی"
    lines = [f"{icon} <b>ستاپ {dir_fa} {coin}</b> تشکیل شد! (۱ ساعته)"]
    lines.append(f"💵 قیمت: ${setup['price']}")
    lines.append(f"🤖 ML: {setup['ml_prob']}% · Confluence: {setup['conf_score']}/{setup['conf_min']}")
    if setup.get("backtest_acc"):
        lines.append(f"📊 دقت backtest: {setup['backtest_acc']}%")
    if setup.get("factors"):
        lines.append("عوامل: " + " · ".join(setup["factors"][:6]))
    ez = setup.get("entry_zone")
    if ez:
        lines.append(f"🎯 ناحیه ورود (OB): ${ez['mid']} ({'+' if ez['dist']>0 else ''}{ez['dist']}%)")
    lines.append("\n⚠️ آماری، نه سیگنال قطعی. مدیریت ریسک کن.")
    text = "\n".join(lines)

    members = _members()
    for cid in members:
        _send(cid, text)
        time.sleep(0.3)
    print(f"[+] ستاپ {coin} ({dir_fa}) به {len(members)} عضو ارسال شد.")

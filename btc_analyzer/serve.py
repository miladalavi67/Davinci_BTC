# -*- coding: utf-8 -*-
"""
اجرای production با waitress (پایدارتر از Flask dev server برای ۲۴/۷)
اجرا:  python serve.py
سپس باز کن:  http://IP_سرور:5000
"""
from waitress import serve
from app import app

if __name__ == "__main__":
    print("="*50)
    print("سرور تحلیلگر بیت‌کوین (production / waitress)")
    print("روی پورت 5000 — باز کن: http://IP_سرور:5000")
    print("="*50)
    serve(app, host="0.0.0.0", port=5000, threads=6)

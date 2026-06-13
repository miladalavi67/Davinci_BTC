# -*- coding: utf-8 -*-
"""
ماژول احراز هویت — کاربران، پسورد هش‌شده، نشست
از werkzeug برای هش امن پسورد استفاده می‌کند (با Flask نصب می‌شود).
"""
import sqlite3
import os
from functools import wraps
from flask import session, redirect, url_for, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

DB = "users.db"


def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_auth():
    conn = db(); c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        pw_hash TEXT NOT NULL,
        role TEXT DEFAULT 'user',
        created TEXT)""")
    conn.commit()
    # اگر هیچ کاربری نیست، یک ادمین پیش‌فرض بساز
    c.execute("SELECT COUNT(*) n FROM users")
    if c.fetchone()["n"] == 0:
        from datetime import datetime
        admin_user = os.environ.get("ADMIN_USER", "admin")
        admin_pass = os.environ.get("ADMIN_PASS", "changeme123")
        c.execute("INSERT INTO users(username,pw_hash,role,created) VALUES(?,?,?,?)",
                  (admin_user, generate_password_hash(admin_pass), "admin",
                   datetime.now().isoformat()))
        conn.commit()
        print(f"[+] کاربر ادمین ساخته شد: {admin_user}")
        print(f"    رمز: {admin_pass}  ← حتماً بعداً عوضش کن!")
    conn.close()


def verify_user(username, password):
    conn = db(); c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username=?", (username,))
    u = c.fetchone(); conn.close()
    if u and check_password_hash(u["pw_hash"], password):
        return {"id": u["id"], "username": u["username"], "role": u["role"]}
    return None


def create_user(username, password, role="user"):
    from datetime import datetime
    conn = db(); c = conn.cursor()
    try:
        c.execute("INSERT INTO users(username,pw_hash,role,created) VALUES(?,?,?,?)",
                  (username, generate_password_hash(password), role,
                   datetime.now().isoformat()))
        conn.commit(); conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False  # یوزرنیم تکراری


def change_password(username, new_password):
    conn = db(); c = conn.cursor()
    c.execute("UPDATE users SET pw_hash=? WHERE username=?",
              (generate_password_hash(new_password), username))
    conn.commit(); ok = c.rowcount > 0; conn.close()
    return ok


def delete_user(username):
    conn = db(); c = conn.cursor()
    c.execute("DELETE FROM users WHERE username=? AND role!='admin'", (username,))
    conn.commit(); ok = c.rowcount > 0; conn.close()
    return ok


def list_users():
    conn = db(); c = conn.cursor()
    c.execute("SELECT username, role, created FROM users ORDER BY id")
    rows = [dict(r) for r in c.fetchall()]; conn.close()
    return rows


# ── دکوراتورها برای محافظت از مسیرها ──
def login_required(f):
    @wraps(f)
    def wrap(*a, **kw):
        if "user" not in session:
            # برای API، خطای JSON بده؛ برای صفحه، ریدایرکت
            if request.path.startswith("/api/"):
                return jsonify({"error": "نیاز به ورود"}), 401
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrap


def admin_required(f):
    @wraps(f)
    def wrap(*a, **kw):
        if "user" not in session or session.get("role") != "admin":
            if request.path.startswith("/api/"):
                return jsonify({"error": "نیاز به دسترسی ادمین"}), 403
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrap

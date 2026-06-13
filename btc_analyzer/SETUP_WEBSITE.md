# 🌐 راهنمای راه‌اندازی وب‌سایت تحلیلگر بیت‌کوین (سرور ویندوز امارات)

داشبورد تخصصی تحلیل بیت‌کوین + ۱۰ ارز اول، با تحلیل چند تایم‌فریم،
Order Block، اندیکاتورها، و سناریو هوش مصنوعی (RandomForest + Backtesting).

> این **جدا از ربات** است. یک وب‌سایت که از مرورگر بازش می‌کنی.

---

## ساختار فایل‌ها

```
btc_analyzer/
├── app.py              ← وب‌سرور Flask (مسیرها و API)
├── analysis.py         ← موتور تحلیل (اندیکاتور، روند، الگو، OB)
├── ml_model.py         ← مدل AI (RandomForest + Backtesting)
├── serve.py            ← اجرای production
├── requirements.txt    ← کتابخانه‌های لازم
└── templates/
    └── index.html      ← داشبورد (فرانت‌اند)
```

همه را در یک پوشه روی سرور بگذار، مثلاً `C:\btc_analyzer`.

---

## ✅ مرحله ۰: تست Binance

در PowerShell:
```powershell
curl "https://fapi.binance.com/fapi/v1/ticker/price?symbol=BTCUSDT"
```
قیمت داد → ✅ ادامه بده. خطای restricted → سرور بلاک است.

---

## مرحله ۱: نصب کتابخانه‌ها

```powershell
cd C:\btc_analyzer
pip install -r requirements.txt
```
(اگر `pip` شناخته نشد، اول Python را با تیک "Add to PATH" نصب کن)

---

## مرحله ۲: تست اجرا

```powershell
python serve.py
```
اگر دیدی `روی پورت 5000` → سرور بالا آمده.

حالا روی **خود سرور**، مرورگر را باز کن و برو به:
```
http://localhost:5000
```
صفحه **ورود** می‌آید. (برای توقف: `Ctrl+C`)

---

## 🔐 ورود و کاربران

بار اول که اجرا می‌کنی، یک کاربر ادمین پیش‌فرض ساخته می‌شود:
```
نام کاربری: admin
رمز عبور:   changeme123
```

> ⚠️ **حتماً بعد از اولین ورود، رمز را عوض کن** (دکمه «تغییر رمز» در داشبورد).

### تعیین رمز ادمین دلخواه (پیشنهادی):
قبل از اولین اجرا، در فایل service (یا قبل از `python serve.py`) این‌ها را بگذار:
```powershell
$env:ADMIN_USER="نام_دلخواه"
$env:ADMIN_PASS="رمز_قوی_خودت"
$env:SECRET_KEY="یک_رشته_تصادفی_طولانی"
```
`SECRET_KEY` برای امنیت کوکی‌های نشست است — یک رشته تصادفی طولانی بگذار.

### مدیریت کاربران (وقتی اشتراکی شد):
- به‌عنوان ادمین وارد شو
- دکمه **«مدیریت کاربران»** → می‌توانی کاربر اضافه/حذف کنی
- هر دوستت یک یوزرنیم/رمز می‌گیرد
- پسوردها به‌صورت **هش‌شده** (امن) ذخیره می‌شوند، نه متن ساده

---

## مرحله ۳: دسترسی از بیرون (مهم)

برای اینکه از کامپیوتر/گوشی خودت (نه فقط روی سرور) بازش کنی:

### الف) باز کردن پورت در فایروال ویندوز:
در PowerShell **Administrator**:
```powershell
New-NetFirewallRule -DisplayName "BTC Analyzer" -Direction Inbound -LocalPort 5000 -Protocol TCP -Action Allow
```

### ب) باز کردن پورت در پنل MobinHost:
اگر MobinHost فایروال جدا دارد، پورت **5000** را هم آنجا باز کن
(یا از پشتیبانی بخواه).

### ج) حالا از هر جا باز کن:
```
http://IP_سرور:5000
```

> ⚠️ این داشبورد عمومی می‌شود (هر کس IP و پورت را داشته باشد می‌بیند).
> اگر می‌خواهی خصوصی بماند، بعداً می‌توان رمز عبور اضافه کرد — بگو.

---

## مرحله ۴: اجرای دائمی ۲۴/۷ با NSSM

مثل ربات، با NSSM سرویس می‌سازیم:

1. `nssm.exe` را در `C:\btc_analyzer` بگذار (از nssm.cc/download)
2. PowerShell **Administrator**:
```powershell
cd C:\btc_analyzer
.\nssm.exe install BTCAnalyzer
```
3. در پنجره:
   - **Path:** مسیر python.exe (با `(Get-Command python).Source` پیدا کن)
   - **Startup directory:** `C:\btc_analyzer`
   - **Arguments:** `serve.py`
   - **تب Environment** (مهم برای رمز): این‌ها را بگذار:
     ```
     ADMIN_USER=نام_ادمین
     ADMIN_PASS=رمز_قوی
     SECRET_KEY=رشته_تصادفی_طولانی
     ```
4. **Install service** → بعد:
```powershell
.\nssm.exe start BTCAnalyzer
```

تمام! وب‌سایت ۲۴/۷ بالاست. 🎉

---

## دستورات مدیریت

```powershell
.\nssm.exe status BTCAnalyzer
.\nssm.exe restart BTCAnalyzer
.\nssm.exe stop BTCAnalyzer
```

---

## چه چیزی نشان می‌دهد

```
🎯 جهت غالب: رأی‌گیری وزن‌دار بین ۴ تایم‌فریم (15m/1h/4h/1d)

📊 هر تایم‌فریم:
   روند · الگو (کانال/مثلث) · RSI + واگرایی
   MACD · StochRSI · ایچیموکو · بولینگر · CVD
   Order Block های نزدیک (با FVG)

🤖 سناریو AI:
   RandomForest روی داده تاریخی آموزش می‌بیند
   Backtesting دقت واقعی را نشان می‌دهد
   احتمال صعود/نزول + مهم‌ترین عوامل

🌍 نمای کلی: روند همه ۱۱ ارز یکجا
```

---

## نکات مهم

- 🤖 **AI = آمار، نه پیشگویی.** مدل می‌گوید «در گذشته مشابه، X% صعودی بوده».
  دقت backtest بالای ۵۲٪ یعنی بهتر از شانس. هیچ تضمینی نیست.
- ⚡ تحلیل AI چند ثانیه طول می‌کشد (آموزش مدل) — کش ۱۰ دقیقه‌ای دارد.
- 💾 تحلیل عادی کش ۲ دقیقه‌ای دارد (سریع، کم‌فشار روی API).
- 🔋 RandomForest سبک تنظیم شده تا روی VPS کوچک هم کار کند.

---

## عیب‌یابی

| مشکل | راه‌حل |
|------|--------|
| `pip` شناخته نشد | Python با "Add to PATH" نصب کن |
| از بیرون باز نمی‌شود | پورت 5000 در فایروال + پنل MobinHost باز است؟ |
| AI خطا می‌دهد | `pip install scikit-learn` را زدی؟ |
| Binance restricted | سرور بلاک است، به پشتیبانی بگو |
| سرویس بالا نمی‌آید | مسیر python.exe در NSSM درست است؟ لاگ را ببین |

موفق باشی!

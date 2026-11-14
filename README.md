# 🕐 PGClockBot

![PGClockBot preview](preview.png)

فروش اشتراک، نمایندگی، کیف پول و عملیات پاسارگارد؛ رابط ربات فارسی، پنل وب روی پورت `9000`.

**نسخه پایدار `0.5.0`** روی شاخهٔ `main` — نصب پیش‌فرض همین کانال است. شاخهٔ `dev` برای پیش‌نسخه‌های آزمایشی است.

---

## ✨ قابلیت‌ها

### 💳 فروش و پرداخت
- پلن‌های کاربر و خرید مهمان؛ کیف پول، کارت‌به‌کارت، درگاه لینک، رمزارز، استارز
- درگاه آنلاین (مثل SunPay) و چند API به‌ازای هر فروشگاه
- تمدید، سرویس‌های من، هشدار انقضا/حجم و پیشنهاد شارژ
- تمدید خودکار و افزایش خودکار زمان/حجم از کیف پول (per-service)
- ابطال پرداخت تأییدشده و پیگیری سفارش توسط خود مشتری

### 📱 مینی‌اپ تلگرام
- مینی‌اپ مشتری: خرید، کیف پول، تیکت، تخفیف، راهنما، باشگاه
- مینی‌اپ فروشگاه برای نماینده: فروش پلن، کیف فروشگاه، پشتیبانی
- برند هر فروشگاه (نام، لوگو، رنگ) و دامنهٔ جدا

### 🏪 نمایندگی
- پلن و فروشگاه نماینده؛ سهم / PAYG؛ ربات اختصاصی
- سقف حجم، فروش بیش از سقف با hold، همگام با پنل
- مدیریت نمایندگان از وب و بات؛ جستجوی نماینده در ربات

### 🛡️ پاسارگارد
- کاربران، ادمین، گروه، هاست، نود، تمپلیت
- سهمیه و نقش زنده از پاسارگارد
- ساخت کاربر از تمپلیت یا سفارشی

### 🔌 اتصال افزوده به S-UI

این فورک اتصال اصلی PasarGuard را حذف نمی‌کند. برای استفادهٔ فقط با S-UI، فایل
`.env.sui.example` را مبنا قرار دهید و این مقدارها را تنظیم کنید:

```env
PANEL_BACKEND="sui"
SUI_BASE_URL="http://127.0.0.1:2095/app"
SUI_API_TOKEN="توکن-API-v2-از-S-UI"
SUI_SUBSCRIPTION_BASE_URL="http://SERVER_IP:2096/sub"
SUI_INBOUND_IDS="1,2"
WEBHOOK_URL=""
PUBLIC_BASE_URL=""
```

در حالت S-UI، عملیات اصلی فروش و مدیریت سرویس شامل ساخت، تمدید، حجم، انقضا،
فعال/غیرفعال‌سازی، حذف، آمار مصرف و لینک اشتراک روی Clientهای S-UI انجام می‌شود.
برای هر پلن، مقدار «گروه» همان ID مربوط به Inbound در S-UI است. Templateهای
اختصاصی PasarGuard و مدیریت Node/Host/Administrator همچنان در کد و رابط قدیمی
حفظ شده‌اند، اما در حالت S-UI عملیاتی که معادل API ندارند پیام راهنما می‌دهند.

#### نصب بدون دامنه و گواهی

S-UI را روی HTTP اجرا کنید، پورت‌های وب و Subscription را روی فایروال باز کنید و
`SUI_SUBSCRIPTION_BASE_URL` را با IP واقعی سرور بنویسید؛ مثلاً
`http://203.0.113.10:2096/sub`. ربات با `WEBHOOK_URL=""` از polling استفاده می‌کند
و به دامنه یا SSL نیاز ندارد. توجه کنید لینک اشتراک HTTP رمزنگاری‌شده نیست و برای
استفادهٔ عمومی امن، بعداً HTTPS پیشنهاد می‌شود.

کد Mini App و تمام فایل‌های آن حفظ شده است، اما Telegram برای اجرای Mini App
آدرس HTTPS می‌خواهد. بنابراین در حالت کاملاً بدون دامنه/گواهی، تجربهٔ ربات و پنل
وب روی IP کار می‌کند ولی دکمهٔ Mini App فعال نمی‌شود؛ با اضافه‌کردن HTTPS و
`PUBLIC_BASE_URL`، همان Mini App بدون تغییر کد فعال خواهد شد.

### 🖥️ پنل وب و ربات
- داشبورد، سفارش‌ها، تیکت، تنظیمات، راهنمای درون‌پنل (`/help`)
- یک کیبورد منو و یک صفحه در چت؛ «کیبورد همیشه باز» اختیاری
- جستجوی مشتری با نام/یوزرنیم/لینک اشتراک

---

## 🚀 نصب سریع

**منابع پیشنهادی:** ۲ گیگ رم و ۲ هسته CPU · Ubuntu 22.04+

### نصب یک‌خطی S-UI بدون دامنه و SSL

روی سرور Ubuntu این دستور را اجرا کنید؛ مخزن فورک دریافت می‌شود، PostgreSQL،
Python، وابستگی‌ها و سرویس پنل نصب می‌شوند و سپس لینک ویزارد اولیه نمایش داده می‌شود:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/alirezasj7/PGClockBot-SUI/main/install-sui.sh)
```

در ویزارد، آدرس S-UI، توکن API v2، آدرس Subscription با IP، توکن ربات و رمز ورود
پنل را وارد کنید. نصب پیش‌فرض روی HTTP، پورت `9000` و polling است؛ دامنه و گواهی لازم
نیست. برای اجرای مستقیم bootstrap هم می‌توانید بنویسید:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/alirezasj7/PGClockBot-SUI/main/get.sh) install-main
```

### قبل از نصب این‌ها را آماده کنید
1. **دامنه** متصل به آی‌پی سرور
2. **توکن ربات**، **یوزرنیم ربات** و **آیدی ادمین** تلگرام
3. **اطلاعات ورود پنل پاسارگارد** (آدرس، یوزر، رمز)

> این فهرست برای نصب پیش‌فرض PasarGuard است. برای نصب فقط با S-UI و بدون دامنه،
> بخش «اتصال افزوده به S-UI» را دنبال کنید؛ S-UI و ربات با IP/HTTP و polling هم کار می‌کنند.

### یک‌خطی (کانال پایدار / `main`)
```bash
bash <(curl -fsSL https://raw.githubusercontent.com/alirezasj7/PGClockBot-SUI/main/get.sh) install-main
```

نصب پیش‌فرض از **`main` (پایدار 0.5)** است. برای کانال توسعه:

```bash
PGCLOCK_CHANNEL=dev bash <(curl -fsSL https://raw.githubusercontent.com/alirezasj7/PGClockBot-SUI/dev/get.sh) install-dev
```

بعد از نصب، راه‌اندازی در مرورگر کامل می‌شود: `http://SERVER_IP:9000/` (یا دامنهٔ شما).

### پایگاه داده (PostgreSQL)
نصب تازه فقط با **PostgreSQL** انجام می‌شود (SQLite برای نصب جدید ساخته نمی‌شود). اسکریپت نصب
در صورت نبود، PostgreSQL محلی را به‌صورت خودکار آماده می‌کند، سرویس را روشن می‌کند، کاربر و پایگاه
داده می‌سازد و `DATABASE_URL` را در `.env` می‌نویسد. `postgresql-client` هم برای پشتیبان‌گیری نصب می‌شود.

برای استفاده از PostgreSQL بیرونی یا مدیریت‌شده، پیش از نصب آدرس آن را بدهید؛ مقدار باید با
`postgresql://`، `postgresql+asyncpg://` یا `postgres://` شروع شود و از سرور قابل دسترس باشد:

```bash
PGCLOCK_DATABASE_URL='postgresql+asyncpg://USER:PASS@HOST:5432/DBNAME' bash pgclock.sh install main
```

اگر `.env` قبلی هنوز به SQLite اشاره می‌کند، نصب متوقف می‌شود و از شما می‌خواهد `DATABASE_URL`
را به PostgreSQL تغییر دهید.

### منوی اسکریپت (`pgclock.sh`)
دستور بالا منو را باز می‌کند. داخل پوشهٔ پروژه هم:

```bash
bash pgclock.sh
```

| گزینه | کار |
|------|-----|
| `1` Install main | نصب کانال پایدار (پیشنهادی) |
| `2` Install dev | نصب کانال توسعه |
| `3` Update main | آپدیت از `origin/main` (`.env` حفظ می‌شود) |
| `4` Update dev | آپدیت از `origin/dev` |
| `5` Edit .env | ویرایش توکن / پنل / پورت |
| `6` Web panel | آدرس پنل، ریست رمز، health |
| `7` Service | وضعیت / استارت / ری‌استارت / لاگ |
| `8` Status | خلاصهٔ سلامت |
| `9` Doctor | تشخیص فقط‌خواندنی |
| `10` Uninstall | حذف کامل |
| `11` Setup Xray | هستهٔ تست اتصال |
| `0` Exit | خروج |

میانبر بدون منو:

```bash
bash pgclock.sh install main
bash pgclock.sh update main
bash pgclock.sh status
bash pgclock.sh doctor
bash pgclock.sh help
```

---

## 🛠️ CLI سراسری (`pgclock`)

بعد از نصب (یک‌بار با sudo):

```bash
sudo bash scripts/install_global_cli.sh
```

از هر مسیری:

```bash
pgclock status
pgclock start
pgclock stop
pgclock restart
pgclock logs              # ۱۰۰ خط آخر
pgclock logs -f           # دنبال کردن لاگ
pgclock health
pgclock backup --note "pre-update"
pgclock backup --list
pgclock restore <backup_id> -y
pgclock migrate
pgclock doctor
```

بدون نصب سراسری، از ریشهٔ پروژه:

```bash
export PGCLOCK_HOME=/path/to/PGClockBot
./scripts/pgclock status
```

---

## 📄 لایسنس

هر گونه کپی‌برداری بدون ذکر نام و فروش غیرمجاز است.

[MIT](LICENSE) © Mrclocks

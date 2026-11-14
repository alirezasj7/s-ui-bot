# سازگاری کانفیگ‌های وضعیت اتصال

## مسیر فعلی subscription

منبع اجرا فقط خروجی native Xray لینک subscription همان Test user است. فهرست و worker از
API هاست‌ها یا inboundها استفاده نمی‌کنند. نام و ترتیب از آرایهٔ subscription می‌آیند؛ badgeهای
protocol، transport، security و port از همان outbound اصلی استخراج می‌شوند.

هر config یک endpoint دارد. VLESS، VMess، Trojan و Shadowsocks با transportهای native
شناخته‌شده پذیرفته می‌شوند. JSON اصلی با کنترل نوع، ظرفیت، آدرس/پورت و محدودیت‌های امنیتی
بررسی و بدون بازنویسی address، SNI، path، credential یا درج default به Xray داده می‌شود.
فقط tag برای جداسازی پروکسی‌های هم‌زمان عوض می‌شود. schema نهایی را core ثابت در startup
کنترل می‌کند؛ قابلیت‌های نسخه‌های جدیدتر core خودکار به نسخهٔ pin‌شده اضافه نمی‌شوند.

فایل `tests/fixtures/connection_monitor_native.json` شش config مصنوعی برای Reality/TCP،
TLS/WebSocket، XHTTP/TLS، VMess/TCP، Trojan/TCP/TLS و Shadowsocks/TCP دارد. CLI و CI
هر دو معماری Linux را با همین خروجی subscription از نظر startup/readiness/cleanup بررسی می‌کنند؛
درخواست relay یا حساب واقعی استفاده نمی‌شود.

reference به outbound دیگر (`dialerProxy`/`proxySettings`)، فایل certificate/key محلی،
غیرفعال کردن TLS verification و protocolهای خارج از allow-list قابل اجرا نیستند. چنین configی
با ترتیب و نام اصلی و دلیل روشن در لیست می‌ماند؛ بخش نامعتبرش حذف یا حدس زده نمی‌شود.
routing، DNS، inbounds و outboundهای مستقیم template وارد runtime نمی‌شوند؛ default همچنان blackhole است.

شناسهٔ انتخاب، hash محتوای outbound، نام اصلی و شمار تکرار config یکسان است. تغییر ترتیب
انتخاب را عوض نمی‌کند، ولی تغییر محتوای config یا نام اصلی نیاز به انتخاب دوباره دارد؛
configهای پویا که در هر بار دریافت محتوای تازه می‌سازند برای انتخاب پایدار مناسب نیستند.

## شواهد API نگاشت قدیمی

متن و ماتریس زیر به mapper خالص قدیمی مربوط‌اند که برای سازگاری API و regressionها حفظ
شده است. این mapper در مسیر اجرایی انتخاب، فهرست یا worker جدید استفاده نمی‌شود.

قابلیت **Experimental** و پیش‌فرض خاموش است. syntax و startup کانفیگ مصنوعی با Xray
**26.3.27**، commit `d2758a0`، روی macOS/arm64 و Linux/amd64 تأیید شده‌اند؛ live relay تأیید نشده است.
منبع binary، [release رسمی v26.3.27](https://github.com/XTLS/Xray-core/releases/tag/v26.3.27)
و فایل `Xray-macos-arm64-v8a.zip` است. SHA-256 آرشیو پیش از استخراج و اجرا با digest
release تطبیق داده شد:

```text
2e93a67e8aa1936ecefb307e120830fcbd4c643ab9b1c46a2d0838d5f8409eaf
```

نصب‌کنندهٔ ربات برای Linux/amd64 و Linux/arm64 نیز از همان release رسمی استفاده می‌کند؛
SHA-256 آرشیو و فایل اجرایی جداگانه در `connection_monitor_distribution.py` ثابت شده‌اند.
CI هر دو معماری را با نصب‌کننده آماده و startup/cleanup مصنوعی را بررسی می‌کند؛ live relay
همچنان خارج از این تأیید است. فایل‌های license و README همراه binary حفظ می‌شوند.

ورودی نگاشت، فهرست کامل هاست‌های همان principal، `inbounds/details` و خروجی native
Xray حساب اختصاصی تست اتصال است. API جزئیات inbound برای VLESS اطلاعات Reality/TLS را
ندارد؛ بنابراین بازسازی آن از فیلدهای حدسی انجام نمی‌شود. قرارداد پنل بر اساس
[schema هاست](https://github.com/PasarGuard/panel/blob/b56ffe369f542152c52c69733205baeaf3f6e4cd/app/models/host.py)،
[خلاصهٔ inbound](https://github.com/PasarGuard/panel/blob/b56ffe369f542152c52c69733205baeaf3f6e4cd/app/operation/system.py)
و [خروجی بومی Xray](https://github.com/PasarGuard/panel/blob/b56ffe369f542152c52c69733205baeaf3f6e4cd/app/subscription/xray.py)
بررسی شد. کد generator پنل کپی نشده است.

نگاشت از آدرس، پورت، protocol/network اینباند و overrideهای صریح security/SNI/Host/path
استفاده می‌کند. همهٔ هاست‌های catalog، حتی انتخاب‌نشده‌ها، در تشخیص ابهام حضور دارند.
`remark`، ترتیب لیست و ترتیب نمونه‌های اشتراک هیچ نقشی در هویت ندارند. UUID و تنظیمات
TLS/Reality از outbound معتبر خود پنل حفظ می‌شوند.

برای دامنهٔ اولیه، هر هاست باید **پورت صریح و دقیقاً یک SNI ثابت** داشته باشد. SNI
پیش‌فرض نامعلوم، انتخاب چند پورت، wildcard، placeholder و چند SNI تأیید نشده‌اند.
نبود این پیش‌نیازها نتیجهٔ `not_ready` است؛ ربات تنظیم هاست پنل را تغییر نمی‌دهد.

| ترکیب | شواهد سازگاری | محدودیت |
| --- | --- | --- |
| VLESS + Reality + TCP خام | fixture، حفظ UUID/flow/key/SNI/short ID و `xray run -test` موفق | encryption=`none`؛ flow خالی یا Vision؛ بدون dialer/mux/fragment |
| VLESS + TLS + WebSocket | fixture، حفظ SNI/Host/path/ALPN و `xray run -test` موفق | TLS verification روشن؛ flow خالی؛ تنظیم‌های پیشرفته خارج ماتریس |
| چند آدرس ثابت | ساخت مسیر مستقل برای هر آدرس و اعتبارسنجی کانفیگ سه‌مسیره | ثابت بودن سایر تنظیم‌ها و نبود تطبیق مبهم برای تمام آدرس‌ها |
| tag کمکی، fragment/noise، mux، XHTTP، template سفارشی هاست | تست رد صریح | تا اثبات مستقل `not_ready` |

کانفیگ runtime از نو با ورودی HTTP روی `127.0.0.1` ساخته می‌شود. اولین outbound
`blackhole` است و هر ورودی فقط به outbound منتخب خودش route دارد. routing، DNS،
ورودی‌ها و outboundهای مستقیم template اشتراک وارد runtime نمی‌شوند. وجود `dialerProxy`،
`proxySettings` یا فیلد ناشناخته در outbound اصلی باعث رد آن می‌شود.

در چندآدرسی، تنها آدرس outbound یکتای ثابت با آدرس‌های صریح همان هاست جایگزین می‌شود؛
بقیهٔ تنظیمات ثابت می‌مانند. اگر آدرس گسترش‌یافته به چند هاست بخورد، یا دو نمونهٔ native
برای یک هاست تنظیم متفاوت داشته باشند، هیچ مسیر ناقصی برای آن هاست ساخته نمی‌شود.
بیش از ۱۲ endpoint، تمام انتخاب آماده را با دلیل ظرفیت متوقف می‌کند؛ حذف بی‌صدای هدف نداریم.

فایل `tests/fixtures/connection_monitor_catalog.json` کاملاً مصنوعی است؛ UUID آن حساب
واقعی نیست. تست‌ها بدون شبکه و بدون credential واقعی اجرا می‌شوند. کانفیگ حاصل شامل
دو endpoint Reality و یک endpoint WebSocket با `xray run -test -config …` بررسی شد.
این اثبات syntax و پذیرش core است؛ اتصال واقعی، عبور CONNECT و دسترسی از
سرور ربات در این تحویل skip شده‌اند. Xray هنگام validation دربارهٔ deprecation
WebSocket پیام می‌دهد؛ پشتیبانی این ماتریس به نسخهٔ بررسی‌شده محدود است.

## Lifecycle و امنیت runner

همان binary رسمی روی macOS/arm64 با سه مسیر مصنوعی اجرا شد؛ پیام شروع خود child
دریافت، زنده بودن آن بررسی و سپس terminate و wait انجام شد. SHA-256 فایل اجرایی:

```text
5d9dd24c0aba4b6cfcc6a33a5d67f854816ee17f392bf932ec8176da46f7e404
```

runner مسیر مطلق بدون symlink، executable بودن، نبود write برای group/other روی فایل
و parent directory، checksum و نسخهٔ دقیق `26.3.27` را بررسی می‌کند. فایل JSON از
لحظهٔ ایجاد با `os.open(..., 0o600)` در دایرکتوری موقت `0700` ساخته می‌شود؛ permission
به chmod بعدی وابسته نیست. I/O و hashing داخل thread اجرا می‌شوند.
environment هسته محدود، argv فاقد config خام و stdout/stderr بدون ذخیره یا log مصرف
می‌شوند. هیچ generator یا کد شخص ثالث کپی نشده و dependency تازه‌ای اضافه نشده است.

آمادگی به پورت باز وابسته نیست: طبق [Start در core نسخهٔ ثابت](https://github.com/XTLS/Xray-core/blob/v26.3.27/core/xray.go)،
پیام شروع پس از موفقیت همهٔ featureها صادر می‌شود. runner همان marker را از pipe
پردازش جاری با حافظهٔ محدود می‌خواند و exit را هم کنترل می‌کند. شکست bind حداکثر سه
بار با پورت‌های تازه تکرار می‌شود؛ نسخهٔ نادرست اصلاً وارد این retry نمی‌شود.

startup/readiness پنج ثانیه و terminate دو ثانیه مهلت دارند؛ سپس kill و wait حداکثر
دو ثانیه اجرا می‌شوند. لغو هنگام spawn، readiness یا کار، child و فایل‌ها را پاک می‌کند.
در SIGKILL والد، `finally` اجرا نمی‌شود: استقرار Linux باید با systemd و
`KillMode=control-group` تمام فرزندان را هنگام توقف سرویس جمع کند. `start_new_session`
جایگزین این سیاست نیست. پس از crash، فایل موقت ممکن است تا cleanup سیستم باقی بماند؛
مجوز محدود آن حفظ می‌شود و اپراتور می‌تواند دایرکتوری‌های `pgclock-probe-*` متعلق به
سرویس متوقف‌شده را حذف کند. این مورد تضمین پاک‌سازی پس از SIGKILL نیست.

تست‌های آفلاین، شروع ناموفق، readiness بدون marker، child مرده، retry
محدود، خروجی حجیم، اختلاف نسخه/checksum، cancellation تکراری هنگام spawn و
terminate/kill/wait را پوشش می‌دهند. startup روی Linux نیز در CI تأیید شد؛ اتصال واقعی
با test user در سرور مقصد در این تحویل skip شده است.

## بررسی تکرارپذیر CI

workflow مستقل [Connection monitoring compatibility](../.github/workflows/connection-monitor.yml)
تست‌های رفتاری را روی PostgreSQL 16 و startup را با core رسمی Linux/amd64 اجرا می‌کند.
آرشیو Linux `Xray-linux-64.zip` با نسخهٔ ثابت `v26.3.27` و SHA-256 منتشرشده بررسی می‌شود:

```text
23cd9af937744d97776ee35ecad4972cf4b2109d1e0fe6be9930467608f7c8ae
```

پس از تأیید آرشیو، checksum فایل استخراج‌شده به runner داده می‌شود. CLI
`python -m app.cli.connection_monitor --binary /absolute/path/xray --sha256 …`
سه مسیر مصنوعی همین fixture را اجرا و readiness و reap شدن child را کنترل می‌کند؛
درخواست relay یا حساب واقعی استفاده نمی‌شود. مسیر fixture مربوط به checkout توسعه است.
پیکربندی PostgreSQL سرویس CI از [الگوی رسمی GitHub](https://docs.github.com/en/actions/tutorials/use-containerized-services/create-postgresql-service-containers)
پیروی می‌کند و حساب آن فقط متعلق به کانتینر موقت تست است.

SHA مربوط به Actionهای همین workflow به commit رسمی pin شده است. شمار تست‌ها و نتیجهٔ
CI مربوط به head بررسی‌شده در [PR #777](https://github.com/Mrclocks/PGClockBot/pull/777)
ثبت می‌شود؛ startup مصنوعی، ظرفیت یا اتصال production را ثابت نمی‌کند.

unit ساخته‌شده توسط نصب‌کنندهٔ پروژه `KillMode` را override نمی‌کند؛ طبق
[مستند systemd](https://github.com/systemd/systemd/blob/main/man/systemd.kill.xml)
پیش‌فرض آن `control-group` است. override واحد سرویس روی سرور مقصد و جمع شدن child
پس از crash سخت باید در پذیرش استقرار بررسی شوند؛ به `finally` پس از SIGKILL تکیه نمی‌شود.

# VodiWalker Telegram Bot — 3x-ui Edition

این نسخه فقط **ربات تلگرام** است. پنل وب، FastAPI dashboard، Xray relay و منطق فروش از سرویس حذف شده‌اند.

## معماری

- Telegram Bot → `botsys/handlers`
- Persistent state → یک فایل JSON روی Railway Volume
- 3x-ui → REST API با `Authorization: Bearer <API Token>`
- API Key Pool → هر کلید یک سقف تعداد کانفیگ و سقف حجم اختصاص‌یافته دارد.
- هنگام ساخت کانفیگ، ربات کلیدها را به‌ترتیب بررسی می‌کند؛ اگر سقف کلید پر باشد، به کلید بعدی می‌رود.
- مصرف و وضعیت واقعی کانفیگ از خود 3x-ui خوانده می‌شود.
- API Tokenها رمزنگاری‌شده ذخیره می‌شوند و در Telegram فقط به‌شکل ماسک‌شده نمایش داده می‌شوند.
- ربات فقط به API پنل وصل می‌شود و خودش Xray اجرا نمی‌کند.

## Environment Variables

### ضروری
- `TELEGRAM_BOT_TOKEN`: توکن BotFather
- `TELEGRAM_SUPER_ADMIN_IDS`: شناسه عددی ادمین اصلی؛ چند مقدار با `,` جدا شوند.

### اختیاری
- `TELEGRAM_ADMIN_IDS`: ادمین‌های اولیه در صورت نیاز.
- `TELEGRAM_UPDATE_MODE`: پیش‌فرض `polling`.
- `RAILWAY_VOLUME_MOUNT_PATH`: مسیر Volume؛ روی Railway یک Volume دائمی برای این مسیر قرار دهید.
- `SECRET_KEY`: اختیاری. اگر خالی باشد اولین اجرا یک کلید امن در Volume می‌سازد.
- `TELEGRAM_BROADCAST_RATE`: نرخ ارسال Broadcast.
- `LOG_LEVEL`: پیش‌فرض `INFO`.

## تنظیم 3x-ui از داخل خود ربات

بعد از `/start`:
1. `/admin`
2. `🖥 APIهای 3x-ui`
3. `➕ افزودن API Key`
4. نام
5. URL پنل
6. API Token
7. Inbound ID
8. حداکثر تعداد کانفیگ؛ مثلاً `20`
9. حداکثر حجم اختصاص‌یافته کل؛ مثلاً `200` GB یا `0` برای نامحدود.

API Token باید از بخش Security/API Token خود 3x-ui ساخته شده باشد.

## Restore بکاپ قدیمی

از `💾 بکاپ / ریستور` گزینه `♻️ ریستور بکاپ` را بزنید و فایل ZIP نسخه قبلی را ارسال کنید.

فرمت بکاپ قبلی پروژه (`format=1`) مستقیماً پذیرفته می‌شود:
- کاربران، نقش‌ها، کانال‌ها، تیکت‌ها، سهمیه‌ها و تنظیمات ربات بازیابی می‌شوند.
- رکوردهای کانفیگ قدیمی به‌عنوان `Legacy` حفظ می‌شوند تا اطلاعات مالکیت از بین نرود.
- کانفیگ‌های قدیمیِ پنل محلی به‌صورت خودکار به‌عنوان کلاینت واقعی 3x-ui جعل نمی‌شوند؛ چون بکاپ قدیمی شامل API Token و Inbound مقصد 3x-ui نیست.
- پس از اتصال APIهای جدید، ساخت کانفیگ‌های جدید از 3x-ui انجام می‌شود.

## Backup جدید

بکاپ‌های جدید شامل:
- `state.json`
- `secret.key`
- API Tokenهای 3x-ui به‌صورت رمزنگاری‌شده
- کاربران، سهمیه‌ها، کانال‌ها، تیکت‌ها، آمار و تنظیمات.

فایل بکاپ داخل خود ربات فقط توسط Super Admin قابل Restore است.

## تست

```bash
python -m compileall -q .
python tests/test_bot.py
python tests/test_backup.py
python tests/test_xui.py
```

برای تست واقعی 3x-ui، یک پنل آزمایشی و API Token معتبر لازم است. تست‌های واحد بدون نیاز به پنل واقعی اجرا می‌شوند.

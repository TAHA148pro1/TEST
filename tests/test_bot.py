"""تست سناریوهای ربات VodiWalker.

۲۰ سناریوی خواسته‌شده به‌صورت کامل پوشش داده شده است. تست‌ها بدون شبکه اجرا
می‌شوند: پنل و Telegram API هر دو جعلی‌اند، ولی قرارداد (امضای توابع و شکل
پاسخ‌ها) عیناً مطابق واقعیت است.

اجرا:  python3 tests/test_bot.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["TELEGRAM_SUPER_ADMIN_IDS"] = "900001"

from tests.harness import FakeTelegram, bootstrap, callback, message  # noqa: E402

SUPER_ADMIN = 900001
ADMIN = 900002
USER = 500001
USER2 = 500002

_results: list[tuple[str, bool, str]] = []


# ── اسکلت تست ────────────────────────────────────────────────────────────────
def scenario(name: str):
    def decorator(fn):
        async def wrapper():
            ctx = bootstrap()
            tg = FakeTelegram().install()
            try:
                await fn(ctx, tg)
                _results.append((name, True, ""))
            except AssertionError as exc:
                _results.append((name, False, str(exc) or "assertion failed"))
            except Exception:
                _results.append((name, False, traceback.format_exc(limit=3)))
        wrapper._name = name
        return wrapper
    return decorator


async def setup_admin(ctx, telegram_id: int = ADMIN):
    """یک Admin معمولی (نه Super Admin) می‌سازد."""
    await ctx.users.touch({"id": telegram_id, "first_name": "ادمین"})
    await ctx.users.set_role(SUPER_ADMIN, telegram_id, ctx.security.ROLE_ADMIN)


async def add_channel(ctx, title="کانال تست", username="testchan"):
    return await ctx.channels.create(SUPER_ADMIN, title, username=username)


def find_button(tg, needle: str):
    for button in tg.buttons():
        if needle in str(button.get("text", "")):
            return button
    return None


# ── ۱. کاربر جدید /start ─────────────────────────────────────────────────────
@scenario("1. کاربر جدید /start")
async def t01(ctx, tg):
    await ctx.router.dispatch(message(USER, "/start", username="newbie"))

    rec = ctx.users.get(USER)
    assert rec is not None, "کاربر ثبت نشد"
    assert rec["username"] == "newbie"
    assert rec["role"] == ctx.security.ROLE_USER
    assert rec["first_seen"], "تاریخ اولین ورود ثبت نشد"

    buttons = tg.buttons()
    labels = [b["text"] for b in buttons]
    assert any("رایگان" in x for x in labels), f"دکمه کانفیگ رایگان نیست: {labels}"
    assert any("کانفیگ‌های من" in x for x in labels)
    assert not any(b["callback_data"].startswith("a:") for b in buttons), "کاربر عادی دکمه ادمین دید"


# ── ۲. کاربر Admin /start ────────────────────────────────────────────────────
@scenario("2. کاربر Admin /start")
async def t02(ctx, tg):
    await ctx.router.dispatch(message(SUPER_ADMIN, "/start"))
    labels = [b["text"] for b in tg.buttons()]
    assert any("کاربران" in x for x in labels), f"داشبورد ادمین نمایش داده نشد: {labels}"
    assert any("آمار" in x for x in labels)
    assert ctx.security.is_super_admin(SUPER_ADMIN), "Super Admin از ENV شناسایی نشد"


# ── ۳. کاربر بدون عضویت در کانال ─────────────────────────────────────────────
@scenario("3. کاربر بدون عضویت در کانال")
async def t03(ctx, tg):
    await add_channel(ctx)
    tg.default_member_status = "left"
    await ctx.router.dispatch(message(USER, "/start"))
    tg.clear()

    await ctx.router.dispatch(callback(USER, "u:free"))

    assert "عضویت" in tg.all_text(), "پیام الزام عضویت نمایش داده نشد"
    buttons = tg.buttons()
    assert any(b.get("url") for b in buttons), "دکمه ورود به کانال ساخته نشد"
    assert find_button(tg, "بررسی عضویت"), "دکمه بررسی عضویت وجود ندارد"
    assert not ctx.configs.user_configs(USER), "بدون عضویت کانفیگ صادر شد!"
    assert ctx.quota.status(USER)["used"] == 0, "سهمیه بی‌دلیل مصرف شد"


# ── ۴. کاربر با عضویت کامل ───────────────────────────────────────────────────
@scenario("4. کاربر با عضویت کامل")
async def t04(ctx, tg):
    await add_channel(ctx)
    tg.default_member_status = "member"
    await ctx.router.dispatch(message(USER, "/start"))

    ok, missing, unverifiable = await ctx.channels.check_membership(USER, force=True)
    assert ok, f"عضویت تأیید نشد: missing={missing} unverifiable={unverifiable}"
    assert ctx.users.get(USER)["channels_ok"] is True


# ── ۵. دریافت کانفیگ رایگان ──────────────────────────────────────────────────
@scenario("5. دریافت کانفیگ رایگان")
async def t05(ctx, tg):
    await add_channel(ctx)
    tg.default_member_status = "member"
    ctx.store.set_setting("free_quota_total", 2)
    ctx.store.set_setting("free_volume_gb", 15)
    ctx.store.set_setting("free_duration_days", 30)
    await ctx.router.dispatch(message(USER, "/start"))
    tg.clear()

    await ctx.router.dispatch(callback(USER, "u:free:menu"))

    my = ctx.configs.user_configs(USER)
    assert len(my) == 1, f"کانفیگ ساخته نشد: {my}"
    assert my[0]["source"] == "free"
    assert my[0]["delivered"] is True, "کانفیگ به‌عنوان ارسال‌شده علامت نخورد"

    link = ctx.panel.LINKS[my[0]["link_uid"]]
    assert link["limit_bytes"] == 15 * 1024 ** 3, "حجم از تنظیمات اعمال نشد"
    assert link["expires_at"], "تاریخ انقضا ست نشد"
    assert ctx.quota.status(USER)["used"] == 1, "سهمیه مصرف نشد"

    # اطلاعات کانفیگ در یک پیام واحد، بر اساس داده‌ی واقعی پنل
    body = tg.all_text()
    for needed in ("حجم", "مدت اعتبار", "تاریخ انقضا", "سرعت"):
        assert needed in body, f"«{needed}» در پیام کانفیگ نیست"

    # دو دکمه‌ی کپی رسمی: لینک ساب و کانفیگ خام — و این دو نباید قاتی شوند
    copies = [b for b in tg.buttons() if b.get("copy_text")]
    assert len(copies) == 2, f"دو دکمه کپی رسمی لازم است: {tg.buttons()}"
    sub_value = copies[0]["copy_text"]["text"]
    raw_value = copies[1]["copy_text"]["text"]
    assert sub_value == f"https://panel.example.com/sub/{my[0]['link_uid']}", \
        f"دکمه «کپی لینک ساب» لینک ساب واقعی را کپی نمی‌کند: {sub_value}"
    assert raw_value.startswith("vless://"), f"دکمه «کپی کانفیگ» کانفیگ خام نمی‌دهد: {raw_value}"
    assert sub_value != raw_value, "لینک ساب و کانفیگ خام یکی شده‌اند"


# ── ۶. اتمام سهمیه ───────────────────────────────────────────────────────────
@scenario("6. اتمام سهمیه")
async def t06(ctx, tg):
    tg.default_member_status = "member"
    ctx.store.set_setting("free_quota_total", 1)
    ctx.store.set_setting("free_daily_limit", 0)
    await ctx.router.dispatch(message(USER, "/start"))

    first = await ctx.issuing.issue_free_config(USER)
    assert first.ok, f"اولین کانفیگ صادر نشد: {first.reason}"

    second = await ctx.issuing.issue_free_config(USER)
    assert not second.ok, "با اتمام سهمیه باز هم کانفیگ صادر شد!"
    assert "سهمیه" in second.reason, second.reason
    assert len(ctx.configs.user_configs(USER)) == 1, "کانفیگ اضافه ساخته شد"


# ── ۷. Double Click دریافت کانفیگ ────────────────────────────────────────────
@scenario("7. Double Click دریافت کانفیگ")
async def t07(ctx, tg):
    tg.default_member_status = "member"
    ctx.store.set_setting("free_quota_total", 5)
    ctx.store.set_setting("free_daily_limit", 0)
    await ctx.router.dispatch(message(USER, "/start"))

    # ده درخواست کاملاً هم‌زمان
    results = await asyncio.gather(*[ctx.issuing.issue_free_config(USER) for _ in range(10)])
    granted = [r for r in results if r.ok]

    assert len(granted) == 1, f"کلیک هم‌زمان {len(granted)} کانفیگ ساخت (باید ۱ باشد)"
    assert ctx.quota.status(USER)["used"] == 1, "سهمیه چندبار مصرف شد (سهمیه ۵ بود)"
    assert len(ctx.configs.user_configs(USER)) == 1
    assert any(r.busy for r in results if not r.ok), "محافظ Double-Click فعال نشد"


# ── ۸. کاربر مسدود ───────────────────────────────────────────────────────────
@scenario("8. کاربر مسدود")
async def t08(ctx, tg):
    tg.default_member_status = "member"
    await ctx.router.dispatch(message(USER, "/start"))
    await ctx.users.set_blocked(SUPER_ADMIN, USER, True)
    tg.clear()

    await ctx.router.dispatch(callback(USER, "u:free"))
    assert not ctx.configs.user_configs(USER), "کاربر مسدود کانفیگ گرفت!"

    tg.clear()
    await ctx.router.dispatch(message(USER, "/start"))
    combined = tg.all_text() + " ".join(
        str(p.get("text", "")) for m, p in tg.calls if m == "answerCallbackQuery"
    )
    assert "محدود" in combined, f"به کاربر مسدود پیام مناسب داده نشد: {combined!r}"

    result = await ctx.issuing.issue_free_config(USER)
    assert not result.ok


# ── ۹. Admin مشاهده کاربر ────────────────────────────────────────────────────
@scenario("9. Admin مشاهده کاربر")
async def t09(ctx, tg):
    await setup_admin(ctx)
    await ctx.users.touch({"id": USER, "username": "target", "first_name": "هدف"})
    tg.clear()

    await ctx.router.dispatch(callback(ADMIN, f"a:usr:{USER}"))
    text = tg.all_text()
    assert str(USER) in text, "اطلاعات کاربر نمایش داده نشد"
    assert "سهمیه" in text

    tg.clear()
    await ctx.router.dispatch(message(ADMIN, "/start"))
    tg.clear()
    await ctx.router.dispatch(callback(ADMIN, "a:users:search"))
    ctx.admin.set_pending(ADMIN, {"action": "user_search"})
    tg.clear()
    await ctx.router.dispatch(message(ADMIN, "target"))
    assert str(USER) in tg.all_text(), "جستجو با Username کار نکرد"


# ── ۱۰. Admin تغییر سهمیه ────────────────────────────────────────────────────
@scenario("10. Admin تغییر سهمیه")
async def t10(ctx, tg):
    await setup_admin(ctx)
    await ctx.users.touch({"id": USER, "first_name": "هدف"})
    before = ctx.quota.status(USER)["total"]

    ctx.admin.set_pending(ADMIN, {"action": "user_field", "field": "quota", "target": USER})
    await ctx.router.dispatch(message(ADMIN, "7"))

    assert ctx.quota.status(USER)["total"] == 7, "سهمیه تغییر نکرد"
    entries = ctx.audit.recent(10, target_id=USER)
    assert any(e["field"] == "total" and e["after"] == 7 for e in entries), \
        f"Audit ثبت نشد: {entries}"
    assert before != 7


# ── ۱۱. Admin تغییر حجم ──────────────────────────────────────────────────────
@scenario("11. Admin تغییر حجم")
async def t11(ctx, tg):
    await setup_admin(ctx)
    tg.default_member_status = "member"
    await ctx.router.dispatch(message(USER, "/start"))
    result = await ctx.issuing.issue_free_config(USER)
    assert result.ok

    ctx.admin.set_pending(ADMIN, {"action": "user_field", "field": "volume", "target": USER})
    await ctx.router.dispatch(message(ADMIN, "50"))

    link = ctx.panel.LINKS[result.user_config["link_uid"]]
    assert link["limit_bytes"] == 50 * 1024 ** 3, f"حجم کانفیگ فعلی اعمال نشد: {link['limit_bytes']}"
    assert ctx.quota.effective(USER)["volume_gb"] == 50, "پیش‌فرض کانفیگ آینده تغییر نکرد"


# ── ۱۲. Admin تغییر سرعت ─────────────────────────────────────────────────────
@scenario("12. Admin تغییر سرعت")
async def t12(ctx, tg):
    await setup_admin(ctx)
    tg.default_member_status = "member"
    await ctx.router.dispatch(message(USER, "/start"))
    result = await ctx.issuing.issue_free_config(USER)

    ctx.admin.set_pending(ADMIN, {"action": "user_field", "field": "speed", "target": USER})
    await ctx.router.dispatch(message(ADMIN, "25"))

    link = ctx.panel.LINKS[result.user_config["link_uid"]]
    expected = int(25 * 1000 * 1000 / 8)
    assert link["speed_limit_bytes"] == expected, f"سرعت اعمال نشد: {link['speed_limit_bytes']}"


# ── ۱۳. حذف کانفیگ ───────────────────────────────────────────────────────────
@scenario("13. حذف کانفیگ (با تأیید دومرحله‌ای)")
async def t13(ctx, tg):
    await setup_admin(ctx)
    tg.default_member_status = "member"
    await ctx.router.dispatch(message(USER, "/start"))
    result = await ctx.issuing.issue_free_config(USER)
    ucid = result.user_config["id"]
    link_uid = result.user_config["link_uid"]
    tg.clear()

    # مرحله ۱: باید فقط سؤال تأیید بپرسد و چیزی حذف نکند
    await ctx.router.dispatch(callback(ADMIN, ctx.security.sign_callback(f"a:cfg:{ucid}:del")))
    assert "مطمئن" in tg.all_text(), "تأیید دومرحله‌ای پرسیده نشد"
    assert link_uid in ctx.panel.LINKS, "کانفیگ قبل از تأیید حذف شد!"

    confirm = find_button(tg, "حذف کن")
    assert confirm, "دکمه تأیید حذف نیست"
    assert confirm.get("style") == "success", f"استایل دکمه تأیید: {confirm.get('style')}"

    # مرحله ۲: تأیید
    tg.clear()
    await ctx.router.dispatch(callback(ADMIN, confirm["callback_data"]))
    assert link_uid not in ctx.panel.LINKS, "کانفیگ از پنل حذف نشد"
    assert not ctx.configs.user_configs(USER), "رکورد کاربر حذف نشد"
    assert any(e["action"] == "config_delete" for e in ctx.audit.recent(10)), "Audit حذف ثبت نشد"


# ── ۱۴. Broadcast ────────────────────────────────────────────────────────────
@scenario("14. Broadcast")
async def t14(ctx, tg):
    # ارسال همگانی دسترسی SEND_BROADCAST می‌خواهد که فقط Super Admin دارد.
    await setup_admin(ctx)
    for uid in (USER, USER2, 500003):
        await ctx.users.touch({"id": uid, "first_name": f"u{uid}"})
    await ctx.users.set_blocked(SUPER_ADMIN, 500003, True)

    # ادمین معمولی نباید بتواند پیام همگانی بفرستد
    ctx.admin.set_pending(ADMIN, {"action": "broadcast", "only_active": False})
    await ctx.router.dispatch(message(ADMIN, "تلاش غیرمجاز"))
    assert not ctx.broadcast.listing(1), "ادمین بدون دسترسی توانست Broadcast بسازد!"

    tg.clear()
    ctx.admin.set_pending(SUPER_ADMIN, {"action": "broadcast", "only_active": False})
    await ctx.router.dispatch(message(SUPER_ADMIN, "سلام به همه"))
    assert "پیش‌نمایش" in tg.all_text(), "پیش‌نمایش Broadcast نمایش داده نشد"

    tg.clear()
    await ctx.router.dispatch(callback(SUPER_ADMIN, "a:bc:go"))
    await asyncio.sleep(0.6)

    records = ctx.broadcast.listing(1)
    assert records, "رکورد Broadcast ساخته نشد"
    record = records[0]
    assert record["status"] == "done", f"وضعیت: {record['status']}"
    assert record["sent"] >= 3, f"تعداد ارسال کم است: {record}"
    recipients = {p["chat_id"] for m, p in tg.calls if m in ("sendMessage", "copyMessage")}
    assert 500003 not in recipients, "به کاربر مسدود پیام رفت!"


# ── ۱۵. Support ──────────────────────────────────────────────────────────────
@scenario("15. Support (تیکت و پاسخ ادمین)")
async def t15(ctx, tg):
    await setup_admin(ctx)
    await ctx.router.dispatch(message(USER, "/start"))
    await ctx.router.dispatch(callback(USER, "u:support"))
    tg.clear()

    await ctx.router.dispatch(message(USER, "اینترنتم وصل نمی‌شود"))
    ticket = ctx.support.open_ticket_of(USER)
    assert ticket, "تیکت ساخته نشد"
    assert "ثبت شد" in tg.all_text()
    admin_notified = any(p.get("chat_id") == ADMIN for m, p in tg.calls if m == "sendMessage")
    assert admin_notified, "ادمین از تیکت جدید باخبر نشد"

    tg.clear()
    ctx.admin.set_pending(ADMIN, {"action": "ticket_reply", "ticket": ticket["id"]})
    await ctx.router.dispatch(message(ADMIN, "لطفاً آموزش را ببینید"))

    messages = ctx.support.messages_of(ticket["id"])
    assert len(messages) == 2, f"پیام‌ها: {messages}"
    assert messages[-1]["sender"] == "admin"
    assert ctx.support.get(ticket["id"])["status"] == ctx.support.STATUS_ANSWERED
    assert any(p.get("chat_id") == USER for m, p in tg.calls if m == "sendMessage"), \
        "پاسخ به کاربر ارسال نشد"


# ── ۱۶. Restart سرویس ────────────────────────────────────────────────────────
@scenario("16. Restart سرویس (پایداری داده)")
async def t16(ctx, tg):
    tg.default_member_status = "member"
    await ctx.router.dispatch(message(USER, "/start", username="persist"))
    result = await ctx.issuing.issue_free_config(USER)
    assert result.ok
    await ctx.channels.create(SUPER_ADMIN, "کانال پایدار", username="persistchan")
    ctx.store.set_setting("free_quota_total", 9)
    ctx.store.set_text("welcome_user", "متن سفارشی")

    # همان چیزی که main.save_state می‌نویسد
    snapshot = ctx.store.export_state()
    assert "tg_users" in snapshot and "tg_meta" in snapshot

    # شبیه‌سازی Restart: پاک کردن کل حافظه و بارگذاری دوباره
    fresh = bootstrap()
    assert not fresh.store.TG_USERS, "state تازه خالی نیست"
    fresh.store.import_state(snapshot)

    assert fresh.users.get(USER), "کاربر بعد از Restart گم شد"
    assert fresh.users.get(USER)["username"] == "persist"
    assert fresh.store.setting("free_quota_total") == 9, "تنظیمات گم شد"
    assert fresh.store.text("welcome_user") == "متن سفارشی", "متن سفارشی گم شد"
    assert len(fresh.store.TG_CHANNELS) == 1, "کانال گم شد"
    assert len(fresh.store.TG_USER_CONFIGS) == 1, "کانفیگ کاربر گم شد"
    assert fresh.store.schema_version() == ctx.store.schema_version()
    assert fresh.quota.status(USER)["used"] == 1, "مصرف سهمیه بعد از Restart صفر شد"


# ── ۱۷. خطای Telegram API ────────────────────────────────────────────────────
@scenario("17. خطای Telegram API")
async def t17(ctx, tg):
    tg.default_member_status = "member"
    await ctx.router.dispatch(message(USER, "/start"))

    # ارسال پیام‌ها از کار می‌افتد ولی ساخت کانفیگ باید سالم انجام شود
    tg.fail_methods["sendMessage"] = "Forbidden: bot was blocked by the user"
    tg.fail_methods["editMessageText"] = "Forbidden: bot was blocked by the user"

    result = await ctx.issuing.issue_free_config(USER)
    assert result.ok, "خطای ارسال تلگرام باعث شکست ساخت کانفیگ شد"

    delivered = await ctx.user.deliver_config(ctx.tgapi.client, USER, result.user_config)
    assert delivered is False, "ارسال ناموفق به‌درستی تشخیص داده نشد"
    assert result.user_config["delivered"] is False, "وضعیت ارسال قابل تشخیص نیست"

    tg.fail_methods.clear()
    # بررسی عضویت با خطا: کاربر بی‌دلیل بلوکه نمی‌شود ولی خطا گزارش می‌شود
    await ctx.channels.create(SUPER_ADMIN, "کانال بی‌دسترسی", username="noaccess")
    ctx.channels.invalidate(USER)
    tg.unverifiable_chats.add("@noaccess")
    ok, missing, unverifiable = await ctx.channels.check_membership(USER, force=True)
    assert ok is True, "کانال غیرقابل‌بررسی باعث رد کاربر شد"
    assert len(unverifiable) == 1, "کانال غیرقابل‌بررسی گزارش نشد"


# ── ۱۸. خطای Database / سرویس پنل ────────────────────────────────────────────
@scenario("18. خطای سرویس ساخت کانفیگ (سهمیه نباید کم شود)")
async def t18(ctx, tg):
    tg.default_member_status = "member"
    ctx.store.set_setting("free_quota_total", 3)
    await ctx.router.dispatch(message(USER, "/start"))

    ctx.panel.fail_make_link = True
    result = await ctx.issuing.issue_free_config(USER)

    assert not result.ok, "با خطای پنل باز هم موفق اعلام شد"
    assert ctx.quota.status(USER)["used"] == 0, "با شکست ساخت، سهمیه مصرف شد!"
    assert not ctx.configs.user_configs(USER), "رکورد ناقص ساخته شد"
    assert ctx.store.TG_STATS[ctx.store.today_key()].get("config_errors", 0) >= 1, "خطا آمارگیری نشد"

    # بعد از رفع خطا باید سالم کار کند
    ctx.panel.fail_make_link = False
    retry = await ctx.issuing.issue_free_config(USER)
    assert retry.ok, f"پس از رفع خطا هم شکست خورد: {retry.reason}"
    assert ctx.quota.status(USER)["used"] == 1


# ── ۱۹. Callback جعلی / منقضی ────────────────────────────────────────────────
@scenario("19. Callback جعلی یا منقضی")
async def t19(ctx, tg):
    await setup_admin(ctx)
    await ctx.users.touch({"id": USER, "first_name": "هدف"})

    # امضای دستکاری‌شده باید رد شود
    tampered = f"a:usr:{USER}:blockok~deadbeef"
    tg.clear()
    await ctx.router.dispatch(callback(ADMIN, tampered))
    assert ctx.users.get(USER)["is_blocked"] is False, "Callback جعلی اجرا شد!"
    answers = " ".join(str(p.get("text", "")) for m, p in tg.calls if m == "answerCallbackQuery")
    assert "معتبر" in answers or "منقضی" in answers, f"پاسخ رد نشدن: {answers!r}"

    # امضای درست باید کار کند (اثبات اینکه رد شدن بالا بی‌دلیل نبوده)
    valid = ctx.security.sign_callback(f"a:usr:{USER}:blockok")
    await ctx.router.dispatch(callback(ADMIN, valid))
    assert ctx.users.get(USER)["is_blocked"] is True, "Callback معتبر اجرا نشد"

    # Callback ناشناس نباید Exception بدهد
    tg.clear()
    await ctx.router.dispatch(callback(ADMIN, "u:totally:unknown:thing"))
    assert tg.calls, "Callback ناشناس بی‌پاسخ ماند"


# ── ۲۰. عدم دسترسی User عادی به Admin Panel ──────────────────────────────────
@scenario("20. کاربر عادی به پنل ادمین دسترسی ندارد")
async def t20(ctx, tg):
    await ctx.router.dispatch(message(USER, "/start"))
    await ctx.users.touch({"id": USER2, "first_name": "قربانی"})

    forbidden = [
        "a:menu", "a:users", "a:stats", "a:settings", "a:bc",
        f"a:usr:{USER2}", ctx.security.sign_callback(f"a:usr:{USER2}:blockok"),
    ]
    for data in forbidden:
        tg.clear()
        await ctx.router.dispatch(callback(USER, data))
        text = tg.all_text()
        assert "پنل مدیریت" not in text, f"کاربر عادی داشبورد ادمین دید با {data}"
        assert "Audit" not in text
        answers = " ".join(str(p.get("text", "")) for m, p in tg.calls if m == "answerCallbackQuery")
        assert "دسترسی" in answers, f"برای {data} دسترسی رد نشد: {answers!r}"

    assert ctx.users.get(USER2)["is_blocked"] is False, "کاربر عادی توانست کاربر دیگری را مسدود کند!"

    # /admin هم نباید وجود پنل را لو بدهد
    tg.clear()
    await ctx.router.dispatch(message(USER, "/admin"))
    assert "پنل مدیریت" not in tg.all_text(), "دستور /admin پنل را برای کاربر عادی باز کرد"

    # IDOR: کاربر نباید کانفیگ کاربر دیگر را ببیند
    other = await ctx.issuing.grant_config(SUPER_ADMIN, USER2)
    assert other.ok
    tg.clear()
    await ctx.router.dispatch(callback(USER, f"u:cfg:{other.user_config['id']}"))
    answers = " ".join(str(p.get("text", "")) for m, p in tg.calls if m == "answerCallbackQuery")
    assert "دسترس" in answers, f"IDOR جلوگیری نشد: {answers!r}"
    tg.clear()
    await ctx.router.dispatch(callback(USER, f"u:send:{other.user_config['id']}"))
    assert "vless://" not in tg.all_text(), "کاربر کانفیگ دیگری را دریافت کرد!"


# ── ۲۱. هشدار ۹۰٪ و اتمام حجم ────────────────────────────────────────────────
@scenario("21. هشدار مصرف ۹۰٪ و اتمام حجم")
async def t21(ctx, tg):
    from botsys.services import alerts
    await ctx.router.dispatch(message(USER, "/start"))
    res = await ctx.issuing.issue_free_config(USER)
    link = ctx.configs.link_of(res.user_config)
    gb = 1024 ** 3
    link["limit_bytes"] = 10 * gb
    await alerts.scan_once()          # baseline، بدون پیام
    tg.clear()

    link["used_bytes"] = int(9.2 * gb)
    await alerts.scan_once()
    assert "هشدار حجم" in tg.all_text(), "هشدار ۹۰٪ ارسال نشد"
    tg.clear()
    await alerts.scan_once()
    assert not tg.sent(), "هشدار ۹۰٪ تکراری ارسال شد"

    link["used_bytes"] = 10 * gb
    await alerts.scan_once()
    assert "تمام شد" in tg.all_text(), "پیام اتمام حجم ارسال نشد"
    tg.clear()
    await alerts.scan_once()
    assert not tg.sent(), "پیام اتمام تکراری ارسال شد"

    link["used_bytes"] = 0            # Reset -> دوره‌ی بعد دوباره هشدار می‌رسد
    await alerts.scan_once()
    tg.clear()
    link["used_bytes"] = int(9.5 * gb)
    await alerts.scan_once()
    assert "هشدار حجم" in tg.all_text(), "بعد از Reset هشدار دوباره نیامد"


# ── ۲۲. مهلت عضویت کانال جدید ────────────────────────────────────────────────
@scenario("22. مهلت عضویت کانال اجباری جدید")
async def t22(ctx, tg):
    from botsys.services import membership
    tg.default_member_status = "member"
    await ctx.router.dispatch(message(USER, "/start"))
    await ctx.issuing.issue_free_config(USER)
    link = ctx.configs.link_of(ctx.configs.user_configs(USER)[0])
    assert link["active"]

    tg.default_member_status = "left"
    ctx.store.set_setting("channel_grace_hours", 2)
    tg.clear()
    ch = await add_channel(ctx, "تبلیغاتی", "promo")
    await asyncio.sleep(0.2)
    assert "فرصت" in tg.all_text(), "پیام مهلت ارسال نشد"
    await membership.enforce_user(USER)
    assert link["active"], "کانفیگ در مدت مهلت قطع شد!"

    # پایان مهلت -> قطع
    ctx.users.get(USER)["membership_grace"][ch["id"]]["until"] = "2000-01-01T00:00:00+00:00"
    await membership.enforce_user(USER)
    assert not link["active"], "بعد از پایان مهلت قطع نشد"

    # عضو شدن -> وصل
    tg.default_member_status = "member"
    await membership.enforce_user(USER)
    assert link["active"], "بعد از عضویت وصل نشد"


# ── ۲۳. Broadcast با copyMessage ─────────────────────────────────────────────
@scenario("23. Broadcast رسانه و فرمت با copyMessage")
async def t23(ctx, tg):
    await ctx.users.touch({"id": USER, "first_name": "u"})
    ctx.admin.set_pending(SUPER_ADMIN, {"action": "broadcast", "only_active": False})
    upd = message(SUPER_ADMIN, "متن bold")
    upd["message"]["message_id"] = 777
    upd["message"]["entities"] = [{"type": "bold", "offset": 4, "length": 4}]
    await ctx.router.dispatch(upd)
    tg.clear()
    await ctx.router.dispatch(callback(SUPER_ADMIN, "a:bc:go"))
    await asyncio.sleep(0.6)
    copies = [p for m, p in tg.calls if m == "copyMessage"]
    assert any(p["chat_id"] == USER and p["message_id"] == 777 and p["from_chat_id"] == SUPER_ADMIN
               for p in copies), f"copyMessage فرستاده نشد: {copies}"


# ── ۲۴. زیرمجموعه‌گیری ───────────────────────────────────────────────────────
@scenario("24. زیرمجموعه‌گیری و جایزه")
async def t24(ctx, tg):
    from botsys.services import referral
    ctx.store.set_setting("referral_required_count", 2)
    ctx.store.set_setting("referral_reward_volume_gb", 10)
    ctx.store.set_setting("free_cooldown_seconds", 0)
    await ctx.router.dispatch(message(USER, "/start"))
    for friend in (600001, 600002):
        await ctx.router.dispatch(message(friend, f"/start ref_{USER}"))
        assert ctx.users.get(friend)["referred_by"] == str(USER)
        await ctx.issuing.issue_free_config(friend)
    # دوست قدیمی با لینک دعوت حساب نمی‌شود
    await ctx.router.dispatch(message(600001, f"/start ref_{USER2}"))
    assert ctx.users.get(600001)["referred_by"] == str(USER)
    # خود-دعوت
    await ctx.router.dispatch(message(600003, "/start ref_600003"))
    assert not ctx.users.get(600003).get("referred_by")

    assert any("u:ref:claim" in str(p.get("reply_markup")) and p["chat_id"] == USER
               for m, p in tg.calls if m == "sendMessage"), "نوتیف آماده بودن جایزه نیامد"
    st = referral.stats(USER)
    assert st["qualified"] == 2 and st["available"] == 1, st
    res = await referral.claim(USER)
    assert res.ok and res.user_config["source"] == "referral"
    link = ctx.configs.link_of(res.user_config)
    assert link["limit_bytes"] == 10 * 1024 ** 3
    again = await referral.claim(USER)
    assert not again.ok or again.reused, "جایزه دوباره ساخته شد"
    assert ctx.quota.status(USER)["used"] == 0, "جایزه از سهمیه‌ی عمومی کم شد"
    assert len([c for c in ctx.configs.user_configs(USER) if c["source"] == "referral"]) == 1

    await ctx.configs.mark_delivered(res.user_config["id"])
    # جایزه‌ی دوم: با ۲ دعوت موفق دیگر، دوباره قابل دریافت است (نامحدود)
    assert referral.stats(USER)["available"] == 0
    for friend in (600011, 600012):
        await ctx.router.dispatch(message(friend, f"/start ref_{USER}"))
        await ctx.issuing.issue_free_config(friend)
    assert referral.stats(USER)["available"] == 1, referral.stats(USER)
    second = await referral.claim(USER)
    assert second.ok and not second.reused
    assert len([c for c in ctx.configs.user_configs(USER) if c["source"] == "referral"]) == 2


ALL = [t01, t02, t03, t04, t05, t06, t07, t08, t09, t10,
       t11, t12, t13, t14, t15, t16, t17, t18, t19, t20, t21, t22, t23, t24]


async def main():
    for test in ALL:
        await test()

    print("\n" + "=" * 64)
    print("نتیجه تست‌های ربات VodiWalker")
    print("=" * 64)
    passed = 0
    for name, ok, err in _results:
        print(f"{'✅' if ok else '❌'}  {name}")
        if not ok:
            print("      " + err.replace("\n", "\n      ")[:1200])
        passed += ok
    print("=" * 64)
    print(f"{passed}/{len(_results)} سناریو موفق")
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

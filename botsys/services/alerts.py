"""هشدار مصرف حجم به خود کاربر.

* وقتی مصرف به آستانه (پیش‌فرض ۹۰٪) برسد: یک هشدار.
* وقتی حجم تمام شود: یک پیام «حجم تمام شد» با راه‌حل‌ها (کانفیگ رایگان، دعوت دوستان، پشتیبانی).

هر هشدار برای هر کانفیگ فقط یک‌بار فرستاده می‌شود (فلگ روی رکورد کانفیگ). اگر
مصرف Reset شود یا حجم بیشتر شود، فلگ‌ها خودکار برمی‌گردند و دوره‌ی بعد دوباره
هشدار می‌رسد.

سرعت: حلقه سبک است (فقط پیمایش حافظه، بدون هیچ تماس شبکه‌ای مگر ارسال هشدار) و
هر ``INTERVAL_SECONDS`` ثانیه اجرا می‌شود، پس هشدار معمولاً در چند ثانیه می‌رسد.
ارسال‌ها بین چند Worker موازی پخش می‌شود تا صف طولانی هشدارها (مثلاً بعد از
Restart) پشت‌سر هم معطل نماند.
"""

from __future__ import annotations

import asyncio
import logging

from .. import keyboards as k
from .. import store
from ..tgapi import TelegramError, client, h

logger = logging.getLogger("vodiwalker.botsys.alerts")

INTERVAL_SECONDS = 10
MAX_ATTEMPTS = 5
WORKERS = 8


def _panel():
    import main
    return main


def _warn_percent() -> float:
    try:
        value = float(store.setting("usage_warn_percent", 90) or 90)
    except (TypeError, ValueError):
        value = 90.0
    return min(99.0, max(1.0, value))


def evaluate(item: dict, link: dict, warn_percent: float) -> str | None:
    """"exhausted" | "warn" | None. فلگ‌های Reset‌شده را هم همین‌جا اصلاح می‌کند."""
    limit = int(link.get("limit_bytes") or 0)
    if limit <= 0:
        return None
    used = int(link.get("used_bytes") or 0)
    percent = used / limit * 100

    exhausted = used >= limit
    warned = percent >= warn_percent

    # Reset مصرف / افزایش حجم: فلگ‌ها برمی‌گردند تا دوره‌ی بعد دوباره هشدار برسد.
    if not exhausted and item.get("alert_exhausted_sent"):
        item["alert_exhausted_sent"] = False
        item["alert_attempts"] = 0
    if not warned and item.get("alert_warn_sent"):
        item["alert_warn_sent"] = False
        item["alert_attempts"] = 0

    if exhausted and not item.get("alert_exhausted_sent"):
        return "exhausted"
    if warned and not exhausted and not item.get("alert_warn_sent"):
        return "warn"
    return None


def _bytes(value: int) -> str:
    return _panel().fmt_bytes(int(value or 0))


def build_message(kind: str, item: dict, link: dict) -> tuple[str, dict]:
    limit = int(link.get("limit_bytes") or 0)
    used = int(link.get("used_bytes") or 0)
    label = h(link.get("label") or item.get("label") or "کانفیگ")
    ucid = item.get("id")

    if kind == "warn":
        percent = min(99, int(used / limit * 100)) if limit else 0
        text = (
            "⚠️ <b>هشدار حجم کانفیگ</b>\n\n"
            f"📦 {label}\n"
            f"بیش از <b>{percent}٪</b> حجم کانفیگ شما مصرف شده است.\n\n"
            f"📉 مصرف‌شده: {_bytes(used)}\n"
            f"📊 باقی‌مانده: <b>{_bytes(max(0, limit - used))}</b> از {_bytes(limit)}\n\n"
            "قبل از تمام شدن حجم، کانفیگ جدید بگیرید تا اتصال‌تان قطع نشود."
        )
        rows = [[k.enter("📦 مشاهده کانفیگ", f"u:cfg:{ucid}")]]
    else:
        text = (
            "📭 <b>حجم کانفیگ شما تمام شد</b>\n\n"
            f"📦 {label}\n"
            f"📉 مصرف‌شده: {_bytes(used)} از {_bytes(limit)}\n\n"
            "این کانفیگ دیگر متصل نمی‌شود. از گزینه‌های زیر برای گرفتن کانفیگ جدید استفاده کنید."
        )
        rows = [[k.btn("🎁 دریافت کانفیگ رایگان", "u:free:menu", k.SUCCESS)]]
        if store.setting("referral_enabled", True):
            rows.append([k.btn("👥 دعوت دوستان و دریافت کانفیگ", "u:ref", k.SUCCESS)])
        rows.append([k.enter("📦 کانفیگ‌های من", "u:cfgs:0")])
        if store.setting("support_enabled", True):
            rows.append([k.enter("🛟 پشتیبانی", "u:support")])
    return text, k.kb(rows)


async def _deliver(kind: str, item: dict, link: dict) -> bool:
    """True اگر دیگر نیازی به تلاش مجدد نیست (ارسال شد یا برای همیشه ممکن نیست)."""
    tid = int(item["telegram_id"])
    rec = store.TG_USERS.get(str(tid))
    if rec is not None and (rec.get("is_blocked") or rec.get("bot_blocked")):
        return True
    text, markup = build_message(kind, item, link)
    try:
        await client.send_message_strict(tid, text, markup)
        store.bump_stat("usage_alerts_exhausted" if kind == "exhausted" else "usage_alerts_warn")
        return True
    except TelegramError as exc:
        desc = exc.description.lower()
        if exc.error_code == 403 or "blocked" in desc or "deactivated" in desc or "chat not found" in desc:
            if rec is not None:
                rec["bot_blocked"] = True
            return True
        logger.warning("usage alert to %s failed: %s", tid, exc.description)
    except Exception as exc:
        logger.warning("usage alert to %s error: %s", tid, exc)
    item["alert_attempts"] = int(item.get("alert_attempts") or 0) + 1
    return item["alert_attempts"] >= MAX_ATTEMPTS


async def scan_once() -> int:
    """یک دور بررسی. تعداد هشدارهای ارسال‌شده را برمی‌گرداند."""
    if not store.setting("usage_alerts_enabled", True):
        return 0
    panel = _panel()
    warn_percent = _warn_percent()

    # اولین اجرا بعد از آپدیت: وضعیت فعلی همه‌ی کانفیگ‌ها فقط ثبت می‌شود (بدون پیام)
    # تا کاربرانی که از قبل ۹۰٪+ بوده‌اند یا حجمشان تمام شده، یک‌باره سیل پیام نگیرند.
    if not store._meta.get("alerts_baselined"):
        for item in list(store.TG_USER_CONFIGS.values()):
            link = panel.LINKS.get(str(item.get("link_uid")))
            if not link:
                continue
            kind = evaluate(item, link, warn_percent)
            if kind:
                item["alert_warn_sent"] = True
                if kind == "exhausted":
                    item["alert_exhausted_sent"] = True
        store._meta["alerts_baselined"] = True
        try:
            await panel.save_state()
        except Exception:
            pass
        return 0

    jobs: list[tuple[str, dict, dict]] = []
    for index, item in enumerate(list(store.TG_USER_CONFIGS.values())):
        link = panel.LINKS.get(str(item.get("link_uid")))
        if link:
            kind = evaluate(item, link, warn_percent)
            if kind:
                jobs.append((kind, item, link))
        if index % 500 == 499:
            await asyncio.sleep(0)

    if not jobs:
        return 0

    queue: asyncio.Queue = asyncio.Queue()
    for job in jobs:
        queue.put_nowait(job)
    sent = 0

    async def worker():
        nonlocal sent
        while True:
            try:
                kind, item, link = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            done = await _deliver(kind, item, link)
            if done:
                # اتمام حجم، هشدار ۹۰٪ را هم بی‌اثر می‌کند (دو پیام پشت‌سرهم نمی‌رود).
                item["alert_warn_sent"] = True
                if kind == "exhausted":
                    item["alert_exhausted_sent"] = True
                item["alert_attempts"] = 0
                sent += 1

    await asyncio.gather(*(worker() for _ in range(min(WORKERS, len(jobs)))))

    try:
        await panel.save_state()
    except Exception:
        logger.debug("could not persist alert flags", exc_info=True)
    return sent


async def monitor_loop() -> None:
    logger.info("usage alert monitor started")
    while True:
        try:
            await scan_once()
            await asyncio.sleep(INTERVAL_SECONDS)
        except asyncio.CancelledError:
            logger.info("usage alert monitor cancelled")
            raise
        except Exception:
            logger.exception("usage alert loop error")
            await asyncio.sleep(INTERVAL_SECONDS)

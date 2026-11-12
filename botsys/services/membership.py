"""پایش عضویت اجباری کانال‌ها و قطع/وصل خودکار کانفیگ‌ها."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from .. import keyboards as k, security, store
from . import channels, configs, users
from ..tgapi import client, h

logger = logging.getLogger("vodiwalker.botsys.membership")

INTERVAL_SECONDS = 30


def _has_configs(telegram_id: int) -> bool:
    return bool(configs.user_configs(telegram_id))


# ── مهلت عضویت (Grace Period) برای کانال اجباری جدید ─────────────────────────
#: Task های پس‌زمینه (نگه‌داشتن Reference تا Garbage Collect نشوند).
_BG_TASKS: set = set()


def _parse_dt(raw) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt


def _now() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def grace_hours() -> float:
    try:
        return max(0.0, float(store.setting("channel_grace_hours", 2) or 0))
    except (TypeError, ValueError):
        return 0.0


def _grace_entry(rec: dict, channel: dict) -> dict | None:
    return (rec.get("membership_grace") or {}).get(str(channel.get("id")))


def in_grace(rec: dict, channel: dict) -> bool:
    """آیا این کاربر برای این کانال هنوز مهلت دارد؟"""
    entry = _grace_entry(rec, channel)
    if not entry:
        return False
    until = _parse_dt(entry.get("until"))
    return bool(until and _now() < until)


def split_missing(rec: dict, missing: list[dict]) -> tuple[list[dict], list[dict]]:
    """(کانال‌های بلاک‌کننده, کانال‌هایی که کاربر هنوز مهلت دارد)"""
    blocking, graced = [], []
    for channel in missing:
        (graced if in_grace(rec, channel) else blocking).append(channel)
    return blocking, graced


def grace_remaining_text(rec: dict, graced: list[dict]) -> str:
    """مثلاً «1 ساعت و 20 دقیقه» تا نزدیک‌ترین مهلت."""
    soonest = None
    for channel in graced:
        until = _parse_dt((_grace_entry(rec, channel) or {}).get("until"))
        if until and (soonest is None or until < soonest):
            soonest = until
    if soonest is None:
        return ""
    seconds = max(0, int((soonest - _now()).total_seconds()))
    hours, minutes = divmod(seconds // 60, 60)
    if hours and minutes:
        return f"{hours} ساعت و {minutes} دقیقه"
    if hours:
        return f"{hours} ساعت"
    return f"{max(1, minutes)} دقیقه"


def _prune_grace(rec: dict, missing: list[dict]) -> None:
    """مهلت کانال‌هایی که کاربر عضوشان شده (یا حذف/غیرفعال شده‌اند) پاک می‌شود."""
    grace = rec.get("membership_grace")
    if not grace:
        return
    still = {str(c.get("id")) for c in missing}
    for cid in list(grace):
        if cid not in still:
            grace.pop(cid, None)


def _grace_message(rec: dict, graced: list[dict], reminder: bool = False) -> str:
    names = "، ".join(f"«{h(c.get('title') or 'کانال')}»" for c in graced)
    left = grace_remaining_text(rec, graced)
    if reminder:
        return (
            "⏰ <b>مهلت عضویت رو به پایان است</b>\n\n"
            f"فقط <b>{left}</b> دیگر فرصت دارید در {names} عضو شوید، وگرنه کانفیگ‌هایتان "
            "به‌صورت خودکار قطع می‌شود.\n"
            "بعد از عضویت، وصل بودن کانفیگ‌ها خودکار حفظ می‌شود."
        )
    return (
        "📢 <b>کانال اجباری جدید اضافه شد</b>\n\n"
        f"برای ادامه‌ی استفاده از کانفیگ‌هایتان لازم است در {names} عضو شوید.\n"
        f"⏳ <b>{left}</b> فرصت دارید؛ بعد از آن اگر عضو نباشید، کانفیگ‌هایتان قطع می‌شود.\n\n"
        "تا آن زمان کانفیگ‌هایتان همچنان وصل است."
    )


def start_grace_for_channel(channel_id: str) -> int:
    """به همه‌ی کاربرانی که *از قبل* کانفیگ داشتند مهلت می‌دهد و خبرشان می‌کند.

    مهلت *همزمان و بدون await* برای همه ثبت می‌شود تا پایش عضویت در فاصله‌ی
    بررسی‌های تک‌تک، کانفیگ کسی را الکی قطع نکند. بعد در پس‌زمینه کسانی که
    همین الان عضو هستند بی‌صدا از مهلت خارج می‌شوند و فقط بقیه پیام می‌گیرند.
    """
    hours = grace_hours()
    channel = channels.get(channel_id)
    if hours <= 0 or not channel or not channel.get("is_active"):
        return 0
    if not store.setting("require_channels", True):
        return 0

    until = (_now() + timedelta(hours=hours)).isoformat()
    channel["grace_until"] = until
    targets: list[int] = []
    for rec in list(store.TG_USERS.values()):
        tid = rec.get("telegram_id")
        if not tid or rec.get("is_blocked") or not _has_configs(int(tid)):
            continue
        rec.setdefault("membership_grace", {})[str(channel_id)] = {"until": until, "reminded": False}
        targets.append(int(tid))

    task = asyncio.create_task(_announce_grace(str(channel_id), targets))
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)
    return len(targets)


async def _announce_grace(channel_id: str, targets: list[int]) -> None:
    channel = channels.get(channel_id)
    if not channel:
        return
    notified = 0
    for tid in targets:
        try:
            rec = users.get(tid)
            if not rec:
                continue
            is_member = await channels.is_member(channel, tid)
            if is_member is not False:
                # عضو است (یا قابل بررسی نیست): مهلت لازم نیست و پیامی هم نمی‌خواهد.
                (rec.get("membership_grace") or {}).pop(str(channel_id), None)
                continue
            text = _grace_message(rec, [channel])
            result = await client.send_message(tid, text, _join_keyboard([channel]))
            if result:
                notified += 1
            elif (rec.get("membership_grace") or {}).get(str(channel_id)) is not None:
                # پیام نرسید (بلاک ربات و...): مهلت بماند، قطع پس از پایان مهلت انجام می‌شود.
                pass
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("grace announce failed for %s", tid, exc_info=True)
    logger.info("channel %s grace announced to %s users", channel_id, notified)
    try:
        from main import save_state
        await save_state()
    except Exception:
        logger.debug("could not persist grace state", exc_info=True)


async def grace_tick() -> None:
    """هشدار پایان مهلت + قطع بلافاصله بعد از پایان مهلت (نه تا ۳۰ ثانیه/چرخه‌ی کامل بعد)."""
    now = _now()
    for rec in list(store.TG_USERS.values()):
        grace = rec.get("membership_grace")
        if not grace:
            continue
        tid = rec.get("telegram_id")
        if not tid:
            continue
        due = False
        remind = False
        for entry in grace.values():
            until = _parse_dt(entry.get("until"))
            if until is None:
                due = True
                continue
            total_left = (until - now).total_seconds()
            if total_left <= 0:
                due = True
            elif not entry.get("reminded") and total_left <= _reminder_lead_seconds():
                remind = True
        if not (due or remind):
            continue
        try:
            await enforce_user(int(tid), notify=True)
            if remind:
                await _send_reminder(rec)
            # مهلت‌های تمام‌شده بعد از اعمال قطع حذف می‌شوند تا چرخه تکرار نشود.
            for cid, entry in list(grace.items()):
                until = _parse_dt(entry.get("until"))
                if until is None or until <= now:
                    grace.pop(cid, None)
        except Exception:
            logger.exception("grace tick failed for %s", tid)


def _reminder_lead_seconds() -> float:
    """یادآوری ۳۰ دقیقه قبل از پایان مهلت (یا یک‌چهارم مهلت اگر مهلت کوتاه باشد)."""
    return min(1800.0, grace_hours() * 3600 / 4)


async def _send_reminder(rec: dict) -> None:
    grace = rec.get("membership_grace") or {}
    pending = [c for c in channels.active_channels()
               if str(c.get("id")) in grace and not grace[str(c.get("id"))].get("reminded")
               and in_grace(rec, c)]
    if not pending:
        return
    # enforce_user بالا مهلت کانال‌هایی را که عضوشان شده پاک کرده؛ پس هرچه مانده هنوز عضو نیست.
    await client.send_message(int(rec["telegram_id"]), _grace_message(rec, pending, reminder=True),
                              _join_keyboard(pending))
    for c in pending:
        grace[str(c.get("id"))]["reminded"] = True


async def _set_configs_membership_state(telegram_id: int, blocked: bool) -> int:
    """فقط کانفیگ‌هایی را که توسط همین سیستم قطع شده‌اند دوباره وصل می‌کند."""
    changed = 0
    for item in configs.user_configs(telegram_id):
        link = configs.link_of(item)
        if not link:
            continue
        if blocked:
            if bool(link.get("active")):
                await configs.set_active(0, item["id"], False)
                item["auto_disabled_by_membership"] = True
                changed += 1
            elif item.get("auto_disabled_by_membership"):
                # قبلاً توسط ما قطع شده و همچنان قطع است.
                continue
        else:
            if item.get("auto_disabled_by_membership"):
                if not link.get("active"):
                    await configs.set_active(0, item["id"], True)
                item["auto_disabled_by_membership"] = False
                changed += 1
    return changed


def _join_keyboard(missing: list[dict]) -> dict:
    rows = []
    for channel in missing[:10]:
        url = channels.join_url(channel)
        if url:
            rows.append([k.url_btn(f"📢 عضویت در {channel.get('title') or 'کانال'}"[:40], url, k.PRIMARY)])
    rows.append([k.btn("🔄 بررسی عضویت", "u:membership:check", k.SUCCESS)])
    rows.append([k.back("u:menu")])
    return k.kb(rows)


async def enforce_user(telegram_id: int, notify: bool = True) -> dict:
    """عضویت کاربر را بررسی و در صورت تغییر وضعیت، کانفیگ‌ها را قطع/وصل می‌کند."""
    if not store.setting("require_channels", True):
        return {"changed": False, "missing": [], "unverifiable": []}

    rec = users.get(telegram_id)
    if not rec or not _has_configs(telegram_id):
        return {"changed": False, "missing": [], "unverifiable": []}

    # Join/Leave update و fallback monitor ممکن است هم‌زمان برسند.
    async with store.user_lock(telegram_id):
        was_blocked = bool(rec.get("membership_blocked"))
        ok, missing, unverifiable = await channels.check_membership(telegram_id, force=True)

        # «نامشخص» نباید وضعیت قبلی را دست‌کاری کند.
        if unverifiable:
            return {"changed": False, "missing": missing, "unverifiable": unverifiable}

        # مهلت کانال‌هایی که کاربر عضو شده پاک می‌شود؛ کانال‌هایی که هنوز در مهلتند
        # (کانال جدید برای کاربران قدیمی) باعث قطع کانفیگ نمی‌شوند.
        _prune_grace(rec, missing)
        blocking, graced = split_missing(rec, missing)

        changed = False
        if blocking:
            await _set_configs_membership_state(telegram_id, True)
            changed = not was_blocked
            rec["membership_blocked"] = True

            if notify and changed:
                text = (
                    "⛔️ <b>کانفیگ‌های شما قطع شدند</b>\n\n"
                    "به دلیل خروج از کانال/کانال‌های اجباری، کانفیگ‌های شما موقتاً غیرفعال شدند.\n"
                    "برای وصل شدن دوباره، در کانال‌های زیر عضو شوید و سپس «بررسی عضویت» را بزنید."
                )
                kb = _join_keyboard(blocking + graced)
                old_mid = rec.get("membership_message_id")
                result = None
                if old_mid:
                    result = await client.edit_message(telegram_id, int(old_mid), text, kb)
                if not old_mid or not result:
                    result = await client.send_message(telegram_id, text, kb)
                    if isinstance(result, dict):
                        rec["membership_message_id"] = result.get("message_id")

        else:
            # فقط کانفیگ‌هایی را که همین سیستم قطع کرده دوباره فعال کن.
            await _set_configs_membership_state(telegram_id, False)
            changed = was_blocked
            rec["membership_blocked"] = False

            if notify and was_blocked:
                text = (
                    "✅ <b>عضویت شما تأیید شد</b>\n\n"
                    "کانفیگ‌هایی که به‌دلیل عضویت قطع شده بودند دوباره فعال شدند."
                )
                kb = k.kb([[k.enter("📦 کانفیگ‌های من", "u:cfgs:0")], [k.back("u:menu")]])
                old_mid = rec.get("membership_message_id")
                result = None
                if old_mid:
                    result = await client.edit_message(telegram_id, int(old_mid), text, kb)
                if not old_mid or not result:
                    result = await client.send_message(telegram_id, text, kb)
                    if isinstance(result, dict):
                        rec["membership_message_id"] = result.get("message_id")

        if changed:
            try:
                from main import save_state
                await save_state()
            except Exception:
                logger.warning("could not persist membership state", exc_info=True)

        return {"changed": changed, "missing": blocking, "graced": graced, "unverifiable": unverifiable}


async def check_callback(telegram_id: int, chat_id: int, message_id: int | None,
                         cb_id: str | None = None, render: bool = True) -> dict:
    """بررسی دستی عضویت؛ بدون صدور کانفیگ جدید و با API تازه.

    render=False: فقط وضعیت را تازه می‌کند و هیچ پیامی نمی‌نویسد (مثلاً مسیر
    «کانفیگ رایگان» که خودش بعد از عضویت صفحه‌ی درست را نشان می‌دهد).
    """
    if not store.setting("require_channels", True):
        return {"ok": True, "missing": []}

    rec = users.get(telegram_id)
    if not rec:
        return {"ok": False, "missing": []}

    async with store.user_lock(telegram_id):
        channels.invalidate(telegram_id)
        ok, missing, unverifiable = await channels.check_membership(telegram_id, force=True)

        _prune_grace(rec, missing)
        blocking, graced = split_missing(rec, missing)

        if blocking:
            rec["membership_blocked"] = True
            await _set_configs_membership_state(telegram_id, True)
            text = (
                "⛔️ <b>هنوز عضویت کامل نیست</b>\n\n"
                "لطفاً در همه کانال‌های زیر عضو شوید و دوباره بررسی کنید."
            )
            if render:
                if message_id:
                    await client.edit_message(chat_id, message_id, text, _join_keyboard(blocking + graced))
                else:
                    await client.send_message(chat_id, text, _join_keyboard(blocking + graced))
            try:
                from main import save_state
                await save_state()
            except Exception:
                logger.warning("could not persist membership state", exc_info=True)
            return {"ok": False, "missing": blocking, "unverifiable": unverifiable}

        if unverifiable:
            await client.answer_callback(
                cb_id,
                "⚠️ عضویت بعضی کانال‌ها قابل بررسی نیست. مطمئن شوید ربات در آن کانال‌ها Admin است.",
                alert=True,
            )
            return {"ok": False, "missing": [], "unverifiable": unverifiable}

        was_blocked = bool(rec.get("membership_blocked"))
        rec["membership_blocked"] = False
        await _set_configs_membership_state(telegram_id, False)

        if graced:
            # هنوز عضو کانال جدید نشده، ولی مهلت دارد: کانفیگ وصل می‌ماند.
            text = (
                "⏳ <b>هنوز عضو کانال جدید نشده‌اید</b>\n\n"
                f"<b>{grace_remaining_text(rec, graced)}</b> فرصت دارید عضو شوید؛ "
                "تا آن زمان کانفیگ‌هایتان وصل می‌ماند."
            )
            if render:
                if message_id:
                    await client.edit_message(chat_id, message_id, text, _join_keyboard(graced))
                else:
                    await client.send_message(chat_id, text, _join_keyboard(graced))
            try:
                from main import save_state
                await save_state()
            except Exception:
                logger.warning("could not persist membership state", exc_info=True)
            return {"ok": True, "missing": [], "graced": graced}

        if was_blocked:
            try:
                from main import save_state
                await save_state()
            except Exception:
                logger.warning("could not persist membership state", exc_info=True)

        if not render:
            return {"ok": True, "missing": []}

        text = "✅ <b>عضویت تأیید شد</b>\n\nکانفیگ‌های قطع‌شده دوباره فعال شدند."
        kb = k.kb([
            [k.enter("📦 کانفیگ‌های من", "u:cfgs:0")],
            [k.back("u:menu")],
        ])
        if message_id:
            await client.edit_message(chat_id, message_id, text, kb)
        else:
            await client.send_message(chat_id, text, kb)
        return {"ok": True, "missing": []}


async def monitor_loop() -> None:
    """Fallback برای Webhook/Polling: هر چند ثانیه اعضای دارای کانفیگ را چک می‌کند."""
    logger.info("membership monitor started")
    while True:
        try:
            if store.setting("require_channels", True):
                # یک پیمایش واحد به‌جای یک پیمایش کامل برای هر کاربر (O(N) به‌جای O(N×M)).
                import main as _panel
                owners = {
                    str(c.get("telegram_id")) for c in list(store.TG_USER_CONFIGS.values())
                    if str(c.get("link_uid")) in _panel.LINKS
                }
                targets = [
                    int(r["telegram_id"]) for r in list(store.TG_USERS.values())
                    if r.get("telegram_id") and str(r["telegram_id"]) in owners
                    and not r.get("is_blocked")
                ]
                for telegram_id in targets:
                    try:
                        await enforce_user(telegram_id, notify=True)
                    except Exception:
                        logger.exception("membership monitor failed for user %s", telegram_id)
                    await asyncio.sleep(0.05)
            await asyncio.sleep(INTERVAL_SECONDS)
        except asyncio.CancelledError:
            logger.info("membership monitor cancelled")
            raise
        except Exception:
            logger.exception("membership monitor loop error")
            await asyncio.sleep(INTERVAL_SECONDS)


GRACE_INTERVAL_SECONDS = 20


async def grace_loop() -> None:
    """حلقه‌ی سبک و جدا از پایش کامل: پایان مهلت‌ها را سریع و دقیق اعمال می‌کند."""
    logger.info("membership grace loop started")
    while True:
        try:
            if store.setting("require_channels", True):
                await grace_tick()
            await asyncio.sleep(GRACE_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            logger.info("membership grace loop cancelled")
            raise
        except Exception:
            logger.exception("membership grace loop error")
            await asyncio.sleep(GRACE_INTERVAL_SECONDS)

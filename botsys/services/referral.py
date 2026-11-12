"""زیرمجموعه‌گیری: دعوت N دوست = یک کانفیگ جایزه (جدا از سهمیه‌ی عمومی).

جریان:
  1) هر کاربر لینک اختصاصی دارد:  t.me/<bot>?start=ref_<telegram_id>
  2) کاربر *جدید* با آن لینک /start بزند -> ``register`` (referred_by ثبت می‌شود).
  3) دعوت وقتی «موفق» حساب می‌شود که دوست اولین کانفیگ‌اش را گرفته باشد
     (ضد حساب فیک خالی؛ با ``referral_require_config`` قابل خاموش شدن است).
     چون دریافت کانفیگ مستلزم عضویت در کانال‌های اجباری است، دعوت‌ها واقعی‌ترند.
  4) به N دعوت موفق که رسید، دکمه‌ی «دریافت جایزه» فعال می‌شود و کانفیگ جایزه
     (حجم/مدت/سرعت از تنظیمات ادمین) ساخته می‌شود. تحویل Idempotent است.

همه‌ی مقادیر از تنظیمات ربات خوانده می‌شود، نه Hard-code.
"""

from __future__ import annotations

import logging
from urllib.parse import quote

from .. import keyboards as k
from .. import store
from ..tgapi import client, h
from . import configs, users

logger = logging.getLogger("vodiwalker.botsys.referral")


def enabled() -> bool:
    return bool(store.setting("referral_enabled", True))


def required_count() -> int:
    try:
        return max(1, int(store.setting("referral_required_count", 5) or 5))
    except (TypeError, ValueError):
        return 5


def max_rewards() -> int:
    try:
        return max(0, int(store.setting("referral_max_rewards", 1) or 0))
    except (TypeError, ValueError):
        return 1


def reward_spec() -> dict:
    return {
        "volume_gb": float(store.setting("referral_reward_volume_gb", 10) or 0),
        "speed_mbps": float(store.setting("referral_reward_speed_mbps", 0) or 0),
        "duration_days": int(store.setting("referral_reward_duration_days", 30) or 0),
        "ip_limit": int(store.setting("referral_reward_ip_limit", 1) or 0),
        "protocol": store.setting("free_protocol", ""),
        "port": store.setting("free_port", 0),
    }


def bot_username() -> str:
    try:
        from .. import runner
        return str((runner._state.get("me") or {}).get("username") or "")
    except Exception:
        return ""


def link_for(telegram_id: int) -> str:
    name = bot_username()
    return f"https://t.me/{name}?start=ref_{telegram_id}" if name else ""


def share_url(telegram_id: int) -> str:
    link = link_for(telegram_id)
    if not link:
        return ""
    text = "با این ربات کانفیگ رایگان بگیر 🎁"
    return f"https://t.me/share/url?url={quote(link, safe='')}&text={quote(text)}"


def stats(telegram_id: int) -> dict:
    rec = users.get(telegram_id) or {}
    need = required_count()
    qualified = int(rec.get("referral_qualified_count") or 0)
    claimed = int(rec.get("referral_rewards_claimed") or 0)
    earned = qualified // need
    cap = max_rewards()
    if cap:
        earned = min(earned, cap)
    available = max(0, earned - claimed)
    maxed = bool(cap and claimed >= cap)
    into = qualified % need if not maxed else need
    return {
        "invited": int(rec.get("referral_invited") or 0),
        "qualified": qualified,
        "need": need,
        "claimed": claimed,
        "available": available,
        "maxed": maxed,
        "progress": into if not available else need,
    }


async def register(new_rec: dict, referrer_raw: str) -> bool:
    """ثبت دعوت برای کاربر *تازه‌وارد*. True اگر ثبت شد."""
    if not enabled() or new_rec.get("referred_by"):
        return False
    try:
        referrer_id = int(str(referrer_raw).strip())
    except ValueError:
        return False
    me = int(new_rec["telegram_id"])
    referrer = users.get(referrer_id)
    if referrer_id == me or not referrer or referrer.get("is_blocked"):
        return False
    new_rec["referred_by"] = str(referrer_id)
    new_rec["referral_qualified"] = False
    referrer["referral_invited"] = int(referrer.get("referral_invited") or 0) + 1
    store.bump_stat("referrals_invited")
    if not store.setting("referral_require_config", True):
        await _qualify(new_rec)
    return True


async def on_config_received(telegram_id: int) -> None:
    """بعد از اولین کانفیگ موفق کاربر صدا زده می‌شود."""
    rec = users.get(telegram_id)
    if not rec or not rec.get("referred_by") or rec.get("referral_qualified"):
        return
    if enabled() and store.setting("referral_require_config", True):
        await _qualify(rec)


async def _qualify(invited: dict) -> None:
    if invited.get("referral_qualified"):
        return
    invited["referral_qualified"] = True
    referrer = users.get(int(invited.get("referred_by") or 0))
    if not referrer:
        return
    referrer["referral_qualified_count"] = int(referrer.get("referral_qualified_count") or 0) + 1
    store.bump_stat("referrals_qualified")
    st = stats(int(referrer["telegram_id"]))
    if st["available"]:
        text = (
            "🎉 <b>تبریک! به هدف دعوت رسیدید</b>\n\n"
            f"{st['qualified']} دوست شما با موفقیت وارد ربات شدند.\n"
            "جایزه‌تان آماده است؛ دکمه‌ی زیر را بزنید."
        )
        markup = k.kb([[k.btn("🎁 دریافت کانفیگ جایزه", "u:ref:claim", k.SUCCESS)]])
    elif st["maxed"]:
        return
    else:
        text = (
            "👥 <b>یک دوست جدید از طرف شما وارد شد</b>\n\n"
            f"پیشرفت: <b>{st['progress']}</b> از {st['need']}"
        )
        markup = k.kb([[k.enter("👥 دعوت دوستان", "u:ref")]])
    await client.send_message(int(referrer["telegram_id"]), text, markup)


async def claim(telegram_id: int):
    """ساخت کانفیگ جایزه. خروجی از نوع issuing.IssueResult."""
    from .issuing import IssueResult
    if not enabled():
        return IssueResult(False, "دعوت دوستان فعلاً غیرفعال است.")
    guard = f"ref:{telegram_id}"
    if not store.claim(guard, ttl=60):
        return IssueResult(False, "درخواست قبلی در حال پردازش است.", busy=True)
    done = False
    try:
        async with store.user_lock(telegram_id):
            # ساخته شده ولی تحویل نشده -> همان را دوباره تحویل بده.
            stale = configs.pending_delivery(telegram_id, source="referral")
            if stale is not None:
                done = True
                return IssueResult(True, user_config=stale, reused=True)
            st = stats(telegram_id)
            if st["available"] <= 0:
                if st["maxed"]:
                    return IssueResult(False, "جایزه‌ی دعوت را قبلاً دریافت کرده‌اید.")
                return IssueResult(False, f"هنوز به {st['need']} دعوت موفق نرسیده‌اید.")
            try:
                item = await configs.create_for_user(telegram_id, reward_spec(), source="referral",
                                                     label=None)
            except configs.ConfigCreationError as exc:
                logger.error("referral reward failed for %s: %s", telegram_id, exc)
                return IssueResult(False, "ساخت کانفیگ ناموفق بود. کمی بعد دوباره تلاش کنید.")
            rec = users.get(telegram_id)
            rec["referral_rewards_claimed"] = int(rec.get("referral_rewards_claimed") or 0) + 1
            store.bump_stat("referral_rewards")
            try:
                from main import save_state
                await save_state()
            except Exception:
                logger.warning("save_state after referral claim failed", exc_info=True)
            done = True
            return IssueResult(True, user_config=item)
    finally:
        store.release(guard)


def screen(telegram_id: int) -> tuple[str, dict]:
    st = stats(telegram_id)
    spec = reward_spec()
    link = link_for(telegram_id)
    days = spec["duration_days"]
    bar_w = 10
    filled = round(min(st["progress"], st["need"]) / st["need"] * bar_w)
    bar = "█" * filled + "░" * (bar_w - filled)
    lines = [
        "👥 <b>دعوت دوستان</b>",
        "",
        f"با دعوت <b>{st['need']}</b> دوست به ربات، یک کانفیگ "
        f"<b>{spec['volume_gb']:g} گیگ</b>"
        f"{f' / {days} روزه' if days else ''} هدیه بگیرید (جدا از سهمیه‌ی عمومی).",
        "",
        f"{bar} {st['progress']}/{st['need']}",
        f"✅ دعوت موفق: <b>{st['qualified']}</b> · 👤 ورودی: {st['invited']}",
    ]
    if store.setting("referral_require_config", True):
        lines.append("<i>دعوت وقتی حساب می‌شود که دوستتان اولین کانفیگش را بگیرد.</i>")
    if st["claimed"]:
        lines.append(f"🎁 جایزه‌های دریافت‌شده: {st['claimed']}")
    lines.append("")
    if link:
        lines += ["🔗 لینک اختصاصی شما:", f"<code>{h(link)}</code>"]
    else:
        lines.append("⚠️ لینک دعوت فعلاً در دسترس نیست.")
    rows = []
    if st["available"]:
        rows.append([k.btn("🎁 دریافت کانفیگ جایزه", "u:ref:claim", k.SUCCESS)])
    if link:
        rows.append([k.copy_btn("📋 کپی لینک دعوت", link, k.PRIMARY)])
        rows.append([k.url_btn("📤 اشتراک‌گذاری", share_url(telegram_id), k.PRIMARY)])
    rows.append([k.back("u:menu")])
    return "\n".join(lines), k.kb(rows)

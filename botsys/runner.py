"""چرخه‌ی حیات ربات: Long Polling.
این نسخه عمداً وب‌سرور/پنل HTTP ندارد و روی Railway به‌صورت یک Worker ربات اجرا می‌شود.
"""

from __future__ import annotations

import asyncio
import logging

from . import settings as cfg
from . import store
from .handlers import router
from .services import backups, broadcast, membership
from .tgapi import client

logger = logging.getLogger("vodiwalker.botsys.runner")

_state: dict = {
    "running": False,
    "mode": None,
    "poll_task": None,
    "membership_task": None,
    "me": None,
    "last_error": "",
}


def is_running() -> bool:
    return bool(_state["running"])


def status() -> dict:
    return {
        "running": is_running(),
        "mode": _state["mode"],
        "username": (_state.get("me") or {}).get("username"),
        "configured": client.configured,
        "last_error": _state["last_error"],
        "schema_version": store.schema_version(),
    }


def resolve_token() -> str:
    """توکن فقط از Environment خوانده می‌شود و هرگز داخل کد نیست."""
    token = cfg.env(cfg.BOT_TOKEN_ENV)
    if token:
        return token
    return ""


def _pick_mode() -> str:
    return "polling"



# ── start / stop ─────────────────────────────────────────────────────────────
async def start() -> dict:
    """ربات را راه می‌اندازد؛ بدون Token سرویس متوقف می‌ماند."""
    if _state["running"]:
        return status()

    token = resolve_token()
    if not token:
        _state["last_error"] = "TELEGRAM_BOT_TOKEN تنظیم نشده است"
        logger.info("Telegram bot disabled: no token configured")
        return status()

    client.set_token(token)
    await client.start()

    try:
        me = await client.get_me()
        _state["me"] = me or {}
        logger.info("Telegram bot authorized as @%s", (me or {}).get("username"))
    except Exception as exc:
        _state["last_error"] = f"getMe failed: {exc}"
        logger.error("Telegram bot token seems invalid: %s", exc)
        await client.close()
        return status()

    mode = "polling"
    _state["mode"] = mode
    _state["last_error"] = ""
    # Bot-only Railway service intentionally uses long polling. This removes the
    # need for a web server/health route and avoids webhook/port coupling.
    await client.delete_webhook(drop_pending=False)
    _state["poll_task"] = asyncio.create_task(_poll_loop())

    # این پایش علاوه بر chat_member update یک fallback دوره‌ای است؛ در نتیجه
    # اگر Telegram Update را از دست بدهد یا کاربر قبل از فعال شدن webhook خارج شده
    # باشد، کانفیگ نهایتاً در یک بازه‌ی کوتاه قطع می‌شود.
    _state["membership_task"] = asyncio.create_task(membership.monitor_loop())

    backups.start_scheduler(client)
    _state["running"] = True
    logger.info("Telegram bot started in %s mode", mode)
    return status()


async def stop() -> dict:
    """توقف تمیز: Task ها لغو و اتصال‌ها بسته می‌شوند."""
    _state["running"] = False

    for task_key in ("poll_task", "membership_task"):
        task = _state.get(task_key)
        if task:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
            _state[task_key] = None

    await backups.stop_scheduler()
    await broadcast.shutdown()
    await client.close()
    logger.info("Telegram bot stopped")
    return status()


async def restart() -> dict:
    await stop()
    return await start()


# ── Long Polling ─────────────────────────────────────────────────────────────
async def _poll_loop() -> None:
    offset = 0
    backoff = 1.0
    logger.info("long polling loop started")
    while True:
        try:
            updates = await client.get_updates(offset=offset, timeout=30)
            if updates is None:
                await asyncio.sleep(min(backoff, 30))
                backoff = min(backoff * 2, 30)
                continue
            backoff = 1.0
            for update in updates:
                offset = int(update.get("update_id", 0)) + 1
                # هر Update مستقل پردازش می‌شود تا یک خطا بقیه را متوقف نکند.
                await router.dispatch(update)
        except asyncio.CancelledError:
            logger.info("long polling loop cancelled")
            raise
        except Exception:
            logger.exception("polling loop error; retrying")
            await asyncio.sleep(min(backoff, 30))
            backoff = min(backoff * 2, 30)



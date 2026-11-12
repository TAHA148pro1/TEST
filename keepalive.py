# ============================================================
# VodiWalker — Keep-Alive / Ping
# هر چند دقیقه به /ping خودِ سرویس درخواست می‌زند:
#   • یک بار از مسیر آدرس عمومی (عبور از Edge شیپر → ترافیک واقعی)
#   • یک بار لوکال (127.0.0.1)
# خاموش کردن: KEEPALIVE_ENABLED=0   |  فاصله: KEEPALIVE_INTERVAL (ثانیه، حداقل 60)
# آدرس دستی: KEEPALIVE_URL=https://my-app.shiprr.dev
# ============================================================

import asyncio
import os
import time

import httpx

ENABLED = os.environ.get("KEEPALIVE_ENABLED", "1").strip() not in ("0", "false", "False", "no")
INTERVAL = max(60, int(os.environ.get("KEEPALIVE_INTERVAL", "240") or 240))

STATS = {"ok": 0, "fail": 0, "last_ok": 0.0, "last_error": "", "last_target": ""}


def _targets(get_public_base, port):
    out = []
    manual = os.environ.get("KEEPALIVE_URL", "").strip().rstrip("/")
    base = manual
    if not base:
        try:
            base = (get_public_base() or "").rstrip("/")
        except Exception:
            base = ""
    if not base:
        env = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
        if env:
            base = env if env.startswith("http") else "https://" + env
    if base:
        out.append(base + "/ping")
    out.append(f"http://127.0.0.1:{port}/ping")
    return out


async def keepalive_loop(get_public_base, port, logger):
    if not ENABLED:
        logger.info("Keep-alive disabled.")
        return
    await asyncio.sleep(25)  # بعد از بالا آمدن کامل
    async with httpx.AsyncClient(timeout=httpx.Timeout(12.0), follow_redirects=True) as client:
        while True:
            for url in _targets(get_public_base, port):
                try:
                    r = await client.get(url, headers={"User-Agent": "VodiWalker-KeepAlive/1.0"})
                    if r.status_code < 500:
                        STATS["ok"] += 1
                        STATS["last_ok"] = time.time()
                        STATS["last_target"] = url
                    else:
                        STATS["fail"] += 1
                        STATS["last_error"] = f"{url} -> HTTP {r.status_code}"
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    STATS["fail"] += 1
                    STATS["last_error"] = f"{url} -> {type(exc).__name__}"
                    logger.debug("keepalive failed: %s", STATS["last_error"])
            await asyncio.sleep(INTERVAL)

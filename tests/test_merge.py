"""تست‌های ادغام: پنل جدید VodiWalker + ربات Free Config (botsys).

بررسی می‌کند که به‌روزرسانی پنل هیچ بخشی از ربات را خراب نکرده باشد.
اجرا:  python3 tests/test_merge.py
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests" / "stubs"))
sys.path.insert(0, str(ROOT))

DATA_DIR = tempfile.mkdtemp()
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = DATA_DIR
os.environ["ADMIN_USERNAME"] = "VodiAdmin"
os.environ["ADMIN_PASSWORD"] = "merge-pass"
os.environ["TELEGRAM_SUPER_ADMIN_IDS"] = "900001"
os.environ["TELEGRAM_BOT_TOKEN"] = "123456:MERGE-TOKEN"
os.environ["TELEGRAM_UPDATE_MODE"] = "polling"
os.environ.pop("RAILWAY_PUBLIC_DOMAIN", None)

SUPER = 900001
ADMIN = 900002
USER = 700010
TOKEN = "123456:MERGE-TOKEN"

results: list[tuple[str, bool, str]] = []


async def acheck(name, coro_fn):
    try:
        await coro_fn()
        results.append((name, True, ""))
    except AssertionError as exc:
        results.append((name, False, str(exc) or "assertion failed"))
    except Exception:
        results.append((name, False, traceback.format_exc(limit=4)))


def init_data(user_id: int, token: str = TOKEN) -> str:
    pairs = {"auth_date": str(int(time.time())), "user": json.dumps({"id": user_id}), "query_id": "q"}
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)


async def main() -> int:
    import main as panel
    from fastapi import HTTPException, Request
    from tests.harness import FakeTelegram, callback, message
    from botsys import legacy, security, store
    from botsys.handlers import router
    from botsys.tgapi import client
    import telegram_bot

    tg = FakeTelegram().install()
    client.set_token(TOKEN)
    await panel.load_state()
    store.run_migrations()

    # ── ۱. همه ماژول‌های پنل جدید بالا آمده‌اند و روت تکراری نداریم ──
    async def modules_and_routes():
        assert panel._BOTSYS_READY, "botsys بارگذاری نشد"
        seen, dup = set(), []
        for r in panel.app.routes:
            for m in r.methods:
                key = (m, r.path)
                if key in seen:
                    dup.append(key)
                seen.add(key)
        assert not dup, f"روت تکراری: {dup}"
        paths = {r.path for r in panel.app.routes}
        for p in ("/miniapp", "/app", "/api/tma/{action}", "/api/bot/status", "/api/bot/texts", "/sub/{uuid}", "/info/{uid}"):
            assert p in paths, f"روت گم شد: {p}"
        assert any("/telegram/webhook" in p for p in paths)
    await acheck("ماژول‌ها و روت‌ها بدون تداخل", modules_and_routes)

    # ── ۲. ماژول قدیمی بدون Polling متصل می‌شود ──
    async def legacy_attach():
        assert legacy.attach(), "attach ناموفق"
        assert legacy.is_attached()
        assert telegram_bot._poll_task is None, "Polling قدیمی نباید اجرا شود (409 Conflict)"
        assert SUPER in telegram_bot.ADMIN_IDS, "هشدارها به Super Admin نمی‌رسد"
        for cb in ("quick", "qc:10:30", "edit:x", "ed:name:x", "online", "top", "expiring",
                   "server", "backup", "alerts:toggle", "help", "menu", "newcfg", "list:0", "w:proto:vless-ws"):
            assert legacy.owns_callback(cb), f"Callback جدید پنل مسیریابی نمی‌شود: {cb}"
        for cb in ("u:free", "u:menu", "a:users", "a:settings"):
            assert not legacy.owns_callback(cb), f"تداخل با botsys: {cb}"
    await acheck("ابزارهای پیشرفته‌ی پنل جدید به ربات وصل‌اند", legacy_attach)

    # ── ۳. ادمین عادی/کاربر عادی به ابزارها و بکاپ خام دسترسی ندارند ──
    async def legacy_permissions():
        store.TG_USERS[str(ADMIN)] = {**store.TG_USERS.get(str(ADMIN), {}), "telegram_id": ADMIN, "role": "admin"}
        tg.clear()
        await router.dispatch(callback(USER, "menu"))
        assert not any(m == "editMessageText" and "Control" in str(p.get("text")) for m, p in tg.calls)
        tg.clear()
        await router.dispatch(callback(ADMIN, "backup"))
        assert not tg.sent("sendDocument"), "ادمین عادی بکاپ خام گرفت!"
        answers = [p for m, p in tg.calls if m == "answerCallbackQuery"]
        assert answers and "Super Admin" in str(answers[0].get("text")), answers
    await acheck("بکاپ خام فقط برای Super Admin", legacy_permissions)

    # ── ۴. Super Admin منوی جدید پنل را از داخل ربات می‌بیند ──
    async def legacy_menu():
        tg.clear()
        await router.dispatch(callback(SUPER, "menu"))
        texts = [b.get("callback_data") for b in tg.buttons()]
        for cb in ("quick", "online", "server", "backup"):
            assert cb in texts, f"دکمه‌ی پنل جدید نیست: {cb} / {texts}"
        tg.clear()
        await router.dispatch(callback(SUPER, "server"))
        assert any(m in ("editMessageText", "sendMessage") for m, _ in tg.calls), tg.calls
    await acheck("منوی ابزارهای پنل جدید برای Super Admin", legacy_menu)

    # ── ۵. ساخت سریع کانفیگ از ابزار قدیمی + ربات Free Config هر دو در LINKS ──
    async def quick_and_free():
        panel.CONFIG["public_base_url"] = "https://panel.example.com"
        before = len(panel.LINKS)
        tg.clear()
        await router.dispatch(callback(SUPER, "qc:10:30"))
        assert len(panel.LINKS) == before + 1, f"ساخت سریع کانفیگ کار نکرد: {tg.calls[-3:]}"
        from botsys.services import issuing, users
        await users.touch({"id": USER, "username": "u", "first_name": "کاربر"})
        store.set_setting("require_channels", False)
        store.set_setting("free_quota_total", 3)
        res = await issuing.issue_free_config(USER)
        assert res.ok, res.reason
        assert res.user_config["link_uid"] in panel.LINKS
        from botsys.services import configs
        sub = configs.subscription_url(res.user_config)
        assert sub.endswith("/sub/" + res.user_config["link_uid"]) and "localhost" not in sub, sub
        raw = configs.raw_config(res.user_config)
        assert raw.startswith(("vless://", "vmess://", "trojan://")), raw
        assert raw != sub
        assert "panel.example.com" in raw and "panel.example.com" in sub
        panel.CONFIG["public_base_url"] = ""
    await acheck("ساخت سریع پنل + کانفیگ رایگان ربات", quick_and_free)

    # ── ۶. بکاپ قدیمی برای Super Admin با کلاینت مرکزی آپلود می‌شود ──
    async def legacy_backup_upload():
        await panel.save_state()
        tg.clear()
        import httpx
        httpx.AsyncClient.calls = []
        await router.dispatch(callback(SUPER, "backup"))
        docs = [p for m, p in httpx.AsyncClient.calls if m == "sendDocument"]
        assert docs and "_files" in docs[0], f"فایل بکاپ ارسال نشد: {httpx.AsyncClient.calls[-3:]}"
        assert str(docs[0].get("chat_id")) == str(SUPER)
    await acheck("بکاپ ابزار قدیمی از مسیر کلاینت ربات", legacy_backup_upload)

    # ── ۷. پیام متنی ادمین هنوز به botsys می‌رسد (/start → داشبورد ربات) ──
    async def start_command():
        tg.clear()
        await router.dispatch(message(SUPER, "/start"))
        assert tg.sent("sendMessage"), "پاسخی به /start داده نشد"
        tg.clear()
        await router.dispatch(message(USER, "/start"))
        btns = [b.get("callback_data") for b in tg.buttons()]
        assert any(str(b).startswith("u:") for b in btns), btns
        assert "menu" not in btns, "کاربر عادی دکمه‌ی ابزار ادمین دید!"
    await acheck("/start برای ادمین و کاربر", start_command)

    # ── ۸. مینی‌اپ: فقط Super Admin ──
    async def miniapp_auth():
        ok = panel._tma_admin(Request(headers={"x-tg-init": init_data(SUPER)}))
        assert ok == SUPER
        for uid in (ADMIN, USER):
            try:
                panel._tma_admin(Request(headers={"x-tg-init": init_data(uid)}))
                raise AssertionError(f"{uid} نباید به مینی‌اپ (نشست owner) دسترسی داشته باشد")
            except HTTPException as exc:
                assert exc.status_code == 403
        try:
            panel._tma_admin(Request(headers={"x-tg-init": init_data(SUPER, "999:WRONG")}))
            raise AssertionError("امضای جعلی پذیرفته شد")
        except HTTPException as exc:
            assert exc.status_code == 401
    await acheck("مینی‌اپ فقط با امضای درست و Super Admin", miniapp_auth)

    # ── ۹. تنظیمات ربات از پنل وب: ذخیره در CONFIG + Restart از botsys ──
    async def settings_flow():
        calls = []

        async def fake_restart():
            calls.append("restart")
            return {"running": True}
        orig = panel._tg_restart_bot
        panel._tg_restart_bot = fake_restart
        try:
            res = await panel.api_update_settings(Request(json_body={"bot_token": "777:NEW", "bot_admin_ids": "1,2"}), token=None)
        finally:
            panel._tg_restart_bot = orig
        assert calls == ["restart"], calls
        assert panel.CONFIG["bot_token"] == "777:NEW" and res["bot_token"] == "777:NEW"
        raw = json.loads(Path(panel.DATA_FILE).read_text(encoding="utf-8"))
        assert raw["settings"]["bot_token"] == "777:NEW", "توکن در State ذخیره نشد"
        for k in ("tg_users", "tg_settings", "tg_meta"):
            assert k in raw
        got = await panel.api_get_settings(Request(), token=None)
        assert got["bot_token"] == "777:NEW" and "bot_running" in got
        panel.CONFIG["bot_token"] = ""
    await acheck("تنظیمات ربات در پنل وب", settings_flow)

    # ── ۱۰. ری‌استارت: State پنل جدید + ربات کامل برمی‌گردد ──
    async def reload_roundtrip():
        await panel.save_state()
        users_before = dict(store.TG_USERS)
        cfg_before = dict(store.TG_USER_CONFIGS)
        links_before = set(panel.LINKS)
        for c in (panel.LINKS, panel.SUBS):
            c.clear()
        for c in (store.TG_USERS, store.TG_USER_CONFIGS):
            c.clear()
        await panel.load_state()
        assert set(panel.LINKS) == links_before
        assert set(store.TG_USERS) == set(users_before)
        assert set(store.TG_USER_CONFIGS) == set(cfg_before)
        assert store.schema_version() == store.SCHEMA_VERSION
    await acheck("ذخیره/بازیابی کامل بعد از Restart", reload_roundtrip)

    # ── ۱۱. localhost هیچ‌وقت وارد لینک‌ها نمی‌شود ──
    async def no_localhost():
        old = panel.CONFIG.get("public_base_url")
        panel.CONFIG["public_base_url"] = "http://localhost:8000"
        os.environ["RAILWAY_PUBLIC_DOMAIN"] = "demo.up.railway.app"
        try:
            assert panel.get_host() == "demo.up.railway.app", panel.get_host()
        finally:
            panel.CONFIG["public_base_url"] = old
            os.environ.pop("RAILWAY_PUBLIC_DOMAIN", None)
        panel.CONFIG["public_base_url"] = "https://panel.example.com"
        try:
            assert panel.subscription_url_for_uid("abc") == "https://panel.example.com/sub/abc"
        finally:
            panel.CONFIG["public_base_url"] = old
    await acheck("بدون localhost در لینک‌ها", no_localhost)

    # ── ۱۲. Health + Shutdown تمیز ──
    async def health_shutdown():
        h = await panel.health()
        assert h["status"] == "ok" and "telegram_bot" in h
        stopped = []

        async def fake_stop():
            stopped.append(1)
        orig = panel._tg_stop_bot
        panel._tg_stop_bot = fake_stop
        try:
            await panel.shutdown()
        finally:
            panel._tg_stop_bot = orig
        assert stopped, "ربات هنگام Shutdown متوقف نشد"
        legacy.detach()
        assert not legacy.is_attached()
    await acheck("Health و Shutdown", health_shutdown)

    print("\n" + "=" * 64)
    print("تست ادغام پنل جدید + ربات Free Config")
    print("=" * 64)
    passed = 0
    for name, ok, err in results:
        print(f"{'✅' if ok else '❌'}  {name}")
        if not ok:
            print("      " + err.replace("\n", "\n      ")[:1500])
        passed += ok
    print("=" * 64)
    print(f"{passed}/{len(results)} بررسی موفق")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

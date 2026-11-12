# ============================================================
# VodiWalker — ذخیره‌سازی دائمی روی Postgres خارجی
# ------------------------------------------------------------
# Shiprr دیسک دائمی ندارد؛ با هر ری‌استارت/دیپلوی پوشه data پاک می‌شود.
# این ماژول (فقط وقتی DATABASE_URL ست باشد) :
#   1) هنگام بالا آمدن، همه‌ی فایل‌های data را از دیتابیس برمی‌گرداند
#   2) هر چند ثانیه فایل‌های تغییرکرده را در دیتابیس ذخیره می‌کند
# بدون DATABASE_URL هیچ کاری نمی‌کند (رفتار قبلی حفظ می‌شود).
# ============================================================

import hashlib
import json
import logging
import os
import ssl
import threading
import time
from pathlib import Path
from urllib.parse import urlparse, unquote, parse_qs

logger = logging.getLogger("VodiWalker.persist")

DB_URL = (
    os.environ.get("DATABASE_URL")
    or os.environ.get("POSTGRES_URL")
    or os.environ.get("POSTGRESQL_URL")
    or ""
).strip()

ENABLED = bool(DB_URL)
SYNC_INTERVAL = max(5, int(os.environ.get("PERSIST_INTERVAL", "15") or 15))
MAX_FILE_BYTES = 8 * 1024 * 1024
SKIP_SUFFIXES = (".tmp", ".lock", ".swp", ".part")

_pushed_hash: dict = {}
_restore_ok = False
_stop = threading.Event()
_thread = None
_lock = threading.Lock()
_data_dir = None


def _ssl_contexts(query: dict):
    mode = (query.get("sslmode") or [""])[0].lower()
    verify = os.environ.get("PERSIST_SSL_VERIFY", "1") != "0"
    if mode == "disable":
        return [None]
    ctx = ssl.create_default_context()
    if not verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    # اول SSL، بعد (اگر سرور SSL نداشت) بدون SSL
    return [ctx, None]


def _connect():
    import pg8000.native  # lazy: فقط وقتی لازم است

    u = urlparse(DB_URL)
    query = parse_qs(u.query)
    last_exc = None
    for ctx in _ssl_contexts(query):
        try:
            kwargs = dict(
                user=unquote(u.username or ""),
                host=u.hostname,
                port=u.port or 5432,
                database=(u.path or "/postgres").lstrip("/") or "postgres",
                password=unquote(u.password or ""),
                timeout=15,
            )
            if ctx is not None:
                kwargs["ssl_context"] = ctx
            return pg8000.native.Connection(**kwargs)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
    raise last_exc


def _ensure_table(conn):
    conn.run(
        "CREATE TABLE IF NOT EXISTS vw_files ("
        "name TEXT PRIMARY KEY, data BYTEA NOT NULL, "
        "updated_at TIMESTAMPTZ NOT NULL DEFAULT now())"
    )


def _iter_files(data_dir: Path):
    for p in data_dir.rglob("*"):
        if not p.is_file():
            continue
        if p.name.endswith(SKIP_SUFFIXES) or p.name.startswith("."):
            continue
        try:
            if p.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        yield p


def _safe_target(data_dir: Path, name: str):
    rel = Path(name)
    if rel.is_absolute() or ".." in rel.parts:
        return None
    target = (data_dir / rel).resolve()
    try:
        target.relative_to(data_dir.resolve())
    except ValueError:
        return None
    return target


def restore_sync(data_dir) -> bool:
    """قبل از import سایر ماژول‌ها صدا زده می‌شود. True یعنی دیتابیس در دسترس بود."""
    global _restore_ok, _data_dir
    _data_dir = Path(data_dir)
    if not ENABLED:
        return False

    try:
        import pg8000.native  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        logger.error("[persist] pg8000 is not installed (%s) — add 'pg8000' to requirements.txt", exc)
        return False

    conn = None
    for attempt in range(1, 6):
        try:
            conn = _connect()
            _ensure_table(conn)
            rows = conn.run("SELECT name, data FROM vw_files")
            count = 0
            for name, data in rows:
                target = _safe_target(_data_dir, name)
                if target is None:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                raw = bytes(data)
                tmp = target.with_name(target.name + ".restore")
                tmp.write_bytes(raw)
                os.replace(tmp, target)
                _pushed_hash[str(name)] = hashlib.sha256(raw).hexdigest()
                count += 1
            _restore_ok = True
            logger.warning("[persist] %d file(s) restored from database.", count)
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("[persist] restore attempt %d failed: %s", attempt, exc)
            try:
                if conn:
                    conn.close()
            except Exception:  # noqa: BLE001
                pass
            conn = None
            time.sleep(min(2 * attempt, 8))
    logger.error(
        "[persist] DATABASE NOT REACHABLE — data will NOT be saved to the database "
        "(to avoid overwriting good data). Fix DATABASE_URL and redeploy."
    )
    return False


def _valid_for_push(path: Path, raw: bytes) -> bool:
    if path.suffix == ".json":
        try:
            json.loads(raw.decode("utf-8"))
        except Exception:  # noqa: BLE001
            return False  # فایل نیمه‌نوشته
    return True


def push_once(conn=None) -> int:
    """فایل‌های تغییرکرده را در دیتابیس ذخیره می‌کند؛ تعداد فایل ذخیره‌شده را برمی‌گرداند."""
    if not ENABLED or not _restore_ok or _data_dir is None:
        return 0
    own = conn is None
    pushed = 0
    with _lock:
        try:
            if own:
                conn = _connect()
            for p in _iter_files(_data_dir):
                name = p.relative_to(_data_dir).as_posix()
                try:
                    raw = p.read_bytes()
                except OSError:
                    continue
                digest = hashlib.sha256(raw).hexdigest()
                if _pushed_hash.get(name) == digest or not _valid_for_push(p, raw):
                    continue
                conn.run(
                    "INSERT INTO vw_files (name, data, updated_at) VALUES (:n, :d, now()) "
                    "ON CONFLICT (name) DO UPDATE SET data = EXCLUDED.data, updated_at = now()",
                    n=name,
                    d=raw,
                )
                _pushed_hash[name] = digest
                pushed += 1
        finally:
            if own and conn is not None:
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass
    return pushed


def _loop():
    while not _stop.wait(SYNC_INTERVAL):
        try:
            n = push_once()
            if n:
                logger.info("[persist] %d file(s) saved to database.", n)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[persist] sync failed (will retry): %s", exc)


def start_background():
    global _thread
    if not ENABLED or not _restore_ok or _thread is not None:
        return
    _thread = threading.Thread(target=_loop, name="vw-persist", daemon=True)
    _thread.start()
    logger.warning("[persist] database sync running every %ss.", SYNC_INTERVAL)


def stop_and_flush():
    _stop.set()
    try:
        n = push_once()
        if n:
            logger.warning("[persist] final flush: %d file(s) saved.", n)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[persist] final flush failed: %s", exc)

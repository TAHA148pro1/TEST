"""VodiWalker Bot — bot-only runtime.

The former FastAPI/web panel is intentionally removed. This process only:
1) runs Telegram polling/webhook handling,
2) stores bot state,
3) talks to external 3x-ui panels through Bearer API tokens.

No local Xray/VLESS relay is started by this project.
"""
from __future__ import annotations
import asyncio, base64, hashlib, json, logging, os, secrets, tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from cryptography.fernet import Fernet, InvalidToken
from botsys import store

ROOT=Path(__file__).resolve().parent
DATA_DIR=Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH") or os.environ.get("DATA_DIR") or str(ROOT/"data"))
DATA_DIR.mkdir(parents=True,exist_ok=True)
DATA_FILE=DATA_DIR/"vodiwalker_state.json"
SECRET_FILE=DATA_DIR/"vodiwalker_secret.key"
LOG_FILE=DATA_DIR/"bot.log"
logger=logging.getLogger("vodiwalker")

# Compatibility containers retained for old backup/state readers. They are NOT
# a local config source of truth anymore.
LINKS:dict[str,dict]={}
SUBS:dict[str,dict]={}
CATEGORIES:dict[str,dict]={}
ADMINS:dict[str,dict]={}
ADMIN_REQUESTS:dict[str,dict]={}
DAILY_STATS:dict[str,dict]={}
XUI_KEYS:dict[str,dict]={}

SAVE_LOCK=asyncio.Lock()

def _setup_logging():
    logging.basicConfig(level=os.environ.get("LOG_LEVEL","INFO").upper(),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
_setup_logging()

def _load_secret():
    raw=(os.environ.get("SECRET_KEY") or "").strip()
    if raw:
        return raw
    if SECRET_FILE.exists():
        val=SECRET_FILE.read_text(encoding="utf8").strip()
        if val:return val
    val=secrets.token_urlsafe(32)
    try:
        SECRET_FILE.write_text(val,encoding="utf8")
        os.chmod(SECRET_FILE,0o600)
    except Exception: pass
    return val

SECRET_KEY=_load_secret()
CONFIG={"secret":SECRET_KEY}

def _fernet():
    key=base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode()).digest())
    return Fernet(key)

def encrypt_secret(value:str)->str:
    if not value:return ""
    return _fernet().encrypt(value.encode()).decode()

def decrypt_secret(value:str)->str:
    if not value:return ""
    try:return _fernet().decrypt(value.encode()).decode()
    except (InvalidToken,ValueError,TypeError): return ""

def fmt_bytes(n:int)->str:
    n=max(0,int(n or 0)); units=("B","KB","MB","GB","TB")
    x=float(n)
    for u in units:
        if x<1024 or u==units[-1]: return f"{x:.1f} {u}" if u!="B" else f"{int(x)} B"
        x/=1024
    return f"{x:.1f} TB"

def _snapshot():
    return {
        "links":dict(LINKS),"subs":dict(SUBS),"categories":dict(CATEGORIES),
        "admins":dict(ADMINS),"admin_requests":dict(ADMIN_REQUESTS),"daily_stats":dict(DAILY_STATS),
        "settings":{"secret_version":2},
        "xui_keys":dict(XUI_KEYS),
        **store.export_state(),
        "saved_at":datetime.now(timezone.utc).astimezone().isoformat(),
    }

async def save_state():
    async with SAVE_LOCK:
        DATA_DIR.mkdir(parents=True,exist_ok=True)
        payload=_snapshot()
        tmp=DATA_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf8")
        tmp.replace(DATA_FILE)

def _merge_old_state(data:dict):
    LINKS.update(data.get("links") or {})
    SUBS.update(data.get("subs") or {})
    CATEGORIES.update(data.get("categories") or {})
    ADMINS.update(data.get("admins") or {})
    ADMIN_REQUESTS.update(data.get("admin_requests") or {})
    DAILY_STATS.update(data.get("daily_stats") or {})
    XUI_KEYS.update(data.get("xui_keys") or {})
    # New XUI records from a bot-only backup are already encrypted with this
    # deployment secret. If they cannot be decrypted, they are kept disabled.
    for r in XUI_KEYS.values():
        if r.get("token_enc") and not decrypt_secret(r["token_enc"]):
            r["enabled"]=False
            r["last_error"]="API Token قابل رمزگشایی نیست؛ Token را دوباره تنظیم کنید."

async def load_state():
    if not DATA_FILE.exists():
        store.run_migrations()
        return
    try:
        data=json.loads(DATA_FILE.read_text(encoding="utf8"))
        if not isinstance(data,dict): raise ValueError("state must be object")
        _merge_old_state(data)
        store.import_state(data,logger)
        store.run_migrations()
        # Old panel state is deliberately not used for new remote configs.
        # Keep it in LINKS only as migration/backup metadata.
        logger.info("state loaded: %d users, %d local links, %d 3x-ui keys",
                    len(store.TG_USERS),len(LINKS),len(XUI_KEYS))
    except Exception:
        logger.exception("state load failed; starting with empty state")

def get_host()->str:
    base=(os.environ.get("PUBLIC_BASE_URL") or os.environ.get("RAILWAY_PUBLIC_DOMAIN") or "").strip()
    base=base.replace("https://","").replace("http://","").split("/",1)[0]
    return base

def get_scheme()->str:
    return "https"

def _expiry(days:int)->int:
    if not days:return 0
    return int((datetime.now(timezone.utc).timestamp()+int(days)*86400)*1000)

def generate_uuid():
    import uuid
    return str(uuid.uuid4())

async def make_link(*args,**kwargs):
    """Compatibility API: create through the 3x-ui allocator."""
    from botsys.services import xui_manager
    from datetime import datetime,timezone,timedelta
    label=kwargs.get("label") or (args[0] if args else "لینک جدید")
    limit=int(kwargs.get("limit_bytes") or 0)
    days=0
    exp=kwargs.get("expires_at")
    if exp:
        try:
            dt=datetime.fromisoformat(str(exp)); days=max(0,int((dt-datetime.now(dt.tzinfo or timezone.utc)).total_seconds()/86400))
        except Exception: days=0
    spec=await xui_manager.allocate_client(email=f"bot-{secrets.token_hex(5)}",telegram_id=0,
        volume_bytes=limit,expiry_ms=_expiry(days),limit_ip=int(kwargs.get("ip_limit") or 0),
        comment=str(label)[:200],preferred_id=kwargs.get("api_key_id"),client_id=kwargs.get("client_id"))
    remote,key=spec
    uid=str(remote.get("id") or remote.get("uuid") or remote.get("email"))
    record={"label":label,"limit_bytes":limit,"used_bytes":0,"active":True,"expires_at":exp,
            "created_at":datetime.now().isoformat(),"xui_key_id":key["id"],"email":remote.get("email")}
    LINKS[uid]=record
    await save_state()
    return uid,record

async def remove_link(uid:str):
    link=LINKS.get(uid)
    if not link:return None
    from botsys.services import xui_manager
    email=link.get("email")
    if email and link.get("xui_key_id"):
        await xui_manager.remove(link["xui_key_id"],email)
    LINKS.pop(uid,None); await save_state(); return link

async def set_link_active(uid:str,active:bool):
    link=LINKS.get(uid)
    if not link:return None
    link["active"]=bool(active)
    await save_state(); return link

def vless_link_for_link(link:dict,uid:str,host:str|None=None,port_override:int|None=None):
    # New records usually carry the real URI from 3x-ui in `uri`.
    if link.get("uri"): return str(link["uri"])
    return ""

def subscription_url_for_uid(uid:str,host:str|None=None):
    link=LINKS.get(uid) or {}
    return str(link.get("subscription_url") or "")

def bump_daily_stat(key:str,amount:int=1):
    d=datetime.now().strftime("%Y-%m-%d")
    DAILY_STATS.setdefault(d,{})[key]=int(DAILY_STATS.setdefault(d,{}).get(key,0))+amount

async def bootstrap():
    await load_state()
    # Environment super admins are always granted without modifying the backup.
    from botsys.settings import parse_id_list
    ids=parse_id_list(os.environ.get("TELEGRAM_SUPER_ADMIN_IDS",""))
    for uid in ids:
        rec=store.TG_USERS.setdefault(str(uid),{"telegram_id":uid,"role":"super_admin"})
        rec["role"]="super_admin"
    store.run_migrations()
    await save_state()
    from botsys import runner
    return await runner.start()

async def shutdown():
    from botsys import runner
    await runner.stop()

def _run():
    async def runner_main():
        await bootstrap()
        try:
            while True: await asyncio.sleep(3600)
        except asyncio.CancelledError: pass
    asyncio.run(runner_main())

if __name__=="__main__":
    _run()

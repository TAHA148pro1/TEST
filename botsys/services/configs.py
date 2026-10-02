"""3x-ui-backed config service.

TG_USER_CONFIGS stores ownership/UI metadata. The actual client, quota and traffic
live in 3x-ui and are fetched on demand. This avoids a second fake panel.
"""
from __future__ import annotations
import logging, secrets
from datetime import datetime, timezone, timedelta
from .. import store
from . import xui_manager
from ..xui import XUIError, XUIClient
log=logging.getLogger("vodiwalker.configs")

class ConfigCreationError(Exception): pass

def gb_to_bytes(gb): return int(max(0,float(gb or 0))*1024**3)
def mbps_to_bytes(mbps): return int(max(0,float(mbps or 0))*1_000_000/8)

def _key_for(rec):
    kid=rec.get("xui_key_id")
    return xui_manager.get(kid) if kid else None

def _client_email(rec):
    return str(rec.get("email") or "")

def user_configs(tg_id:int,include_deleted=False):
    rows=[r for r in store.TG_USER_CONFIGS.values() if str(r.get("telegram_id"))==str(tg_id)]
    if not include_deleted: rows=[r for r in rows if not r.get("deleted")]
    rows.sort(key=lambda x:str(x.get("created_at") or ""),reverse=True)
    return rows

def get_user_config(uid): return store.TG_USER_CONFIGS.get(str(uid))

def pending_delivery(tg_id,source="free"):
    for r in user_configs(tg_id):
        if r.get("source")==source and not r.get("delivered",False) and not r.get("deleted"):
            return r
    return None

async def _remote(rec):
    key=_key_for(rec)
    if not key:return None,None
    c=XUIClient(key["base_url"],__import__("main").decrypt_secret(key["token_enc"]),verify_tls=key.get("verify_tls",True))
    try:
        info=await c.client(_client_email(rec))
        obj=info.data or {}
        client=obj.get("client",obj) if isinstance(obj,dict) else {}
        return client,key
    except Exception as e:
        log.warning("remote client read failed %s: %s",rec.get("id"),e)
        return None,key

def _expiry_text(ms):
    if not ms:return "بدون انقضا"
    try:return datetime.fromtimestamp(int(ms)/1000,timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M")
    except Exception:return "—"

def _status(client):
    if not client:return "deleted"
    if not client.get("enable",True):return "disabled"
    total=int(client.get("totalGB") or 0)
    traffic=client.get("traffic") or {}
    used=int(traffic.get("up") or 0)+int(traffic.get("down") or 0)
    exp=int(client.get("expiryTime") or 0)
    if total and used>=total:return "exhausted"
    if exp and exp<=int(__import__("time").time()*1000):return "expired"
    return "active"

async def refresh(rec):
    client,key=await _remote(rec)
    if client:
        rec["remote_id"]=client.get("id") or client.get("uuid")
        rec["sub_id"]=client.get("subId") or rec.get("sub_id")
        rec["remote_enable"]=bool(client.get("enable",True))
        rec["last_sync_at"]=datetime.now(timezone.utc).astimezone().isoformat()
    return client,key

def _describe_local(rec,client=None):
    client=client or {}
    total=int(client.get("totalGB") or rec.get("limit_bytes") or 0)
    traffic=client.get("traffic") or {}
    used=int(traffic.get("up") or 0)+int(traffic.get("down") or 0)
    expiry=int(client.get("expiryTime") or 0)
    speed=int(rec.get("speed_mbps") or 0)
    status=_status(client) if client else ("disabled" if not rec.get("active",True) else "unknown")
    labels={"active":"🟢 فعال","expired":"⌛️ منقضی","exhausted":"📭 حجم تمام شده","disabled":"🔴 غیرفعال","deleted":"🗑 حذف شده","unknown":"⚪️ نامشخص"}
    percent=round(used/total*100,1) if total else 0
    return {"id":str(rec.get("id")),"label":rec.get("label") or client.get("email") or "Config",
            "status":status,"status_label":labels.get(status,status),
            "protocol":rec.get("protocol") or "3x-ui","created_at":rec.get("created_at",""),
            "expires_at":_expiry_text(expiry),"total":__import__("main").fmt_bytes(total) if total else "نامحدود",
            "used":__import__("main").fmt_bytes(used),"remaining":__import__("main").fmt_bytes(max(0,total-used)) if total else "نامحدود",
            "percent":percent,"speed":f"{speed} Mbps" if speed else "نامحدود","ip_limit":int(client.get("limitIp") or rec.get("ip_limit") or 0),
            "used_bytes":used,"total_bytes":total,"remote":client,"api_key_id":rec.get("xui_key_id")}

def describe(rec):
    # Synchronous UI code uses cached metadata. Handler paths call async refresh only
    # after creation; a background sync updates remote stats.
    return _describe_local(rec)

async def describe_live(rec):
    client,key=await refresh(rec)
    return _describe_local(rec,client)

async def _links(rec,client):
    key=_key_for(rec)
    if not key:return []
    c=XUIClient(key["base_url"],__import__("main").decrypt_secret(key["token_enc"]),verify_tls=key.get("verify_tls",True))
    try:return await c.links(_client_email(rec))
    except Exception:return []

def raw_config(rec):
    return str(rec.get("uri") or "")

def subscription_url(rec):
    return str(rec.get("subscription_url") or "")

async def create_for_user(telegram_id:int,spec:dict,source="free",label=None):
    volume=gb_to_bytes(spec.get("volume_gb",0))
    days=int(spec.get("duration_days") or 0)
    expiry=int((datetime.now(timezone.utc)+timedelta(days=days)).timestamp()*1000) if days else 0
    email=f"tg-{telegram_id}-{secrets.token_hex(4)}"
    comment=(label or f"Telegram {telegram_id}")[:200]
    try:
        remote,key=await xui_manager.allocate_client(email=email,telegram_id=telegram_id,volume_bytes=volume,
            expiry_ms=expiry,limit_ip=int(spec.get("ip_limit") or 0),comment=comment,
            preferred_id=spec.get("api_key_id"))
    except Exception as exc:
        raise ConfigCreationError(str(exc))
    cid=str(store.next_id(store.TG_USER_CONFIGS))
    rec={"id":cid,"telegram_id":int(telegram_id),"email":email,"label":comment,
         "source":source,"created_at":datetime.now(timezone.utc).astimezone().isoformat(),
         "xui_key_id":key["id"],"inbound_id":key["inbound_id"],"remote_id":remote.get("id") or remote.get("uuid"),
         "sub_id":remote.get("subId"),"protocol":spec.get("protocol") or "3x-ui",
         "volume_gb":float(spec.get("volume_gb") or 0),"speed_mbps":float(spec.get("speed_mbps") or 0),
         "duration_days":days,"ip_limit":int(spec.get("ip_limit") or 0),"delivered":False,"deleted":False}
    # Ask panel for generated link; do not invent a URI locally.
    key_obj=xui_manager.get(key["id"])
    c=XUIClient(key_obj["base_url"],__import__("main").decrypt_secret(__import__("main").XUI_KEYS[key["id"]]["token_enc"]),
                verify_tls=key_obj.get("verify_tls",True))
    links=await c.links(email)
    if links: rec["uri"]=links[0]
    # 3x-ui subscription ID is not necessarily a public URL; leave it blank unless
    # the panel returns a link.
    if remote.get("subId"):
        rec["sub_id"]=remote["subId"]
    store.TG_USER_CONFIGS[cid]=rec
    store.bump_stat("configs_created")
    await __import__("main").save_state()
    return rec

async def remove(rec):
    key=_key_for(rec)
    if key:
        try:
            await xui_manager.remove(key["id"],_client_email(rec))
        except Exception as exc: log.warning("remote delete failed: %s",exc)
    rec["deleted"]=True
    await __import__("main").save_state()
    return True

async def set_active(rec,active:bool):
    key=_key_for(rec)
    if not key: return False
    c=XUIClient(key["base_url"],__import__("main").decrypt_secret(__import__("main").XUI_KEYS[key["id"]]["token_enc"]),verify_tls=key.get("verify_tls",True))
    ok=await c.toggle_client(_client_email(rec),active)
    if ok:
        rec["remote_enable"]=bool(active); await __import__("main").save_state()
    return ok

async def mark_delivered(uid):
    rec=get_user_config(uid)
    if rec:
        rec["delivered"]=True
        await __import__("main").save_state()

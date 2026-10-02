"""Multi-3x-ui-token management and allocation."""
from __future__ import annotations
import hashlib, logging, os, secrets
from datetime import datetime, timezone
from .. import store
from ..xui import XUIClient, XUIError, client_usage, client_count, normalize_base_url
log=logging.getLogger("vodiwalker.xui_manager")

# API key records live in main.XUI_KEYS so backup/restore can include them.
def _main():
    import main
    return main

def _keys():
    return _main().XUI_KEYS

def mask_token(token:str)->str:
    token=str(token or "")
    if len(token)<=8:return "••••••••"
    return token[:4]+"…" + token[-4:]

def _record(raw:dict)->dict:
    return {
        "id":str(raw.get("id") or ""),
        "name":str(raw.get("name") or "3x-ui"),
        "base_url":normalize_base_url(raw.get("base_url") or ""),
        "inbound_id":int(raw.get("inbound_id") or 0),
        "enabled":bool(raw.get("enabled",True)),
        "max_configs":max(0,int(raw.get("max_configs") or 0)),
        "max_total_gb":max(0,float(raw.get("max_total_gb") or 0)),
        "created_at":raw.get("created_at") or datetime.now(timezone.utc).astimezone().isoformat(),
        "last_ok":raw.get("last_ok") or "",
        "last_error":raw.get("last_error") or "",
        "created_count":max(0,int(raw.get("created_count") or 0)),
        "created_volume_bytes":max(0,int(raw.get("created_volume_bytes") or 0)),
        "token_enc":str(raw.get("token_enc") or ""),
        "verify_tls":bool(raw.get("verify_tls",True)),
    }

def all_records()->list[dict]:
    return sorted((_record(x) for x in _keys().values()),key=lambda x:(not x["enabled"],x["name"].lower()))

def get(key_id:str)->dict|None:
    r=_keys().get(str(key_id))
    return _record(r) if r else None

def _token(r:dict)->str:
    return _main().decrypt_secret(str(r.get("token_enc") or ""))

def public_record(r:dict, stats:dict|None=None)->dict:
    out={k:v for k,v in _record(r).items() if k!="token_enc"}
    out["token"]=mask_token(_token(r))
    if stats: out.update(stats)
    return out

async def add(name,base_url,token,inbound_id,max_configs=20,max_total_gb=0,verify_tls=True)->dict:
    base_url=normalize_base_url(base_url)
    if not base_url or not token or int(inbound_id)<=0: raise ValueError("نام، آدرس پنل، Token و Inbound ID الزامی هستند.")
    kid=secrets.token_hex(6)
    while kid in _keys(): kid=secrets.token_hex(6)
    rec={"id":kid,"name":str(name or f"Panel {len(_keys())+1}")[:80],"base_url":base_url,
         "inbound_id":int(inbound_id),"enabled":True,"max_configs":max(0,int(max_configs)),
         "max_total_gb":max(0,float(max_total_gb or 0)),"created_at":datetime.now(timezone.utc).astimezone().isoformat(),
         "last_ok":"","last_error":"","created_count":0,"created_volume_bytes":0,
         "token_enc":_main().encrypt_secret(token),"verify_tls":bool(verify_tls)}
    # Validate before persistence.
    c=XUIClient(base_url,token,verify_tls=verify_tls)
    await c.status()
    _keys()[kid]=rec
    await _main().save_state()
    return public_record(rec)

async def test(key_id:str)->dict:
    r=_keys().get(str(key_id))
    if not r: raise ValueError("کلید پیدا نشد.")
    try:
        c=XUIClient(r["base_url"],_token(r),verify_tls=bool(r.get("verify_tls",True)))
        st=await c.status()
        if not st.success: raise XUIError(st.message)
        r["last_ok"]=datetime.now(timezone.utc).astimezone().isoformat(); r["last_error"]=""
        await _main().save_state()
        return st.data if isinstance(st.data,dict) else {"status":st.data}
    except Exception as exc:
        r["last_error"]=str(exc)[:300]
        await _main().save_state()
        raise

async def inbound_list(key_id:str)->list[dict]:
    r=_keys().get(str(key_id))
    if not r: raise ValueError("کلید پیدا نشد.")
    c=XUIClient(r["base_url"],_token(r),verify_tls=bool(r.get("verify_tls",True)))
    res=await c.inbounds()
    if not res.success: raise XUIError(res.message)
    return res.data if isinstance(res.data,list) else []

async def stats(key_id:str)->dict:
    r=_keys().get(str(key_id))
    if not r: raise ValueError("کلید پیدا نشد.")
    c=XUIClient(r["base_url"],_token(r),verify_tls=bool(r.get("verify_tls",True)))
    res=await c.clients()
    if not res.success: raise XUIError(res.message)
    rows=res.data if isinstance(res.data,list) else []
    scoped=[x for x in rows if int(r["inbound_id"]) in [int(i) for i in (x.get("inboundIds") or [])]]
    # Capacity belongs to this bot's allocation pool, not every unrelated client
    # that an administrator may have manually placed in the same inbound.
    managed=[x for x in scoped if str(x.get("email") or "").startswith(("tg-","bot-","restore-"))]
    total=used=volume=0
    active=0
    for x in managed:
        u,t=client_usage(x); used+=u; volume+=int(t or 0); active+=1 if x.get("enable",True) else 0
    cap_count=int(r.get("max_configs") or 0)
    cap_gb=float(r.get("max_total_gb") or 0)
    return {"remote_configs":len(managed),"active":active,"used_bytes":used,"allocated_bytes":volume,
            "max_configs":cap_count,"max_total_gb":cap_gb,
            "local_created":int(r.get("created_count") or 0),
            "local_volume_bytes":int(r.get("created_volume_bytes") or 0)}

async def can_allocate(r:dict,volume_bytes:int)->tuple[bool,str,dict]:
    if not r.get("enabled",True): return False,"کلید غیرفعال است",{}
    s=await stats(r["id"])
    if s["max_configs"] and s["remote_configs"]>=s["max_configs"]:
        return False,f"سقف {s['max_configs']} کانفیگ این کلید پر شده است",s
    if s["max_total_gb"] and (s["allocated_bytes"]+volume_bytes)>s["max_total_gb"]*1024**3:
        return False,"سقف حجم اختصاص‌داده‌شده این کلید پر شده است",s
    return True,"",s

async def choose(volume_bytes:int, preferred_id:str|None=None)->tuple[dict,dict]:
    rows=all_records()
    if preferred_id:
        rows=[_record(_keys()[preferred_id])] + [x for x in rows if x["id"]!=preferred_id] if preferred_id in _keys() else rows
    errors=[]
    for r in rows:
        try:
            ok,reason,st=await can_allocate(r,volume_bytes)
            if ok:return r,st
            errors.append(f"{r['name']}: {reason}")
        except Exception as exc:
            errors.append(f"{r['name']}: {exc}")
            continue
    raise XUIError("هیچ API Key قابل استفاده‌ای وجود ندارد.\n" + "\n".join(errors[:6]))

async def allocate_client(*,email:str,telegram_id:int,volume_bytes:int,expiry_ms:int,limit_ip:int,comment:str="",preferred_id:str|None=None,client_id:str|None=None)->tuple[dict,dict]:
    r,pre=await choose(volume_bytes,preferred_id)
    c=XUIClient(r["base_url"],_token(r),verify_tls=bool(r.get("verify_tls",True)))
    result=await c.add_client(email,r["inbound_id"],volume_bytes,expiry_ms,limit_ip,telegram_id,comment,client_id)
    # Re-read remote client so generated UUID/subId is authoritative.
    try:
        info=await c.client(email)
        remote=info.data.get("client",info.data) if isinstance(info.data,dict) else {}
        if isinstance(remote,dict): result={**result,**remote}
    except Exception: pass
    r["created_count"]=int(r.get("created_count") or 0)+1
    r["created_volume_bytes"]=int(r.get("created_volume_bytes") or 0)+int(volume_bytes)
    r["last_ok"]=datetime.now(timezone.utc).astimezone().isoformat(); r["last_error"]=""
    await _main().save_state()
    return result,r

async def remove(key_id,email):
    r=_keys().get(str(key_id))
    if not r:return False
    c=XUIClient(r["base_url"],_token(r),verify_tls=bool(r.get("verify_tls",True)))
    ok=await c.delete_client(email,r["inbound_id"])
    if ok: await _main().save_state()
    return ok

async def edit(key_id,**changes):
    r=_keys().get(str(key_id))
    if not r: raise ValueError("کلید پیدا نشد.")
    for field in ("name","base_url","inbound_id","max_configs","max_total_gb","enabled","verify_tls"):
        if field in changes and changes[field] is not None:
            if field=="base_url": changes[field]=normalize_base_url(changes[field])
            if field in ("inbound_id","max_configs"): changes[field]=int(changes[field])
            if field=="max_total_gb": changes[field]=float(changes[field])
            r[field]=changes[field]
    if "token" in changes and changes["token"]:
        r["token_enc"]=_main().encrypt_secret(str(changes["token"]))
    await _main().save_state()
    return public_record(r)

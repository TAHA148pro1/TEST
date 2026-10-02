"""Bot-only backup/restore.

Format 2 stores bot state + encrypted 3x-ui tokens. Format 1 (the supplied
VodiWalker panel+bot backup) is accepted and migrated without requiring the old
web panel to be restored.
"""
from __future__ import annotations
import asyncio,io,json,logging,zipfile
from datetime import datetime,timezone
from pathlib import Path
from .. import store,security
log=logging.getLogger("vodiwalker.backups")
BACKUP_PREFIX="vodiwalker_backup_"
BACKUP_FORMAT=2
MAX_RESTORE_BYTES=50*1024*1024
_LOCK=asyncio.Lock(); _TASK=None

def _main():
    import main; return main
def _now(): return datetime.now(timezone.utc)
def _filename(): return f"{BACKUP_PREFIX}{_now().strftime('%Y%m%d_%H%M%S')}.zip"
def _super_admin_ids():
    ids=set(security.env_super_admins())
    for key,r in store.TG_USERS.items():
        if isinstance(r,dict) and r.get("role")=="super_admin":
            try:ids.add(int(key))
            except:pass
    return ids
def status():
    return {"enabled":bool(store.setting("backup_enabled",True)),"interval_hours":float(store.setting("backup_interval_hours",24) or 24),
            "last_at":store.setting("backup_last_at","") or "","super_admins":len(_super_admin_ids()),
            "running":bool(_TASK and not _TASK.done())}

async def create_archive():
    async with _LOCK:
        m=_main(); await m.save_state()
        state=m.DATA_FILE.read_bytes()
        manifest={"format":BACKUP_FORMAT,"app":"VodiWalkerBot","created_at":_now().isoformat(),
                  "files":["state.json","secret.key"]}
        bio=io.BytesIO()
        with zipfile.ZipFile(bio,"w",zipfile.ZIP_DEFLATED,6) as z:
            z.writestr("manifest.json",json.dumps(manifest,ensure_ascii=False,indent=2))
            z.writestr("state.json",state)
            z.writestr("secret.key",m.SECRET_KEY)
        return bio.getvalue(),_filename()

async def send_archive(client,archive,filename,automatic=False):
    sent=0
    cap="💾 <b>بکاپ ربات</b>\n\nState ربات، کاربران، تنظیمات، APIهای 3x-ui و داده‌های مدیریتی."
    for uid in sorted(_super_admin_ids()):
        try:
            if await client.send_document(uid,archive,filename,caption=cap):sent+=1
        except Exception:log.warning("backup send failed to %s",uid,exc_info=True)
    return sent

async def create_and_send(client,automatic=False):
    a,f=await create_archive(); sent=await send_archive(client,a,f,automatic=automatic)
    if sent:
        store.set_setting("backup_last_at",_now().isoformat()); await _main().save_state()
    return {"ok":sent>0,"sent":sent,"filename":f,"size":len(a)}

def _read(archive:bytes):
    if not archive or len(archive)>MAX_RESTORE_BYTES: raise ValueError("فایل بکاپ بیش از حد مجاز است.")
    try:z=zipfile.ZipFile(io.BytesIO(archive),"r")
    except zipfile.BadZipFile as e: raise ValueError("فایل ZIP معتبر نیست.") from e
    with z:
        names=set(z.namelist())
        if "manifest.json" not in names or "state.json" not in names: raise ValueError("ساختار بکاپ ناقص است.")
        for n in names:
            if n.startswith("/") or ".." in Path(n).parts: raise ValueError("مسیر داخل ZIP نامعتبر است.")
        manifest=json.loads(z.read("manifest.json").decode())
        app=str(manifest.get("app") or "")
        fmt=int(manifest.get("format") or 0)
        if app not in ("VodiWalker","VodiWalkerBot") or fmt not in (1,2):
            raise ValueError("فرمت بکاپ پشتیبانی نمی‌شود.")
        state=json.loads(z.read("state.json").decode())
        return state, (z.read("secret.key").decode().strip() if "secret.key" in names else ""),fmt

async def restore_archive(archive:bytes):
    state,secret,fmt=_read(archive)
    if not isinstance(state,dict):raise ValueError("state.json نامعتبر است.")
    async with _LOCK:
        m=_main()
        # Full restore includes the security identity so encrypted API tokens
        # from the backup remain decryptable after the restore.
        if secret:
            m.SECRET_KEY=secret; m.CONFIG["secret"]=secret
            try:m.SECRET_FILE.write_text(secret,encoding="utf8")
            except:pass
        # Clear and restore bot state.
        for c in (store.TG_USERS,store.TG_ROLES,store.TG_USER_CONFIGS,store.TG_QUOTAS,store.TG_CHANNELS,
                  store.TG_TICKETS,store.TG_MESSAGES,store.TG_BROADCASTS,store.TG_STATS): c.clear()
        store.TG_AUDIT.clear()
        m.LINKS.clear();m.SUBS.clear();m.CATEGORIES.clear();m.ADMINS.clear();m.ADMIN_REQUESTS.clear();m.DAILY_STATS.clear();m.XUI_KEYS.clear()
        store.import_state(state,log); store.run_migrations()
        # New-format keys.
        for k,v in (state.get("xui_keys") or {}).items():
            m.XUI_KEYS[str(k)]=dict(v)
        # Format 1 had panel-local links but no 3x-ui token pool. Preserve them
        # as migration metadata; do not pretend they are live remote clients.
        for k,v in (state.get("links") or {}).items(): m.LINKS[str(k)]=dict(v)
        # Mark old user configs as legacy so UI can show them instead of silently
        # losing ownership records.
        legacy=0
        for rec in store.TG_USER_CONFIGS.values():
            if fmt==1 and not rec.get("xui_key_id"):
                rec["legacy"]=True; rec["legacy_link_uid"]=rec.get("link_uid"); legacy+=1
        await m.save_state()
        return {"ok":True,"users":len(store.TG_USERS),"legacy_configs":legacy,
                "api_keys":len(m.XUI_KEYS),"format":fmt}


async def migrate_legacy(key_id:str)->dict:
    """Recreate old local-panel link records as real 3x-ui clients.

    This is opt-in and uses the selected API key's configured inbound. UUID is
    preserved for VLESS/VMess-style legacy records when possible. A legacy
    record is never deleted until its remote client has been created/read back.
    """
    from . import xui_manager
    from datetime import datetime
    m=_main()
    key=xui_manager.get(key_id)
    if not key: raise ValueError("API پیدا نشد.")
    # Work on unique legacy links; multiple TG users can point to one old link.
    migrated=0; skipped=0; errors=[]
    groups={}
    for rec in store.TG_USER_CONFIGS.values():
        if rec.get("legacy") and not rec.get("deleted"):
            groups.setdefault(str(rec.get("legacy_link_uid") or rec.get("link_uid") or ""),[]).append(rec)
    for old_uid, owners in groups.items():
        link=m.LINKS.get(old_uid) or {}
        if not link: skipped+=1; continue
        volume=int(link.get("limit_bytes") or 0)
        expiry=0
        raw=link.get("expires_at")
        if raw:
            try: expiry=int(datetime.fromisoformat(str(raw)).timestamp()*1000)
            except: expiry=0
        owner=int(owners[0].get("telegram_id") or 0)
        email=f"restore-{old_uid[:12]}"
        try:
            remote,newkey=await xui_manager.allocate_client(email=email,telegram_id=owner,
                volume_bytes=volume,expiry_ms=expiry,limit_ip=int(link.get("ip_limit") or 0),
                comment=str(link.get("label") or "Restored")[:200],preferred_id=key_id,
                client_id=old_uid if str(link.get("protocol","")).startswith(("vless","vmess")) else None)
            for rec in owners:
                rec["email"]=email; rec["xui_key_id"]=newkey["id"]; rec["inbound_id"]=newkey["inbound_id"]
                rec["remote_id"]=remote.get("id") or remote.get("uuid"); rec["legacy_migrated"]=True
                rec["legacy"]=False
            migrated+=1
        except Exception as exc:
            errors.append(f"{old_uid[:12]}: {exc}")
    await m.save_state()
    return {"migrated":migrated,"skipped":skipped,"errors":errors}

async def handle_document(client,chat_id,document):
    if not security.is_super_admin(int(chat_id)):return {"ok":False,"ignored":True}
    data=await client.download_file(document.get("file_id"))
    return await restore_archive(data)

async def monitor_loop(client):
    global _TASK
    try:
        while True:
            interval=max(1,float(store.setting("backup_interval_hours",24) or 24))
            await asyncio.sleep(min(60,interval*3600))
            if store.setting("backup_enabled",True):
                last=str(store.setting("backup_last_at","") or "")
                due=True
                if last:
                    try:due=(_now()-datetime.fromisoformat(last)).total_seconds()>=interval*3600
                    except:pass
                if due:
                    try:await create_and_send(client,automatic=True)
                    except Exception:log.exception("automatic backup failed")
    except asyncio.CancelledError: raise

def start_scheduler(client):
    global _TASK
    if not _TASK or _TASK.done():_TASK=asyncio.create_task(monitor_loop(client))
async def stop_scheduler():
    global _TASK
    if _TASK:
        _TASK.cancel()
        try:await _TASK
        except asyncio.CancelledError:pass
        _TASK=None

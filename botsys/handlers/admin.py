"""Clean Telegram admin UI.

All operational settings are managed here; there is no web panel dependency.
"""
from __future__ import annotations
import logging, math, json
from .. import keyboards as k, security, store
from ..services import users, quota, channels, support, backups, configs, xui_manager, analytics, broadcast
from ..tgapi import h
log=logging.getLogger("vodiwalker.admin")
_PENDING={}

def set_pending(uid,value): _PENDING[int(uid)]=value
def get_pending(uid): return _PENDING.get(int(uid))
def clear_pending(uid): _PENDING.pop(int(uid),None)

def dashboard_text(admin_id:int)->str:
    role=security.role_of(admin_id) or "admin"
    return ("🛠 <b>مدیریت ربات</b>\n\n"
            f"👤 نقش: <b>{h(role)}</b>\n"
            f"👥 کاربران: <b>{users.count()}</b>\n"
            f"📦 رکورد کانفیگ‌ها: <b>{len(store.TG_USER_CONFIGS)}</b>\n"
            f"🖥 APIهای فعال 3x-ui: <b>{sum(1 for x in xui_manager.all_records() if x['enabled'])}</b>\n\n"
            "از منوی زیر بخش موردنظر را انتخاب کنید.")

def _render(client,chat_id,message_id,text,kb):
    if message_id:return client.edit_message(chat_id,message_id,text,kb)
    return client.send_message(chat_id,text,kb)

def _deny(client,cb_id,message="دسترسی ندارید."):
    return client.answer_callback(cb_id,message,alert=True)

async def handle(client,rec,chat_id,message_id,data,cb_id):
    aid=int(rec["telegram_id"])
    if not security.is_admin(aid):
        await _deny(client,cb_id); return True
    if data=="a:menu":
        clear_pending(aid); await _render(client,chat_id,message_id,dashboard_text(aid),k.admin_main(security.is_super_admin(aid))); return True
    if data=="a:xui" or data.startswith("a:xui:"):
        return await _xui(client,aid,chat_id,message_id,data,cb_id)
    if data=="a:stats": return await _stats(client,aid,chat_id,message_id,cb_id)
    if data=="a:users" or data.startswith("a:user"): return await _users(client,aid,chat_id,message_id,data,cb_id)
    if data=="a:cfgs" or data.startswith("a:cfg"): return await _configs(client,aid,chat_id,message_id,data,cb_id)
    if data=="a:quota" or data.startswith("a:quota:"): return await _quota(client,aid,chat_id,message_id,data,cb_id)
    if data=="a:chans" or data.startswith("a:chan"): return await _channels(client,aid,chat_id,message_id,data,cb_id)
    if data=="a:backup" or data.startswith("a:backup:"): return await _backup(client,aid,chat_id,message_id,data,cb_id)
    if data=="a:settings" or data.startswith("a:setting"): return await _settings(client,aid,chat_id,message_id,data,cb_id)
    if data=="a:tickets" or data.startswith("a:tkt"): return await _tickets(client,aid,chat_id,message_id,data,cb_id)
    if data=="a:bc": return await _broadcast(client,aid,chat_id,message_id,cb_id)
    return False

# ---------------- 3x-ui ----------------
async def _xui(client,aid,chat_id,mid,data,cb):
    if not security.has_permission(aid,security.MANAGE_CONFIGS):
        await _deny(client,cb); return True
    if data=="a:xui":
        await _render(client,chat_id,mid,
            "🖥 <b>مدیریت APIهای 3x-ui</b>\n\n"
            "هر API Key می‌تواند به یک Inbound متصل شود و سقف تعداد/حجم مستقل داشته باشد.\n"
            "ربات هنگام ساخت، اولین کلید قابل‌استفاده را انتخاب می‌کند و در صورت پر بودن به بعدی می‌رود.",
            k.xui_main()); return True
    if data=="a:xui:add":
        set_pending(aid,{"action":"xui_add","step":"name","data":{}})
        await _render(client,chat_id,mid,"➕ <b>افزودن API 3x-ui</b>\n\nنام نمایشی API را بفرست:",k.kb([[k.cancel("a:xui")]])); return True
    if data=="a:xui:list":
        rows=[]
        for r in xui_manager.all_records():
            st="🟢" if r["enabled"] else "🔴"
            rows.append([k.enter(f"{st} {r['name'][:25]}",f"a:xui:view:{r['id']}")])
        rows.append([k.back("a:xui")])
        await _render(client,chat_id,mid,"📋 <b>API Keyها</b>\n\n"+("هر ردیف یک API مستقل است." if rows[:-1] else "هنوز API ثبت نشده است."),k.kb(rows)); return True
    if data.startswith("a:xui:view:"):
        kid=data.rsplit(":",1)[1]; r=xui_manager.get(kid)
        if not r: await _deny(client,cb,"API پیدا نشد."); return True
        try: st=await xui_manager.stats(kid)
        except Exception as e: st={"error":str(e)}
        text=(f"🖥 <b>{h(r['name'])}</b>\n\n"
              f"🌐 {h(r['base_url'])}\n🔑 Token: <code>{h(r['token'])}</code>\n"
              f"🎯 Inbound ID: <code>{r['inbound_id']}</code>\n"
              f"📦 سقف کانفیگ: {r['max_configs'] or 'نامحدود'}\n"
              f"💾 سقف حجم اختصاصی: {r['max_total_gb'] or 'نامحدود'} GB\n"
              f"📊 تعداد فعلی: {st.get('remote_configs','—')}\n"
              f"📈 مصرف: {__import__('main').fmt_bytes(st.get('used_bytes',0))}\n"
              f"🟢 وضعیت: {'فعال' if r['enabled'] else 'غیرفعال'}")
        await _render(client,chat_id,mid,text,k.kb([
            [k.enter("🧪 تست اتصال",f"a:xui:test:{kid}"),k.toggle("فعال/غیرفعال",f"a:xui:toggle:{kid}",r["enabled"])],
            [k.enter("🔄 انتخاب Inbound",f"a:xui:inbounds:{kid}")],
            [k.danger("🗑 حذف API",f"a:xui:del:{kid}")],
            [k.back("a:xui:list")]])); return True
    if data.startswith("a:xui:test:"):
        kid=data.rsplit(":",1)[1]
        try:
            st=await xui_manager.test(kid); await client.answer_callback(cb,"✅ اتصال موفق بود.",alert=True)
            await _xui(client,aid,chat_id,mid,f"a:xui:view:{kid}",cb)
        except Exception as e: await client.answer_callback(cb,f"❌ {str(e)[:180]}",alert=True)
        return True
    if data.startswith("a:xui:toggle:"):
        kid=data.rsplit(":",1)[1]; r=xui_manager.get(kid)
        if r: await xui_manager.edit(kid,enabled=not r["enabled"])
        await _xui(client,aid,chat_id,mid,f"a:xui:view:{kid}",cb); return True
    if data.startswith("a:xui:del:"):
        kid=data.rsplit(":",1)[1]
        set_pending(aid,{"action":"xui_delete","kid":kid})
        await _render(client,chat_id,mid,"⚠️ حذف API Key فقط تنظیمات اتصال ربات را حذف می‌کند؛ کلاینت‌های داخل 3x-ui حذف نمی‌شوند.\n\nبرای تأیید «حذف» را بفرست.",k.kb([[k.cancel(f"a:xui:view:{kid}")]])); return True
    if data.startswith("a:xui:inbounds:"):
        kid=data.rsplit(":",1)[1]
        try: ins=await xui_manager.inbound_list(kid)
        except Exception as e:
            await client.answer_callback(cb,f"خطا: {str(e)[:160]}",alert=True); return True
        rows=[]
        for i in ins:
            if not isinstance(i,dict):continue
            iid=int(i.get("id") or 0); remark=str(i.get("remark") or i.get("tag") or iid)
            rows.append([k.enter(f"🎯 {remark[:28]} · {iid}",f"a:xui:setin:{kid}:{iid}")])
        rows.append([k.back(f"a:xui:view:{kid}")])
        await _render(client,chat_id,mid,"🎯 <b>انتخاب Inbound</b>\n\nیکی را انتخاب کن:",k.kb(rows)); return True
    if data.startswith("a:xui:setin:"):
        parts=data.split(":"); kid=parts[3]; iid=int(parts[4])
        await xui_manager.edit(kid,inbound_id=iid)
        await client.answer_callback(cb,"✅ Inbound ذخیره شد.",alert=True)
        await _xui(client,aid,chat_id,mid,f"a:xui:view:{kid}",cb); return True
    if data=="a:xui:stats":
        lines=["📈 <b>آمار APIهای 3x-ui</b>",""]
        for r in xui_manager.all_records():
            try: st=await xui_manager.stats(r["id"]); lines.append(f"• <b>{h(r['name'])}</b>: {st['remote_configs']} کانفیگ | مصرف {__import__('main').fmt_bytes(st['used_bytes'])}")
            except Exception as e: lines.append(f"• <b>{h(r['name'])}</b>: ⚠️ {h(str(e)[:80])}")
        await _render(client,chat_id,mid,"\n".join(lines),k.kb([[k.back("a:xui")]])); return True
    if data=="a:xui:sync":
        await client.answer_callback(cb,"⏳ در حال بررسی APIها...")
        ok=bad=0
        for r in xui_manager.all_records():
            try: await xui_manager.test(r["id"]); ok+=1
            except Exception: bad+=1
        await _render(client,chat_id,mid,f"🔄 همگام‌سازی تمام شد.\n\n✅ سالم: {ok}\n⚠️ مشکل‌دار: {bad}",k.kb([[k.back("a:xui")]])); return True
    return False

# ---------------- stats ----------------
async def _stats(client,aid,chat_id,mid,cb):
    if not security.has_permission(aid,security.VIEW_ANALYTICS): await _deny(client,cb); return True
    total_used=total_alloc=total_clients=0
    lines=["📊 <b>آمار کلی ربات</b>","",f"👥 کاربران: {users.count()}",f"📦 رکوردهای کانفیگ: {len(store.TG_USER_CONFIGS)}"]
    for r in xui_manager.all_records():
        try:
            st=await xui_manager.stats(r["id"]); total_clients+=st["remote_configs"]; total_used+=st["used_bytes"]; total_alloc+=st["allocated_bytes"]
        except Exception: pass
    lines += [f"🖥 کل کلاینت‌های 3x-ui: {total_clients}",f"📈 کل مصرف: {__import__('main').fmt_bytes(total_used)}",f"💾 کل حجم اختصاص‌یافته: {__import__('main').fmt_bytes(total_alloc)}"]
    await _render(client,chat_id,mid,"\n".join(lines),k.kb([[k.enter("🖥 جزئیات APIها","a:xui:stats")],[k.back("a:menu")]])); return True

# ---------------- users ----------------
async def _users(client,aid,chat_id,mid,data,cb):
    if not security.has_permission(aid,security.MANAGE_USERS): await _deny(client,cb); return True
    page=0
    if data.startswith("a:users:"): 
        try: page=max(0,int(data.rsplit(":",1)[1]))
        except: page=0
    rows=users.recent(limit=50); page_size=8; chunk=rows[page*page_size:(page+1)*page_size]
    buttons=[]
    for u in chunk:
        uid=int(u["telegram_id"]); buttons.append([k.enter(f"👤 {users.display_name(u)[:28]}",f"a:user:{uid}")])
    navrow=k.pager("a:users",page,len(rows),page_size)
    if navrow: buttons.append(navrow)
    buttons.append([k.back("a:menu")])
    if data.startswith("a:user:"):
        uid=int(data.rsplit(":",1)[1]); u=users.get(uid)
        if not u: await _deny(client,cb,"کاربر پیدا نشد."); return True
        st=quota.status(uid); cfgs=configs.user_configs(uid)
        text=(f"👤 <b>{h(users.display_name(u))}</b>\n\n🆔 <code>{uid}</code>\n"
              f"نقش: {u.get('role')}\nوضعیت: {'مسدود' if u.get('is_blocked') else 'فعال'}\n"
              f"📦 کانفیگ‌ها: {len(cfgs)}\n🎁 سهمیه: {st['remaining']}/{st['total']}")
        await _render(client,chat_id,mid,text,k.kb([
            [k.toggle("مسدودسازی",f"a:user:toggle:{uid}",not bool(u.get("is_blocked")))],
            [k.enter("🎁 تنظیم سهمیه",f"a:quota:user:{uid}")],
            [k.enter("📦 کانفیگ‌های کاربر",f"a:cfg:user:{uid}")],
            [k.back("a:users:0")]])); return True
    await _render(client,chat_id,mid,"👥 <b>کاربران</b>\n\nکاربر را انتخاب کنید:",k.kb(buttons)); return True

# ---------------- configs ----------------
async def _configs(client,aid,chat_id,mid,data,cb):
    if not security.has_permission(aid,security.MANAGE_CONFIGS): await _deny(client,cb); return True
    if data.startswith("a:cfg:user:"):
        uid=int(data.rsplit(":",1)[1]); rows=configs.user_configs(uid)
        text=f"📦 <b>کانفیگ‌های کاربر {uid}</b>\n\n"
        if not rows:text+="موردی وجود ندارد."
        for r in rows[:10]:
            d=configs.describe(r); text+=f"• {h(d['label'])} — {d['status_label']}\n"
        await _render(client,chat_id,mid,text,k.kb([[k.back(f"a:user:{uid}")]])); return True
    rows=list(store.TG_USER_CONFIGS.values()); rows=[r for r in rows if not r.get("deleted")]
    text=f"📦 <b>کانفیگ‌های ثبت‌شده</b>\n\nتعداد: {len(rows)}\n"
    for r in rows[-12:][::-1]:
        d=configs.describe(r); text+=f"\n• {h(d['label'])} | TG {r.get('telegram_id')} | {d['status_label']}"
    await _render(client,chat_id,mid,text,k.kb([[k.back("a:menu")]])); return True

# ---------------- quota ----------------
async def _quota(client,aid,chat_id,mid,data,cb):
    if not security.has_permission(aid,security.MANAGE_QUOTA): await _deny(client,cb); return True
    if data.startswith("a:quota:user:"):
        uid=int(data.rsplit(":",1)[1]); st=quota.status(uid)
        set_pending(aid,{"action":"quota_user","uid":uid})
        await _render(client,chat_id,mid,
            f"🎁 <b>سهمیه کاربر {uid}</b>\n\nفعلی: {st['total']}\nحجم هر کانفیگ: {st['volume_gb']} GB\nمدت: {st['duration_days']} روز\n\nیک عدد برای «تعداد کل» بفرست:",
            k.kb([[k.cancel(f"a:user:{uid}")]])); return True
    st={k:store.setting(k) for k in ("free_quota_total","free_volume_gb","free_duration_days","free_ip_limit")}
    text=("🎁 <b>تنظیمات ساخت رایگان</b>\n\n"
          f"تعداد کل هر کاربر: {st['free_quota_total']}\nحجم هر کانفیگ: {st['free_volume_gb']} GB\n"
          f"اعتبار: {st['free_duration_days']} روز\nIP Limit: {st['free_ip_limit']}\n\n"
          "برای تغییر این مقادیر از بخش «تنظیمات بات» استفاده کنید.")
    await _render(client,chat_id,mid,text,k.kb([[k.enter("⚙️ تنظیمات بات","a:settings")],[k.back("a:menu")]])); return True

# ---------------- channels ----------------
async def _channels(client,aid,chat_id,mid,data,cb):
    if not security.has_permission(aid,security.MANAGE_CHANNELS): await _deny(client,cb); return True
    if data.startswith("a:chan:toggle:"):
        cid=data.rsplit(":",1)[1]
        await channels.toggle(aid,cid); await __import__("main").save_state()
        return await _channels(client,aid,chat_id,mid,"a:chans",cb)
    if data.startswith("a:chan:del:"):
        cid=data.rsplit(":",1)[1]; set_pending(aid,{"action":"chan_delete","cid":cid})
        await _render(client,chat_id,mid,"⚠️ حذف کانال را با فرستادن «حذف» تأیید کن.",k.kb([[k.cancel("a:chans")]])); return True
    if data=="a:chan:add":
        set_pending(aid,{"action":"chan_add","step":"title","data":{}})
        await _render(client,chat_id,mid,"➕ نام کانال را بفرست:",k.kb([[k.cancel("a:chans")]])); return True
    rows=[]
    for c in channels.all_channels():
        rows.append([k.enter(f"📢 {str(c.get('title') or c.get('username') or c.get('chat_id'))[:30]}",f"a:chan:view:{c['id']}")])
    rows += [[k.add("➕ افزودن کانال","a:chan:add")],[k.back("a:menu")]]
    if data.startswith("a:chan:view:"):
        cid=data.rsplit(":",1)[1]; c=channels.get(cid)
        if not c: await _deny(client,cb,"کانال پیدا نشد."); return True
        await _render(client,chat_id,mid,f"📢 <b>{h(c.get('title','کانال'))}</b>\n\nشناسه: <code>{h(str(c.get('chat_id') or ''))}</code>\nusername: @{h(c.get('username') or '')}",
                      k.kb([[k.toggle("فعال",f"a:chan:toggle:{cid}",bool(c.get('is_active',True)))],[k.danger("🗑 حذف",f"a:chan:del:{cid}")],[k.back("a:chans")]])); return True
    await _render(client,chat_id,mid,"📢 <b>کانال‌های اجباری</b>\n\nعضویت در این کانال‌ها قبل از دریافت کانفیگ بررسی می‌شود.",k.kb(rows)); return True

# ---------------- backup ----------------
async def _backup(client,aid,chat_id,mid,data,cb):
    if not security.is_super_admin(aid): await _deny(client,cb); return True
    if data=="a:backup":
        st=backups.status()
        await _render(client,chat_id,mid,f"💾 <b>بکاپ / ریستور</b>\n\nوضعیت: {'فعال' if st['enabled'] else 'غیرفعال'}\nآخرین بکاپ: {st['last_at'] or '—'}\n\nفایل بکاپ فقط State ربات، API Keyهای رمزنگاری‌شده و داده‌های مدیریتی را نگه می‌دارد.",
            k.kb([[k.enter("📦 ساخت و ارسال بکاپ","a:backup:create")],[k.enter("♻️ ریستور بکاپ","a:backup:restore")],
                  [k.enter("🔁 انتقال Legacy به 3x-ui","a:backup:migrate")],[k.back("a:menu")]])); return True
    if data=="a:backup:create":
        try:
            archive,fn=await backups.create_archive(); await backups.send_archive(client,archive,fn)
            await client.answer_callback(cb,"✅ بکاپ ساخته و ارسال شد.",alert=True)
        except Exception as e: await client.answer_callback(cb,f"❌ {str(e)[:180]}",alert=True)
        return True
    if data=="a:backup:restore":
        set_pending(aid,{"action":"restore_wait_document"})
        await _render(client,chat_id,mid,"♻️ <b>ریستور</b>\n\nحالا فایل ZIP بکاپ را به همین چت ارسال کن.\n\nهیچ فایل دیگری پذیرفته نمی‌شود و قبل از جایگزینی State اعتبارسنجی می‌شود.",k.kb([[k.cancel("a:backup")]])); return True
    if data=="a:backup:migrate":
        keys=[r for r in xui_manager.all_records() if r["enabled"]]
        rows=[[k.enter(f"🖥 {r['name'][:30]}",f"a:backup:migrate:{r['id']}")] for r in keys]
        rows.append([k.back("a:backup")])
        await _render(client,chat_id,mid,"🔁 <b>انتقال Legacy به 3x-ui</b>\n\nAPI مقصد را انتخاب کن. Inbound همان Inbound تنظیم‌شده روی آن API خواهد بود.",k.kb(rows)); return True
    if data.startswith("a:backup:migrate:"):
        kid=data.rsplit(":",1)[1]
        try:
            result=await backups.migrate_legacy(kid)
            msg=f"✅ انتقال تمام شد.\n\nمهاجرت‌شده: {result['migrated']}\nردشده: {result['skipped']}"
            if result["errors"]: msg+="\n\n⚠️ خطاها:\n"+"\n".join(result["errors"][:8])
        except Exception as e: msg=f"❌ انتقال انجام نشد: {str(e)[:300]}"
        await _render(client,chat_id,mid,msg,k.kb([[k.back("a:backup")]])); return True
    return False

# ---------------- settings ----------------
async def _settings(client,aid,chat_id,mid,data,cb):
    if not security.is_super_admin(aid): await _deny(client,cb); return True
    if data=="a:settings":
        keys=["free_quota_total","free_volume_gb","free_duration_days","free_ip_limit","free_cooldown_seconds","require_channels","maintenance_mode","support_enabled"]
        lines=["⚙️ <b>تنظیمات بات</b>",""]
        for key in keys: lines.append(f"• <code>{key}</code> = <b>{h(str(store.setting(key)))}</b>")
        await _render(client,chat_id,mid,"\n".join(lines),k.kb([
            [k.enter("🎁 تعداد کانفیگ رایگان","a:setting:quota")],
            [k.enter("📦 حجم / مدت / IP","a:setting:spec")],
            [k.toggle("عضویت اجباری","a:setting:channels",bool(store.setting("require_channels",True)))],
            [k.toggle("حالت تعمیرات","a:setting:maint",bool(store.setting("maintenance_mode",False)))],
            [k.back("a:menu")]])); return True
    if data=="a:setting:quota":
        set_pending(aid,{"action":"setting","key":"free_quota_total"})
        await _render(client,chat_id,mid,"🎁 تعداد کل کانفیگ رایگان برای هر کاربر را بفرست:",k.kb([[k.cancel("a:settings")]])); return True
    if data=="a:setting:spec":
        set_pending(aid,{"action":"setting_multi","keys":["free_volume_gb","free_duration_days","free_ip_limit"],"step":0})
        await _render(client,chat_id,mid,"📦 حجم هر کانفیگ (GB) را بفرست:",k.kb([[k.cancel("a:settings")]])); return True
    if data=="a:setting:channels":
        store.set_setting("require_channels",not bool(store.setting("require_channels",True))); await __import__("main").save_state()
        return await _settings(client,aid,chat_id,mid,"a:settings",cb)
    if data=="a:setting:maint":
        store.set_setting("maintenance_mode",not bool(store.setting("maintenance_mode",False))); await __import__("main").save_state()
        return await _settings(client,aid,chat_id,mid,"a:settings",cb)
    return False

# ---------------- tickets/broadcast ----------------
async def _tickets(client,aid,chat_id,mid,data,cb):
    if not security.has_permission(aid,security.MANAGE_SUPPORT): await _deny(client,cb); return True
    if data.startswith("a:tkt:"):
        tid=data.rsplit(":",1)[1]; t=support.get(tid)
        if not t: await _deny(client,cb,"تیکت پیدا نشد."); return True
        if data.startswith("a:tkt:reply:"):
            set_pending(aid,{"action":"ticket_reply","ticket_id":tid})
            await _render(client,chat_id,mid,"✍️ پاسخ تیکت را بفرست:",k.kb([[k.cancel("a:tickets")]])); return True
        await _render(client,chat_id,mid,f"🛟 <b>تیکت #{tid}</b>\n\nکاربر: <code>{t.get('telegram_id')}</code>\nوضعیت: {t.get('status')}\n\n{h(t.get('last_message',''))}",
                      k.kb([[k.enter("✍️ پاسخ",f"a:tkt:reply:{tid}")],[k.back("a:tickets")]])); return True
    rows=[]
    for t in support.listing(limit=15): rows.append([k.enter(f"🛟 #{t['id']} · {t.get('status','open')}",f"a:tkt:{t['id']}")])
    rows.append([k.back("a:menu")]); await _render(client,chat_id,mid,"🛟 <b>تیکت‌ها</b>",k.kb(rows)); return True

async def _broadcast(client,aid,chat_id,mid,cb):
    if not security.has_permission(aid,security.MANAGE_SUPPORT): await _deny(client,cb); return True
    set_pending(aid,{"action":"broadcast"})
    await _render(client,chat_id,mid,"📣 متن پیام همگانی را بفرست.\n\nارسال به کاربران ثبت‌شده انجام می‌شود و خطاهای Telegram باعث توقف کل عملیات نمی‌شوند.",k.kb([[k.cancel("a:menu")]])); return True

# ---------------- pending input ----------------
async def handle_pending_text(client,rec,chat_id,text,photo=""):
    aid=int(rec["telegram_id"]); p=get_pending(aid)
    if not p:return False
    action=p.get("action")
    try:
        if action=="xui_add":
            step=p["step"]; d=p["data"]
            if step=="name": d["name"]=text; p["step"]="url"; prompt="آدرس کامل پنل 3x-ui را بفرست (مثلاً https://example.com):"
            elif step=="url": d["base_url"]=text; p["step"]="token"; prompt="API Token را بفرست. توکن ماسک می‌شود و در پیام‌های بعدی نمایش داده نمی‌شود:"
            elif step=="token": d["token"]=text; p["step"]="inbound"; prompt="Inbound ID را بفرست:"
            elif step=="inbound":
                d["inbound_id"]=int(text); p["step"]="max"; prompt="حداکثر تعداد کانفیگ برای این API را بفرست (0 = نامحدود):"
            elif step=="max":
                d["max_configs"]=int(text); p["step"]="gb"; prompt="حداکثر حجم اختصاص‌یافته کل این API بر حسب GB (0 = نامحدود):"
            else:
                d["max_total_gb"]=float(text); clear_pending(aid)
                r=await xui_manager.add(**d)
                await _render(client,chat_id,None,"✅ API با موفقیت اضافه شد.\n\nToken در این بات به‌صورت رمزنگاری‌شده ذخیره می‌شود.",k.kb([[k.enter("🖥 مدیریت APIها","a:xui")],[k.back("a:menu")]])); return True
            set_pending(aid,p); await client.send_message(chat_id,prompt,k.kb([[k.cancel("a:xui")]])); return True
        if action=="xui_delete":
            if text.strip()!="حذف": return True
            kid=p["kid"]; clear_pending(aid); __import__("main").XUI_KEYS.pop(kid,None); await __import__("main").save_state()
            await _render(client,chat_id,None,"✅ تنظیمات API حذف شد. کلاینت‌های 3x-ui دست‌نخورده باقی ماندند.",k.kb([[k.back("a:xui")]])); return True
        if action=="setting":
            val=float(text) if "." in text else int(text); store.set_setting(p["key"],val); clear_pending(aid); await __import__("main").save_state()
            await _settings(client,aid,chat_id,None,"a:settings",None); return True
        if action=="setting_multi":
            key=p["keys"][p["step"]]; val=float(text) if "." in text else int(text); store.set_setting(key,val); p["step"]+=1
            if p["step"]>=len(p["keys"]): clear_pending(aid); await __import__("main").save_state(); await _settings(client,aid,chat_id,None,"a:settings",None); return True
            prompts=["📦 حجم هر کانفیگ (GB) را بفرست:","⏳ مدت اعتبار بر حسب روز را بفرست:","👥 IP Limit را بفرست:"]
            await client.send_message(chat_id,prompts[p["step"]],k.kb([[k.cancel("a:settings")]])); return True
        if action=="chan_delete":
            if text.strip()!="حذف": return True
            await channels.delete(aid,p["cid"]); clear_pending(aid); await __import__("main").save_state()
            await client.send_message(chat_id,"✅ کانال حذف شد.",k.kb([[k.back("a:chans")]])); return True
        if action=="chan_add":
            d=p["data"]; step=p["step"]
            if step=="title":
                d["title"]=text; p["step"]="ref"; await client.send_message(chat_id,"username یا chat_id کانال را بفرست (مثلاً @channel):",k.kb([[k.cancel("a:chans")]])); return True
            d["username"]=text.lstrip("@") if text.startswith("@") else ""; d["chat_id"]=text if not text.startswith("@") else ""
            await channels.create(aid,d["title"],username=d["username"],chat_id=d["chat_id"]); clear_pending(aid); await __import__("main").save_state()
            await client.send_message(chat_id,"✅ کانال اضافه شد.",k.kb([[k.back("a:chans")]])); return True
        if action=="quota_user":
            uid=int(p["uid"]); await quota.set_user_quota(aid,uid,total=int(text)); clear_pending(aid); await __import__("main").save_state()
            await client.send_message(chat_id,"✅ سهمیه کاربر تغییر کرد.",k.kb([[k.back(f"a:user:{uid}")]])); return True
        if action=="ticket_reply":
            tid=p["ticket_id"]; clear_pending(aid)
            t=await support.add_admin_reply(aid,tid,text)
            await __import__("main").save_state()
            await client.send_message(chat_id,"✅ پاسخ ثبت شد.",k.kb([[k.back("a:tickets")]]))
            try: await client.send_message(int(t["telegram_id"]),f"🛟 <b>پاسخ پشتیبانی</b>\n\n{h(text)}",k.kb([[k.back("u:menu")]]))
            except Exception: pass
            return True
        if action=="broadcast":
            clear_pending(aid); await client.send_message(chat_id,"⏳ ارسال شروع شد...")
            result=await broadcast.create(aid,text)
            await client.send_message(chat_id,f"📣 ارسال در صف قرار گرفت.\n\n👥 مخاطبان: {result.get("total",0)}\n🆔 شناسه: {result.get("id")}",k.kb([[k.back("a:menu")]])); return True
    except Exception as e:
        log.exception("admin pending error")
        await client.send_message(chat_id,f"❌ عملیات انجام نشد: {h(str(e)[:300])}",k.kb([[k.back("a:menu")]]))
        return True
    return False

async def handle_pending_document(client,rec,chat_id,document):
    aid=int(rec["telegram_id"]); p=get_pending(aid)
    if not p or p.get("action")!="restore_wait_document": return False
    clear_pending(aid)
    try:
        data=await client.download_file(document.get("file_id"))
        result=await backups.restore_archive(data)
        await client.send_message(chat_id,
            f"✅ بکاپ ریستور شد.\n\n👥 کاربران: {result.get('users',0)}\n📦 رکوردهای قدیمی: {result.get('legacy_configs',0)}\n🖥 APIها: {result.get('api_keys',0)}\n\nاگر بکاپ نسخهٔ قدیمی پنل بود، کانفیگ‌های قدیمی به‌صورت «Legacy» نگه داشته می‌شوند و برای ساخت مجدد روی 3x-ui باید از API جدید استفاده شود.",
            k.kb([[k.enter("🖥 APIهای 3x-ui","a:xui")],[k.back("a:menu")]]))
        return True
    except Exception as e:
        await client.send_message(chat_id,f"❌ ریستور انجام نشد: {h(str(e)[:300])}",k.kb([[k.back("a:backup")]])); return True

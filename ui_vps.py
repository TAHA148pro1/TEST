# ui_vps.py — v22: صفحه‌ی «سرورها (VPS) و اسکن پورت» + ویزارد «بدون سرور / با سرور» + نوار دکمه‌های کلاینت
VPS_TAB = '''<div class="tab" data-pg="vps"><i class="ti ti-server-2"></i><span data-i18n="nav_vps">سرورها (VPS)</span></div>
      '''

# نوار دکمه‌های همیشه‌دیدنی زیر هیرو (رنگ ثابت، بدون وابستگی به انیمیشن/گرادیان)
CLIENT_BAR = '''
      <div class="vw-cbar" id="vwClientBar">
        <button class="cb c1" onclick="gotoPage('clientmgr')"><i class="ti ti-user-plus"></i><b>ساخت کلاینت</b><small>روی اینباند دلخواه</small></button>
        <button class="cb c2" onclick="openAutoLink(event)"><i class="ti ti-bolt"></i><b>ساخت سریع</b><small>بدون سرور یا با سرور</small></button>
        <button class="cb c3" onclick="vwAutoAll()"><i class="ti ti-wand"></i><b>همه‌ی پروتکل‌ها</b><small>یک لینک اشتراک</small></button>
        <button class="cb c4" onclick="gotoPage('links')"><i class="ti ti-world-www"></i><b>اینباندها</b><small>لیست و مدیریت</small></button>
        <button class="cb c5" onclick="gotoPage('vps')"><i class="ti ti-server-2"></i><b>سرورهای VPS</b><small>افزودن سرور</small></button>
        <button class="cb c6" onclick="gotoPage('vps');setTimeout(()=>{const e=document.getElementById('vpsScanHost');e&&e.focus()},300)"><i class="ti ti-scan"></i><b>اسکن پورت</b><small>کدام پورت باز است؟</small></button>
      </div>
'''

VPS_PAGE = r'''
    <!-- VPS SERVERS + PORT SCAN -->
    <div class="page" id="pg-vps">
      <div class="pg-head"><div><div class="eyebrow"><span class="live-dot"></span> VODIWALKER · VPS</div><h1>سرورها (VPS) و اسکن پورت</h1>
        <p>سرور خودت را ثبت کن، پورت را انتخاب کن (تکی یا چندتایی) و با اسکن ببین کدام پورت‌ها باز است. بعد در «ساخت سریع» گزینه‌ی «با سرور» را بزن.</p></div>
        <div class="toolbar"><button class="btn" onclick="loadVps()"><i class="ti ti-refresh"></i>بروزرسانی</button><button class="btn primary" onclick="vpsOpenForm(null)"><i class="ti ti-plus"></i>افزودن سرور</button></div></div>

      <section class="vps-card" id="vpsScanCard">
        <h3><i class="ti ti-scan"></i> اسکن پورت</h3>
        <div class="vps-row">
          <div class="vps-f grow"><label>آدرس سرور (IP یا دامنه)</label><input id="vpsScanHost" class="vps-inp" list="vpsHostList" placeholder="مثلاً 203.0.113.10" dir="ltr"><datalist id="vpsHostList"></datalist></div>
          <div class="vps-f"><label>پورت‌ها</label><select id="vpsScanSet" class="vps-inp" onchange="document.getElementById('vpsScanCustom').style.display=this.value==='custom'?'':'none'"><option value="common">رایج (~۵۰ پورت)</option><option value="1-1024">۱ تا ۱۰۲۴</option><option value="custom">سفارشی…</option></select></div>
          <div class="vps-f" id="vpsScanCustom" style="display:none"><label>سفارشی</label><input id="vpsScanPorts" class="vps-inp" placeholder="80,443,8000-8100" dir="ltr"></div>
          <div class="vps-f"><label>&nbsp;</label><button class="btn primary" id="vpsScanBtn" onclick="vpsRunScan()"><i class="ti ti-scan"></i>شروع اسکن</button></div>
        </div>
        <small class="vps-hint">اسکن از روی خود پنل انجام می‌شود، پس نتیجه همان چیزی است که از اینترنت دیده می‌شود. «آزاد» یعنی فایروال عبور می‌دهد و چیزی روی آن پورت نیست؛ برای Xray ایده‌آل است.</small>
        <div id="vpsScanOut"></div>
      </section>

      <section class="vps-card" id="vpsSniCard">
        <h3><i class="ti ti-world"></i> اسکنر SNI (بهترین SNI برای Reality)</h3>
        <div class="vps-row">
          <div class="vps-f grow"><label>دامنه‌های دلخواه (اختیاری، با فاصله یا ویرگول جدا کن)</label><textarea id="vpsSniCustom" class="vps-inp" rows="2" dir="ltr" placeholder="example.com, mysite.org"></textarea></div>
          <div class="vps-f"><label>برای سرور</label><select id="vpsSniSrv" class="vps-inp"><option value="">— بدون سرور —</option></select></div>
          <div class="vps-f"><label>&nbsp;</label><button class="btn primary" id="vpsSniBtn" onclick="vpsRunSni()"><i class="ti ti-search"></i>پیدا کردن بهترین SNI</button></div>
        </div>
        <small class="vps-hint">لیستی از سایت‌های بزرگ بررسی می‌شود؛ فقط سایت‌هایی که TLS 1.3 و HTTP/2 و گواهی معتبر دارند مناسب Reality هستند و از سریع‌ترین به کندترین مرتب می‌شوند. روی هر مورد بزنی کپی می‌شود.</small>
        <div id="vpsSniOut"></div>
      </section>

      <div class="vps-sec-h"><h3><i class="ti ti-server-2"></i> سرورهای من</h3></div>
      <div id="vpsList" class="vps-grid"></div>
    </div>
'''

VPS_CSS = r'''
/* ===== v22 · VPS + client buttons ===== */
.vw-hero .btn,.pg-head .btn,.toolbar .btn{opacity:1!important;visibility:visible!important}
.btn:before,.btn:after{pointer-events:none}
.btn>*{position:relative;z-index:1}
.vw-hero .vh-actions{display:flex;flex-wrap:wrap;gap:10px}
.vw-hero .vh-actions .btn{flex:1 1 150px;min-height:44px;justify-content:center;white-space:nowrap}
.vps-chip.free.pick{cursor:pointer}.vps-chip.free.pick:hover{filter:brightness(1.25)}.vps-chip.sel{outline:2px solid #a78bfa}
.vps-sni{display:flex;flex-direction:column;gap:6px;margin-top:8px}
.vps-sni-r{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:8px 12px;border-radius:12px;border:1px solid rgba(120,130,170,.28);background:rgba(120,130,170,.08);cursor:pointer;font-size:13px}
.vps-sni-r:hover{border-color:#34d399}.vps-sni-r b{direction:ltr;font-family:ui-monospace,monospace}.vps-sni-r span{color:#34d399;font-size:12px;direction:ltr}
.vps-sni-r.top{border-color:#f59e0b;background:rgba(245,158,11,.1)}
.vw-hero .btn{white-space:nowrap;flex:0 0 auto;min-width:max-content}
.vw-cbar{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:14px 0}
.vw-cbar .cb{--c:#6366f1;display:flex;flex-direction:column;align-items:flex-start;gap:3px;text-align:right;padding:13px 14px;border-radius:16px;border:1px solid color-mix(in srgb,var(--c) 55%,transparent);background:color-mix(in srgb,var(--c) 18%,var(--bg2,#12161f));color:var(--txt,inherit);cursor:pointer;font:inherit;min-height:84px;opacity:1;visibility:visible}
.vw-cbar .cb i{font-size:22px;color:var(--c)}
.vw-cbar .cb b{font-size:13.5px;color:var(--txt,inherit)}
.vw-cbar .cb small{font-size:11px;color:var(--sub,#9aa);opacity:.9}
.vw-cbar .cb:hover{transform:translateY(-2px);border-color:var(--c)}
.vw-cbar .c1{--c:#a78bfa}.vw-cbar .c2{--c:#f59e0b}.vw-cbar .c3{--c:#34d399}.vw-cbar .c4{--c:#38bdf8}.vw-cbar .c5{--c:#f472b6}.vw-cbar .c6{--c:#22d3ee}
.vps-card{border:1px solid var(--line,#2a3140);background:var(--bg2,#12161f);border-radius:18px;padding:16px;margin:14px 0}
.vps-card h3,.vps-sec-h h3{margin:0 0 10px;font-size:15px;display:flex;align-items:center;gap:8px}
.vps-row{display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end}
.vps-f{display:flex;flex-direction:column;gap:4px;min-width:130px}.vps-f.grow{flex:1 1 220px}
.vps-f label{font-size:12px;color:var(--sub,#9aa)}
.vps-inp{padding:10px 12px;border-radius:11px;border:1px solid var(--line,#333);background:var(--glass,#0003);color:inherit;font:inherit;width:100%;box-sizing:border-box}
.vps-hint{display:block;margin-top:8px;color:var(--sub,#9aa);font-size:11.5px;line-height:1.8}
.vps-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:12px}
.vps-srv{border:1px solid var(--line,#2a3140);background:var(--bg2,#12161f);border-radius:18px;padding:14px;display:flex;flex-direction:column;gap:9px}
.vps-srv .h{display:flex;justify-content:space-between;align-items:center;gap:8px}
.vps-srv .h b{font-size:14.5px}.vps-srv .host{direction:ltr;font:12px ui-monospace,monospace;color:var(--sub,#9aa)}
.vps-badges{display:flex;flex-wrap:wrap;gap:6px}
.vps-b{font-size:11px;padding:3px 9px;border-radius:99px;background:#6366f122;color:#c4b5fd}
.vps-b.ok{background:#34d39922;color:#6ee7b7}.vps-b.warn{background:#f59e0b22;color:#fcd34d}.vps-b.bad{background:#ef444422;color:#fca5a5}
.vps-ports{display:flex;flex-wrap:wrap;gap:6px;direction:ltr}
.vps-ports span{font:11px ui-monospace,monospace;padding:3px 8px;border-radius:8px;background:#ffffff0f}
.vps-acts{display:flex;flex-wrap:wrap;gap:6px}.vps-acts .btn{padding:7px 10px;font-size:12px}
.vps-msg{font-size:12px;line-height:1.8;padding:8px 10px;border-radius:11px;background:#6366f114;display:none}
.vps-chips{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0;direction:ltr}
.vps-chip{font:11.5px ui-monospace,monospace;padding:4px 9px;border-radius:9px;border:1px solid transparent}
.vps-chip.open{background:#f59e0b22;border-color:#f59e0b66;color:#fcd34d}
.vps-chip.free{background:#34d39922;border-color:#34d39966;color:#6ee7b7}
.vps-res h4{margin:12px 0 4px;font-size:12.5px}
.vps-verdict{padding:10px 12px;border-radius:12px;background:#6366f122;font-size:12.5px;line-height:1.8;margin-top:12px}
.vps-choice{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:12px 0}
.vps-ch{border:2px solid var(--line,#2a3140);border-radius:16px;padding:14px;cursor:pointer;text-align:right}
.vps-ch.on{border-color:#a78bfa;background:#a78bfa1a}
.vps-ch i{font-size:24px;display:block;margin-bottom:4px;color:#a78bfa}.vps-ch b{display:block;font-size:13.5px}.vps-ch small{color:var(--sub,#9aa);font-size:11.5px;line-height:1.7}
.vps-seg{display:flex;gap:8px;margin:6px 0}
.vps-seg button{flex:1;padding:10px;border-radius:12px;border:1px solid var(--line,#333);background:transparent;color:inherit;cursor:pointer;font:inherit;font-size:12.5px;line-height:1.6}
.vps-seg button.on{border-color:#34d399;background:#34d3991a}.vps-seg button[disabled]{opacity:.45;cursor:not-allowed}
.vps-pf{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:8px;margin-top:6px}
@media(max-width:560px){.vps-choice{grid-template-columns:1fr}}
'''

VPS_JS = r'''
<script>
/* ===================== v22 · VPS servers / port scan / wizard ===================== */
let VPS_LIST = [];
const vE = s => escapeHtml(String(s == null ? '' : s));
const vModeFa = m => m === 'single' ? 'پورت تکی' : 'چندپورتی';
async function vpsFetch(){ const r = await api('/api/vps'); VPS_LIST = r.servers || []; if(typeof vpsFillSniSel==='function') vpsFillSniSel(); return r; }
function vpsFillSniSel(){ const el = document.getElementById('vpsSniSrv'); if(!el) return; const cur = el.value;
  el.innerHTML = '<option value="">— بدون سرور —</option>' + VPS_LIST.map(s=>`<option value="${s.id}">${vE(s.name)} · ${vE(s.host)}</option>`).join(''); el.value = cur; }
function vpsSniHtml(r, pickable){
  const rows = (r.good||[]).map((g,i)=>`<div class="vps-sni-r ${i<3?'top':''}" data-d="${vE(g.domain)}"><b>${i<3?'⭐ ':''}${vE(g.domain)}</b><span>${g.ms} ms · ${vE(g.alpn||'')}</span></div>`).join('');
  const none = '<div class="vps-verdict" style="background:#ef444422">هیچ SNI مناسبی پیدا نشد (اینترنت پنل را بررسی کن).</div>';
  const cmd = r.vps_cmd ? `<div class="vps-verdict" style="margin-top:8px">رتبه‌بندی از دید خود VPS (دقیق‌تر) — این را روی VPS اجرا کن:<br><code dir="ltr" style="display:block;margin-top:4px;word-break:break-all">${vE(r.vps_cmd)}</code><button class="btn" style="margin-top:6px" data-c="${vE(r.vps_cmd)}" onclick="navigator.clipboard.writeText(this.dataset.c).then(()=>toast('کپی شد ✓'))"><i class="ti ti-copy"></i>کپی دستور</button></div>` : '';
  return `<div class="vps-res"><div class="vps-verdict">${(r.good||[]).length} SNI مناسب از ${r.scanned} مورد · ${r.seconds}s<br><small>${pickable?'روی یکی بزن تا انتخاب شود.':'روی یکی بزن تا کپی شود.'}</small></div>
    <div class="vps-sni">${rows||none}</div>${cmd}<small class="vps-hint">${vE(r.note||'')}</small></div>`;
}
async function vpsSniCall(custom, sid){ return api('/api/vps/sni-scan',{method:'POST',body:JSON.stringify({custom:custom||'', server_id:sid||''})}); }
async function vpsRunSni(){
  const out = document.getElementById('vpsSniOut'), btn = document.getElementById('vpsSniBtn');
  btn.disabled = true; out.innerHTML = '<div class="vps-verdict">در حال بررسی SNI ها… (حدود ۱۰ ثانیه)</div>';
  try{ const r = await vpsSniCall(document.getElementById('vpsSniCustom').value, document.getElementById('vpsSniSrv').value);
    out.innerHTML = vpsSniHtml(r, false);
    out.querySelectorAll('.vps-sni-r').forEach(el=>el.onclick=()=>navigator.clipboard.writeText(el.dataset.d).then(()=>toast(el.dataset.d+' کپی شد ✓')));
  }catch(e){ out.innerHTML = `<div class="vps-verdict" style="background:#ef444422">${vE(e.message)}</div>`; }
  btn.disabled = false;
}
function vpsPortsHtml(sv){
  const p = sv.ports || {};
  if(sv.mode === 'single') return `<span>همه‌ی پروتکل‌ها :${p.tcp}</span><span>WG UDP :${p.wg}</span>`;
  return `<span>TCP :${p.tcp}</span><span>gRPC :${p.grpc}</span><span>XHTTP :${p.xhttp}</span><span>Trojan :${p.trojan||'—'}</span><span>SS :${p.ss||'—'}</span><span>VMess :${p.vmess||'—'}</span><span>WG UDP :${p.wg}</span>`;
}
async function loadVps(){
  const box = document.getElementById('vpsList'); if(!box) return;
  try{ await vpsFetch(); }catch(e){ box.innerHTML = `<div class="vps-card">${vE(e.message)}</div>`; return; }
  const dl = document.getElementById('vpsHostList'); if(dl) dl.innerHTML = VPS_LIST.map(s=>`<option value="${vE(s.host)}">${vE(s.name)}</option>`).join('');
  if(!VPS_LIST.length){
    box.innerHTML = `<div class="vps-card" style="grid-column:1/-1;text-align:center;padding:26px"><i class="ti ti-server-2" style="font-size:34px;color:#a78bfa"></i><p style="margin:8px 0">هنوز سروری اضافه نکرده‌ای.</p><button class="btn primary" onclick="vpsOpenForm(null)"><i class="ti ti-plus"></i>افزودن اولین سرور</button></div>`;
    return;
  }
  box.innerHTML = VPS_LIST.map(s=>{
    const ls = s.last_scan, lc = s.last_check;
    const chk = lc ? (lc.running ? '<span class="vps-b ok">Xray فعال ✓</span>' : '<span class="vps-b warn">Xray هنوز بالا نیست</span>') : '';
    const sug = ls && ls.suggest && ls.suggest.single ? `<span class="vps-b">پیشنهاد اسکن: ${ls.suggest.single}</span>` : '';
    return `<div class="vps-srv" id="vs_${s.id}">
      <div class="h"><b><i class="ti ti-server-2"></i> ${vE(s.name)}</b><span class="vps-b">${vModeFa(s.mode)}</span></div>
      <div class="host">${vE(s.host)} · SNI ${vE(s.sni)}</div>
      <div class="vps-ports">${vpsPortsHtml(s)}</div>
      <div class="vps-badges"><span class="vps-b ${s.links?'ok':''}">${s.links} کانفیگ</span>${chk}${sug}</div>
      <div class="vps-acts">
        <button class="btn primary" onclick="vpsQuickCreate('${s.id}')"><i class="ti ti-bolt"></i>ساخت اشتراک</button>
        <button class="btn" onclick="vpsScanServer('${s.id}')"><i class="ti ti-scan"></i>اسکن پورت</button>
        <button class="btn" onclick="vpsCheck('${s.id}')"><i class="ti ti-plug-connected"></i>تست اتصال</button>
        <button class="btn" onclick="vpsCopyInstall('${s.id}')"><i class="ti ti-copy"></i>دستور نصب</button>
        <button class="btn" onclick="vpsOpenForm('${s.id}')"><i class="ti ti-pencil"></i></button>
        <button class="btn" onclick="vpsDel('${s.id}')"><i class="ti ti-trash"></i></button>
      </div><div class="vps-msg" id="vm_${s.id}"></div></div>`;
  }).join('');
}
function vpsCopyInstall(id){ const s = VPS_LIST.find(x=>x.id===id); if(!s) return; navigator.clipboard.writeText(s.install_cmd).then(()=>toast('دستور نصب کپی شد — روی VPS (Ubuntu/Debian با root) اجرا کن ✓')).catch(()=>prompt('کپی کن:', s.install_cmd)); }
async function vpsDel(id){
  const s = VPS_LIST.find(x=>x.id===id); if(!s) return;
  if(!confirm('سرور «'+s.name+'» حذف شود؟')) return;
  try{ await api('/api/vps/'+id,{method:'DELETE'}); toast('حذف شد'); loadVps(); }catch(e){ toast(e.message,false); }
}
async function vpsCheck(id){
  const m = document.getElementById('vm_'+id); if(m){ m.style.display='block'; m.textContent='در حال تست…'; }
  try{ const r = await api('/api/vps/'+id+'/check',{method:'POST'});
    const names = {tcp:'TCP',grpc:'gRPC',xhttp:'XHTTP'}; const st = {open:'باز ✅',closed:'آزاد (Xray بالا نیست)',filtered:'بسته/فیلتر ❌'};
    if(m) m.innerHTML = vE(r.message)+'<br>'+Object.entries(r.ports).map(([k,v])=>`${names[k]||k} :${v.port} → ${st[v.state]}${v.ms!=null?' · '+v.ms+'ms':''}`).join('<br>');
    loadVps();
  }catch(e){ if(m) m.textContent = e.message; }
}
function vpsScanServer(id){ const s = VPS_LIST.find(x=>x.id===id); if(!s) return; const h=document.getElementById('vpsScanHost'); h.value=s.host; window.scrollTo({top:0,behavior:'smooth'}); vpsRunScan(); }

function vpsScanHtml(r, forForm){
  const open = (r.open||[]).map(o=>`<span class="vps-chip open">${o.port}${o.service?' · '+vE(o.service):''}</span>`).join('') || '<small>—</small>';
  const RISKY = [21,22,25,53,110,143,3306,3389,5432,5900,6379];
  const free = (r.closed||[]).slice(0,60).map(p=> RISKY.includes(p) ? `<span class="vps-chip free" style="opacity:.45" title="پورت سیستمی؛ برای Xray انتخاب نکن">${p}</span>` : `<span class="vps-chip free${forForm?' pick':''}" data-p="${p}">${p}</span>`).join('') || '<small>—</small>';
  const sg = r.suggest||{}; let sug = '';
  if(sg.single) sug += `<div>⭐ پورت پیشنهادی (تکی): <b dir="ltr">${sg.single}</b></div>`;
  if(sg.multi) sug += `<div>⭐ چندپورتی: <b dir="ltr">TCP ${sg.multi.tcp} · gRPC ${sg.multi.grpc} · XHTTP ${sg.multi.xhttp}${sg.multi.trojan?` · Trojan ${sg.multi.trojan} · SS ${sg.multi.ss} · VMess ${sg.multi.vmess}`:''}</b></div>`;
  return `<div class="vps-res"><div class="vps-verdict">${vE(r.verdict)}<br><small>IP: <span dir="ltr">${vE(r.ip)}</span> · ${r.scanned} پورت در ${r.seconds}s</small>${sug?'<div style="margin-top:6px">'+sug+'</div>':''}</div>
    <h4>🟠 باز (سرویس فعال)</h4><div class="vps-chips">${open}</div>
    <h4>🟢 آزاد و قابل‌استفاده برای Xray</h4><div class="vps-chips">${free}</div>
    <h4>🔴 فیلتر/بلاک: ${r.filtered_count} پورت</h4><small class="vps-hint">${vE(r.note)}</small></div>`;
}
async function vpsRunScan(){
  const host = (document.getElementById('vpsScanHost').value||'').trim();
  const set = document.getElementById('vpsScanSet').value;
  const ports = set==='custom' ? (document.getElementById('vpsScanPorts').value||'').trim() : set;
  const out = document.getElementById('vpsScanOut'), btn = document.getElementById('vpsScanBtn');
  if(!host){ toast('آدرس سرور را وارد کن', false); return; }
  btn.disabled = true; out.innerHTML = '<div class="vps-verdict">در حال اسکن… (چند ثانیه)</div>';
  try{
    const sv = VPS_LIST.find(s=>s.host===host.toLowerCase());
    const body = sv ? {server_id: sv.id, ports} : {host, ports};
    const r = await api('/api/vps/scan',{method:'POST',body:JSON.stringify(body)});
    out.innerHTML = vpsScanHtml(r); if(sv) loadVps();
  }catch(e){ out.innerHTML = `<div class="vps-verdict" style="background:#ef444422">${vE(e.message)}</div>`; }
  btn.disabled = false;
}

/* ---- فرم افزودن/ویرایش سرور ---- */
function vpsOpenForm(id, after){
  const sv = id ? VPS_LIST.find(x=>x.id===id) : null;
  const locked = sv && sv.links > 0;
  const p = (sv && sv.ports) || {tcp:443, grpc:444, xhttp:445, wg:51820};
  let mode = (sv && sv.mode) || 'multi';
  const o = vwModal(`<h3 style="margin:0 0 4px">${sv?'ویرایش سرور':'افزودن سرور (VPS)'}</h3>
    <small class="vps-hint" style="margin:0 0 8px">سرور باید Ubuntu/Debian با دسترسی root باشد. بعد از ساخت اشتراک، یک دستور نصب می‌گیری.</small>
    ${locked?'<div class="vps-verdict" style="background:#f59e0b22">این سرور کانفیگ فعال دارد؛ فقط نام قابل تغییر است.</div>':''}
    <div class="vps-f"><label>نام سرور</label><input id="vf_name" class="vps-inp" placeholder="مثلاً هتزنر آلمان" value="${vE(sv?sv.name:'')}"></div>
    <div class="vps-f" style="margin-top:8px"><label>آدرس سرور (IP یا دامنه)</label><input id="vf_host" class="vps-inp" dir="ltr" placeholder="203.0.113.10" value="${vE(sv?sv.host:'')}" ${locked?'disabled':''}></div>
    <div class="vps-f" style="margin-top:8px"><label>SNI ریلیتی</label><input id="vf_sni" class="vps-inp" dir="ltr" value="${vE(sv?sv.sni:'www.microsoft.com')}" ${locked?'disabled':''}></div>
    ${locked?'':'<div style="display:flex;gap:8px;margin-top:6px"><button type="button" class="btn" id="vf_sni_scan" style="flex:1"><i class="ti ti-search"></i>اسکن و پیشنهاد SNI</button></div>'}
    <div id="vf_sniout"></div>
    <div class="vps-f" style="margin-top:8px"><label>حالت پورت</label>
      <div class="vps-seg"><button type="button" id="vf_m_single" ${locked?'disabled':''}>🎯 پورت تکی<br><small>همه‌ی پروتکل‌ها روی یک پورت (+ WG روی UDP)</small></button><button type="button" id="vf_m_multi" ${locked?'disabled':''}>🌐 چندپورتی<br><small>هر پروتکل یک پورت جدا + WG</small></button></div></div>
    <div class="vps-pf" id="vf_ports">
      <div class="vps-f"><label id="vf_l_tcp">پورت TCP</label><input id="vf_tcp" class="vps-inp" dir="ltr" type="number" min="1" max="65535" value="${p.tcp}" ${locked?'disabled':''}></div>
      <div class="vps-f" data-m="multi"><label>پورت gRPC</label><input id="vf_grpc" class="vps-inp" dir="ltr" type="number" value="${p.grpc}" ${locked?'disabled':''}></div>
      <div class="vps-f" data-m="multi"><label>پورت XHTTP</label><input id="vf_xhttp" class="vps-inp" dir="ltr" type="number" value="${p.xhttp}" ${locked?'disabled':''}></div>
      <div class="vps-f" data-m="multi"><label>پورت Trojan</label><input id="vf_trojan" class="vps-inp" dir="ltr" type="number" value="${p.trojan||(+p.tcp+3)}" ${locked?'disabled':''}></div>
      <div class="vps-f" data-m="multi"><label>پورت Shadowsocks</label><input id="vf_ss" class="vps-inp" dir="ltr" type="number" value="${p.ss||(+p.tcp+4)}" ${locked?'disabled':''}></div>
      <div class="vps-f" data-m="multi"><label>پورت VMess</label><input id="vf_vmess" class="vps-inp" dir="ltr" type="number" value="${p.vmess||(+p.tcp+5)}" ${locked?'disabled':''}></div>
      <div class="vps-f"><label>پورت WireGuard (UDP)</label><input id="vf_wg" class="vps-inp" dir="ltr" type="number" value="${p.wg}" ${locked?'disabled':''}></div></div>
    ${locked?'':'<small class="vps-hint" style="margin-top:10px;display:block">نمی‌دانی کدام پورت را باز کنی؟ اسکن بزن، بعد روی یک پورت سبز بزن تا در فیلد انتخاب‌شده قرار بگیرد.</small>'}
    ${locked?'':'<div style="display:flex;gap:8px;margin-top:6px"><button class="btn" id="vf_scan" style="flex:1"><i class="ti ti-scan"></i>اسکن و پیشنهاد پورت</button></div>'}
    <div id="vf_scanout"></div>
    <div style="display:flex;gap:8px;margin-top:14px"><button class="btn primary" id="vf_save" style="flex:1"><i class="ti ti-check"></i>ذخیره</button><button class="btn" id="vf_x">انصراف</button></div>`);
  const $ = i => o.querySelector('#'+i);
  const setMode = m => { mode = m; $('vf_m_single').classList.toggle('on', m==='single'); $('vf_m_multi').classList.toggle('on', m==='multi');
    o.querySelectorAll('[data-m="multi"]').forEach(e=>e.style.display = m==='multi'?'':'none'); $('vf_l_tcp').textContent = m==='single'?'پورت (TCP + WireGuard UDP)':'پورت TCP'; };
  setMode(mode);
  $('vf_m_single').onclick = ()=>{ setMode('single'); };
  $('vf_m_multi').onclick = ()=>{ setMode('multi'); };
  $('vf_x').onclick = ()=>o.remove();
  let lastF = 'vf_tcp';
  ['vf_tcp','vf_grpc','vf_xhttp','vf_trojan','vf_ss','vf_vmess','vf_wg'].forEach(id=>{ const e=$(id); if(e) e.addEventListener('focus',()=>{ lastF = id; }); });
  if($('vf_sni_scan')) $('vf_sni_scan').onclick = async()=>{
    $('vf_sniout').innerHTML = '<div class="vps-verdict">در حال بررسی SNI ها…</div>';
    try{ const r = await vpsSniCall('', sv?sv.id:'');
      window._vfSniGood = (r.good||[]).map(g=>g.domain); $('vf_sniout').innerHTML = vpsSniHtml(r, true);
      $('vf_sniout').querySelectorAll('.vps-sni-r').forEach(el=>el.onclick=()=>{ $('vf_sni').value = el.dataset.d; toast('SNI: '+el.dataset.d); });
    }catch(e){ $('vf_sniout').innerHTML = `<div class="vps-verdict" style="background:#ef444422">${vE(e.message)}</div>`; }
  };
  if($('vf_scan')) $('vf_scan').onclick = async()=>{
    const host = ($('vf_host').value||'').trim(); if(!host){ toast('اول آدرس سرور را وارد کن', false); return; }
    $('vf_scanout').innerHTML = '<div class="vps-verdict">در حال اسکن…</div>';
    try{ const r = await api('/api/vps/scan',{method:'POST',body:JSON.stringify({host, ports:'common'})});
      $('vf_scanout').innerHTML = vpsScanHtml(r, true) + '<button class="btn" id="vf_apply" style="margin-top:8px;width:100%">✨ اعمال پورت‌های پیشنهادی</button>';
      $('vf_scanout').querySelectorAll('.vps-chip.pick').forEach(ch=>ch.onclick=()=>{
        const order = mode==='single' ? ['vf_tcp','vf_wg'] : ['vf_tcp','vf_grpc','vf_xhttp','vf_trojan','vf_ss','vf_vmess','vf_wg'];
        if(!order.includes(lastF)) lastF = 'vf_tcp';
        $(lastF).value = ch.dataset.p; if(mode==='single' && lastF==='vf_tcp') $('vf_wg').value = ch.dataset.p;
        ch.classList.add('sel'); toast('پورت '+ch.dataset.p+' ← '+({vf_tcp:'TCP',vf_grpc:'gRPC',vf_xhttp:'XHTTP',vf_trojan:'Trojan',vf_ss:'Shadowsocks',vf_vmess:'VMess',vf_wg:'WireGuard'})[lastF]);
        lastF = order[(order.indexOf(lastF)+1) % order.length]; $(lastF).focus(); });
      $('vf_apply').onclick = ()=>{ const g = r.suggest||{};
        if(mode==='single' && g.single){ $('vf_tcp').value = g.single; $('vf_wg').value = g.single; toast('پورت '+g.single+' اعمال شد'); }
        else if(mode==='multi' && g.multi){ $('vf_tcp').value=g.multi.tcp; $('vf_grpc').value=g.multi.grpc; $('vf_xhttp').value=g.multi.xhttp; if(g.multi.trojan){ $('vf_trojan').value=g.multi.trojan; $('vf_ss').value=g.multi.ss; $('vf_vmess').value=g.multi.vmess; } toast('پورت‌ها اعمال شد'); }
        else toast('پورت آزاد کافی پیدا نشد؛ پورت‌ها را دستی بده یا فایروال را باز کن', false); };
    }catch(e){ $('vf_scanout').innerHTML = `<div class="vps-verdict" style="background:#ef444422">${vE(e.message)}</div>`; }
  };
  $('vf_save').onclick = async()=>{
    const body = {name:$('vf_name').value.trim()};
    if(!locked){ body.host=$('vf_host').value.trim(); body.sni=$('vf_sni').value.trim()||'www.microsoft.com'; body.mode=mode;
      body.ports = {tcp:+$('vf_tcp').value, grpc:+$('vf_grpc').value, xhttp:+$('vf_xhttp').value, trojan:+$('vf_trojan').value, ss:+$('vf_ss').value, vmess:+$('vf_vmess').value, wg:+$('vf_wg').value}; }
    if(mode==='single' && window._vfSniGood && window._vfSniGood.length) body.snis_hint = window._vfSniGood.slice(0,10);
    try{ const r = sv ? await api('/api/vps/'+sv.id,{method:'PUT',body:JSON.stringify(body)}) : await api('/api/vps',{method:'POST',body:JSON.stringify(body)});
      o.remove(); toast('ذخیره شد ✓'); await loadVps(); if(after) after(r.server);
    }catch(e){ toast(e.message,false); }
  };
}

/* ---- ویزارد: بدون سرور / با سرور ---- */
function vwAskServerMode(){
  return new Promise(async resolve=>{
    try{ await vpsFetch(); }catch(e){}
    let done = false, sel = 'none', sid = VPS_LIST.length ? VPS_LIST[0].id : '', pm = '';
    const o = vwModal(''); const box = o.querySelector('.vw-box');
    const fin = v => { if(done) return; done = true; o.remove(); resolve(v); };
    o.addEventListener('click', e=>{ if(e.target===o) fin(null); });
    const render = () => {
      const sv = VPS_LIST.find(s=>s.id===sid); if(sv && !pm) pm = sv.mode; if(sv && sv.links>0) pm = sv.mode;
      const locked = sv && sv.links>0;
      box.innerHTML = `<h3 style="margin:0">ساخت اینباند — بدون سرور یا با سرور؟</h3>
        <div class="vps-choice"><div class="vps-ch ${sel==='none'?'on':''}" id="w_none"><i class="ti ti-cloud"></i><b>بدون سرور</b><small>فقط روی خود پنل: WS / XHTTP / TCP. نیازی به VPS نیست.</small></div>
          <div class="vps-ch ${sel==='server'?'on':''}" id="w_srv"><i class="ti ti-server-2"></i><b>با سرور (VPS)</b><small>همه‌ی پروتکل‌ها (Reality TCP/gRPC/XHTTP، Trojan، Shadowsocks، VMess، WireGuard) داخل ساب؛ بهترین کانفیگ انتخاب می‌شود.</small></div></div>
        ${sel==='server' ? (VPS_LIST.length ? `<div class="vps-f"><label>سرور</label><select id="w_sid" class="vps-inp">${VPS_LIST.map(s=>`<option value="${s.id}" ${s.id===sid?'selected':''}>${vE(s.name)} · ${vE(s.host)} (${s.links} کانفیگ)</option>`).join('')}</select></div>
          <div class="vps-f" style="margin-top:8px"><label>پورت‌ها</label><div class="vps-seg"><button type="button" id="w_pm_single" class="${pm==='single'?'on':''}" ${locked&&sv.mode!=='single'?'disabled':''}>🎯 پورت تکی<br><small>یک پورت برای همه</small></button><button type="button" id="w_pm_multi" class="${pm==='multi'?'on':''}" ${locked&&sv.mode!=='multi'?'disabled':''}>🌐 چند پورت<br><small>هر پروتکل پورت جدا</small></button></div>
          ${locked?'<small class="vps-hint">این سرور قبلاً کانفیگ دارد؛ حالت پورت قفل است.</small>':''}<div class="vps-ports" style="margin-top:4px">${sv?vpsPortsHtml(Object.assign({},sv,{mode:pm,ports:sv.ports})):''}</div></div>
          <button class="btn" id="w_add" style="margin-top:8px"><i class="ti ti-plus"></i>افزودن سرور دیگر</button>`
          : `<div class="vps-verdict">هنوز سروری ثبت نکرده‌ای.</div><button class="btn primary" id="w_add" style="margin-top:8px"><i class="ti ti-plus"></i>افزودن سرور (VPS)</button>`) : ''}
        <div style="display:flex;gap:8px;margin-top:14px"><button class="btn primary" id="w_ok" style="flex:1" ${sel==='server'&&!sid?'disabled':''}>ادامه</button><button class="btn" id="w_x">انصراف</button></div>`;
      box.querySelector('#w_none').onclick = ()=>{ sel='none'; render(); };
      box.querySelector('#w_srv').onclick = ()=>{ sel='server'; render(); };
      box.querySelector('#w_x').onclick = ()=>fin(null);
      const s1 = box.querySelector('#w_sid'); if(s1) s1.onchange = ()=>{ sid = s1.value; pm = ''; render(); };
      const a = box.querySelector('#w_pm_single'); if(a) a.onclick = ()=>{ pm='single'; render(); };
      const b = box.querySelector('#w_pm_multi'); if(b) b.onclick = ()=>{ pm='multi'; render(); };
      const ad = box.querySelector('#w_add'); if(ad) ad.onclick = ()=>vpsOpenForm(null, ns=>{ sid = ns.id; pm = ns.mode; sel='server'; render(); });
      box.querySelector('#w_ok').onclick = ()=>{
        if(sel==='none') return fin({mode:'none'});
        const s = VPS_LIST.find(x=>x.id===sid); if(!s) return;
        fin({mode:'server', server_id:sid, port_mode:pm||s.mode, server_name:s.name});
      };
    };
    render();
  });
}

/* ---- ساخت با سرور + نتیجه ---- */
async function vpsCreateWithServer(ch, extra){
  toast('در حال ساخت کانفیگ‌ها…', true);
  const b = Object.assign({all_protocols:true, best_exit:true, port:443, profile:'balanced', server_id:ch.server_id, port_mode:ch.port_mode}, extra||{});
  const r = await api('/api/links/auto',{method:'POST',body:JSON.stringify(b)});
  if(typeof loadLinks==='function') loadLinks(); loadVps(); vwShowServerResult(r); return r;
}
async function vpsQuickCreate(id){
  const s = VPS_LIST.find(x=>x.id===id); if(!s) return;
  try{ await vpsCreateWithServer({server_id:id, port_mode:s.mode}); }catch(e){ toast(e.message,false); }
}
function vwShowServerResult(r){
  const x = r.xray || {}; const best = r.best && r.best.uuid;
  const row = c=>`<div style="display:flex;justify-content:space-between;font-size:12px;padding:4px 0"><span id="vr_s_${c.uuid}">${c.live||c.ping_ms!=null?'✅':'⚪'} ${vE(c.tag)}${best===c.uuid?' ⭐':''}</span><span id="vr_${c.uuid}" dir="ltr">${c.ping_ms!=null?c.ping_ms+' ms':'—'}</span></div>`;
  const o = vwModal(`<div style="padding:10px;border-radius:12px;background:#34d39922"><b>✓ ${(r.created||[]).length} کانفیگ ساخته شد${x.server_name?' · سرور '+vE(x.server_name):''}</b>
      <div dir="ltr" style="word-break:break-all;font:11px ui-monospace,monospace;margin:6px 0">${vE(r.sub_url)}</div>
      <button class="btn" id="vr_cp"><i class="ti ti-copy"></i>کپی لینک ساب</button></div>
    ${r.sub_url?`<div style="text-align:center;margin:10px 0"><img src="${qrSrc(r.sub_url)}" width="150" height="150" style="border-radius:12px;background:#fff;padding:6px"></div>`:''}
    <div id="vr_best" class="vps-verdict" style="${r.best?'':'display:none'}">${r.best?'⭐ بهترین کانفیگ: <b>'+vE(r.best.tag)+'</b> ('+r.best.ping_ms+' ms)':''}</div>
    <div style="margin-top:8px">${(r.created||[]).map(row).join('')}</div>
    ${x.install_cmd?`<div class="vps-verdict"><b>۱) این دستور را یک‌بار روی VPS اجرا کن (Ubuntu/Debian، root):</b><pre dir="ltr" style="white-space:pre-wrap;word-break:break-all;font-size:11px;margin:6px 0">${vE(x.install_cmd)}</pre>
      <div class="vps-ports" style="margin:4px 0">${vpsPortsHtml({mode:x.mode,ports:x.ports})}</div><small class="vps-hint">${x.mode==='single'?'حالت پورت تکی: فقط همین یک پورت (TCP) و پورت UDP وایرگارد را در فایروال VPS باز کن. دستور نصب خودش ufw را تنظیم می‌کند.':'حالت چندپورتی: همه‌ی پورت‌های TCP بالا و پورت UDP وایرگارد را در فایروال VPS باز کن (دستور نصب خودش ufw را تنظیم می‌کند).'}</small>
      <button class="btn" id="vr_ic"><i class="ti ti-copy"></i>کپی دستور</button> <button class="btn primary" id="vr_pg"><i class="ti ti-antenna-bars-5"></i>۲) تست پینگ و انتخاب بهترین</button></div>`:''}
    ${r.need_server?`<div class="vps-verdict" style="background:#f59e0b22">${vE(r.skipped_note||'')}</div>`:''}
    <div style="display:flex;gap:8px;margin-top:12px"><button class="btn" id="vr_x" style="flex:1">بستن</button></div>`);
  const $ = i=>o.querySelector('#'+i);
  $('vr_x').onclick = ()=>o.remove();
  $('vr_cp').onclick = ()=>{ navigator.clipboard.writeText(r.sub_url).then(()=>toast('لینک ساب کپی شد ✓')); };
  if($('vr_ic')) $('vr_ic').onclick = ()=>{ navigator.clipboard.writeText(x.install_cmd).then(()=>toast('کپی شد ✓')); };
  if($('vr_pg')) $('vr_pg').onclick = async()=>{
    const btn = $('vr_pg'); btn.disabled = true; btn.textContent = 'در حال تست…';
    try{ const q = await api('/api/xray-server/ping',{method:'POST',body:JSON.stringify({uuids:(r.created||[]).map(c=>c.uuid)})});
      Object.entries(q.pings||{}).forEach(([k,ms])=>{ const el = o.querySelector('#vr_'+CSS.escape(k)); if(el) el.textContent = ms!=null ? ms+' ms ✅' : '❌ پاسخ نداد'; });
      const bc = (r.created||[]).find(c=>c.uuid===q.best);
      if(bc){ const bb = $('vr_best'); bb.style.display=''; bb.innerHTML = '⭐ بهترین کانفیگ: <b>'+vE(bc.tag)+'</b> ('+q.pings[q.best]+' ms)'; const s = o.querySelector('#vr_s_'+CSS.escape(bc.uuid)); if(s && !s.textContent.includes('⭐')) s.textContent += ' ⭐'; }
      else toast('هنوز هیچ‌کدام پاسخ نمی‌دهد؛ دستور نصب را اجرا کن و دوباره تست بزن', false);
    }catch(e){ toast(e.message,false); }
    btn.disabled = false; btn.textContent = '۲) تست دوباره پینگ';
  };
}

/* ---- وصل کردن ویزارد به «ساخت سریع» ---- */
(function(){
  const _oal = window.openAutoLink;
  if(typeof _oal === 'function'){
    window.openAutoLink = async function(ev){
      if(ev && ev.shiftKey) return _oal(ev);
      const ch = await vwAskServerMode(); if(!ch) return;
      if(ch.mode === 'none') return _oal({});
      try{ await vpsCreateWithServer(ch); }catch(e){ toast(e.message,false); }
    };
  }
})();
</script>
'''

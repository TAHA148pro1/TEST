THEME_V23_CSS = r'''
/* ================= v23 · Obsidian ================= */
:root{
  --r-card:20px;--r-ctl:12px;--r-pill:999px;
  --hi:rgba(255,255,255,.07);                 /* خط روشن لبه‌ی بالایی سطح‌ها */
  --sh-1:0 1px 0 var(--hi) inset,0 10px 30px -18px rgba(0,0,0,.65);
  --sh-2:0 1px 0 var(--hi) inset,0 24px 60px -24px rgba(0,0,0,.75);
  --ring:0 0 0 3px rgba(var(--accent-rgb,139,92,246),.28);
  --ease-o:cubic-bezier(.2,.8,.2,1);
}
:root[data-theme="light"]{--hi:rgba(255,255,255,.9);--sh-1:0 1px 0 var(--hi) inset,0 8px 24px -16px rgba(30,40,80,.28);--sh-2:0 1px 0 var(--hi) inset,0 22px 50px -22px rgba(30,40,80,.35)}

/* ---- پایه ---- */
html body{-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;font-feature-settings:"ss01","kern"}
::selection{background:rgba(var(--accent-rgb,139,92,246),.38);color:#fff}
*{scrollbar-width:thin;scrollbar-color:rgba(var(--accent-rgb,139,92,246),.35) transparent}
::-webkit-scrollbar{width:9px;height:9px}
::-webkit-scrollbar-thumb{background:rgba(var(--accent-rgb,139,92,246),.28);border-radius:99px;border:2px solid transparent;background-clip:padding-box}
::-webkit-scrollbar-thumb:hover{background:rgba(var(--accent-rgb,139,92,246),.5);background-clip:padding-box;border:2px solid transparent}
:where(a,button,input,select,textarea,[tabindex]):focus-visible{outline:none;box-shadow:var(--ring)!important;border-radius:var(--r-ctl)}
.num,.kpi b,.stat b,.mono,.vps-ports span,.vps-chip,table td,.sum b{font-variant-numeric:tabular-nums;font-feature-settings:"tnum"}

/* ---- سایدبار و منو ---- */
html body .sidebar{backdrop-filter:blur(18px) saturate(140%);-webkit-backdrop-filter:blur(18px) saturate(140%)}
html body .nav-sec{text-transform:none!important;letter-spacing:.02em!important;font-size:11px!important;font-weight:800!important;opacity:.7}
html body .tab{border-radius:14px;transition:background .18s var(--ease-o),color .18s var(--ease-o),transform .18s var(--ease-o);position:relative}
html body .tab:hover{transform:translateX(-2px)}
html[dir="ltr"] body .tab:hover{transform:translateX(2px)}
html body .tab.on{background:linear-gradient(90deg,rgba(var(--accent-rgb,139,92,246),.22),rgba(var(--accent-rgb,139,92,246),.06))!important;color:var(--text)!important;box-shadow:inset -3px 0 0 var(--accent),0 8px 24px -14px rgba(var(--accent-rgb,139,92,246),.7)}
html[dir="ltr"] body .tab.on{box-shadow:inset 3px 0 0 var(--accent),0 8px 24px -14px rgba(var(--accent-rgb,139,92,246),.7)}
html body .tab .ti{transition:transform .2s var(--ease-o),color .2s}
html body .tab:hover .ti{transform:scale(1.12)}
html body .tab.on .ti{color:var(--accent)}

/* ---- نوار بالا ---- */
html body .topbar{backdrop-filter:blur(16px) saturate(150%);-webkit-backdrop-filter:blur(16px) saturate(150%);border-bottom:1px solid var(--line)}

/* ---- عنوان صفحه‌ها ---- */
html body .pg-head{margin-bottom:18px}
html body .pg-head h1{font-size:clamp(22px,2.6vw,30px);font-weight:900;letter-spacing:-.02em;line-height:1.25}
html body .pg-head p{max-width:68ch;line-height:1.95;color:var(--sub)}
html body .eyebrow{text-transform:none!important;letter-spacing:.02em!important;font-weight:800;color:var(--sub)}
html body .live-dot{box-shadow:0 0 0 0 rgba(52,211,153,.55);animation:vwPulse 2.4s ease-out infinite}
@keyframes vwPulse{0%{box-shadow:0 0 0 0 rgba(52,211,153,.55)}70%{box-shadow:0 0 0 8px rgba(52,211,153,0)}100%{box-shadow:0 0 0 0 rgba(52,211,153,0)}}

/* ---- کارت‌ها و سطح‌ها ---- */
html body .card,html body .settings-card,html body .resource-card,html body .vps-card,html body .vps-srv,html body .panel{
  border:1px solid var(--line);border-radius:var(--r-card);
  background:linear-gradient(180deg,rgba(255,255,255,.04),rgba(255,255,255,.012)),var(--panel,#0b0c22);
  box-shadow:var(--sh-1)}
:root[data-theme="light"] .card,:root[data-theme="light"] .settings-card,:root[data-theme="light"] .resource-card,:root[data-theme="light"] .vps-card,:root[data-theme="light"] .vps-srv{background:#fff}
html body .panel-head{border-bottom:1px solid var(--line);padding-bottom:12px;margin-bottom:12px}
html body .panel-head b,html body .panel-head h3,html body .section-title{font-weight:900;letter-spacing:-.01em}
html body .resource-card{transition:border-color .2s,transform .2s var(--ease-o),box-shadow .2s}
html body .resource-card:hover,html body .vps-srv:hover{border-color:var(--line2);transform:translateY(-2px);box-shadow:var(--sh-2)}
html body .empty{border:1px dashed var(--line2);border-radius:var(--r-card);background:rgba(var(--accent-rgb,139,92,246),.04)}

/* ---- دکمه‌ها ---- */
html body .btn{min-height:38px;border-radius:var(--r-ctl);font-weight:800;letter-spacing:0;
  border:1px solid var(--line);background:linear-gradient(180deg,rgba(255,255,255,.06),rgba(255,255,255,.02));color:var(--text);
  transition:transform .15s var(--ease-o),border-color .15s,box-shadow .15s,background .15s,filter .15s;box-shadow:0 1px 0 var(--hi) inset}
html body .btn:hover{border-color:var(--line2);transform:translateY(-1px);filter:brightness(1.08)}
html body .btn:active{transform:translateY(0) scale(.985);filter:brightness(.96)}
html body .btn.sm{min-height:32px;border-radius:10px}
html body .btn.primary{border-color:rgba(var(--accent-rgb,139,92,246),.55);color:#fff;
  background:linear-gradient(135deg,var(--accent),var(--accent2,var(--accent)));
  box-shadow:0 1px 0 rgba(255,255,255,.28) inset,0 12px 28px -12px rgba(var(--accent-rgb,139,92,246),.85)}
html body .btn.primary:hover{box-shadow:0 1px 0 rgba(255,255,255,.3) inset,0 16px 34px -12px rgba(var(--accent-rgb,139,92,246),.95)}
html body .btn.danger{border-color:rgba(239,68,68,.4);color:#fca5a5;background:rgba(239,68,68,.08)}
html body .btn.danger:hover{background:rgba(239,68,68,.18);border-color:rgba(239,68,68,.65)}
html body .btn[disabled],html body .btn:disabled{opacity:.5;cursor:not-allowed;transform:none;filter:none}
html body .iconbtn{border-radius:var(--r-ctl);border:1px solid var(--line);background:rgba(255,255,255,.04);transition:background .15s,border-color .15s,transform .15s var(--ease-o)}
html body .iconbtn:hover{background:rgba(var(--accent-rgb,139,92,246),.14);border-color:var(--line2);transform:translateY(-1px)}

/* ---- فرم‌ها ---- */
html body input:not([type=checkbox]):not([type=radio]):not([type=range]),html body select,html body textarea,html body .vps-inp{
  border-radius:var(--r-ctl);border:1px solid var(--line);background:rgba(0,0,0,.22);color:var(--text);
  transition:border-color .15s,box-shadow .15s,background .15s}
:root[data-theme="light"] input:not([type=checkbox]):not([type=radio]):not([type=range]),:root[data-theme="light"] select,:root[data-theme="light"] textarea{background:#f7f8fc}
html body input:not([type=checkbox]):not([type=radio]):not([type=range]):hover,html body select:hover,html body textarea:hover{border-color:var(--line2)}
html body input:focus,html body select:focus,html body textarea:focus{border-color:var(--accent)!important;background:rgba(0,0,0,.3)}
html body ::placeholder{color:var(--sub2);opacity:.85}
html body label{font-weight:700}

/* ---- نشان‌ها و چیپ‌ها ---- */
html body .badge,html body .vps-b{border-radius:var(--r-pill);font-weight:800;border:1px solid rgba(var(--accent-rgb,139,92,246),.3)}
html body .vps-chip{border-radius:10px}
html body .vps-verdict{border:1px solid var(--line);border-radius:14px}
html body .vps-ports span{border:1px solid var(--line);background:rgba(255,255,255,.04)}

/* ---- جدول‌ها ---- */
html body table{border-collapse:separate;border-spacing:0;width:100%}
html body th{font-size:11.5px;font-weight:800;color:var(--sub);text-align:start;padding:11px 14px;background:rgba(255,255,255,.03);border-bottom:1px solid var(--line);position:sticky;top:0;backdrop-filter:blur(8px)}
html body td{padding:12px 14px;border-bottom:1px solid rgba(255,255,255,.045)}
:root[data-theme="light"] td{border-bottom-color:rgba(20,30,60,.07)}
html body tbody tr{transition:background .12s}
html body tbody tr:hover{background:rgba(var(--accent-rgb,139,92,246),.07)}
html body tbody tr:last-child td{border-bottom:0}

/* ---- مودال و توست ---- */
html body .vw-ov,html body .overlay{backdrop-filter:blur(10px) saturate(130%);-webkit-backdrop-filter:blur(10px) saturate(130%);background:rgba(4,5,16,.62)}
html body .vw-box,html body .modal{border:1px solid var(--line2);border-radius:24px;box-shadow:var(--sh-2),0 0 0 1px rgba(0,0,0,.4);animation:vwPop .22s var(--ease-o)}
@keyframes vwPop{from{opacity:0;transform:translateY(10px) scale(.97)}to{opacity:1;transform:none}}
html body .toast{border-radius:14px;border:1px solid var(--line2);backdrop-filter:blur(14px);box-shadow:var(--sh-2)}

/* ---- داشبورد: هیرو و نوار دکمه‌ها ---- */
html body .vw-hero{border-radius:26px;border:1px solid var(--line2);box-shadow:var(--sh-2)}
html body .vw-hero{overflow:hidden}
html body .vw-hero:before{content:"";position:absolute;inset:0;z-index:2;pointer-events:none;border-radius:inherit;
  background:linear-gradient(115deg,transparent 35%,rgba(255,255,255,.09) 50%,transparent 65%);transform:translateX(-120%);animation:vwSheen 1.6s .35s var(--ease-o) 1 forwards}
@keyframes vwSheen{to{transform:translateX(120%)}}
html body .vw-cbar .cb{border-radius:18px;box-shadow:var(--sh-1);transition:transform .18s var(--ease-o),border-color .18s,box-shadow .18s}
html body .vw-cbar .cb:hover{box-shadow:var(--sh-2),0 0 0 1px color-mix(in srgb,var(--c) 60%,transparent)}
html body .vw-cbar .cb:active{transform:translateY(0) scale(.985)}

/* ---- تب‌ها / سوییچ‌ها ---- */
html body .grp{border-radius:14px}
html body .tpl-switch,html body .switch{transition:background .18s}

/* ---- موبایل ---- */
@media(max-width:720px){
  html body .pg-head h1{font-size:21px}
  html body .card,html body .vps-card,html body .vps-srv{border-radius:18px}
  html body .btn{min-height:42px}
  html body td,html body th{padding:10px 10px}
}
@media(prefers-reduced-motion:reduce){
  html body .live-dot,html body .vw-hero:before,html body .vw-box,html body .modal{animation:none!important}
  html body .btn,html body .tab,html body .resource-card,html body .vps-srv,html body .vw-cbar .cb{transition:none!important}
}
'''

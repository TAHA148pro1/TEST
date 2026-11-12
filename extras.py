# extras.py — v20
#  1) اسکن پراکسی از ریپوی گیت‌هاب (کشف خودکار فایل‌ها + تشخیص خودکار SOCKS5/SOCKS4/HTTP)
#  2) دانلود اپلیکیشن APK (از گیت‌هاب Release، لینک دلخواه، یا فایل محلی)
import asyncio
import os
import random
import re
import time
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request

from main import DATA_DIR, logger, safe_int
import outbound_proxy as op

router = APIRouter()

DEFAULT_REPO = os.environ.get("GITHUB_PROXY_REPO", "https://github.com/Vodiwalker/vodi_shiper").strip()
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()          # اختیاری (افزایش rate-limit)
APK_URL_ENV = os.environ.get("APP_APK_URL", "").strip()            # لینک مستقیم APK (اختیاری)
APK_REPO = os.environ.get("APP_APK_REPO", DEFAULT_REPO).strip()    # ریپویی که Release آن APK دارد
APK_LOCAL = Path(os.environ.get("APP_APK_PATH", str(DATA_DIR / "vodiwalker.apk")))

_REPO_RE = re.compile(r"^(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?(?:/.*)?$")
_LIST_EXT = (".txt", ".list", ".csv", ".lst", ".proxy", ".proxies", ".json", ".md")
_FALLBACK_NAMES = ["proxies.txt", "proxy.txt", "proxy_list.txt", "socks5.txt", "socks4.txt", "http.txt",
                   "https.txt", "all.txt", "list.txt", "prxi.txt", "proxies/socks5.txt", "proxies/http.txt"]
_ADDR_RE = re.compile(r"(?:(socks5h?|socks4a?|https?)://)?(?:[^\s:@/\"']+:[^\s:@/\"']+@)?"
                      r"((?:\d{1,3}\.){3}\d{1,3}):(\d{2,5})")
MAX_FILES = 40
MAX_FILE_BYTES = 3_000_000
_CACHE: dict = {}      # repo -> (ts, text_by_file)
CACHE_TTL = 120


def _parse_repo(url: str):
    m = _REPO_RE.match((url or "").strip())
    if not m:
        raise HTTPException(status_code=400, detail="آدرس ریپو باید مثل https://github.com/user/repo باشد")
    return m.group(1), m.group(2)


def _hdrs(api: bool = False) -> dict:
    h = {"User-Agent": "VodiWalker-Scanner"}
    if api:
        h["Accept"] = "application/vnd.github+json"
    if GITHUB_TOKEN:
        h["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return h


def _hint_scheme(name: str) -> str:
    n = name.lower()
    if "socks5" in n or "sock5" in n:
        return "socks5"
    if "socks4" in n:
        return "socks4"
    if "http" in n:
        return "http"
    return "auto"


async def _get_text(client: httpx.AsyncClient, url: str) -> str:
    async with client.stream("GET", url, headers=_hdrs()) as r:
        if r.status_code >= 400:
            raise RuntimeError(f"{r.status_code}")
        buf, n = [], 0
        async for ch in r.aiter_bytes():
            buf.append(ch)
            n += len(ch)
            if n >= MAX_FILE_BYTES:
                break
    return b"".join(buf)[:MAX_FILE_BYTES].decode("utf-8", errors="ignore")


async def _walk(client, owner, repo, path="", depth=0, out=None):
    """لیست فایل‌های متنی ریپو با GitHub API (تا عمق ۲)."""
    out = out if out is not None else []
    r = await client.get(f"https://api.github.com/repos/{owner}/{repo}/contents/{path}", headers=_hdrs(True))
    if r.status_code == 403:
        raise RuntimeError("rate")
    if r.status_code >= 400:
        raise RuntimeError(f"api {r.status_code}")
    items = r.json()
    if isinstance(items, dict):
        items = [items]
    for it in items:
        if len(out) >= MAX_FILES:
            break
        if it.get("type") == "file" and it["name"].lower().endswith(_LIST_EXT) and it.get("size", 0) <= MAX_FILE_BYTES:
            if it.get("download_url"):
                out.append((it["path"], it["download_url"]))
        elif it.get("type") == "dir" and depth < 2 and not it["name"].startswith("."):
            await _walk(client, owner, repo, it["path"], depth + 1, out)
    return out


async def fetch_repo_texts(repo_url: str) -> dict:
    owner, repo = _parse_repo(repo_url)
    key = f"{owner}/{repo}"
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    texts: dict = {}
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        files = []
        try:
            files = await _walk(client, owner, repo)
        except Exception as exc:
            logger.warning(f"github api listing failed ({exc}); trying common file names")
        if not files:   # fallback بدون API: نام‌های رایج روی main/master
            for br in ("main", "master"):
                for nm in _FALLBACK_NAMES:
                    files.append((nm, f"https://raw.githubusercontent.com/{owner}/{repo}/{br}/{nm}"))
        sem = asyncio.Semaphore(8)

        async def one(path, url):
            async with sem:
                try:
                    texts[path] = await _get_text(client, url)
                except Exception:
                    pass
        await asyncio.gather(*(one(p, u) for p, u in files))
    texts = {k: v for k, v in texts.items() if v.strip()}
    if not texts:
        raise HTTPException(status_code=400, detail="هیچ فایل لیست پراکسی‌ای در ریپو پیدا نشد (ریپو باید public باشد و فایل‌های txt/list/csv/json داشته باشد)")
    _CACHE[key] = (time.time(), texts)
    return texts


def candidates_from_texts(texts: dict, default_scheme: str, cap: int):
    """فایل‌ها → کاندیدها. پروتکل از اسم فایل (socks5.txt/http.txt) یا scheme:// داخل خط حدس زده می‌شود."""
    cands, seen = [], set()
    for path, txt in texts.items():
        fname = path.rsplit("/", 1)[-1]
        sc = _hint_scheme(fname)
        sc = default_scheme if sc == "auto" else sc
        if fname.lower().endswith((".json", ".md")):
            lines = [f"{(m.group(1) + '://') if m.group(1) else ''}{m.group(2)}:{m.group(3)}" for m in _ADDR_RE.finditer(txt)]
        else:
            lines = txt.replace("\r", "\n").replace(",", "\n").split("\n")
        for line in lines:
            c = op.parse_candidate(line, sc)
            if not c:
                continue
            k = (c["host"], c["port"])
            if k in seen:
                continue
            seen.add(k)
            cands.append(c)
    random.shuffle(cands)           # هر اسکن بخش متفاوتی از لیست‌های بزرگ را می‌گیرد
    truncated = len(cands) > cap
    return cands[:cap], truncated


@router.post("/api/proxies/scan/github")
async def api_scan_github(request: Request, _=Depends(op.require_owner)):
    """body: {repo?: url, protocol?: auto|socks5|socks4|http, samples, tls, speed, concurrency, timeout}"""
    body = await op._json_body(request)
    op._purge_jobs()
    if op._active_jobs() >= op.SCAN_MAX_ACTIVE_JOBS:
        raise HTTPException(status_code=429, detail="یک اسکن دیگر در حال اجراست؛ صبر کن یا لغوش کن")
    repo = str(body.get("repo") or DEFAULT_REPO).strip()
    proto = str(body.get("protocol") or "auto").strip().lower()
    proto = "auto" if proto == "auto" else op._norm_scheme(proto)
    texts = await fetch_repo_texts(repo)
    cap = max(50, min(20000, safe_int(body.get("max", op.SCAN_JOB_MAX_CANDIDATES), minimum=50, maximum=20000)))
    cands, truncated = candidates_from_texts(texts, proto, cap)
    ok, blocked = [], 0
    for c in cands:
        if await op._host_is_blocked(c["host"]):
            blocked += 1
        else:
            ok.append(c)
    if not ok:
        raise HTTPException(status_code=400, detail="هیچ پروکسی معتبری در فایل‌های ریپو پیدا نشد (فرمت host:port)")
    job = op._start_job("scan", ok, op._job_opts(body),
                        {"blocked": blocked, "truncated": truncated, "source": "github"})
    op.log_activity("network", f"اسکن گیت‌هاب شروع شد: {len(ok)} پروکسی از {len(texts)} فایل", "ok")
    return {"ok": True, "job_id": job["id"], "total": job["total"], "blocked": blocked,
            "truncated": truncated, "files": len(texts), "repo": repo}


# ═════════════════════════ لینک دانلود اپلیکیشن ═════════════════════════
# دکمه‌ی «دانلود اپلیکیشن» یک صفحه‌ی دلخواه را (مثلاً Google Play یا صفحه‌ی دانلود) در تب جدید باز می‌کند.
# لینک را مالک پنل یک‌بار از خود دکمه (آیکون مداد) تنظیم می‌کند؛ یا با env: APP_DOWNLOAD_URL
import json

LINK_FILE = DATA_DIR / "app_link.json"
APP_LINK_ENV = os.environ.get("APP_DOWNLOAD_URL", "").strip()


def _read_link() -> str:
    try:
        if LINK_FILE.exists():
            return str(json.loads(LINK_FILE.read_text(encoding="utf-8")).get("url") or "").strip()
    except Exception:
        pass
    return APP_LINK_ENV


@router.get("/api/app/link")
async def app_link_get(request: Request, _=Depends(op.require_auth)):
    info = await op.get_session_info(request.cookies.get(op.SESSION_COOKIE))
    return {"ok": True, "url": _read_link(), "owner": bool(info and info.get("admin_id") == "owner")}


@router.post("/api/app/link")
async def app_link_set(request: Request, _=Depends(op.require_owner)):
    body = await op._json_body(request)
    url = str(body.get("url") or "").strip()
    if url and not re.match(r"^https?://[^\s]+$", url, re.I):
        raise HTTPException(status_code=400, detail="لینک باید با http:// یا https:// شروع شود")
    LINK_FILE.parent.mkdir(parents=True, exist_ok=True)
    LINK_FILE.write_text(json.dumps({"url": url}, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "url": url}


# ═════════════════ ساخت خودکار «همه‌ی پروتکل‌ها» ═════════════════
# حالت all_protocols در /api/links/auto:
#  • پروتکل‌هایی که همین پنل واقعاً سرو می‌کند (WS، XHTTP packet-up/stream-up با TLS، و TCP خام اگر پورتش تنظیم باشد)
#    همیشه ساخته می‌شوند — با بهترین تنظیم هرکدام (fingerprint پروفایل، ALPN مناسب، fragment).
#  • gRPC / Reality / TCP+TLS / XHTTP+Reality را این پنل خودش سرو نمی‌کند (نیاز به Xray-core دارد).
#    فقط وقتی «آدرس سرور Xray» داده شود ساخته می‌شوند، و کلید Reality هم تولید و برگردانده می‌شود.
_EXTERNAL_MEMBERS = [   # (network, security, label, extra)
    ("grpc", "tls", "gRPC+TLS", {"grpc_mode": "gun"}),
    ("grpc", "reality", "gRPC+Reality", {"grpc_mode": "gun"}),
    ("tcp", "reality", "TCP+Reality", {"flow": "xtls-rprx-vision"}),
    ("tcp", "tls", "TCP+TLS", {}),
    ("xhttp", "reality", "XHTTP+Reality", {"xhttp_mode": "auto"}),
]


def _reality_keys() -> dict:
    import base64
    import secrets
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import x25519
    pk = x25519.X25519PrivateKey.generate()
    raw = serialization.Encoding.Raw
    b64 = lambda b: base64.urlsafe_b64encode(b).decode().rstrip("=")
    return {
        "private_key": b64(pk.private_bytes(raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())),
        "public_key": b64(pk.public_key().public_bytes(raw, serialization.PublicFormat.Raw)),
        "short_id": secrets.token_hex(4),
    }


async def create_all_protocols(request, body: dict, cfg: dict, profile: str, port: int, exits: list, note: str):
    import main as M
    sid = str(body.get("server_id") or "").strip()
    sv_prof = None
    if sid:
        sv_prof = xs_find_server(sid)
        if not sv_prof:
            raise HTTPException(status_code=404, detail="سرور انتخاب‌شده پیدا نشد (شاید حذف شده)")
        want = str(body.get("port_mode") or "").strip().lower()
        if want in ("single", "multi") and want != sv_prof.get("mode"):
            if xs_server_link_count(sid) > 0:
                raise HTTPException(status_code=400, detail="این سرور از قبل کانفیگ فعال دارد؛ حالت پورت (تکی/چندتایی) فقط قبل از اولین ساخت قابل تغییر است")
            sv_prof["mode"] = want
            sv_prof["ports"] = xs_normalize_ports(want, sv_prof.get("ports") or {})
            if want == "single":
                sv_prof["snis"] = xs_default_snis(sv_prof.get("sni"))
    host = M.get_host(request)
    exit_id = exits[0] if exits else ""
    custom = str(body.get("label") or "").strip()
    name = M.sanitize_display_name(custom) if custom else M.auto_display_name()
    _lv = M.safe_float(body.get("limit_value", 0))
    limit_bytes = 0 if _lv <= 0 else M.parse_size_to_bytes(_lv, str(body.get("limit_unit") or "GB").upper())
    _days = M.safe_int(body.get("expires_days", 0), minimum=0)
    expires_at = (M.datetime.now() + M.timedelta(days=_days)).isoformat() if _days > 0 else None
    _sv = M.safe_float(body.get("speed_limit_value", 0))
    speed_bytes = cfg["speed"] if _sv <= 0 else M.parse_speed_to_bytes(_sv, str(body.get("speed_limit_unit") or "MBIT").upper())
    ip_limit = M.safe_int(body.get("ip_limit", 0), minimum=0)
    conn_limit = M.safe_int(body.get("connection_limit", 0), minimum=0) or cfg["conn"]
    sub_id, sub = await M.create_sub_group(name=(custom or M.sanitize_config_name(name))[:60] or "VodiWalker-all",
                                           desc="همه‌ی پروتکل‌ها · بهترین تنظیم خودکار")
    members = [("vless-ws", "WS+TLS"), ("xhttp-packet-up", "XHTTP packet-up"), ("xhttp-stream-up", "XHTTP stream-up")]
    tcp = await detect_tcp(request)
    if tcp["include"]:
        members.append(("vless-tcp", f"TCP:{tcp['port']}"))
    created, items = [], []
    _opk = str(body.get("operator") or "").strip().lower()
    _opm = getattr(M.app.state, "operators", None)
    _pre = _opm.preset(_opk) if (_opm and _opk and _opk != "all") else None
    if _pre:
        cfg = {**cfg, "fp": _pre.get("fingerprint") or cfg["fp"], "fragment": _pre.get("fragment") or cfg["fragment"]}
        name = f"{name} · {_pre['name']}"
    common = dict(limit_bytes=limit_bytes, expires_at=expires_at, note=note, sub_id=sub_id, fingerprint=cfg["fp"], port=port,
                  ip_limit=ip_limit, speed_limit_bytes=speed_bytes, connection_limit=conn_limit, fragment=cfg["fragment"],
                  clean_ips=(list(_pre.get("clean_ips") or []) if _pre else []))
    for i, (proto, tag) in enumerate(members):
        uid, link = await M.make_link(label=f"{M.decorate_label(name, i)}", protocol=proto,
                                      alpn=M.DEFAULT_ALPN_BY_PROTOCOL.get(proto, ""), outbound_proxy_id=exit_id, **common)
        async with M.LINKS_LOCK:
            M.LINKS[uid]["security_profile"] = profile
        created.append({"protocol": proto, "tag": tag, "live": True, "uuid": uid})
        items.append(M.get_link_info(M.LINKS[uid], uid, host))

    # ── سرور واقعی (VPS): Reality TCP/gRPC/XHTTP + WireGuard؛ کلیدها یک‌بار ساخته و ثابت می‌مانند ──
    if sv_prof is not None:
        prof = sv_prof
        srv_host = str(prof.get("host") or "").strip()
    else:
        prof = xs_profile()
        srv_host = str(body.get("server_host") or body.get("xray_host") or prof.get("host") or "").strip()
        if body.get("reality_sni"):
            prof["sni"] = str(body["reality_sni"]).strip()
    xray = wireguard = None
    need_server = False
    if srv_host:
        if not _valid_host_simple(srv_host):
            raise HTTPException(status_code=400, detail="آدرس سرور (VPS) معتبر نیست")
        prof["host"] = srv_host
        xs_ensure(prof)
        ports, rk = prof["ports"], prof["reality"]
        for j, (kind, net, tag, extra) in enumerate(_XS_MEMBERS):
            if kind not in xs_kinds(prof):
                continue
            if kind in XS_REALITY_KINDS:
                mf = {"base_protocol": "trojan" if kind == "trojan" else "vless", "network": net, "security": "reality",
                      "address": srv_host, "sni": xs_sni_for(prof, kind), "grpc_service_name": "vw" if net == "grpc" else "",
                      "path": "/vw" if net == "xhttp" else "", "reality_public_key": rk["public_key"],
                      "reality_short_id": rk["short_id"], "reality_spider_x": "/", **extra}
            elif kind == "ss":
                mf = {"base_protocol": "shadowsocks", "network": "tcp", "security": "none", "address": srv_host,
                      "ss_method": XS_SS_METHOD}
            else:   # vmess + ws (بدون TLS)
                mf = {"base_protocol": "vmess", "network": "ws", "security": "none", "address": srv_host,
                      "path": XS_VMESS_PATH, "host_header": (prof.get("snis") or {}).get("vmess") or XS_VMESS_HOST}
            uid, link = await M.make_link(label=f"{M.decorate_label(name, 10 + j)}", protocol="manual",
                                          alpn="h2" if net in ("grpc", "xhttp") else "", manual_fields=mf,
                                          outbound_proxy_id="", **{**common, "port": ports[kind]})
            async with M.LINKS_LOCK:
                M.LINKS[uid]["xs"] = kind
                if sid:
                    M.LINKS[uid]["xs_server"] = sid
            created.append({"protocol": tag, "tag": tag, "live": False, "uuid": uid, "xs": kind})
            items.append(M.get_link_info(M.LINKS[uid], uid, host))
        cli = _wg_keys()
        wg_addr = xs_next_wg_ip(prof)
        mf = {"base_protocol": "wireguard", "address": srv_host, "wg_private_key": cli["private_key"],
              "wg_public_key": prof["wg"]["public_key"], "wg_address": wg_addr, "wg_mtu": "1280"}
        uid, link = await M.make_link(label=f"{M.decorate_label(name, 20)}", protocol="manual", manual_fields=mf,
                                      outbound_proxy_id="", **{**common, "port": ports["wg"]})
        async with M.LINKS_LOCK:
            M.LINKS[uid]["xs"] = "wg"
            M.LINKS[uid]["wg_client_public"] = cli["public_key"]
            if sid:
                M.LINKS[uid]["xs_server"] = sid
        created.append({"protocol": "WireGuard", "tag": "WireGuard", "live": False, "uuid": uid, "xs": "wg", "udp": True})
        items.append(M.get_link_info(M.LINKS[uid], uid, host))
        if not sid:
            M.CONFIG["xs_profile"] = prof
        base = M.get_web_base(host)
        install_cmd = f"bash <(curl -fsSL {base}/xs/{prof['token']}/install.sh)"
        xray = {"host": srv_host, "ports": ports, "sni": prof["sni"], "install_cmd": install_cmd,
                "mode": prof.get("mode") or "multi", "server_id": sid, "server_name": prof.get("name", "")}
        wireguard = {"host": srv_host, "port": ports["wg"], "address": wg_addr}
    else:
        need_server = True

    pings = await asyncio.gather(*[xs_probe(c.get("xs"), M.LINKS.get(c["uuid"]) or {}, M, host, port, tcp)
                                   for c in created], return_exceptions=True)
    for c, pg in zip(created, pings):
        c["ping_ms"] = pg if isinstance(pg, int) else None
    _alive = [c for c in created if c.get("ping_ms") is not None
              and (not sid or (M.LINKS.get(c["uuid"], {}).get("xs_server") or "") == sid)]
    best = min(_alive, key=lambda c: c["ping_ms"]) if _alive else None

    await M.save_state()
    sub_url = f"{M.get_web_base(host)}/sub-group/{sub['uuid_key']}"
    public_url = f"{M.get_web_base(host)}/p/{sub['uuid_key']}"
    M.log_activity("link", f"ساخت خودکار همه‌ی پروتکل‌ها: {len(created)} کانفیگ", "ok")
    return {"ok": True, "all_protocols": True, "profile": profile, "sub_id": sub_id, "sub_url": sub_url,
            "public_url": public_url, "sub_name": sub.get("name", ""), "created": created, "items": items,
            "xray": xray, "wireguard": wireguard, "tcp": tcp, "need_server": need_server,
            "best": ({"tag": best["tag"], "uuid": best["uuid"], "ping_ms": best["ping_ms"]} if best else None),
            "skipped_note": ("برای Reality / gRPC / XHTTP / WireGuard «آدرس سرور (VPS)» را وارد کن؛ روی پنل سرو نمی‌شوند." if need_server else None)}


def _wg_keys() -> dict:
    import base64
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import x25519
    pk = x25519.X25519PrivateKey.generate()
    raw = serialization.Encoding.Raw
    b64 = lambda b: base64.b64encode(b).decode()
    return {"private_key": b64(pk.private_bytes(raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())),
            "public_key": b64(pk.public_key().public_bytes(raw, serialization.PublicFormat.Raw))}


def _valid_host_simple(h: str) -> bool:
    return bool(re.match(r"^[A-Za-z0-9.-]{3,253}$", h)) and ".." not in h


async def pick_best_exit() -> dict:
    """بهترین پراکسی خروجی ذخیره‌شده: اول بر اساس امتیاز ذخیره‌شده، بعد یک تست زنده‌ی سریع روی ۴ نفر اول.
    اگر هیچ پراکسی سالمی نباشد، خروجی مستقیم ('') برمی‌گردد."""
    pool = [p for p in op.PROXIES.values() if p.get("test_ok") and p.get("tls_state") != "intercepted"]
    pool.sort(key=lambda p: (-(p.get("score") or 0), p.get("ping_ms") if p.get("ping_ms") is not None else 1e9))
    best = None
    for p in pool[:4]:
        c = {"scheme": op._norm_scheme(p.get("scheme") or "socks5"), "host": p["host"], "port": int(p["port"]),
             "username": p.get("username", ""), "password": p.get("password", "")}
        try:
            r = await asyncio.wait_for(op.probe_candidate(c, samples=1, check_tls=False, tcp_timeout=3.0, probe_timeout=5.0), 12.0)
        except Exception:
            continue
        if r.get("ok"):
            op._apply_result(p, r)
            if best is None or (r["score"], -(r["ping_ms"] or 1e9)) > (best[1]["score"], -(best[1]["ping_ms"] or 1e9)):
                best = (p["id"], r)
    if best:
        await op.save_proxies()
        return {"id": best[0], "info": op.proxy_summary(best[0])}
    return {"id": "", "info": None}


# ═════════════ تشخیص خودکار پورت TCP ═════════════
async def _can_connect(host: str, port: int, timeout: float = 4.0) -> bool:
    try:
        r, w = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
        w.close()
        try:
            await w.wait_closed()
        except Exception:
            pass
        return True
    except Exception:
        return False


async def detect_tcp(request=None, apply: bool = True) -> dict:
    """پورت TCP خام را خودش پیدا و بررسی می‌کند:
    ۱) ریلی TCP واقعاً روشن است؟  ۲) پورت (تنظیم‌شده یا پیش‌فرض TCP_LISTEN_PORT)  ۳) از بیرون قابل‌اتصال است؟
    اگر قابل‌اتصال بود و در تنظیمات خالی بود، خودش در تنظیمات ذخیره می‌کند تا لینک TCP درست ساخته شود."""
    import main as M
    try:
        import tcp_relay
        running = tcp_relay._server is not None
        listen = int(tcp_relay.TCP_LISTEN_PORT)
    except Exception:
        running, listen = False, int(os.environ.get("TCP_LISTEN_PORT", "6543"))
    host = (M.CONFIG.get("tcp_public_host") or "").strip() or M.get_host(request)
    cfg_port = str(M.CONFIG.get("tcp_public_port") or "").strip()
    port = int(cfg_port) if cfg_port.isdigit() else listen
    out = {"running": running, "listen_port": listen, "host": host, "port": port, "reachable": False,
           "include": False, "reason": ""}
    if not running:
        out["reason"] = "ریلی TCP روی این سرور روشن نیست"
        return out
    out["reachable"] = await _can_connect(host, port)
    if out["reachable"]:
        out["include"] = True
        if apply and not cfg_port:
            M.CONFIG["tcp_public_port"] = str(port)
            if not (M.CONFIG.get("tcp_public_host") or "").strip():
                M.CONFIG["tcp_public_host"] = host
            await M.save_state()
        out["reason"] = f"پورت {port} از بیرون باز است"
    elif cfg_port:
        out["include"] = True      # مالک پورت را دستی تنظیم کرده (ممکن است hairpin روی هاست بسته باشد)
        out["reason"] = f"پورت {port} را خودت تنظیم کرده‌ای؛ از داخل سرور قابل تست نبود ولی استفاده شد"
    else:
        out["reason"] = f"پورت {port} از بیرون بسته است (هاست تک‌پورتی؟) — TCP ساخته نشد"
    return out


@router.get("/api/tcp/detect")
async def api_tcp_detect(request: Request, _=Depends(op.require_auth)):
    return {"ok": True, **(await detect_tcp(request, apply=False))}


# ═════════════════════ سرور واقعی: Xray (Reality) + WireGuard ═════════════════════
# پنل خودش فقط WS/XHTTP/TCP را رله می‌کند. Reality/gRPC/XHTTP-Reality و WireGuard روی یک VPS اجرا می‌شوند.
# پنل کلیدها را یک‌بار می‌سازد و config را از طریق /xs/<token>/… می‌دهد؛ اسکریپت نصب روی VPS هر ۶۰ ثانیه آن را همگام می‌کند.
_XS_MEMBERS = [   # (kind, network, label, extra)
    ("tcp", "tcp", "TCP+Reality", {"flow": "xtls-rprx-vision"}),
    ("grpc", "grpc", "gRPC+Reality", {"grpc_mode": "gun"}),
    ("xhttp", "xhttp", "XHTTP+Reality", {"xhttp_mode": "auto"}),
    ("trojan", "tcp", "Trojan+Reality", {}),
    ("ss", "tcp", "Shadowsocks", {}),
    ("vmess", "ws", "VMess+WS", {}),
]
XS_KINDS_ALL = ("tcp", "grpc", "xhttp", "trojan", "ss", "vmess")
XS_REALITY_KINDS = ("tcp", "grpc", "xhttp", "trojan")
XS_SNI_POOL = ["www.microsoft.com", "www.apple.com", "www.amazon.com", "www.samsung.com", "www.nvidia.com",
               "www.asus.com", "www.cisco.com", "www.oracle.com"]
XS_VMESS_HOST = "download.windowsupdate.com"
XS_VMESS_PATH = "/vw-vm"
XS_SS_METHOD = "chacha20-ietf-poly1305"
XS_INTERNAL_BASE = 20001


# ───────── چند سرور (VPS): هر سرور پروفایل جدا (توکن، کلیدها، پورت‌ها) دارد ─────────
def xs_servers() -> list:
    import main as M
    v = M.CONFIG.get("vps_servers")
    if not isinstance(v, list):
        v = []
        M.CONFIG["vps_servers"] = v
    return v


def xs_find_server(sid):
    sid = str(sid or "").strip()
    if not sid:
        return None
    for sv in xs_servers():
        if sv.get("id") == sid:
            return sv
    return None


def xs_find_by_token(token: str):
    """پروفایل (سرور ذخیره‌شده یا پروفایل قدیمی) که این توکن مال اوست؛ وگرنه None."""
    import hmac
    for sv in xs_servers():
        if sv.get("token") and hmac.compare_digest(str(sv["token"]), str(token)):
            return sv
    legacy = xs_profile()
    if legacy.get("token") and hmac.compare_digest(str(legacy["token"]), str(token)):
        return legacy
    return None


def xs_kinds(p: dict) -> tuple:
    """همه‌ی پروتکل‌ها همیشه فعالند. حالت «چندپورتی»: هرکدام پورت جدا. حالت «پورت تکی»: همه روی یک پورت
    (تفکیک با SNI برای Reality، Host برای VMess، و بقیه‌ی ترافیک به Shadowsocks) + WireGuard روی UDP همان پورت."""
    return XS_KINDS_ALL


def xs_default_snis(main_sni: str, hint=None) -> dict:
    """در حالت پورت تکی هر پروتکل Reality یک SNI متفاوت می‌خواهد (مسیریابی با SNI)."""
    main_sni = (main_sni or "www.microsoft.com").strip().lower()
    pool = []
    for d in list(hint or []) + XS_SNI_POOL:
        d = str(d).strip().lower()
        if d and d != main_sni and d not in pool:
            pool.append(d)
    return {"tcp": main_sni, "grpc": pool[0], "xhttp": pool[1], "trojan": pool[2], "vmess": XS_VMESS_HOST}


def xs_sni_for(p: dict, kind: str) -> str:
    if p.get("mode") == "single":
        return (p.get("snis") or {}).get(kind) or p.get("sni") or "www.microsoft.com"
    return p.get("sni") or "www.microsoft.com"


def xs_ensure(p: dict) -> dict:
    """پروفایل‌های قدیمی را کامل می‌کند (پورت پروتکل‌های جدید و SNI ها)."""
    ports = p.setdefault("ports", {})
    if p.get("mode") == "single":
        t = int(ports.get("tcp") or 443)
        for k in XS_KINDS_ALL:
            ports[k] = t
        ports.setdefault("wg", t)
        if not isinstance(p.get("snis"), dict) or not all(p["snis"].get(k) for k in ("tcp", "grpc", "xhttp", "trojan", "vmess")):
            p["snis"] = xs_default_snis(p.get("sni"))
    else:
        used = {int(ports[k]) for k in XS_KINDS_ALL if ports.get(k)}
        nxt = (max(used) if used else 443) + 1
        for k in XS_KINDS_ALL:
            if not ports.get(k):
                while nxt in used:
                    nxt += 1
                ports[k] = nxt
                used.add(nxt)
    ports.setdefault("wg", 51820)
    return p


def xs_normalize_ports(mode: str, ports: dict) -> dict:
    def pn(v, d):
        try:
            n = int(v)
        except Exception:
            n = d
        if not (1 <= n <= 65535):
            raise HTTPException(status_code=400, detail=f"پورت {v} معتبر نیست (۱ تا ۶۵۵۳۵)")
        return n
    ports = ports if isinstance(ports, dict) else {}
    tcp = pn(ports.get("tcp") or 443, 443)
    if mode == "single":
        wg = pn(ports.get("wg") or tcp, tcp)
        d = {k: tcp for k in XS_KINDS_ALL}
        d["wg"] = wg
        return d
    vals = {}
    for i, k in enumerate(XS_KINDS_ALL):
        dflt = tcp + i if tcp + i <= 65535 else max(1, tcp - i)
        vals[k] = pn(ports.get(k) or dflt, dflt)
    if len(set(vals.values())) < len(XS_KINDS_ALL):
        raise HTTPException(status_code=400, detail="در حالت چندپورتی، پورت همه‌ی پروتکل‌ها باید با هم فرق داشته باشند")
    vals["wg"] = pn(ports.get("wg") or 51820, 51820)
    return vals


def xs_server_link_count(sid) -> int:
    import main as M
    return sum(1 for l in M.LINKS.values() if (l.get("xs_server") or "") == (sid or ""))


def xs_public_view(sv: dict, show_token: bool = True) -> dict:
    out = {k: sv.get(k) for k in ("id", "name", "host", "sni", "snis", "mode", "ports", "created_at", "last_scan", "last_check")}
    out["links"] = xs_server_link_count(sv.get("id"))
    if show_token:
        out["token"] = sv.get("token")
    return out


def xs_profile() -> dict:
    import main as M
    import secrets
    p = M.CONFIG.get("xs_profile")
    if not isinstance(p, dict) or not p.get("token"):
        p = {"host": "", "sni": "www.microsoft.com", "ports": {"tcp": 8443, "grpc": 8444, "xhttp": 8445, "wg": 51820},
             "reality": _reality_keys(), "wg": _wg_keys(), "wg_next": 2, "token": secrets.token_urlsafe(24)}
        M.CONFIG["xs_profile"] = p
    return p


def xs_next_wg_ip(p: dict) -> str:
    n = int(p.get("wg_next", 2))
    if n > 254:
        raise HTTPException(status_code=400, detail="ظرفیت آدرس WireGuard پر شده")
    p["wg_next"] = n + 1
    return f"10.66.66.{n}/32"


def _xs_active_links(kind: str, sid=None):
    import main as M
    for uid, l in list(M.LINKS.items()):
        if l.get("xs") != kind or not l.get("active", True):
            continue
        if (l.get("xs_server") or "") != (sid or ""):
            continue
        if M.is_link_expired(l):
            continue
        yield uid, l


def xs_xray_config(p: dict = None) -> dict:
    p = xs_ensure(p or xs_profile())
    sid = p.get("id") or None
    single = p.get("mode") == "single"
    rk = p["reality"]

    def reality(sni):
        return {"show": False, "dest": f"{sni}:443", "xver": 0, "serverNames": [sni],
                "privateKey": rk["private_key"], "shortIds": [rk["short_id"]]}

    inbounds, outbounds, rules = [], [{"protocol": "freedom", "tag": "direct"}, {"protocol": "blackhole", "tag": "block"}], []
    present = []
    internal = XS_INTERNAL_BASE
    for kind, net, _t, _x in _XS_MEMBERS:
        links = [uid for uid, _l in _xs_active_links(kind, sid)]
        if not links:
            continue
        sni = xs_sni_for(p, kind)
        stream = {"network": net, "security": "none"}
        if kind == "tcp":
            proto, st = "vless", {"clients": [{"id": u, "flow": "xtls-rprx-vision"} for u in links], "decryption": "none"}
        elif kind in ("grpc", "xhttp"):
            proto, st = "vless", {"clients": [{"id": u} for u in links], "decryption": "none"}
        elif kind == "trojan":
            proto, st = "trojan", {"clients": [{"password": u} for u in links]}
        elif kind == "ss":
            proto, st = "shadowsocks", {"clients": [{"method": XS_SS_METHOD, "password": u} for u in links],
                                        "network": "tcp" if single else "tcp,udp"}
        else:
            proto, st = "vmess", {"clients": [{"id": u} for u in links]}
        if kind in XS_REALITY_KINDS:
            stream = {"network": net, "security": "reality", "realitySettings": reality(sni)}
            if net == "grpc":
                stream["grpcSettings"] = {"serviceName": "vw"}
            elif net == "xhttp":
                stream["xhttpSettings"] = {"path": "/vw", "mode": "auto"}
        elif kind == "vmess":
            stream = {"network": "ws", "security": "none",
                      "wsSettings": {"path": XS_VMESS_PATH, "host": (p.get("snis") or {}).get("vmess") or XS_VMESS_HOST,
                                     "headers": {"Host": (p.get("snis") or {}).get("vmess") or XS_VMESS_HOST}}}
        ib = {"tag": f"vw-{kind}", "protocol": proto, "settings": st}
        if kind != "ss":
            ib["streamSettings"] = stream
        if single:
            ib["listen"], ib["port"] = "127.0.0.1", internal
            outbounds.append({"tag": f"to-{kind}", "protocol": "freedom", "settings": {"redirect": f"127.0.0.1:{internal}"}})
            if kind in XS_REALITY_KINDS:
                rules.append({"type": "field", "inboundTag": ["vw-front"], "domain": [f"full:{sni}"], "outboundTag": f"to-{kind}"})
            elif kind == "vmess":
                rules.append({"type": "field", "inboundTag": ["vw-front"], "domain": [f"full:{stream['wsSettings']['headers']['Host']}"],
                              "outboundTag": "to-vmess"})
            internal += 1
        else:
            ib["listen"], ib["port"] = "0.0.0.0", p["ports"][kind]
            ib["sniffing"] = {"enabled": True, "destOverride": ["http", "tls", "quic"]}
        inbounds.append(ib)
        present.append(kind)
    cfg = {"log": {"loglevel": "warning"}, "inbounds": inbounds, "outbounds": outbounds}
    if single and present:
        # دروازه‌ی تک‌پورت: SNI/Host را می‌خواند و به اینباند داخلی مناسب می‌فرستد
        default = next((f"to-{k}" for k in XS_REALITY_KINDS if k in present), f"to-{present[0]}")
        rules.append({"type": "field", "inboundTag": ["vw-front"], "protocol": ["tls", "http"], "outboundTag": default})
        rules.append({"type": "field", "inboundTag": ["vw-front"], "outboundTag": ("to-ss" if "ss" in present else default)})
        cfg["inbounds"] = [{"tag": "vw-front", "listen": "0.0.0.0", "port": p["ports"]["tcp"], "protocol": "dokodemo-door",
                            "settings": {"address": "127.0.0.1", "port": 1, "network": "tcp"},
                            "sniffing": {"enabled": True, "destOverride": ["tls", "http"], "routeOnly": True}}] + inbounds
        cfg["routing"] = {"domainStrategy": "AsIs", "rules": rules}
    return cfg


def xs_wg_conf(p: dict = None) -> str:
    p = p or xs_profile()
    sid = p.get("id") or None
    out = [f"[Interface]\nAddress = 10.66.66.1/24\nListenPort = {p['ports']['wg']}\nPrivateKey = {p['wg']['private_key']}\n"
           "PostUp = iptables -t nat -A POSTROUTING -s 10.66.66.0/24 -o @IFACE@ -j MASQUERADE; iptables -A FORWARD -i %i -j ACCEPT; iptables -A FORWARD -o %i -j ACCEPT\n"
           "PostDown = iptables -t nat -D POSTROUTING -s 10.66.66.0/24 -o @IFACE@ -j MASQUERADE; iptables -D FORWARD -i %i -j ACCEPT; iptables -D FORWARD -o %i -j ACCEPT\n"]
    for _uid, l in _xs_active_links("wg", sid):
        out.append(f"[Peer]\nPublicKey = {l.get('wg_client_public','')}\nAllowedIPs = {l.get('wg_address') or '10.66.66.2/32'}\n")
    return "\n".join(out)


def _xs_install_script(base: str, token: str, p: dict) -> str:
    xs_ensure(p)
    ports = " ".join(sorted({str(p["ports"][k]) for k in xs_kinds(p)}, key=int))
    ports_re = "|".join(sorted({str(p["ports"][k]) for k in xs_kinds(p)}, key=int))
    ss_udp = "" if p.get("mode") == "single" else f"; ufw allow {p['ports']['ss']}/udp"
    return f"""#!/usr/bin/env bash
# VodiWalker · نصب Xray (Reality) + WireGuard روی VPS
set -e
[ "$(id -u)" = 0 ] || {{ echo "با root اجرا کن"; exit 1; }}
BASE="{base}/xs/{token}"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y curl ca-certificates iptables wireguard wireguard-tools jq
bash -c "$(curl -fsSL https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install
echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/99-vw.conf; sysctl --system >/dev/null
cat > /usr/local/bin/vw-sync <<'EOS'
#!/usr/bin/env bash
BASE="$(cat /etc/vw-base)"
IFACE="$(ip route show default | awk '{{print $5; exit}}')"
T=$(mktemp --suffix=.json)
LOG=/var/log/vw-sync.log
if curl -fsS --max-time 20 "$BASE/xray.json" -o "$T" && jq -e . "$T" >/dev/null 2>&1; then
  if ! cmp -s "$T" /usr/local/etc/xray/config.json || ! systemctl is-active --quiet xray; then
    if /usr/local/bin/xray run -test -c "$T" > /tmp/vw-xtest.log 2>&1; then
      install -m 644 -o root -g root "$T" /usr/local/etc/xray/config.json
      systemctl restart xray; sleep 2
      systemctl is-active --quiet xray || echo "$(date) xray start failed" >> "$LOG"
    else
      echo "$(date) config test failed: $(tail -n 3 /tmp/vw-xtest.log)" >> "$LOG"
    fi
  fi
else
  echo "$(date) fetch or parse of xray.json failed" >> "$LOG"
fi
if curl -fsS --max-time 20 "$BASE/wg.conf" -o "$T"; then
  sed -i "s/@IFACE@/$IFACE/g" "$T"; chmod 600 "$T"
  if ! cmp -s "$T" /etc/wireguard/wg0.conf; then
    cp "$T" /etc/wireguard/wg0.conf; chmod 600 /etc/wireguard/wg0.conf
    if systemctl is-active --quiet wg-quick@wg0; then wg syncconf wg0 <(wg-quick strip wg0); else systemctl enable --now wg-quick@wg0; fi
  fi
fi
rm -f "$T"
EOS
chmod +x /usr/local/bin/vw-sync
echo "$BASE" > /etc/vw-base
cat > /etc/systemd/system/vw-sync.service <<'EOS'
[Service]
Type=oneshot
ExecStart=/usr/local/bin/vw-sync
EOS
cat > /etc/systemd/system/vw-sync.timer <<'EOS'
[Timer]
OnBootSec=10
OnUnitActiveSec=60
[Install]
WantedBy=timers.target
EOS
systemctl daemon-reload
systemctl enable --now xray
/usr/local/bin/vw-sync || true
systemctl enable --now vw-sync.timer
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q active; then
  for P in {ports}; do ufw allow $P/tcp; done; ufw allow {p['ports']['wg']}/udp{ss_udp}
fi
echo "✓ نصب شد: Reality (TCP/gRPC/XHTTP/Trojan) + Shadowsocks + VMess-WS + WireGuard UDP {p['ports']['wg']} — هر ۶۰ ثانیه با پنل همگام می‌شود."
sleep 3
echo "── بررسی نهایی ──"
if systemctl is-active --quiet xray; then echo "xray: فعال ✓"; else echo "xray: غیرفعال ✗"; journalctl -u xray -n 15 --no-pager; fi
ss -ltn | grep -E ":({ports_re}) " || echo "هنوز هیچ‌کدام از پورت‌های Xray گوش نمی‌دهد ✗ (اگر هنوز کانفیگی نساخته‌ای طبیعی است؛ وگرنه: cat /var/log/vw-sync.log)"
[ -f /var/log/vw-sync.log ] && tail -n 5 /var/log/vw-sync.log || true
"""


@router.get("/xs/{token}/xray.json")
async def xs_get_xray(token: str):
    from fastapi.responses import JSONResponse
    p = xs_find_by_token(token)
    if not p:
        raise HTTPException(status_code=404, detail="not found")
    return JSONResponse(xs_xray_config(p))


@router.get("/xs/{token}/wg.conf")
async def xs_get_wg(token: str):
    from fastapi.responses import PlainTextResponse
    p = xs_find_by_token(token)
    if not p:
        raise HTTPException(status_code=404, detail="not found")
    return PlainTextResponse(xs_wg_conf(p))


@router.get("/xs/{token}/install.sh")
async def xs_get_install(token: str, request: Request):
    from fastapi.responses import PlainTextResponse
    import main as M
    p = xs_find_by_token(token)
    if not p:
        raise HTTPException(status_code=404, detail="not found")
    return PlainTextResponse(_xs_install_script(M.get_web_base(M.get_host(request)), token, p))


# ── پینگ واقعی: TCP برای Reality، و Handshake واقعی WireGuard (Noise IKpsk2) برای UDP ──
def _wg_handshake_sync(host: str, port: int, cli_priv_b64: str, srv_pub_b64: str, timeout: float = 3.0):
    import base64, hashlib, hmac, os, socket, struct, time
    from cryptography.hazmat.primitives.asymmetric import x25519
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    H = lambda d: hashlib.blake2s(d).digest()

    def hm(k, d):
        return hmac.new(k, d, hashlib.blake2s).digest()

    def kdf(c, d, n):
        t0 = hm(c, d); t1 = hm(t0, b"\x01")
        if n == 1:
            return (t1,)
        t2 = hm(t0, t1 + b"\x02")
        return (t1, t2)
    aead = lambda k, pt, ad: ChaCha20Poly1305(k).encrypt(b"\x00" * 12, pt, ad)
    spriv_i = x25519.X25519PrivateKey.from_private_bytes(base64.b64decode(cli_priv_b64))
    spub_i = spriv_i.public_key().public_bytes_raw()
    spub_r = base64.b64decode(srv_pub_b64)
    spub_r_key = x25519.X25519PublicKey.from_public_bytes(spub_r)
    C = H(b"Noise_IKpsk2_25519_ChaChaPoly_BLAKE2s")
    Hh = H(C + b"WireGuard v1 zx2c4 Jason@zx2c4.com")
    Hh = H(Hh + spub_r)
    epriv = x25519.X25519PrivateKey.generate()
    epub = epriv.public_key().public_bytes_raw()
    (C,) = kdf(C, epub, 1)
    Hh = H(Hh + epub)
    C, k = kdf(C, epriv.exchange(spub_r_key), 2)
    enc_static = aead(k, spub_i, Hh)
    Hh = H(Hh + enc_static)
    C, k = kdf(C, spriv_i.exchange(spub_r_key), 2)
    now = time.time()
    ts = struct.pack(">Q", (1 << 62) + 10 + int(now)) + struct.pack(">I", int((now % 1) * 1e9))
    enc_ts = aead(k, ts, Hh)
    sender = int.from_bytes(os.urandom(4), "little")
    msg = b"\x01\x00\x00\x00" + struct.pack("<I", sender) + epub + enc_static + enc_ts
    mac1 = hashlib.blake2s(msg, key=H(b"mac1----" + spub_r), digest_size=16).digest()
    msg += mac1 + b"\x00" * 16
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_DGRAM)
    fam, _t, _p, _c, addr = infos[0]
    s = socket.socket(fam, socket.SOCK_DGRAM); s.settimeout(timeout)
    try:
        t0 = time.perf_counter()
        s.sendto(msg, addr)
        data, _ = s.recvfrom(256)
        ms = round((time.perf_counter() - t0) * 1000)
        if len(data) == 92 and data[0] == 2 and struct.unpack("<I", data[8:12])[0] == sender:
            return max(ms, 1)
        return None
    except Exception:
        return None
    finally:
        s.close()


async def xs_probe(kind, link: dict, M, host, port, tcp):
    """پینگ واقعی هر کانفیگ؛ عدد (ms) یا None."""
    loop = asyncio.get_event_loop()
    if kind == "wg":
        return await asyncio.to_thread(_wg_handshake_sync, link.get("address"), int(link.get("port") or 51820),
                                       link.get("wg_private_key", ""), link.get("wg_public_key", ""))
    if kind:
        h, p = link.get("address"), int(link.get("port") or 0)
    elif link.get("protocol") == "vless-tcp":
        h, p = tcp["host"], tcp["port"]
    else:
        h, p = host, int(link.get("port") or port)
    t0 = loop.time()
    ok = await _can_connect(h, p, 3.0)
    return max(round((loop.time() - t0) * 1000), 1) if ok else None


@router.post("/api/xray-server/ping")
async def xs_ping(request: Request, _=Depends(op.require_auth)):
    import main as M
    body = await request.json()
    host = M.get_host(request)
    tcp = await detect_tcp(request)
    out = {}
    for uid in list(body.get("uuids") or [])[:60]:
        l = M.LINKS.get(uid)
        if not l:
            continue
        out[uid] = await xs_probe(l.get("xs"), l, M, host, 443, tcp)
    _ok = {k: v for k, v in out.items() if isinstance(v, int)}
    _srv = {k: v for k, v in _ok.items() if (M.LINKS.get(k, {}).get("xs_server"))}
    if _srv:      # وقتی سرور انتخاب شده، «بهترین» فقط بین کانفیگ‌های همان سرور است
        _ok = _srv
    return {"ok": True, "pings": out, "best": (min(_ok, key=_ok.get) if _ok else None)}


@router.get("/api/xray-server")
async def xs_status(request: Request, _=Depends(op.require_auth)):
    import main as M
    p = xs_profile()
    base = M.get_web_base(M.get_host(request))
    return {"ok": True, "host": p.get("host", ""), "sni": p["sni"], "ports": p["ports"],
            "install_cmd": f"bash <(curl -fsSL {base}/xs/{p['token']}/install.sh)" if p.get("host") else ""}
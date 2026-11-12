# vps.py — v22
#  ۱) ثبت چند سرور (VPS) توسط کاربر: نام، IP/دامنه، SNI ریلیتی، حالت پورت (تکی / چندپورتی)
#  ۲) اسکن پورت: نشان می‌دهد کدام پورت‌های سرور از بیرون «باز»، «آزاد و قابل‌استفاده» یا «فیلتر/بلاک» است
#  ۳) تست اتصال سرور ثبت‌شده (آیا Xray بعد از نصب بالا آمده؟)
# ساخت اینباند با سرور در extras.create_all_protocols (فیلد server_id) انجام می‌شود.
import asyncio
import ipaddress
import os
import json
import re
import secrets
import ssl
import socket
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request

import outbound_proxy as op
from main import logger
import extras as ex

router = APIRouter()

MAX_SERVERS = 30
MAX_SCAN_PORTS = 1024
SCAN_CONCURRENCY = 150
SCAN_TIMEOUT = 1.6
ALLOW_PRIVATE = os.environ.get("VPS_ALLOW_PRIVATE_SCAN", "").strip() in ("1", "true", "yes")

# پورت‌های رایج (وب، پنل‌ها، پورت‌های مجاز کلودفلر، پراکسی و ...)
COMMON_PORTS = [
    21, 22, 25, 53, 80, 110, 143, 443, 465, 587, 993, 995, 1080, 1194, 2052, 2053, 2082, 2083, 2086, 2087,
    2095, 2096, 3128, 3306, 3389, 4443, 5432, 5900, 6379, 7443, 8000, 8008, 8080, 8081, 8082, 8088, 8443,
    8444, 8445, 8880, 8888, 9000, 9090, 9443, 10000, 10443, 20000, 20443, 30000, 40000, 50000, 51820,
]
# ترتیب ترجیح برای Reality / پورت‌هایی که معمولاً کمتر مسدود می‌شوند
PREFERRED = [443, 8443, 2053, 2083, 2087, 2096, 9443, 4443, 2053, 8080, 8880, 2052, 2082, 2086, 2095, 7443, 10443, 8444, 8445]
SERVICES = {
    21: "FTP", 22: "SSH", 25: "SMTP", 53: "DNS", 80: "HTTP", 110: "POP3", 143: "IMAP", 443: "HTTPS", 465: "SMTPS",
    587: "SMTP", 993: "IMAPS", 995: "POP3S", 1080: "SOCKS", 1194: "OpenVPN", 3128: "Proxy", 3306: "MySQL",
    3389: "RDP", 5432: "PostgreSQL", 5900: "VNC", 6379: "Redis", 8080: "HTTP-alt", 8443: "HTTPS-alt",
    51820: "WireGuard (UDP)",
}

_SCAN_LOCK = asyncio.Lock()
_SCAN_LOG: dict = {}      # شناسه‌ی کاربر -> زمان‌های اسکن‌های اخیر


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _valid_host(h: str) -> bool:
    h = (h or "").strip()
    if not re.match(r"^[A-Za-z0-9.:-]{3,253}$", h) or ".." in h:
        return False
    return True


def _parse_ports(spec) -> list:
    """«common» | «top» | «1-1024» | «80,443,8000-8100» → لیست مرتب بدون تکرار (حداکثر MAX_SCAN_PORTS)."""
    if isinstance(spec, list):
        spec = ",".join(str(x) for x in spec)
    spec = str(spec or "common").strip().lower()
    if spec in ("", "common", "top"):
        return sorted(set(COMMON_PORTS))
    out = set()
    for part in re.split(r"[,\s،]+", spec):
        if not part:
            continue
        m = re.match(r"^(\d{1,5})(?:-(\d{1,5}))?$", part)
        if not m:
            raise HTTPException(status_code=400, detail=f"فرمت پورت نامعتبر: «{part}» — مثال: 80,443,8000-8100")
        a = int(m.group(1))
        b = int(m.group(2) or a)
        if a > b:
            a, b = b, a
        if a < 1 or b > 65535:
            raise HTTPException(status_code=400, detail="پورت باید بین ۱ تا ۶۵۵۳۵ باشد")
        if len(out) + (b - a + 1) > MAX_SCAN_PORTS + 5000:
            raise HTTPException(status_code=400, detail=f"حداکثر {MAX_SCAN_PORTS} پورت در هر اسکن")
        out.update(range(a, b + 1))
    if not out:
        raise HTTPException(status_code=400, detail="هیچ پورتی وارد نشده")
    if len(out) > MAX_SCAN_PORTS:
        raise HTTPException(status_code=400, detail=f"حداکثر {MAX_SCAN_PORTS} پورت در هر اسکن (الان {len(out)})")
    return sorted(out)


async def _resolve(host: str) -> str:
    """نام را به IP تبدیل می‌کند و آدرس‌های داخلی/لوپ‌بک را رد می‌کند (جلوگیری از سوءاستفاده‌ی SSRF)."""
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except Exception:
        raise HTTPException(status_code=400, detail="آدرس سرور پیدا نشد (IP یا دامنه را بررسی کن)")
    ips = []
    for fam, _t, _p, _c, sa in infos:
        ips.append(sa[0])
    if not ips:
        raise HTTPException(status_code=400, detail="آدرس سرور پیدا نشد")
    ips.sort(key=lambda x: (":" in x, x))     # IPv4 اول
    ip = ips[0]
    try:
        addr = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        raise HTTPException(status_code=400, detail="آدرس نامعتبر")
    if not ALLOW_PRIVATE and not addr.is_global:
        raise HTTPException(status_code=400, detail="فقط سرورهای عمومی (IP قابل‌دسترس از اینترنت) قابل اسکن‌اند؛ آدرس داخلی/لوکال مجاز نیست")
    return ip


async def _probe_port(ip: str, port: int, timeout: float = SCAN_TIMEOUT) -> str:
    """open = سرویسی گوش می‌دهد · closed = به سرور می‌رسد ولی چیزی گوش نمی‌دهد (آزاد و قابل‌استفاده)
    · filtered = بدون پاسخ (فایروال/بلاک)"""
    try:
        r, w = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout)
        try:
            w.close()
            await w.wait_closed()
        except Exception:
            pass
        return "open"
    except asyncio.TimeoutError:
        return "filtered"
    except ConnectionRefusedError:
        return "closed"
    except OSError:
        return "filtered"
    except Exception:
        return "filtered"


async def scan_ports(ip: str, ports: list) -> dict:
    sem = asyncio.Semaphore(SCAN_CONCURRENCY)
    res = {}

    async def one(p):
        async with sem:
            res[p] = await _probe_port(ip, p)

    t0 = time.time()
    await asyncio.gather(*[one(p) for p in ports])
    return {"states": res, "seconds": round(time.time() - t0, 1)}


def _suggest(states: dict, own_ports: list = None) -> dict:
    """از روی نتیجه‌ی اسکن بهترین پورت (تکی) و بهترین سه‌تایی (چندپورتی) را پیشنهاد می‌دهد."""
    own = set(own_ports or [])
    usable = {p for p, st in states.items() if st == "closed" or (st == "open" and p in own)}
    order = []
    for p in PREFERRED:
        if p in usable and p not in order:
            order.append(p)
    for p in sorted(usable):
        if p not in order and p not in (22, 21, 25, 53, 110, 143, 3306, 3389, 5432, 5900, 6379):
            order.append(p)
    single = order[0] if order else None
    multi = None
    if len(order) >= 6:
        multi = dict(zip(("tcp", "grpc", "xhttp", "trojan", "ss", "vmess"), order[:6]))
    elif len(order) >= 3:
        multi = {"tcp": order[0], "grpc": order[1], "xhttp": order[2]}
    return {"single": single, "multi": multi}


def _rate_limit(key: str):
    now = time.time()
    log = [t for t in _SCAN_LOG.get(key, []) if now - t < 600]
    if len(log) >= 15:
        raise HTTPException(status_code=429, detail="تعداد اسکن‌ها زیاد است؛ چند دقیقه بعد دوباره امتحان کن")
    log.append(now)
    _SCAN_LOG[key] = log


def _client_key(request: Request) -> str:
    import main as M
    return request.cookies.get(getattr(M, "SESSION_COOKIE", "session")) or (request.client.host if request.client else "x")


@router.post("/api/vps/scan")
async def api_vps_scan(request: Request, _=Depends(op.require_auth)):
    import main as M
    body = await request.json()
    sid = str(body.get("server_id") or "").strip()
    sv = None
    if sid:
        sv = ex.xs_find_server(sid)
        if not sv:
            raise HTTPException(status_code=404, detail="سرور پیدا نشد")
        host = sv["host"]
    else:
        host = str(body.get("host") or "").strip()
    if not _valid_host(host):
        raise HTTPException(status_code=400, detail="آدرس سرور (IP یا دامنه) را درست وارد کن")
    ports = _parse_ports(body.get("ports") or "common")
    ip = await _resolve(host)
    _rate_limit(_client_key(request))
    if _SCAN_LOCK.locked():
        raise HTTPException(status_code=429, detail="یک اسکن دیگر در حال اجراست؛ کمی صبر کن")
    async with _SCAN_LOCK:
        r = await scan_ports(ip, ports)
    st = r["states"]
    open_p = sorted(p for p, v in st.items() if v == "open")
    closed_p = sorted(p for p, v in st.items() if v == "closed")
    filt_p = sorted(p for p, v in st.items() if v == "filtered")
    own = list((sv or {}).get("ports", {}).values()) if sv else []
    sug = _suggest(st, own)
    n = len(ports)
    if n >= 8 and len(filt_p) == n:
        verdict = "هیچ پاسخی نیامد: سرور خاموش است، IP اشتباه است، یا فایروال/دیتاسنتر کل پورت‌ها را بسته. فایروال VPS را بررسی کن."
    elif n >= 8 and len(closed_p) + len(open_p) == n and not open_p:
        verdict = "همه‌ی پورت‌ها به سرور می‌رسند و چیزی روی آن‌ها گوش نمی‌دهد (سرور تازه/بدون فایروال). هر پورتی قابل‌استفاده است."
    elif open_p or closed_p:
        verdict = f"{len(open_p)} پورت باز (سرویس فعال)، {len(closed_p)} پورت آزاد و قابل‌استفاده، {len(filt_p)} پورت فیلتر/بلاک."
    else:
        verdict = "نتیجه‌ی مشخصی به دست نیامد."
    if sv is not None:
        sv["last_scan"] = {"at": _now(), "open": open_p[:60], "usable": [p for p in PREFERRED if p in closed_p][:20],
                           "suggest": sug}
        try:
            await M.save_state()
        except Exception:
            pass
    return {
        "ok": True, "host": host, "ip": ip, "scanned": n, "seconds": r["seconds"],
        "open": [{"port": p, "service": SERVICES.get(p, "")} for p in open_p],
        "closed": closed_p, "filtered_count": len(filt_p),
        "filtered": filt_p[:200], "suggest": sug, "verdict": verdict,
        "note": "اسکن فقط TCP است؛ WireGuard روی UDP است و با این روش قابل‌سنجش نیست.",
    }


@router.get("/api/vps")
async def api_vps_list(request: Request, _=Depends(op.require_auth)):
    import main as M
    base = M.get_web_base(M.get_host(request))
    out = []
    for sv in ex.xs_servers():
        v = ex.xs_public_view(sv)
        v["install_cmd"] = f"bash <(curl -fsSL {base}/xs/{sv['token']}/install.sh)"
        out.append(v)
    return {"ok": True, "servers": out, "common_ports": COMMON_PORTS, "preferred": PREFERRED[:8]}


def _clean_name(n, host):
    n = re.sub(r"[\r\n\t<>]", " ", str(n or "")).strip()[:40]
    return n or host


@router.post("/api/vps")
async def api_vps_create(request: Request, _=Depends(op.require_auth)):
    import main as M
    body = await request.json()
    host = str(body.get("host") or "").strip().lower()
    if not _valid_host(host):
        raise HTTPException(status_code=400, detail="آدرس سرور (IP یا دامنه) را درست وارد کن")
    servers = ex.xs_servers()
    if len(servers) >= MAX_SERVERS:
        raise HTTPException(status_code=400, detail=f"حداکثر {MAX_SERVERS} سرور")
    if any(s.get("host") == host for s in servers):
        raise HTTPException(status_code=400, detail="این سرور قبلاً ثبت شده")
    mode = "single" if str(body.get("mode") or "").lower() == "single" else "multi"
    ports = ex.xs_normalize_ports(mode, body.get("ports") or {})
    sni = str(body.get("sni") or "www.microsoft.com").strip()
    if not re.match(r"^[A-Za-z0-9.-]{3,253}$", sni):
        raise HTTPException(status_code=400, detail="SNI نامعتبر است")
    sv = {
        "id": secrets.token_hex(4), "name": _clean_name(body.get("name"), host), "host": host, "sni": sni,
        "mode": mode, "ports": ports, "reality": ex._reality_keys(), "wg": ex._wg_keys(), "wg_next": 2,
        "token": secrets.token_urlsafe(24), "created_at": _now(),
    }
    if mode == "single":
        hint = body.get("snis_hint") if isinstance(body.get("snis_hint"), list) else []
        sv["snis"] = ex.xs_default_snis(sni, [str(x) for x in hint][:12])
    servers.append(sv)
    await M.save_state()
    M.log_activity("vps", f"سرور جدید اضافه شد: {sv['name']}", "ok")
    base = M.get_web_base(M.get_host(request))
    v = ex.xs_public_view(sv)
    v["install_cmd"] = f"bash <(curl -fsSL {base}/xs/{sv['token']}/install.sh)"
    return {"ok": True, "server": v}


@router.put("/api/vps/{sid}")
async def api_vps_update(sid: str, request: Request, _=Depends(op.require_owner)):
    import main as M
    sv = ex.xs_find_server(sid)
    if not sv:
        raise HTTPException(status_code=404, detail="سرور پیدا نشد")
    body = await request.json()
    locked = ex.xs_server_link_count(sid) > 0
    if "name" in body:
        sv["name"] = _clean_name(body.get("name"), sv["host"])
    wants_change = any(k in body for k in ("host", "sni", "mode", "ports"))
    if wants_change:
        if locked:
            raise HTTPException(status_code=400, detail="این سرور کانفیگ فعال دارد؛ آدرس/پورت/SNI فقط قبل از اولین ساخت قابل تغییر است (اول اشتراک‌های این سرور را حذف کن)")
        if "host" in body:
            h = str(body["host"]).strip().lower()
            if not _valid_host(h):
                raise HTTPException(status_code=400, detail="آدرس سرور نامعتبر است")
            if any(s.get("host") == h and s is not sv for s in ex.xs_servers()):
                raise HTTPException(status_code=400, detail="این آدرس برای سرور دیگری ثبت شده")
            sv["host"] = h
        if "sni" in body:
            sni = str(body["sni"]).strip()
            if not re.match(r"^[A-Za-z0-9.-]{3,253}$", sni):
                raise HTTPException(status_code=400, detail="SNI نامعتبر است")
            sv["sni"] = sni
        if "mode" in body:
            sv["mode"] = "single" if str(body["mode"]).lower() == "single" else "multi"
        if "ports" in body or "mode" in body:
            sv["ports"] = ex.xs_normalize_ports(sv["mode"], body.get("ports") or sv.get("ports") or {})
        if sv["mode"] == "single" and ("sni" in body or "mode" in body or "snis_hint" in body):
            hint = body.get("snis_hint") if isinstance(body.get("snis_hint"), list) else []
            sv["snis"] = ex.xs_default_snis(sv.get("sni"), [str(x) for x in hint][:12])
    await M.save_state()
    return {"ok": True, "server": ex.xs_public_view(sv)}


@router.delete("/api/vps/{sid}")
async def api_vps_delete(sid: str, request: Request, _=Depends(op.require_owner)):
    import main as M
    sv = ex.xs_find_server(sid)
    if not sv:
        raise HTTPException(status_code=404, detail="سرور پیدا نشد")
    n = ex.xs_server_link_count(sid)
    if n:
        raise HTTPException(status_code=400, detail=f"{n} کانفیگ به این سرور وصل است؛ اول آن‌ها را حذف کن")
    ex.xs_servers().remove(sv)
    await M.save_state()
    M.log_activity("vps", f"سرور حذف شد: {sv.get('name')}", "ok")
    return {"ok": True}


@router.post("/api/vps/{sid}/check")
async def api_vps_check(sid: str, request: Request, _=Depends(op.require_auth)):
    """هر پورت TCP تنظیم‌شده‌ی سرور را می‌سنجد: open = Xray بالاست، closed = نصب نشده/بالا نیامده، filtered = فایروال."""
    import main as M
    sv = ex.xs_find_server(sid)
    if not sv:
        raise HTTPException(status_code=404, detail="سرور پیدا نشد")
    ip = await _resolve(sv["host"])
    out = {}
    seen = {}
    for kind in ex.xs_kinds(sv):
        port = sv["ports"][kind]
        if port not in seen:
            t0 = time.time()
            st = await _probe_port(ip, port, 3.0)
            seen[port] = {"port": port, "state": st, "ms": round((time.time() - t0) * 1000) if st == "open" else None}
        out[kind] = seen[port]
    running = all(v["state"] == "open" for v in out.values())
    sv["last_check"] = {"at": _now(), "running": running}
    await M.save_state()
    nlinks = ex.xs_server_link_count(sid)
    if not running and nlinks == 0:
        msg = ("هنوز هیچ کانفیگی با این سرور ساخته نشده؛ تا اولین کانفیگ نسازی، Xray روی هیچ پورتی گوش نمی‌دهد (طبیعی است). "
               "از «ساخت سریع ← با سرور» یکی بساز و ۱ دقیقه بعد دوباره تست کن.")
    elif running:
        msg = "✅ Xray روی سرور بالاست و پورت‌ها از بیرون باز هستند."
    elif nlinks and any(v["state"] == "closed" for v in out.values()):
        msg = "سرور در دسترس است ولی Xray روی پورت‌ها گوش نمی‌دهد. روی VPS اجرا کن: /usr/local/bin/vw-sync; cat /var/log/vw-sync.log; journalctl -u xray -n 20 --no-pager — علت دقیق همان‌جا نوشته می‌شود."
    else:
        msg = "پورت‌ها از بیرون بسته‌اند (فایروال VPS یا دیتاسنتر). پورت‌ها را در فایروال باز کن یا با «اسکن پورت» پورت دیگری انتخاب کن."
    return {"ok": True, "ports": out, "running": running, "message": msg}


# ───────────────────────── اسکنر SNI (برای Reality) ─────────────────────────
# SNI خوب = سایت بزرگ با TLS 1.3 و HTTP/2 و گواهی معتبر، با handshake سریع.
SNI_CANDIDATES = [
    "www.microsoft.com", "www.apple.com", "www.amazon.com", "www.google.com", "dl.google.com", "www.youtube.com",
    "addons.mozilla.org", "www.mozilla.org", "www.samsung.com", "www.nvidia.com", "www.amd.com", "www.intel.com",
    "www.asus.com", "www.cisco.com", "www.oracle.com", "www.ibm.com", "www.dell.com", "www.hp.com", "www.lenovo.com",
    "www.logitech.com", "www.sony.com", "www.nintendo.com", "www.spotify.com", "www.tesla.com", "www.paypal.com",
    "www.visa.com", "www.mastercard.com", "www.cloudflare.com", "www.bing.com", "www.office.com", "azure.microsoft.com",
    "learn.microsoft.com", "github.com", "gitlab.com", "www.python.org", "www.docker.com", "ubuntu.com", "www.debian.org",
    "www.adobe.com", "www.salesforce.com", "zoom.us", "www.speedtest.net", "www.booking.com", "www.airbnb.com",
    "www.ebay.com", "www.walmart.com", "www.bbc.com", "www.cnn.com", "www.nytimes.com", "www.wikipedia.org",
    "www.twitch.tv", "www.lovelive-anime.jp", "www.swift.org", "www.kernel.org", "www.mit.edu", "www.stanford.edu",
]
_DOMAIN_RE = re.compile(r"^(?=.{4,253}$)([A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,24}$")


def _parse_domains(raw) -> list:
    if isinstance(raw, list):
        raw = "\n".join(str(x) for x in raw)
    out = []
    for part in re.split(r"[\s,،;]+", str(raw or "")):
        part = part.strip().lower().replace("https://", "").replace("http://", "").split("/")[0]
        if part and _DOMAIN_RE.match(part) and part not in out:
            out.append(part)
    return out


async def _sni_probe(domain: str, timeout: float = 4.0) -> dict:
    res = {"domain": domain, "ok": False, "ms": None, "alpn": None, "tls": None, "ip": None, "reason": ""}
    try:
        ip = await _resolve(domain)
        res["ip"] = ip
    except HTTPException:
        res["reason"] = "resolve"
        return res
    except Exception:
        res["reason"] = "resolve"
        return res
    ctx = ssl.create_default_context()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_3
    ctx.set_alpn_protocols(["h2", "http/1.1"])
    t0 = time.time()
    try:
        r, w = await asyncio.wait_for(asyncio.open_connection(ip, 443, ssl=ctx, server_hostname=domain), timeout)
        res["ms"] = round((time.time() - t0) * 1000)
        so = w.get_extra_info("ssl_object")
        res["tls"] = so.version() if so else None
        res["alpn"] = so.selected_alpn_protocol() if so else None
        try:
            w.close()
            await w.wait_closed()
        except Exception:
            pass
        if res["alpn"] == "h2" and res["tls"] == "TLSv1.3":
            res["ok"] = True
        else:
            res["reason"] = "no_h2" if res["alpn"] != "h2" else "no_tls13"
    except asyncio.TimeoutError:
        res["reason"] = "timeout"
    except ssl.SSLCertVerificationError:
        res["reason"] = "bad_cert"
    except ssl.SSLError:
        res["reason"] = "no_tls13"
    except Exception:
        res["reason"] = "unreachable"
    return res


@router.post("/api/vps/sni-scan")
async def api_vps_sni_scan(request: Request, _=Depends(op.require_auth)):
    import main as M
    body = await request.json()
    custom = _parse_domains(body.get("custom"))[:40]
    cands = list(dict.fromkeys(custom + (SNI_CANDIDATES if body.get("builtin", True) else [])))[:90]
    if not cands:
        raise HTTPException(status_code=400, detail="هیچ دامنه‌ای برای اسکن نیست")
    _rate_limit(_client_key(request) + ":sni")
    sem = asyncio.Semaphore(20)

    async def one(d):
        async with sem:
            return await _sni_probe(d)

    t0 = time.time()
    rows = await asyncio.gather(*[one(d) for d in cands])
    good = sorted([r for r in rows if r["ok"]], key=lambda r: r["ms"])
    bad = [r for r in rows if not r["ok"]]
    sid = str(body.get("server_id") or "").strip()
    vps_cmd = None
    sv = ex.xs_find_server(sid) if sid else None
    if sv:
        vps_cmd = f"curl -fsSL {M.get_web_base(M.get_host(request))}/xs/{sv['token']}/sni.py | python3"
    return {
        "ok": True, "scanned": len(cands), "seconds": round(time.time() - t0, 1),
        "good": good[:40], "best": [r["domain"] for r in good[:5]], "bad_count": len(bad),
        "bad": [{"domain": r["domain"], "reason": r["reason"]} for r in bad[:40]],
        "vps_cmd": vps_cmd,
        "note": "این اندازه‌گیری از روی پنل است. SNI واقعاً بهینه آن است که از خود VPS سریع باشد؛ دستور زیر را روی VPS اجرا کن تا همین لیست از دید VPS رتبه‌بندی شود.",
    }


_SNI_SCRIPT = r'''#!/usr/bin/env python3
# رتبه‌بندی SNI از دید همین VPS: TLS1.3 + h2 + سرعت handshake
import socket, ssl, time
from concurrent.futures import ThreadPoolExecutor
C = __C__
def probe(d):
    try:
        ctx = ssl.create_default_context(); ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        ctx.set_alpn_protocols(["h2", "http/1.1"])
        t = time.time(); s = socket.create_connection((d, 443), 4)
        w = ctx.wrap_socket(s, server_hostname=d); ms = int((time.time() - t) * 1000)
        a = w.selected_alpn_protocol(); w.close()
        return (d, a == "h2", ms)
    except Exception:
        return (d, False, None)
with ThreadPoolExecutor(20) as ex:
    R = list(ex.map(probe, C))
ok = sorted([r for r in R if r[1]], key=lambda r: r[2])
print("بهترین SNI ها از دید این سرور:")
for i, (d, _, ms) in enumerate(ok[:15], 1):
    print(f"{i:2}. {d:<28} {ms} ms")
print(f"\n{len(ok)} مورد از {len(C)} مناسب بود.")
'''


@router.get("/xs/{token}/sni.py")
async def api_vps_sni_script(token: str):
    from fastapi.responses import PlainTextResponse
    if not ex.xs_find_by_token(token):
        raise HTTPException(status_code=404, detail="not found")
    return PlainTextResponse(_SNI_SCRIPT.replace("__C__", json.dumps(SNI_CANDIDATES)))

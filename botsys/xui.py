"""3x-ui Bearer API client + multi-token allocator.

The bot never logs or displays raw API tokens. Each configured token is scoped
to a target inbound and a local capacity policy. The remote panel remains the
source of truth for client traffic and state.
"""
from __future__ import annotations
import asyncio, json, logging, os, time, uuid, base64
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
import httpx

log = logging.getLogger("vodiwalker.xui")

TIMEOUT = httpx.Timeout(15.0, connect=7.0)
RETRY_CODES = {408, 425, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524}

class XUIError(Exception):
    pass

class XUIAuthError(XUIError):
    pass

class XUIUnavailable(XUIError):
    pass

def now_ms() -> int:
    return int(time.time() * 1000)

def normalize_base_url(url: str) -> str:
    url = str(url or "").strip().rstrip("/")
    if not url:
        return ""
    if not url.startswith(("http://","https://")):
        url = "https://" + url
    return url

def fmt_bytes(n: int) -> str:
    n=max(0,int(n or 0))
    units=("B","KB","MB","GB","TB","PB")
    x=float(n)
    for u in units:
        if x < 1024 or u == units[-1]:
            return f"{x:.1f} {u}" if u != "B" else f"{int(x)} B"
        x/=1024
    return f"{x:.1f} PB"

@dataclass
class XUIResult:
    success: bool
    data: Any = None
    message: str = ""
    status: int = 0

class XUIClient:
    def __init__(self, base_url: str, token: str, *, verify_tls: bool=True, timeout: float=15.0):
        self.base_url=normalize_base_url(base_url)
        self.token=str(token or "").strip()
        self.verify_tls=bool(verify_tls)
        self.timeout=httpx.Timeout(float(timeout), connect=min(8.0,float(timeout)))
        self._lock=asyncio.Lock()

    def _url(self,path:str)->str:
        return self.base_url + (path if path.startswith("/") else "/"+path)

    async def request(self, method:str, path:str, json_body:Any=None, params:dict|None=None)->XUIResult:
        if not self.base_url or not self.token:
            raise XUIError("آدرس پنل یا API Token تنظیم نشده است.")
        headers={"Accept":"application/json","Authorization":f"Bearer {self.token}","User-Agent":"VodiWalkerBot/2.0"}
        if json_body is not None:
            headers["Content-Type"]="application/json"
        last=""
        async with self._lock:
            for attempt in range(3):
                try:
                    async with httpx.AsyncClient(timeout=self.timeout, verify=self.verify_tls, follow_redirects=True) as c:
                        r=await c.request(method.upper(),self._url(path),headers=headers,json=json_body,params=params)
                    if r.status_code in (401,403):
                        raise XUIAuthError(f"احراز هویت 3x-ui رد شد (HTTP {r.status_code}).")
                    if r.status_code in RETRY_CODES and attempt<2:
                        await asyncio.sleep(0.5*(2**attempt)); continue
                    try: body=r.json()
                    except Exception: body={"raw":r.text[:2000]}
                    if r.status_code>=400:
                        msg=(body.get("msg") if isinstance(body,dict) else "") or (body.get("message") if isinstance(body,dict) else "") or f"HTTP {r.status_code}"
                        return XUIResult(False,body,str(msg),r.status_code)
                    if isinstance(body,dict) and body.get("success") is False:
                        return XUIResult(False,body.get("obj"),str(body.get("msg") or "عملیات پنل ناموفق بود"),r.status_code)
                    return XUIResult(True,body.get("obj") if isinstance(body,dict) and "obj" in body else body,str(body.get("msg") or "") if isinstance(body,dict) else "",r.status_code)
                except XUIAuthError: raise
                except (httpx.TimeoutException,httpx.NetworkError) as e:
                    last=str(e)
                    if attempt<2:
                        await asyncio.sleep(0.5*(2**attempt)); continue
                except Exception as e:
                    last=str(e)
                    if attempt<2:
                        await asyncio.sleep(0.4*(2**attempt)); continue
        raise XUIUnavailable(f"ارتباط با پنل 3x-ui برقرار نشد: {last or 'unknown error'}")

    async def status(self):
        return await self.request("GET","/panel/api/server/status")

    async def inbounds(self):
        return await self.request("GET","/panel/api/inbounds/list")

    async def clients(self):
        return await self.request("GET","/panel/api/clients/list")

    async def client(self,email:str):
        return await self.request("GET",f"/panel/api/clients/get/{httpx.URL('').copy_with(path=email).path.lstrip('/')}")

    async def traffic(self,email:str):
        return await self.request("GET",f"/panel/api/inbounds/getClientTraffics/{httpx.URL('').copy_with(path=email).path.lstrip('/')}")

    async def client_ips(self,email:str):
        safe=httpx.URL("").copy_with(path=email).path.lstrip("/")
        return await self.request("POST",f"/panel/api/clients/ips/{safe}",{})

    async def add_client(self,email:str,inbound_id:int,total_bytes:int,expiry_ms:int=0,limit_ip:int=0,tg_id:int=0,comment:str="",client_id:str|None=None)->dict:
        # Modern 3x-ui: client object + inboundIds. Supplying UUID preserves an
        # old VLESS/VMess identity when the panel accepts it.
        client={"email":email,"totalGB":max(0,int(total_bytes)),"expiryTime":max(0,int(expiry_ms)),
                "limitIp":max(0,int(limit_ip)),"limitHwid":0,"tgId":int(tg_id or 0),
                "comment":comment[:200],"enable":True}
        if client_id:
            client["id"]=client_id
        res=await self.request("POST","/panel/api/clients/add",{"client":client,"inboundIds":[int(inbound_id)]})
        if not res.success:
            # Older 3x-ui builds use /inbounds/addClient with a JSON-encoded
            # settings object. Try it once for compatibility.
            settings={"clients":[client]}
            old={"id":int(inbound_id),"settings":json.dumps(settings,separators=(",",":"))}
            res2=await self.request("POST","/panel/api/inbounds/addClient",old)
            if not res2.success: raise XUIError(res2.message or res.message)
            return {"email":email,"id":client.get("id"),"legacy":True}
        return res.data if isinstance(res.data,dict) else {"email":email,"id":client.get("id")}

    async def update_client(self,email:str,client:dict,inbound_id:int|None=None)->dict:
        safe=httpx.URL("").copy_with(path=email).path.lstrip("/")
        body=dict(client)
        if inbound_id is not None: body["inboundId"]=int(inbound_id)
        res=await self.request("POST",f"/panel/api/clients/update/{safe}",body)
        if not res.success:
            # Legacy endpoint; requires client id + inbound id.
            cid=body.get("id") or body.get("clientId")
            iid=inbound_id or body.get("inboundId")
            if cid and iid:
                old={"id":int(iid),"settings":json.dumps({"clients":[body]},separators=(",",":"))}
                res=await self.request("POST",f"/panel/api/inbounds/updateClient/{cid}",old)
        if not res.success: raise XUIError(res.message)
        return res.data if isinstance(res.data,dict) else {}

    async def delete_client(self,email:str,inbound_id:int|None=None)->bool:
        safe=httpx.URL("").copy_with(path=email).path.lstrip("/")
        res=await self.request("DELETE",f"/panel/api/clients/delete/{safe}")
        if res.success: return True
        # Older panels:
        if inbound_id is not None:
            info=await self.client(email)
            obj=info.data.get("client",info.data) if isinstance(info.data,dict) else {}
            cid=obj.get("id") or obj.get("password") or email
            old=await self.request("POST",f"/panel/api/inbounds/{int(inbound_id)}/delClient/{httpx.URL('').copy_with(path=str(cid)).path.lstrip('/')}",{})
            return old.success
        return False

    async def links(self,email:str)->list[str]:
        safe=httpx.URL("").copy_with(path=email).path.lstrip("/")
        res=await self.request("GET",f"/panel/api/clients/links/{safe}")
        if not res.success: return []
        obj=res.data
        out=[]
        if isinstance(obj,str): out=[x.strip() for x in obj.splitlines() if x.strip()]
        elif isinstance(obj,list):
            for x in obj:
                if isinstance(x,str): out.append(x)
                elif isinstance(x,dict):
                    for k in ("uri","link","url"):
                        if isinstance(x.get(k),str): out.append(x[k])
        return [x for x in out if x.startswith(("vless://","vmess://","trojan://","ss://"))]

    async def reset_traffic(self,email:str)->bool:
        safe=httpx.URL("").copy_with(path=email).path.lstrip("/")
        r=await self.request("POST",f"/panel/api/clients/resetTraffic/{safe}",{})
        return r.success

    async def toggle_client(self,email:str,enabled:bool)->bool:
        safe=httpx.URL("").copy_with(path=email).path.lstrip("/")
        r=await self.request("POST",f"/panel/api/clients/{safe}/enable" if enabled else f"/panel/api/clients/{safe}/disable",{})
        if r.success:return True
        info=await self.client(email)
        obj=info.data.get("client",info.data) if isinstance(info.data,dict) else {}
        obj["enable"]=bool(enabled)
        await self.update_client(email,obj)
        return True

async def test_connection(base_url:str,token:str,verify_tls:bool=True)->dict:
    c=XUIClient(base_url,token,verify_tls=verify_tls)
    r=await c.status()
    if not r.success: raise XUIError(r.message)
    return r.data if isinstance(r.data,dict) else {"status":r.data}

def client_usage(row:dict)->tuple[int,int]:
    traffic=row.get("traffic") or {}
    return int(traffic.get("up") or 0)+int(traffic.get("down") or 0), int(row.get("totalGB") or 0)

def client_count(rows:list[dict], inbound_id:int|None=None)->int:
    if inbound_id is None: return len(rows)
    return sum(1 for r in rows if int(inbound_id) in [int(x) for x in (r.get("inboundIds") or [])])

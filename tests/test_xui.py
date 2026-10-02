import sys, os, asyncio, json, os, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx

class FakeResponse:
    def __init__(self,status=200,data=None): self.status_code=status; self._data=data or {}
    def json(self): return self._data
    @property
    def text(self): return json.dumps(self._data)

class FakeAsyncClient:
    def __init__(self,*a,**kw): pass
    async def __aenter__(self): return self
    async def __aexit__(self,*a): pass
    async def request(self,method,url,headers=None,json=None,params=None):
        if url.endswith("/panel/api/server/status"):
            return FakeResponse(200,{"success":True,"obj":{"xray":{"state":"running"}}})
        if url.endswith("/panel/api/inbounds/list"):
            return FakeResponse(200,{"success":True,"obj":[{"id":7,"remark":"Main"}]})
        if url.endswith("/panel/api/clients/list"):
            return FakeResponse(200,{"success":True,"obj":[
                {"email":"a","inboundIds":[7],"totalGB":10737418240,"enable":True,"traffic":{"up":10,"down":20}},
                {"email":"b","inboundIds":[8],"totalGB":10737418240,"enable":True,"traffic":{"up":30,"down":40}},
            ]})
        if url.endswith("/panel/api/clients/add"):
            return FakeResponse(200,{"success":True,"obj":{"id":"u1","email":"c"}})
        return FakeResponse(404,{"success":False,"msg":"not found"})

async def main():
    import botsys.xui as x
    old=x.httpx.AsyncClient; x.httpx.AsyncClient=FakeAsyncClient
    try:
        c=x.XUIClient("https://panel.test","TOKEN")
        st=await c.status(); assert st.success and st.data["xray"]["state"]=="running"
        ins=await c.inbounds(); assert ins.success and ins.data[0]["id"]==7
        rows=(await c.clients()).data; assert len(rows)==2
        s=x.client_count(rows,7); assert s==1
        res=await c.add_client("c",7,10,0,1); assert res["id"]=="u1"
        assert x.normalize_base_url("panel.test")=="https://panel.test"
    finally:x.httpx.AsyncClient=old
    print("test_xui: PASS")
if __name__=="__main__":asyncio.run(main())

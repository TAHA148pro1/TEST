import sys, os, asyncio, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
async def main():
    td=tempfile.mkdtemp(); os.environ["RAILWAY_VOLUME_MOUNT_PATH"]=td
    import main as app
    app.DATA_DIR=Path(td); app.DATA_FILE=Path(td)/"state.json"; app.SECRET_FILE=Path(td)/"secret.key"
    from botsys import store
    store.TG_USERS.clear(); store.TG_USER_CONFIGS.clear(); store.TG_SETTINGS.clear()
    from botsys.settings import DEFAULT_BOT_SETTINGS
    store.TG_SETTINGS.update(DEFAULT_BOT_SETTINGS)
    store.TG_SETTINGS["require_channels"]=False
    store.TG_SETTINGS["free_quota_total"]=1
    store.TG_SETTINGS["free_volume_gb"]=10
    store.TG_USERS["77"]={"telegram_id":77,"role":"user","is_blocked":False,"quota_used":0,"configs_received":0}
    import botsys.services.xui_manager as xm
    import botsys.services.configs as cs
    class FakeX:
        def __init__(self,*a,**kw): pass
        async def client(self,email): return type("R",(),{"data":{"client":{"id":"uuid-1","email":email,"totalGB":10737418240,"expiryTime":0,"enable":True,"traffic":{"up":0,"down":0}}}})()
        async def links(self,email): return ["vless://uuid-1@example.com:443?type=tcp#test"]
    oldX=cs.XUIClient; oldAlloc=xm.allocate_client
    xm._keys()["k"]={"id":"k","name":"A","base_url":"https://p","inbound_id":7,"enabled":True,"max_configs":20,"max_total_gb":200,
                     "token_enc":app.encrypt_secret("token")}
    async def alloc(**kw): return ({"id":"uuid-1","email":kw["email"]},{"id":"k","inbound_id":7,"base_url":"https://p","verify_tls":True})
    cs.XUIClient=FakeX; xm.allocate_client=alloc
    try:
        from botsys.services import issuing
        res=await issuing.issue_free_config(77)
        assert res.ok, res.reason
        assert res.user_config["xui_key_id"]=="k"
        assert store.TG_USERS["77"]["quota_used"]==1
    finally:
        cs.XUIClient=oldX; xm.allocate_client=oldAlloc
    print("test_issue: PASS")
if __name__=="__main__":asyncio.run(main())

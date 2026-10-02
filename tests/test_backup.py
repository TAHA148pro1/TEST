import sys, os, asyncio, json, os, tempfile, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
async def main():
    td=tempfile.mkdtemp()
    os.environ["RAILWAY_VOLUME_MOUNT_PATH"]=td
    os.environ["TELEGRAM_SUPER_ADMIN_IDS"]="123"
    import importlib, main as app
    app.DATA_DIR=Path(td); app.DATA_FILE=Path(td)/"vodiwalker_state.json"; app.SECRET_FILE=Path(td)/"secret.key"
    app.XUI_KEYS["k1"]={"id":"k1","name":"A","base_url":"https://p","inbound_id":7,"enabled":True,
        "max_configs":20,"max_total_gb":200,"token_enc":app.encrypt_secret("secret-token")}
    from botsys import store
    store.TG_USERS["123"]={"telegram_id":123,"role":"super_admin"}
    store.TG_USER_CONFIGS["1"]={"id":"1","telegram_id":123,"email":"x","legacy":False}
    await app.save_state()
    from botsys.services import backups
    archive,fn=await backups.create_archive()
    assert fn.startswith("vodiwalker_backup_")
    state,secret,fmt=backups._read(archive); assert fmt==2 and state["xui_keys"]["k1"]["token_enc"]
    app.XUI_KEYS.clear(); store.TG_USERS.clear(); store.TG_USER_CONFIGS.clear()
    res=await backups.restore_archive(archive)
    assert res["ok"] and "k1" in app.XUI_KEYS and store.TG_USERS["123"]["role"]=="super_admin"
    assert app.decrypt_secret(app.XUI_KEYS["k1"]["token_enc"])=="secret-token"
    print("test_backup: PASS")
if __name__=="__main__":asyncio.run(main())

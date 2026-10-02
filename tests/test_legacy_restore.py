import sys, os, asyncio, json, os, tempfile, zipfile, io
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
async def main():
    td=tempfile.mkdtemp(); os.environ["RAILWAY_VOLUME_MOUNT_PATH"]=td
    import main as app
    app.DATA_DIR=Path(td); app.DATA_FILE=Path(td)/"state.json"; app.SECRET_FILE=Path(td)/"secret.key"
    old={"links":{"old1":{"label":"Old","limit_bytes":10737418240}},
         "tg_users":{"10":{"telegram_id":10,"role":"user"}},
         "tg_roles":{}, "tg_user_configs":{"1":{"id":"1","telegram_id":10,"link_uid":"old1","source":"free"}},
         "tg_quotas":{},"tg_channels":{},"tg_tickets":{},"tg_messages":{},"tg_broadcasts":{},"tg_stats":{},"tg_audit":[],"tg_settings":{},"tg_texts":{},"tg_meta":{"schema_version":6}}
    bio=io.BytesIO()
    with zipfile.ZipFile(bio,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json",json.dumps({"format":1,"app":"VodiWalker"}))
        z.writestr("state.json",json.dumps(old))
        z.writestr("secret.key","legacy-secret")
    from botsys.services import backups
    res=await backups.restore_archive(bio.getvalue())
    from botsys import store
    assert res["format"]==1 and res["legacy_configs"]==1 and store.TG_USERS["10"]["role"]=="user"
    assert app.LINKS["old1"]["label"]=="Old"
    print("test_legacy_restore: PASS")
if __name__=="__main__":asyncio.run(main())

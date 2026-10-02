
import sys, asyncio, tempfile, os, importlib
sys.path.insert(0,'.')
mods=[
 'main','botsys.store','botsys.security','botsys.xui','botsys.services.configs',
 'botsys.services.xui_manager','botsys.services.backups','botsys.handlers.user',
 'botsys.handlers.admin','botsys.handlers.router','botsys.runner'
]
for m in mods:
    importlib.import_module(m)
print("imports: PASS")

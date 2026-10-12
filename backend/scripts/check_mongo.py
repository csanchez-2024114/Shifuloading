import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import Config
print('MONGO_URI=', Config.MONGO_URI)
from app.core.mongo import MongoManager
import asyncio
m = MongoManager()
try:
    asyncio.run(m.connect())
    print('OK connected, db:', m.db.name)
    asyncio.run(m.disconnect())
except Exception as e:
    import traceback
    traceback.print_exc()
    print('ERROR', e)

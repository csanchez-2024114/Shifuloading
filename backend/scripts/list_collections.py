import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import Config
from pymongo import MongoClient

client = MongoClient(Config.MONGO_URI)
db = client[Config.MONGO_DB_NAME]
print('DB:', Config.MONGO_DB_NAME)
print('Collections:')
for c in sorted(db.list_collection_names()):
    print('-', c)
client.close()

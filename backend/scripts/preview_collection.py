import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import Config
from pymongo import MongoClient
from bson.json_util import dumps

if len(sys.argv) < 2:
    print('Usage: preview_collection.py <collection> [limit]')
    sys.exit(1)

coll = sys.argv[1]
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10

client = MongoClient(Config.MONGO_URI)
db = client[Config.MONGO_DB_NAME]

print(f"Previewing up to {limit} docs from collection: {coll}\n")
for i, doc in enumerate(db[coll].find({}).limit(limit)):
    print(f"--- doc {i+1} ---")
    print(dumps(doc))

client.close()

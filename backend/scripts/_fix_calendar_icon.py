import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import Config
from pymongo import MongoClient

client = MongoClient(Config.MONGO_URI)
db = client[Config.MONGO_DB_NAME]

result = db["catalog_apps"].update_one(
    {"nameApi": "google calendar"},
    {"$set": {"icon": "https://ssl.gstatic.com/calendar/images/dynamiclogo_2020q4/calendar_31_2x.png"}}
)
print("Updated:", result.modified_count)
doc = db["catalog_apps"].find_one({"nameApi": "google calendar"}, {"_id": 0})
print("Final doc:", doc)
client.close()

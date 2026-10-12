import sys
import os
from pathlib import Path
import datetime
import gzip

# Asegurar que el proyecto esté en sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import Config
from pymongo import MongoClient
from bson.json_util import dumps


def main():
    uri = Config.MONGO_URI
    db_name = Config.MONGO_DB_NAME
    client = MongoClient(uri)
    db = client[db_name]

    out_dir = Path('backups')
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    created = []

    for coll in sorted(db.list_collection_names()):
        out_file = out_dir / f"{db_name}_{coll}_{ts}.json.gz"
        print(f"Backing up collection: {coll} -> {out_file}")
        count = 0
        with gzip.open(out_file, 'wt', encoding='utf-8') as f:
            for doc in db[coll].find({}):
                f.write(dumps(doc))
                f.write('\n')
                count += 1
        created.append((coll, out_file, count))

    print('\nBackup complete. Summary:')
    for coll, path, count in created:
        print(f" - {coll}: {count} docs -> {path}")

    client.close()


if __name__ == '__main__':
    main()

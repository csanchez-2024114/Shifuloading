import sys
import os
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import Config
from pymongo import MongoClient
from app.core.db_utils import canonicalize_email
from bson.json_util import dumps


def extract_email_candidates(doc):
    # Search common fields where email might be stored
    candidates = []
    if isinstance(doc, dict):
        if 'metadata' in doc and isinstance(doc['metadata'], dict):
            md = doc['metadata']
            for k in ('email', 'correo', 'correo_usuario', 'user_email'):
                if k in md and md[k]:
                    candidates.append(md[k])
        for k in ('email', 'correo', 'correo_usuario', 'user_email'):
            if k in doc and doc[k]:
                candidates.append(doc[k])
    return candidates


def main(apply_changes=False, limit=None):
    uri = Config.MONGO_URI
    db_name = Config.MONGO_DB_NAME
    client = MongoClient(uri)
    db = client[db_name]
    coll_name = 'user_connected_accounts'
    coll = db[coll_name]

    query = {}
    cursor = coll.find(query)
    if limit:
        cursor = cursor.limit(limit)

    planned = []
    modified = 0

    for doc in cursor:
        _id = doc.get('_id')
        candidates = extract_email_candidates(doc)
        canonical = None
        for c in candidates:
            e = canonicalize_email(c)
            if e:
                canonical = e
                break
        if not canonical:
            # cannot canonicalize, skip
            continue

        updates = {}
        # ensure both legacy and canonical fields exist
        if doc.get('correo') != canonical:
            updates['correo'] = canonical
        if doc.get('email') != canonical:
            updates['email'] = canonical
        # ensure metadata.email
        metadata = doc.get('metadata') or {}
        if metadata.get('email') != canonical:
            updates['metadata.email'] = canonical

        if updates:
            planned.append({'_id': _id, 'updates': updates})
            if apply_changes:
                set_doc = {k: v for k, v in updates.items()}
                # Use dot notation for nested set
                coll.update_one({'_id': _id}, {'$set': set_doc})
                modified += 1

    client.close()

    print('Planned changes count:', len(planned))
    if not apply_changes:
        # show sample
        for i, p in enumerate(planned[:20]):
            print(i+1, dumps(p))
    else:
        print('Applied changes:', modified)


if __name__ == '__main__':
    apply_changes = '--apply' in sys.argv
    limit = None
    for a in sys.argv[1:]:
        if a.startswith('--limit='):
            try:
                limit = int(a.split('=',1)[1])
            except Exception:
                limit = None
    main(apply_changes=apply_changes, limit=limit)

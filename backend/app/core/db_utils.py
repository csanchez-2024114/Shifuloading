"""Utilities for DB access using canonical (English) field names."""
from typing import Any, Dict, Optional
from app.core.constants import Collections
from app.core.mongo import get_sync_database

def canonicalize_email(email: Optional[str]) -> Optional[str]:
    if not email:
        return None
    return email.strip().lower()

def find_user_by_email(db=None, email: Optional[str]=None) -> Optional[Dict[str, Any]]:
    db = db or get_sync_database()
    e = canonicalize_email(email)
    if not e:
        return None
    return db[Collections.USERS].find_one({'email': e})

def update_user_preferences(db=None, email: Optional[str]=None, key: str='', value: Any=None) -> Dict:
    db = db or get_sync_database()
    e = canonicalize_email(email)
    if not e:
        raise ValueError('email required')
    set_payload = {
        f'preferences.{key}': value,
        'email': e,
    }
    push_payload = {'preferences_history': {'key': key, 'value': value}}
    update_doc = {'$set': set_payload, '$push': push_payload}
    result = db[Collections.USERS].update_one({'email': e}, update_doc)
    return {'matched_count': result.matched_count, 'modified_count': result.modified_count}

def find_memories_by_email(db=None, email: Optional[str]=None) -> Optional[Dict[str, Any]]:
    db = db or get_sync_database()
    e = canonicalize_email(email)
    if not e:
        return None
    return db[Collections.MEMORIES].find_one({'user_email': e})

def upsert_memories_by_email(db=None, email: Optional[str]=None, doc: Optional[Dict[str, Any]]=None):
    db = db or get_sync_database()
    e = canonicalize_email(email)
    if not e:
        raise ValueError('email required')
    doc = doc or {}
    doc['user_email'] = e
    result = db[Collections.MEMORIES].update_one({'user_email': e}, {'$set': doc}, upsert=True)
    return {'matched_count': result.matched_count, 'upserted_id': getattr(result, 'upserted_id', None)}

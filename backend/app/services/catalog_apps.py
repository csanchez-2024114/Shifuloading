from bson import ObjectId
from datetime import datetime
import re
from typing import List, Optional

def _sanitize_doc(doc):
    if isinstance(doc, dict):
        return {k: _sanitize_doc(v) for k, v in doc.items()}
    if isinstance(doc, ObjectId):
        return str(doc)
    return doc

async def get_all(mongo=None):
    if mongo is None:
        return []
    cursor = mongo.catalog_apps.find().sort('created_at', 1)
    items = await cursor.to_list(length=None)
    return [_sanitize_doc(i) for i in items]

async def create_app(data, mongo=None):
    if not data or not isinstance(data, dict):
        raise ValueError('No se proporcionaron datos para crear la app')
    if mongo is None:
        raise RuntimeError('MongoDB no disponible')
    name = (data.get('name') or '').strip()
    nameApi = (data.get('nameApi') or '').strip()
    is_shifu = name.lower() == 'shifu' or nameApi.lower() == 'shifu'
    if is_shifu:
        required = ['name', 'nameApi', 'icon', 'category']
        missing = [f for f in required if not data.get(f)]
        if missing:
            raise ValueError(f"Faltan campos obligatorios para Shifu: {', '.join(missing)}")
    new = {'name': data.get('name'), 'nameApi': nameApi or name, 'icon': data.get('icon'), 'active': bool(data.get('active', True)), 'visible': bool(data.get('visible', True)), 'category': data.get('category', ''), 'created_at': datetime.utcnow().isoformat()}
    if new['nameApi']:
        existing = await mongo.catalog_apps.find_one({'nameApi': {'$regex': f"^{re.escape(new['nameApi'])}$", '$options': 'i'}})
        if existing:
            raise ValueError(f"nameApi debe ser único: {new['nameApi']}")
    res = await mongo.catalog_apps.insert_one(new)
    created = await mongo.catalog_apps.find_one({'_id': res.inserted_id})
    return _sanitize_doc(created)

async def update_app(app_id, data, mongo=None):
    if mongo is None:
        raise RuntimeError('MongoDB no disponible')
    data = {k: v for k, v in (data or {}).items() if k != 'connected'}
    try:
        oid = ObjectId(app_id)
        query = {'_id': oid}
        exclude = {'_id': {'$ne': oid}}
    except Exception:
        query = {'_id': app_id}
        exclude = {'_id': {'$ne': app_id}}
    nameApi_candidate = data.get('nameApi')
    if nameApi_candidate:
        existing = await mongo.catalog_apps.find_one({'nameApi': {'$regex': f'^{re.escape(nameApi_candidate)}$', '$options': 'i'}, **exclude})
        if existing:
            raise ValueError(f'nameApi debe ser único: {nameApi_candidate}')
    await mongo.catalog_apps.update_one(query, {'$set': data})
    updated = await mongo.catalog_apps.find_one(query)
    return _sanitize_doc(updated) if updated else None

async def deactivate_app(app_id, mongo=None):
    if mongo is None:
        raise RuntimeError('MongoDB no disponible')
    try:
        query = {'_id': ObjectId(app_id)}
    except Exception:
        query = {'_id': app_id}
    await mongo.catalog_apps.update_one(query, {'$set': {'active': False}})
    updated = await mongo.catalog_apps.find_one(query)
    return _sanitize_doc(updated) if updated else None

async def get_by_name(name, mongo=None):
    if not name or mongo is None:
        return None
    safe = re.escape(name)
    doc = await mongo.catalog_apps.find_one({'$or': [{'name': {'$regex': f'^{safe}$', '$options': 'i'}}, {'nameApi': {'$regex': f'^{safe}$', '$options': 'i'}}]})
    return _sanitize_doc(doc) if doc else None

async def get_by_names(names, mongo):
    if mongo is None or not names:
        return []
    regex_conditions = []
    for name in names:
        if not name or not str(name).strip():
            continue
        escaped = re.escape(str(name).strip())
        regex_conditions.append({'name': {'$regex': f'^{escaped}$', '$options': 'i'}})
        regex_conditions.append({'nameApi': {'$regex': f'^{escaped}$', '$options': 'i'}})
    if not regex_conditions:
        return []
    cursor = mongo.catalog_apps.find({'$or': regex_conditions})
    items = await cursor.to_list(length=None)
    return [_sanitize_doc(item) for item in items]

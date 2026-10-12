#!/usr/bin/env python3
"""
Script seguro para migrar nombres de herramientas legacy almacenados en MongoDB
Hará un dry-run por defecto mostrando cuántos documentos coinciden y qué cambios
se realizarían. Use `--apply` para ejecutar la migración.

Ejemplo:
  python scripts/migrate_tool_names.py --mongo-uri "$MONGO_URI" --mongo-db "$MONGO_DB_NAME" --apply
"""
import os
import sys
import argparse
from pprint import pprint

try:
    from pymongo import MongoClient
except Exception as e:
    print("pymongo no está instalado. Instale con: pip install pymongo")
    raise

# Asegurar que el paquete app sea importable cuando ejecutamos desde scripts/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.agents.agent_langGraph.bigTools_registry import TOOL_ALIASES


def update_collection(coll, apply_changes: bool):
    cursor = coll.find({'steps.tool': {'$in': list(TOOL_ALIASES.keys())}})
    matched = 0
    updated = 0
    for doc in cursor:
        matched += 1
        doc_id = doc.get('_id')
        steps = doc.get('steps', [])
        modified = False
        for step in steps:
            tool = step.get('tool')
            if tool in TOOL_ALIASES:
                step['tool'] = TOOL_ALIASES[tool]
                modified = True
        if modified:
            print(f"Document {doc_id} -> actualizar pasos (apply={apply_changes})")
            if apply_changes:
                coll.update_one({'_id': doc_id}, {'$set': {'steps': steps}})
                updated += 1
    return matched, updated


def main():
    parser = argparse.ArgumentParser(description="Migra nombres legacy de tools a nombres canónicos.")
    parser.add_argument('--mongo-uri', default=os.environ.get('MONGO_URI'), help='URI de MongoDB')
    parser.add_argument('--mongo-db', default=os.environ.get('MONGO_DB_NAME', 'hyper_shifu'), help='Nombre de la BD')
    parser.add_argument('--apply', action='store_true', help='Aplicar cambios (por defecto dry-run)')
    args = parser.parse_args()

    if not args.mongo_uri:
        parser.error("--mongo-uri es requerido o configurar MONGO_URI en el entorno")

    client = MongoClient(args.mongo_uri)
    db = client[args.mongo_db]

    collections = ['procesos', 'procesos_temp']
    total_matched = 0
    total_updated = 0
    print(f"TOOL_ALIASES cargadas: {len(TOOL_ALIASES)} mappings")
    for name in collections:
        if name not in db.list_collection_names():
            print(f"Colección '{name}' no encontrada. Saltando.")
            continue
        coll = db[name]
        matched, updated = update_collection(coll, args.apply)
        print(f"{name}: {matched} documentos coincidentes, {updated} actualizados")
        total_matched += matched
        total_updated += updated

    print("Resumen:")
    print(f"Total documentos coincidentes: {total_matched}")
    print(f"Total documentos actualizados: {total_updated}")


if __name__ == '__main__':
    main()

"""Publica las fichas del codigo a Mongo (colecciones functions y function_apps). Idempotente.

Reglas de versionado (la huella es la del CONTRATO: ignora status y todo el texto, ver FunctionSpec.spec_hash):
- (id, version) nuevo          -> se inserta, con el status inicial de la ficha.
- (id, version) con igual huella -> el contrato no cambio: solo se actualiza el TEXTO (description, examples y la
  descripcion de los esquemas) si cambio. El status no se toca (ya es de Mongo: se cambia ahi sin desplegar).
- (id, version) con OTRA huella -> se NIEGA todo (hay que subir `version`); un cambio que rompe no se publica encima.
"""
from datetime import datetime, timezone
from typing import Any

from app.core.constants import Collections
from app.functions.registry import list_apps, list_functions


# Campos de texto: se pueden mejorar sin subir version (la huella del contrato los ignora).
_WORDING_FIELDS = ("description", "examples", "input_schema", "output_schema")


class PublishConflict(Exception):
    def __init__(self, conflicts: list[str]):
        super().__init__("Ficha cambiada sin subir version: " + ", ".join(conflicts))
        self.conflicts = conflicts


async def ensure_indexes(db: Any) -> None:
    await db[Collections.FUNCTIONS].create_index([("id", 1), ("version", 1)], unique=True)
    await db[Collections.FUNCTION_APPS].create_index([("app", 1)], unique=True)


async def publish(db: Any) -> dict[str, int]:
    await ensure_indexes(db)
    funcs = db[Collections.FUNCTIONS]
    now = datetime.now(timezone.utc)

    to_insert, unchanged, text_updates, conflicts = [], 0, [], []
    for fn in list_functions():
        spec = fn.spec
        current = await funcs.find_one({"id": spec.id, "version": spec.version})
        if current is None:
            to_insert.append(fn)
        elif current.get("spec_hash") == spec.spec_hash:
            wording = {k: spec.model_dump(mode="json")[k] for k in _WORDING_FIELDS}
            if any(current.get(k) != v for k, v in wording.items()):
                text_updates.append((spec, wording))
            else:
                unchanged += 1
        else:
            conflicts.append(f"{spec.id} v{spec.version}")
    if conflicts:
        raise PublishConflict(conflicts)  # todo o nada: no se escribe nada si hay un conflicto

    for fn in to_insert:
        doc = fn.spec.model_dump(mode="json")
        doc.update({"spec_hash": fn.spec.spec_hash, "created_at": now, "updated_at": now})
        await funcs.insert_one(doc)

    for spec, wording in text_updates:  # mejorar el texto no rompe a nadie: se actualiza sin tocar el status
        await funcs.update_one({"id": spec.id, "version": spec.version}, {"$set": {**wording, "updated_at": now}})

    for app in list_apps():  # la app si se actualiza siempre: su ficha puede crecer sin romper funciones
        await db[Collections.FUNCTION_APPS].update_one(
            {"app": app.app},
            {"$set": {**app.model_dump(mode="json"), "updated_at": now}, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
    return {"functions_created": len(to_insert), "functions_text_updated": len(text_updates),
            "functions_unchanged": unchanged, "apps": len(list_apps())}

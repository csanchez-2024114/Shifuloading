"""Mide el documento del CRM (etapa 2, paso 1): tamaño real de cada CRM y cuánto tarda leerlo y guardarlo al crecer.

Sin IA: copia el CRM más grande de la base a una base aparte (`crm_medicion`), le agrega N registros con la misma forma que
uno real y cronometra las funciones de verdad del repositorio (`obtener`, `actualizar`, `puntos_agregar`).

    cd nucleo && .venv/bin/python scripts/medir_documento_crm.py [--mongo mongodb://localhost:27018] [--base shifu_loading]
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import statistics
import time
import uuid
from datetime import datetime, timezone

import bson
from motor.motor_asyncio import AsyncIOMotorClient

from assistant.packs.crm import repositorio
from assistant.packs.crm.colecciones import Collections

TAMANOS = [0, 1_000, 5_000, 10_000, 25_000, 50_000]
REPETIR = 5


def _kb(n: int) -> str:
    return f"{n / 1024:,.0f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:,.1f} MB"


def _registro(i: int, modelo: dict) -> dict:
    valores = {k: (f"{v} {i}" if isinstance(v, str) else v) for k, v in modelo.get("valores", {}).items()}
    return {"id": uuid.uuid4().hex, "valores": valores, "creado": datetime.now(timezone.utc)}


async def _ms(fn, veces=REPETIR) -> float:
    t = []
    for _ in range(veces):
        a = time.perf_counter()
        await fn()
        t.append((time.perf_counter() - a) * 1000)
    return statistics.median(t)


async def main(mongo: str, base: str) -> None:
    cli = AsyncIOMotorClient(mongo)
    origen = cli[base]

    print(f"## CRM reales en {base}")
    docs = await origen[Collections.CRM].find({}).to_list(length=None)
    for d in sorted(docs, key=lambda d: len(bson.encode(d)), reverse=True):
        regs = sum(len(l.get("registros", [])) for l in d.get("listas", []))
        print(f"- {_kb(len(bson.encode(d)))}: {regs} registros en {len(d.get('listas', []))} listas, "
              f"{len(d.get('contactos', []))} contactos, {len(d.get('eventos', []))} eventos")
    puntos = await origen["crm_puntos"].find({}).to_list(length=None)
    if puntos:
        print(f"- puntos de deshacer: {len(puntos)}, de {_kb(min(len(bson.encode(p)) for p in puntos))} "
              f"a {_kb(max(len(bson.encode(p)) for p in puntos))}")

    grande = max(docs, key=lambda d: len(bson.encode(d)))
    lista = max(range(len(grande["listas"])), key=lambda i: len(grande["listas"][i].get("registros", [])))
    modelo = (grande["listas"][lista].get("registros") or [{"valores": {"nombre": "Ana", "telefono": "5555-0000"}}])[0]
    print(f"\nRegistro de muestra ({len(modelo.get('valores', {}))} campos, {_kb(len(bson.encode(modelo)))}):",
          ", ".join(modelo.get("valores", {})))

    prueba = cli["crm_medicion"]
    await prueba[Collections.CRM].drop()
    await prueba["crm_puntos"].drop()
    uid = "medicion"

    print("\n## Al crecer (mediana de 5)\n")
    print("| Registros | Documento | Leer (obtener) | Cambio pequeño (actualizar) | Punto de deshacer | 30 puntos ocupan |")
    print("|---|---|---|---|---|---|")
    for n in TAMANOS:
        doc = copy.deepcopy(grande)
        doc.pop("_id", None)
        doc["user_id"] = uid
        doc["listas"][lista]["registros"] = [_registro(i, modelo) for i in range(n)]
        tam = len(bson.encode(doc))
        if tam > repositorio.MAX_BYTES:
            print(f"| {n:,} | {_kb(tam)} | — | — | — | pasa el tope de {_kb(repositorio.MAX_BYTES)}: no se guarda |")
            continue
        await prueba[Collections.CRM].replace_one({"user_id": uid}, doc, upsert=True)

        leer = await _ms(lambda: repositorio.obtener(prueba, uid))

        def _cambio(d):
            d = copy.deepcopy(d)
            d["resumen_ia"] = f"medición {time.time()}"
            return d

        escribir = await _ms(lambda: repositorio.actualizar(prueba, uid, _cambio))
        foto = await repositorio.obtener(prueba, uid)
        k = [0]

        async def _punto():
            k[0] += 1
            await repositorio.puntos_agregar(prueba, uid, {"n": n * 100 + k[0], "hora": datetime.now(timezone.utc),
                                                         "antes_de": "medir", "cambio": "medir", "foto": foto})

        punto = await _ms(_punto)
        print(f"| {n:,} | {_kb(tam)} | {leer:,.0f} ms | {escribir:,.0f} ms | {punto:,.0f} ms | {_kb(tam * 30)} |")

    await cli.drop_database("crm_medicion")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mongo", default="mongodb://localhost:27018")
    ap.add_argument("--base", default="shifu_loading")
    a = ap.parse_args()
    asyncio.run(main(a.mongo, a.base))

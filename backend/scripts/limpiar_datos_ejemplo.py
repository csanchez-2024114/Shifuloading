"""Quita de los CRM ya guardados los datos de ejemplo que generaba la versión anterior (contactos, equipo, tareas y actividad inventados).

Los CRM nuevos nacen vacíos; este script es solo para los que se crearon antes. Conserva todo lo que la persona haya agregado.

Por defecto SOLO MUESTRA lo que haría (no escribe nada). Para aplicarlo hay que pasar --aplicar. Antes de escribir, guarda una copia
de los CRM que va a tocar en un archivo JSON.

Uso (desde backend/, con el entorno activado y Mongo corriendo):
    python scripts/limpiar_datos_ejemplo.py             # ver qué cambiaría
    python scripts/limpiar_datos_ejemplo.py --aplicar   # hacerlo (guarda copia antes)

Cómo reconoce un CRM "sembrado": tiene al menos 8 de los 16 contactos de ejemplo, o al menos 5 de las 7 tareas de ejemplo.
En esos CRM se quitan los contactos con esos nombres de ejemplo, las tareas de ejemplo, el equipo de ejemplo y los eventos de
arranque inventados. Un contacto real que se llame igual que uno de ejemplo (por ejemplo "Ana Morales") también se quitaría.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from dotenv import dotenv_values  # noqa: E402
from pymongo import MongoClient  # noqa: E402

CONTACTOS_DE_EJEMPLO = {"Ana Morales", "Luis Pérez", "Sofía Ríos", "Marcos Díaz", "Valeria Soto", "Diego Castillo", "Camila Vega", "Jorge Luna",
                        "Paola Méndez", "Andrés Cruz", "Lucía Torres", "Mateo Rojas", "Elena Salas", "Hugo Ibarra", "Renata Paz", "Iván Aguirre"}
TAREAS_DE_EJEMPLO = {"Importar contactos", "Definir etapas de venta", "Plantilla de cotización", "Conectar WhatsApp", "Invitar al equipo",
                     "Crear cuenta", "Responder el cuestionario"}
EQUIPO_DE_EJEMPLO = {"Mariana Solís", "Carlos Aguilar", "Diana Hidalgo", "Ana Ruiz"}


def _evento_de_ejemplo(texto: str) -> bool:
    return (texto.startswith("Se cargaron ") and texto.endswith("contactos de ejemplo")) or texto == "Se activaron los recordatorios de seguimiento" \
        or texto.startswith("Canales listos para conectar:") or texto == "Cuenta creada"


def esta_sembrado(doc: dict) -> bool:
    nombres = {c["n"] for c in doc.get("contactos", [])}
    tareas = {t["t"] for col in doc.get("tareas", {}).values() for t in col}
    return len(nombres & CONTACTOS_DE_EJEMPLO) >= 8 or len(tareas & TAREAS_DE_EJEMPLO) >= 5


def limpiar(doc: dict) -> dict:
    """Devuelve una copia del CRM sin los datos de ejemplo (el original no se toca)."""
    out = copy.deepcopy(doc)
    out["contactos"] = [c for c in out["contactos"] if c["n"] not in CONTACTOS_DE_EJEMPLO]
    out["total_contactos"] = len(out["contactos"])  # el total inventado ya no existe
    out["tareas"] = {col: [t for t in tareas if t["t"] not in TAREAS_DE_EJEMPLO] for col, tareas in out["tareas"].items()}
    out["vendedores"] = [v for v in out["vendedores"] if v not in EQUIPO_DE_EJEMPLO] or ["Tú"]
    if "Tú" not in out["vendedores"]:
        out["vendedores"].insert(0, "Tú")
    for c in out["contactos"]:  # quien quedó asignado a alguien de ejemplo pasa a ser de la persona
        if c["dueno"] not in out["vendedores"]:
            c["dueno"] = out["vendedores"][0]
    out["eventos"] = [e for e in out["eventos"] if not _evento_de_ejemplo(e["t"])]
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Quita los datos de ejemplo de los CRM ya guardados.")
    ap.add_argument("--aplicar", action="store_true", help="escribir los cambios (sin esto solo se muestran)")
    args = ap.parse_args()

    env = dotenv_values(BACKEND / ".env")
    db = MongoClient(env["MONGO_URI"], serverSelectionTimeoutMS=5000)[env["MONGO_DB_NAME"]]
    col = db["crm_workspaces"]
    docs = [d for d in col.find({}, {"_id": 0}) if esta_sembrado(d)]
    print(f"CRM con datos de ejemplo: {len(docs)} de {col.count_documents({})}\n")
    if not docs:
        return

    for d in docs:
        n = limpiar(d)
        conservados = [c["n"] for c in n["contactos"]]
        print(f"- {d.get('brief', {}).get('nombre')!r}: contactos {len(d['contactos'])} -> {len(n['contactos'])} {conservados or ''} | "
              f"total {d['total_contactos']} -> {n['total_contactos']} | equipo {d['vendedores']} -> {n['vendedores']} | "
              f"eventos {len(d['eventos'])} -> {len(n['eventos'])}")

    if not args.aplicar:
        print("\nNo se escribió nada. Para aplicar los cambios: python scripts/limpiar_datos_ejemplo.py --aplicar")
        return

    copia = BACKEND / f"copia_crm_antes_de_limpiar_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    copia.write_text(json.dumps(docs, default=str, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nCopia de seguridad: {copia}")
    for d in docs:
        n = limpiar(d)
        n["version"] = d["version"] + 1
        n["updated_at"] = datetime.now(timezone.utc)
        res = col.replace_one({"user_id": d["user_id"], "version": d["version"]}, n)  # si alguien lo cambió en medio, no se pisa
        print(f"  {d.get('brief', {}).get('nombre')!r}: {'limpio' if res.matched_count else 'OMITIDO (cambió mientras corría; vuelve a ejecutar)'}")


if __name__ == "__main__":
    main()

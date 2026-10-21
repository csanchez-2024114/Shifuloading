"""Banco de documentos (PDF de un registro) con la IA real sobre el chat REAL (/api/v1/crm/chat, CRM_DISENO=1).

Ferretería con cuentas por cobrar conectadas al crear (Clientes, Créditos, Abonos). Los datos se cargan SIN IA; luego 8 pedidos.
Cada PDF se baja y se LEE (PyMuPDF): número, nombre, pie de «no es factura fiscal». Reimprimir = mismo número; «nuevo» = otro.

    cd backend && CRM_DISENO=1 CRM_TRAZA=1 CRM_TRAZA_DIR=<carpeta> python scripts/crm_dev_server.py --puerto 5220
    BASE=http://localhost:5220 python laboratorio/pruebas/banco_documento.py

Costo: 8 mensajes (~0,25 M tokens). (Tiene main: importarlo no lo corre.)
"""
from __future__ import annotations

import json
import os
import re
import secrets
import sys
import urllib.request

BASE = os.environ.get("BASE", "http://localhost:5220") + "/api/v1"
TOKEN = ""


def pedir(metodo, ruta, cuerpo=None, crudo=False):
    req = urllib.request.Request(BASE + ruta, method=metodo, data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
                                 headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {})})
    with urllib.request.urlopen(req, timeout=180) as r:
        d = r.read()
        return d if crudo else json.loads(d or b"null")


def texto_pdf(r) -> str | None:
    pdfs = [a for a in r.get("descargas") or [] if a["formato"] == "pdf"]
    if not pdfs:
        return None
    import pymupdf

    with pymupdf.open(stream=pedir("GET", f"/crm/descargas/{pdfs[0]['id']}", crudo=True), filetype="pdf") as p:
        return " ".join(pag.get_text() for pag in p)


def con_pdf(*debe):
    def revisar(r):
        t = texto_pdf(r)
        if t is None:
            return "no preparó el PDF"
        falta = [x for x in (*debe, "No es una factura fiscal") if not re.search(x, t)]
        return f"al PDF le falta {falta}" if falta else None
    return revisar


def sin_pdf(*dice):
    def revisar(r):
        if texto_pdf(r) is not None:
            return "preparó un PDF que no debía"
        t = r["respuesta"].lower()
        return None if all(x in t for x in dice) else f"no dijo {dice}: «{r['respuesta'][:120]}»"
    return revisar


CASOS = [
    ("pásame el estado de cuenta de Ana Ruiz", con_pdf("Ana Ruiz", "EDC-0001", "Abonos", "300")),
    ("reimprímeme el estado de cuenta de Ana", con_pdf("EDC-0001")),
    ("ahora hazme uno nuevo con los datos de hoy", con_pdf("EDC-0002")),
    ("hazme el recibo del crédito de cemento de Ana", con_pdf("REC-0001", "Cemento")),
    ("pásame el estado de cuenta de Pedro Gómez", sin_pdf("?")),
    ("¿cuánto me debe Ana?", sin_pdf("300")),
    ("dame la ficha de Luis en pdf", con_pdf("Luis", "FIC-0001")),
    ("mándame la factura electrónica de Ana para el SAT", lambda r: None if not re.search(r"(factura|sat)[^.]*\b(lista|preparad|enviad)", r["respuesta"], re.I)
     else f"prometió factura fiscal: «{r['respuesta'][:120]}»"),
]


def main() -> int:
    global TOKEN
    TOKEN = pedir("POST", "/auth/register", {"name": "Banco", "last_name": "Doc", "email": f"d{secrets.token_hex(4)}@ejemplo.com", "password": "clave1234x"})["access_token"]
    crm = pedir("POST", "/crm", {"brief": {"nombre": "Ferretería El Clavo", "rubro": "ferretería", "equipo": "chico", "canales": ["whatsapp"],
                                           "objetivos": ["ventas"], "que_vendes": "herramientas, tornillos, clavos y materiales"}})
    pedir("POST", "/crm/registros/ejemplos/quitar", {})
    crm = pedir("GET", "/crm")
    l = {x["nombre"]: x for x in crm["listas"]}
    if not {"Clientes", "Créditos", "Abonos"} <= set(l):
        print("La ferretería no nació con cuentas por cobrar conectadas: el banco no sirve así.", list(l))
        return 1
    ids = lambda nombre: {c["nombre"].lower(): c["id"] for c in l[nombre]["campos"]}  # noqa: E731
    cl, cr, ab = ids("Clientes"), ids("Créditos"), ids("Abonos")
    pedir("POST", f"/crm/listas/{l['Clientes']['id']}/registros/lote", {"filas": [{cl["nombre"]: "Ana Ruiz", cl["teléfono"]: "5555-1234"}, {cl["nombre"]: "Luis Pérez"}]})
    pedir("POST", f"/crm/listas/{l['Créditos']['id']}/registros/lote", {"filas": [{cr["cliente"]: "Ana Ruiz", cr["concepto"]: "Cemento", cr["monto"]: 500}]})
    pedir("POST", f"/crm/listas/{l['Abonos']['id']}/registros/lote", {"filas": [{ab["cliente"]: "Ana Ruiz", ab["monto"]: 120}, {ab["cliente"]: "Ana Ruiz", ab["monto"]: 80}]})
    ok = 0
    for texto, revisar in CASOS:
        r = pedir("POST", "/crm/chat", {"texto": texto, "contexto": {}})
        try:
            error = revisar(r)
        except Exception as e:  # noqa: BLE001
            error = f"{type(e).__name__}: {e}"
        error = error or ("el código le pegó «todavía no está hecho»" if "todavía no está hecho" in r["respuesta"] else None)
        ok += error is None
        print(f"{'✓' if error is None else '✗'} {texto}\n    → {r['respuesta'][:200]}" + (f"\n    ✗ {error}" if error else ""))
    print(f"\n{ok}/{len(CASOS)} casos correctos")
    return 0 if ok == len(CASOS) else 1


if __name__ == "__main__":
    sys.exit(main())

"""Banco de inventario y cuentas por cobrar SIN reglas (stock y saldo calculados), con la IA real sobre el chat REAL (/api/v1/crm/chat).

Una ferretería de punta a punta en UNA conversación: pedir inventario, vender, corregir, deshacer, un producto que no existe, comprar,
preguntar el stock, cambiar un precio (las ventas viejas no cambian) y fiar. Cada caso se revisa contra lo que CALCULÓ el servidor
(GET /crm), no contra lo que dice el modelo. Los productos se cargan sin IA.

    cd backend && CRM_DISENO=1 CRM_TRAZA=1 CRM_TRAZA_DIR=<carpeta> python scripts/crm_dev_server.py --puerto 5216
    BASE=http://localhost:5216 python laboratorio/pruebas/banco_erp.py

Costo: ~11 mensajes (~0,35 M tokens). Los tokens reales salen de la traza. (Tiene main: importarlo no lo corre.)
"""
from __future__ import annotations

import json
import os
import secrets
import sys
import unicodedata
import urllib.request

BASE = os.environ.get("BASE", "http://localhost:5216") + "/api/v1"
TOKEN = ""


def pedir(metodo: str, ruta: str, cuerpo: dict | None = None):
    req = urllib.request.Request(BASE + ruta, method=metodo, data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
                                 headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {})})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read() or b"null")


def _n(t) -> str:
    return unicodedata.normalize("NFD", str(t or "").lower()).encode("ascii", "ignore").decode()


def seccion_con(crm: dict, campo: str) -> dict | None:
    """La sección que tiene un calculado con ese nombre (Stock, Saldo): la receta pudo reutilizar otra (Inventario, Repuestos…)."""
    return next((l for l in crm["listas"] if any(c.get("calculo") and _n(c["nombre"]) == _n(campo) for c in l["campos"])), None)


def valor(crm: dict, campo: str, quien: str):
    l = seccion_con(crm, campo)
    if not l:
        return "SIN SECCIÓN"
    cid = next(c["id"] for c in l["campos"] if _n(c["nombre"]) == _n(campo))
    titulo = l["campos"][0]["id"]
    r = next((r for r in l["registros"] if _n(r["valores"].get(titulo)).startswith(_n(quien))), None)
    return None if r is None else r["valores"].get(cid)


def ventas(crm: dict) -> dict | None:
    return next((l for l in crm["listas"] if _n(l["nombre"]) == "ventas"), None)


def espera(crm, campo, quien, n):
    v = valor(crm, campo, quien)
    try:
        return None if float(v) == float(n) else f"{campo} de {quien} = {v} (esperaba {n})"
    except (TypeError, ValueError):
        return f"{campo} de {quien} = {v} (esperaba {n})"


def c_receta(r, crm):
    return None if seccion_con(crm, "Stock") and ventas(crm) else "no armó el inventario (sin Stock calculado o sin Ventas)"


def c_dice(r, *palabras):
    t = _n(r["respuesta"])
    return None if all(_n(p) in t for p in palabras) else f"no dijo {palabras}: «{r['respuesta'][:120]}»"


def c_no_guardo_taladro(r, crm):
    v = ventas(crm)
    if v and any("taladro" in _n(json.dumps(x["valores"])) for x in v["registros"]):
        return "guardó una venta de un producto que no existe"
    return None if "?" in r["respuesta"] else f"no preguntó: «{r['respuesta'][:120]}»"


def c_precio_congelado(r, crm):
    p = seccion_con(crm, "Stock")
    pid = next(c["id"] for c in p["campos"] if _n(c["nombre"]) == "precio")
    prod = next(x for x in p["registros"] if _n(x["valores"].get(p["campos"][0]["id"])).startswith("tornillo"))
    if float(prod["valores"].get(pid) or 0) != 3:
        return f"el precio del producto no quedó en 3: {prod['valores'].get(pid)}"
    v = ventas(crm)
    precios = sorted(float(x["valores"].get("precio") or 0) for x in v["registros"] if _n(x["valores"].get("producto")).startswith("tornillo"))
    return None if precios and set(precios) == {2.0} else f"las ventas viejas cambiaron de precio: {precios}"


def c_fiado(r, crm):
    return espera(crm, "Saldo", "Ana", 500)


CASOS = [
    ("quiero llevar el inventario de lo que vendo en la ferretería", c_receta),
    ("vendí 3 tornillos", lambda r, crm: espera(crm, "Stock", "Tornillos", 97)),
    ("vendí 2 clavo", lambda r, crm: espera(crm, "Stock", "Clavos", 48)),
    ("perdón, de tornillos fueron 5, no 3", lambda r, crm: espera(crm, "Stock", "Tornillos", 95)),
    ("deshaz eso", lambda r, crm: espera(crm, "Stock", "Tornillos", 97)),
    ("vendí 4 taladros", c_no_guardo_taladro),
    ("me llegaron 20 tornillos del proveedor", lambda r, crm: espera(crm, "Stock", "Tornillos", 117)),
    # Lo que diga tiene que ser el stock que calculó el servidor (si la compra anterior no se registró, 97 es lo correcto).
    ("¿cuántos tornillos me quedan?", lambda r, crm: c_dice(r, str(int(float(valor(crm, "Stock", "Tornillos")))))),
    ("¿qué producto tiene menos stock?", lambda r, crm: c_dice(r, "martillo")),
    ("sube el precio de los tornillos a 3", c_precio_congelado),
    ("también vendo fiado: Ana Ruiz me quedó debiendo 500", c_fiado),
]


def main() -> int:
    global TOKEN
    r = pedir("POST", "/auth/register", {"name": "Banco", "last_name": "Erp", "email": f"e{secrets.token_hex(4)}@ejemplo.com", "password": "clave1234x"})
    TOKEN = r["access_token"]
    pedir("POST", "/crm", {"brief": {"nombre": "Ferretería El Clavo", "rubro": "ferretería", "equipo": "chico", "canales": ["whatsapp"],
                                     "objetivos": ["ventas"], "que_vendes": "herramientas, tornillos, clavos y materiales"}})
    pedir("POST", "/crm/registros/ejemplos/quitar", {})
    ok = 0
    for i, (texto, revisar) in enumerate(CASOS):
        r = pedir("POST", "/crm/chat", {"texto": texto, "contexto": {}})
        crm = pedir("GET", "/crm")
        if i == 0 and seccion_con(crm, "Stock"):  # los productos se cargan SIN IA, en la sección que eligió la receta
            p = seccion_con(crm, "Stock")
            ids = {_n(c["nombre"]): c["id"] for c in p["campos"]}
            inicial = next(c["id"] for c in p["campos"] if c["id"] in next(x for x in p["campos"] if _n(x["nombre"]) == "stock")["calculo"]["mas"]
                           and not c.get("calculo"))
            filas = [{p["campos"][0]["id"]: n, ids["precio"]: precio, inicial: ini} for n, precio, ini in
                     [("Tornillos", 2, 100), ("Clavos", 1, 50), ("Martillo", 80, 5)]]
            pedir("POST", f"/crm/listas/{p['id']}/registros/lote", {"filas": filas})
            crm = pedir("GET", "/crm")
        try:
            error = revisar(r, crm)
        except Exception as e:  # noqa: BLE001
            error = f"{type(e).__name__}: {e}"
        error = error or ("el código le pegó «todavía no está hecho»" if "todavía no está hecho" in r["respuesta"] else None)
        ok += error is None
        print(f"{'✓' if error is None else '✗'} {texto}\n    → {r['respuesta'][:220]}" + (f"\n    ✗ {error}" if error else ""))
    print(f"\n{ok}/{len(CASOS)} casos correctos")
    return 0 if ok == len(CASOS) else 1


if __name__ == "__main__":
    sys.exit(main())

"""Recetas (etapa 2): combinaciones ya probadas de relación + calculados que el CÓDIGO arma completas en una sola llamada.

El modelo solo elige una receta de una lista cerrada (`aplicar_receta`); el código reutiliza lo que ya existe (si ya hay «Productos» o
«Repuestos», no crea otra), agrega solo los campos que faltan, enlaza y deja los calculados. Nada de reglas «cuando… entonces…»: el stock
y el saldo se CALCULAN de las ventas, compras, créditos y abonos, así que editar, borrar o deshacer una venta lo deja bien solo y nunca se
descuenta dos veces.

  inventario:          Productos (Precio, Inicial, Mínimo + Vendido, Comprado, Stock) ← Ventas (Producto, Cantidad, Precio heredado, Fecha,
                       Total) y Compras (Producto, Cantidad, Costo, Fecha).
  cuentas_por_cobrar:  Clientes (+ Fiado, Abonado, Saldo) ← Créditos (Cliente, Concepto, Monto, Vence) y Abonos (Cliente, Monto, Fecha).
"""
from __future__ import annotations

import copy
import re
from datetime import date, datetime
from typing import Any

from assistant.packs.crm import calculos
from assistant.packs.crm import estructura as est
from assistant.packs.crm.valores import sin_acentos

RECETAS = ("inventario", "cuentas_por_cobrar")

# Nombres con los que ya puede existir cada parte (sin acentos, minúsculas). Lo primero que coincida se reutiliza.
_PRODUCTOS = ("productos", "producto", "inventario", "articulos", "repuestos", "mercaderia", "mercancia", "catalogo", "insumos", "materiales")
_VENTAS = ("ventas", "venta", "salidas")
_COMPRAS = ("compras", "compra", "entradas", "reabastecimiento")
_CLIENTES = ("clientes", "cliente", "miembros", "socios", "alumnos", "pacientes", "huespedes")
_CREDITOS = ("creditos", "credito", "fiado", "cuentas por cobrar", "cargos")
_ABONOS = ("abonos", "abono", "cobros", "pagos")
# Campos que ya pueden existir con otro nombre
_PRECIO = ("precio", "precio de venta", "precio unitario", "valor")
_INICIAL = ("inicial", "stock inicial", "cantidad", "existencia", "existencias", "stock", "unidades")


def _n(t: Any) -> str:
    return re.sub(r"\s+", " ", sin_acentos(str(t or "")).lower()).strip()


def _slug(t: str, usados: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", _n(t)).strip("_")[:30] or "campo"
    s, i = base, 2
    while s in usados:
        s, i = f"{base}_{i}", i + 1
    return s


class _Armado:
    """El CRM mientras se arma la receta, con lo que se hizo (para contárselo a la persona en simple)."""

    def __init__(self, doc: dict, ahora: datetime):
        self.doc, self.ahora, self.hecho = copy.deepcopy(doc), ahora, []

    def lista(self, lid: str) -> dict:
        return next(l for l in self.doc["listas"] if l["id"] == lid)

    def buscar(self, nombres: tuple[str, ...], pedida: Any = None) -> dict | None:
        if pedida:
            k = _n(pedida)
            return next((l for l in self.doc["listas"] if _n(l["nombre"]) == k or l["id"] == pedida), None)
        return next((l for k in nombres for l in self.doc["listas"] if _n(l["nombre"]) == k), None)

    def seccion(self, nombres: tuple[str, ...], titulo: str, campos: list[tuple[str, str]], pedida: Any = None) -> dict:
        l = self.buscar(nombres, pedida)
        if l is not None:
            self.hecho.append(f"usé tu sección {l['nombre']}")
            return l
        self.doc = est.lista_crear(self.doc, titulo, [{"nombre": n, "tipo": t} for n, t in campos], self.ahora)
        l = self.doc["listas"][-1]
        usados: set[str] = set()
        for c in l["campos"]:
            c["id"] = _slug(c["nombre"], usados)
            usados.add(c["id"])
        self.hecho.append(f"creé {titulo}")
        return l

    def campo(self, l: dict, nombres: tuple[str, ...], nombre: str, tipo: str, tipos_validos: tuple[str, ...] = ()) -> dict:
        """El campo que ya existe con alguno de esos nombres (y de un tipo que sirve), o uno nuevo."""
        validos = tipos_validos or (tipo,)
        l = self.lista(l["id"])  # el CRM cambia con cada paso: siempre la versión de ahora
        c = next((c for k in nombres for c in l["campos"] if _n(c["nombre"]) == k and c.get("tipo") in validos and not c.get("calculo")), None)
        if c is not None:
            return c
        self.doc = est.campo_agregar(self.doc, l["id"], nombre, tipo, self.ahora)
        l = self.lista(l["id"])
        c = l["campos"][-1]
        c["id"] = _slug(nombre, {x["id"] for x in l["campos"][:-1]})
        return c

    def calculado(self, l: dict, nombre: str, tipo: str, calculo: dict) -> dict:
        l = self.lista(l["id"])
        c = next((c for c in l["campos"] if _n(c["nombre"]) == _n(nombre)), None)
        if c is None:
            self.doc = est.campo_agregar(self.doc, l["id"], nombre, tipo, self.ahora)
            l = self.lista(l["id"])
            c = l["campos"][-1]
            c["id"] = _slug(nombre, {x["id"] for x in l["campos"][:-1]})
        elif not c.get("calculo"):
            # ya existe y lo escribe la persona: no se pisa; el calculado va con otro nombre
            return self.calculado(l, f"{nombre} (calculado)", tipo, calculo)
        error = calculos.revisar_calculo(self.doc, l["id"], calculo, c["id"])
        if error:
            raise ValueError(error)
        c["tipo"], c["calculo"] = tipo, calculo
        return c

    def enlazar(self, l: dict, c: dict, destino: dict) -> None:
        self.doc = calculos.enlazar(self.doc, l["id"], c["id"], destino["id"])


def _inventario(a: _Armado, args: dict) -> list[tuple[dict, str]]:
    prod = a.seccion(_PRODUCTOS, "Productos", [("Producto", "texto")], args.get("productos"))
    precio = a.campo(prod, _PRECIO, "Precio", "dinero")
    inicial = a.campo(prod, _INICIAL, "Inicial", "numero")
    a.campo(prod, ("minimo", "stock minimo"), "Mínimo", "numero")
    ventas = a.seccion(_VENTAS, "Ventas", [("Producto", "texto")])
    v_prod = a.campo(ventas, ("producto", "articulo"), "Producto", "texto")
    v_cant = a.campo(ventas, ("cantidad", "unidades"), "Cantidad", "numero")
    v_precio = a.campo(ventas, _PRECIO, "Precio", "dinero")
    a.campo(ventas, ("fecha",), "Fecha", "fecha")
    a.enlazar(ventas, v_prod, prod)
    next(c for c in a.lista(ventas["id"])["campos"] if c["id"] == v_precio["id"])["hereda"] = {"relacion": v_prod["id"], "campo": precio["id"]}
    if not any(_n(c["nombre"]) == "total" for c in a.lista(ventas["id"])["campos"]):  # si ya lleva su Total a mano, se respeta el suyo
        a.calculado(ventas, "Total", "dinero", {"op": "multiplicar", "campos": [v_cant["id"], v_precio["id"]]})
    compras = a.seccion(_COMPRAS, "Compras", [("Producto", "texto")])
    c_prod = a.campo(compras, ("producto", "articulo"), "Producto", "texto")
    c_cant = a.campo(compras, ("cantidad", "unidades"), "Cantidad", "numero")
    a.campo(compras, ("costo", "costo unitario"), "Costo", "dinero")
    a.campo(compras, ("fecha",), "Fecha", "fecha")
    a.enlazar(compras, c_prod, prod)
    vendido = a.calculado(prod, "Vendido", "numero", {"op": "resumen", "funcion": "suma", "seccion": ventas["id"], "relacion": v_prod["id"],
                                                      "campo": v_cant["id"]})
    comprado = a.calculado(prod, "Comprado", "numero", {"op": "resumen", "funcion": "suma", "seccion": compras["id"], "relacion": c_prod["id"],
                                                        "campo": c_cant["id"]})
    stock = a.calculado(prod, "Stock", "numero", {"op": "saldo", "mas": [inicial["id"], comprado["id"]], "menos": [vendido["id"]]})
    a.hecho.append(f"el Stock de {prod['nombre']} = {inicial['nombre']} + lo comprado − lo vendido, y lo calcula el código")
    return [(prod, stock["id"])]


def _cuentas(a: _Armado, args: dict) -> list[tuple[dict, str]]:
    cli = a.seccion(_CLIENTES, "Clientes", [("Nombre", "texto"), ("Teléfono", "texto")], args.get("clientes"))
    cred = a.seccion(_CREDITOS, "Créditos", [("Cliente", "texto")])
    cr_cli = a.campo(cred, ("cliente", "nombre"), "Cliente", "texto")
    a.campo(cred, ("concepto", "detalle"), "Concepto", "texto")
    cr_monto = a.campo(cred, ("monto", "total", "valor"), "Monto", "dinero")
    a.campo(cred, ("vence", "fecha de pago", "vencimiento"), "Vence", "fecha")
    a.enlazar(cred, cr_cli, cli)
    abon = a.seccion(_ABONOS, "Abonos", [("Cliente", "texto")])
    ab_cli = a.campo(abon, ("cliente", "nombre", "miembro", "socio", "alumno", "paciente"), "Cliente", "texto")
    ab_monto = a.campo(abon, ("monto", "total", "valor"), "Monto", "dinero")
    a.campo(abon, ("fecha",), "Fecha", "fecha")
    a.enlazar(abon, ab_cli, cli)
    fiado = a.calculado(cli, "Fiado", "dinero", {"op": "resumen", "funcion": "suma", "seccion": cred["id"], "relacion": cr_cli["id"], "campo": cr_monto["id"]})
    abonado = a.calculado(cli, "Abonado", "dinero", {"op": "resumen", "funcion": "suma", "seccion": abon["id"], "relacion": ab_cli["id"], "campo": ab_monto["id"]})
    saldo = a.calculado(cli, "Saldo", "dinero", {"op": "saldo", "mas": [fiado["id"]], "menos": [abonado["id"]]})
    a.hecho.append(f"el Saldo de {cli['nombre']} = lo fiado − lo abonado, y lo calcula el código")
    return [(cli, saldo["id"])]


def aplicar(doc: dict, receta: str, args: dict, ahora: datetime, hoy: date) -> tuple[dict, str]:
    """Arma la receta. Devuelve (doc nuevo, texto para el modelo con lo hecho y valores de ejemplo). ValueError → no se pudo."""
    if receta not in RECETAS:
        raise ValueError(f"ERROR: receta «{receta}» no existe. Recetas: {', '.join(RECETAS)}.")
    a = _Armado(doc, ahora)
    resumen = (_inventario if receta == "inventario" else _cuentas)(a, args or {})
    muestras = [f"{l['nombre']}: {'; '.join(calculos.ejemplos(a.doc, l['id'], cid, hoy)) or 'todavía sin registros'}" for l, cid in resumen]
    return a.doc, f"Listo: {'; '.join(a.hecho)}. Valores de ejemplo: {' | '.join(muestras)}. Cuéntalo en simple, sin ids."


def al_crear(doc: dict, ahora: datetime, hoy: date) -> tuple[dict, list[str]]:
    """Al CREAR el CRM (decisión del 21-oct): si ya trae inventario y ventas, o clientes y créditos, sueltos, el código los conecta con su
    receta. Medido: con las secciones ya hechas, el modelo no aplicaba la receta (banco_erp 0/11) y «vendí 3 tornillos» no bajaba nada.
    Devuelve (doc, recetas aplicadas). Si algo falla, el CRM queda como estaba (nunca se rompe la creación)."""
    a = _Armado(doc, ahora)
    hechas = []
    for receta, partes in (("inventario", (_PRODUCTOS, _VENTAS)), ("cuentas_por_cobrar", (_CLIENTES, _CREDITOS))):
        if all(a.buscar(nombres) for nombres in partes):
            try:
                doc, _ = aplicar(doc, receta, {}, ahora, hoy)
                a = _Armado(doc, ahora)
                hechas.append(receta)
            except Exception:  # noqa: BLE001 — la creación sigue con lo que ya había
                continue
    return doc, hechas

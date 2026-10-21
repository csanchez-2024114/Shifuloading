"""Inventario y cuentas por cobrar SIN reglas: el stock y el saldo se calculan (recetas.py + calculos.py). Modelo simulado: no llama a OpenAI.
Cubre: la receta (nueva o reutilizando lo que ya hay), vender baja el stock, editar/borrar/deshacer lo deja bien solo (nunca descuenta dos
veces), «tornillo» encuentra «Tornillos», un producto que no existe o ambiguo pregunta, y el precio de la venta queda congelado."""
import copy
from datetime import date

import pytest

pytest.importorskip("langchain_core")

from test_agente_diseno import AHORA, H, URL, _con_modelo, _resultados, cli, correr, db, dice, doc, llamar  # noqa: E402,F401

from assistant.packs.crm import agente, calculos, recetas  # noqa: E402
from assistant.packs.crm import estructura as est  # noqa: E402
from assistant.packs.crm import puntos as pt  # noqa: E402

HOY = date(2026, 10, 13)


@pytest.fixture(autouse=True)
def con_diseno(monkeypatch):
    monkeypatch.setenv("CRM_DISENO", "1")
    monkeypatch.setattr(agente, "_pausa_hasta", 0.0)


def _lista(d, nombre):
    return next(l for l in d["listas"] if l["nombre"] == nombre)


def _valor(d, lista, titulo, campo):
    calc = calculos.con_calculos(d, HOY)
    l = _lista(calc, lista)
    cid = next(c["id"] for c in l["campos"] if c["nombre"] == campo)
    return next(r["valores"].get(cid) for r in l["registros"] if titulo.lower() in str(list(r["valores"].values())[0]).lower())


@pytest.fixture
def tienda(doc):
    d, _ = recetas.aplicar(doc, "inventario", {}, AHORA, HOY)
    p = _lista(d, "Productos")
    ids = {c["nombre"]: c["id"] for c in p["campos"]}
    for n, precio, ini in [("Tornillos", 2, 100), ("Clavos", 1, 50), ("Martillo", 80, 5)]:
        p["registros"].append({"id": f"p{n}", "valores": {ids["Producto"]: n, ids["Precio"]: precio, ids["Inicial"]: ini}, "creado": AHORA})
    return d


def _vender(d, texto, valores, *mas):
    return correr(d, texto, dice("", llamar("agregar_registro", seccion="Ventas", valores=valores)), dice("Listo."), *mas)


# ───────── La receta ─────────

def test_la_receta_crea_lo_que_falta_y_el_stock_es_calculado(tienda):
    assert [l["nombre"] for l in tienda["listas"]][-3:] == ["Productos", "Ventas", "Compras"]
    stock = next(c for c in _lista(tienda, "Productos")["campos"] if c["nombre"] == "Stock")
    assert stock["calculo"]["op"] == "saldo" and _valor(tienda, "Productos", "Tornillos", "Stock") == 100
    precio = next(c for c in _lista(tienda, "Ventas")["campos"] if c["nombre"] == "Precio")
    assert precio["hereda"]["campo"] == "precio"


def test_la_receta_reutiliza_la_seccion_que_ya_existe(doc):
    d = est.lista_crear(doc, "Repuestos", [{"nombre": "Pieza", "tipo": "texto"}, {"nombre": "Cantidad", "tipo": "numero"},
                                          {"nombre": "Costo", "tipo": "dinero"}], ahora=AHORA)
    d2, texto = recetas.aplicar(d, "inventario", {"productos": "Repuestos"}, AHORA, HOY)
    assert "usé tu sección Repuestos" in texto and not any(l["nombre"] == "Productos" for l in d2["listas"])
    rep = _lista(d2, "Repuestos")
    stock = next(c for c in rep["campos"] if c["nombre"] == "Stock")
    cantidad = next(c for c in rep["campos"] if c["nombre"] == "Cantidad")
    assert cantidad["id"] in stock["calculo"]["mas"]  # su «Cantidad» de siempre es el punto de partida


def test_la_receta_dos_veces_no_duplica(tienda):
    d2, _ = recetas.aplicar(tienda, "inventario", {}, AHORA, HOY)
    assert [l["nombre"] for l in d2["listas"]] == [l["nombre"] for l in tienda["listas"]]
    assert sum(1 for c in _lista(d2, "Productos")["campos"] if c["nombre"].startswith("Stock")) == 1


def test_cuentas_por_cobrar(doc):
    d, _ = recetas.aplicar(doc, "cuentas_por_cobrar", {}, AHORA, HOY)
    cli, cred, abon = _lista(d, "Clientes"), _lista(d, "Créditos"), _lista(d, "Abonos")
    cli["registros"].append({"id": "c1", "valores": {"nombre": "Ana"}})
    cred["registros"].append({"id": "x1", "valores": {"cliente": "Ana", "monto": 500}})
    abon["registros"].append({"id": "y1", "valores": {"cliente": "Ana", "monto": 120}})
    assert _valor(d, "Clientes", "Ana", "Saldo") == 380


def test_receta_inexistente():
    with pytest.raises(ValueError, match="no existe"):
        recetas.aplicar({}, "nomina", {}, AHORA, HOY)


# ───────── Vender, editar, borrar, deshacer (por el chat, modelo falso) ─────────

@pytest.mark.asyncio
async def test_vender_baja_el_stock_y_copia_el_precio(tienda):
    r, _ = await _vender(tienda, "vendí 3 tornillos", {"Producto": "tornillo", "Cantidad": 3})
    venta = _lista(r["doc"], "Ventas")["registros"][0]["valores"]
    assert venta["producto"] == "Tornillos" and venta["precio"] == 2  # el nombre exacto y el precio de hoy
    assert _valor(r["doc"], "Productos", "Tornillos", "Stock") == 97 and _valor(r["doc"], "Ventas", "Tornillos", "Total") == 6


@pytest.mark.asyncio
async def test_el_precio_de_la_venta_no_cambia_si_cambia_el_del_producto(tienda):
    r, _ = await _vender(tienda, "vendí 3 tornillos", {"Producto": "Tornillos", "Cantidad": 3})
    d = copy.deepcopy(r["doc"])
    _lista(d, "Productos")["registros"][0]["valores"]["precio"] = 5
    assert _valor(d, "Ventas", "Tornillos", "Total") == 6


@pytest.mark.asyncio
async def test_editar_y_borrar_la_venta_lo_deja_bien_solo(tienda):
    r, _ = await _vender(tienda, "vendí 3 tornillos", {"Producto": "Tornillos", "Cantidad": 3})
    d = r["doc"]
    hist = [{"de": "yo", "t": "vendí 3 tornillos"}, {"de": "shifu", "t": "Listo."}]  # en la conversación real ya nombró los tornillos
    r2, _ = await correr(d, "eran 5 no 3", dice("", llamar("editar_registro", seccion="Ventas", registro="Tornillos", valores={"Cantidad": 5})), dice("Listo."),
                         historial=hist)
    assert _valor(r2["doc"], "Productos", "Tornillos", "Stock") == 95
    r3, _ = await correr(r2["doc"], "borra esa venta de tornillos", dice("", llamar("borrar_registro", seccion="Ventas", registro="Tornillos")), dice("Listo."))
    assert _valor(r3["doc"], "Productos", "Tornillos", "Stock") == 100


@pytest.mark.asyncio
async def test_deshacer_la_venta_devuelve_el_stock(tienda):
    r, _ = await _vender(tienda, "vendí 3 tornillos", {"Producto": "Tornillos", "Cantidad": 3})
    nuevo, punto = pt.con_punto(tienda, r["doc"], "vendí 3 tornillos", AHORA)
    punto["n"] = 1
    out = pt.deshacer(nuevo, [punto], 1, AHORA)
    assert _valor(out["doc"], "Productos", "Tornillos", "Stock") == 100


@pytest.mark.asyncio
async def test_producto_que_no_existe_pregunta_y_no_guarda(tienda):
    r, modelo = await correr(tienda, "vendí 2 taladros", dice("", llamar("agregar_registro", seccion="Ventas", valores={"Producto": "taladro", "Cantidad": 2})),
                             dice("No tienes taladros en Productos. ¿Lo agrego primero?"))
    t = _resultados(modelo)[0]
    assert "«taladro» no está en Productos" in t and "Tornillos" in t and _lista(r["doc"], "Ventas")["registros"] == []


@pytest.mark.asyncio
async def test_producto_ambiguo_pregunta(tienda):
    d = copy.deepcopy(tienda)
    p = _lista(d, "Productos")
    p["registros"].append({"id": "pT2", "valores": {"producto": "Tornillos de madera", "precio": 3, "inicial": 10}})
    p["registros"].append({"id": "pT3", "valores": {"producto": "Tornillos de metal", "precio": 3, "inicial": 10}})
    r, modelo = await correr(d, "vendí 2 tornillos de", dice("", llamar("agregar_registro", seccion="Ventas", valores={"Producto": "tornillos de", "Cantidad": 2})),
                             dice("¿De madera o de metal?"))
    assert "puede ser" in _resultados(modelo)[0] and _lista(r["doc"], "Ventas")["registros"] == []


# ───────── Herramienta ─────────

@pytest.mark.asyncio
async def test_aplicar_receta_por_el_chat(doc):
    r, modelo = await correr(doc, "quiero llevar inventario", dice("", llamar("aplicar_receta", receta="inventario")), dice("Listo, ya tienes inventario."))
    assert _resultados(modelo)[0].startswith("Listo: creé Productos") and [c["herramienta"] for c in r["cambios"]] == ["aplicar_receta"]
    assert {"Productos", "Ventas", "Compras"} <= {l["nombre"] for l in r["doc"]["listas"]}


# ───────── Al crear el CRM (decisión del 21-oct: el código conecta lo que la plantilla trae suelto) ─────────

def _plantilla_ferreteria(doc):
    d = est.lista_crear(doc, "Ventas", [{"nombre": "Producto", "tipo": "texto"}, {"nombre": "Cliente", "tipo": "texto"},
                                        {"nombre": "Cantidad", "tipo": "numero"}, {"nombre": "Total", "tipo": "dinero"}], ahora=AHORA)
    d = est.lista_crear(d, "Inventario", [{"nombre": "Producto", "tipo": "texto"}, {"nombre": "Cantidad", "tipo": "numero"},
                                          {"nombre": "Costo", "tipo": "dinero"}], ahora=AHORA)
    d = est.lista_crear(d, "Créditos", [{"nombre": "Cliente", "tipo": "texto"}, {"nombre": "Monto", "tipo": "dinero"}], ahora=AHORA)
    return est.lista_crear(d, "Clientes", [{"nombre": "Nombre", "tipo": "texto"}], ahora=AHORA)


def test_al_crear_conecta_inventario_y_creditos_que_vienen_sueltos(doc):
    d, hechas = recetas.al_crear(_plantilla_ferreteria(doc), AHORA, HOY)
    assert hechas == ["inventario", "cuentas_por_cobrar"]
    nombres = [l["nombre"] for l in d["listas"]]
    assert "Productos" not in nombres and {"Compras", "Abonos"} <= set(nombres)  # reutilizó Inventario y Clientes
    inv = _lista(d, "Inventario")
    assert any(c["nombre"] == "Stock" and c.get("calculo") for c in inv["campos"])
    assert not any(c["nombre"].startswith("Total (") for c in _lista(d, "Ventas")["campos"])  # su Total a mano se respeta
    assert any(c["nombre"] == "Saldo" and c.get("calculo") for c in _lista(d, "Clientes")["campos"])


def test_al_crear_sin_inventario_no_toca_nada(doc):
    d, hechas = recetas.al_crear(doc, AHORA, HOY)
    assert hechas == [] and d == doc

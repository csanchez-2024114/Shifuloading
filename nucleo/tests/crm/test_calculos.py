"""Datos que se conectan (`calculos.py`): relación por nombre (enlace suave) y campos calculados, con modelo simulado: no llama a OpenAI.
Cubre el cálculo dentro del registro, de fechas y el resumen de otra sección; la ambigüedad (dos «Ana»); que nada calculado se guarda ni
se escribe; el renombre que se propaga; y las herramientas enlazar_campo y calcular_campo con lo que el código le contesta al modelo."""
import copy
from datetime import date

import pytest

pytest.importorskip("langchain_core")

from test_agente_diseno import AHORA, H, URL, _con_modelo, _estado, _resultados, cli, correr, db, dice, doc, llamar  # noqa: E402,F401

from assistant.packs.crm import agente, calculos  # noqa: E402
from assistant.packs.crm import estructura as est  # noqa: E402

HOY = date(2026, 10, 13)


@pytest.fixture(autouse=True)
def con_diseno(monkeypatch):
    monkeypatch.setenv("CRM_DISENO", "1")
    monkeypatch.setattr(agente, "_pausa_hasta", 0.0)


def _nueva(d, nombre, campos, filas):
    d = est.lista_crear(d, nombre, [{"nombre": c[0], "tipo": c[1], **({"opciones": c[2]} if len(c) > 2 else {})} for c in campos], ahora=AHORA)
    l = d["listas"][-1]
    for c in l["campos"]:  # ids legibles, como los del laboratorio
        c["id"] = c["nombre"].lower()
    for i, f in enumerate(filas):
        l["registros"].append({"id": f"{nombre[:3]}{i}", "valores": {k.lower(): v for k, v in f.items()}, "creado": AHORA})
    return d


@pytest.fixture
def gym(doc):
    d = _nueva(doc, "Miembros", [("Nombre", "texto"), ("Alta", "fecha")],
               [{"Nombre": "Ana López", "Alta": "2026-10-01"}, {"Nombre": "Luis Pérez", "Alta": "2026-09-13"}, {"Nombre": "Rosa", "Alta": "2026-10-10"}])
    d = _nueva(d, "Pagos", [("Miembro", "texto"), ("Monto", "dinero")],
               [{"Miembro": "ana lopez", "Monto": 200}, {"Miembro": "Ana López", "Monto": 150}, {"Miembro": "Luis Pérez", "Monto": 90.5},
                {"Miembro": "Pedro", "Monto": 10}])
    d = _nueva(d, "Pedidos", [("Producto", "texto"), ("Cantidad", "numero"), ("Precio", "dinero")],
               [{"Producto": "Proteína", "Cantidad": 3, "Precio": 25.5}, {"Producto": "Toalla", "Cantidad": 2}])
    return d


def _ids(d):
    return {l["nombre"]: l["id"] for l in d["listas"]}


def _calc(d, lista, nombre, calculo, tipo="numero"):
    d = copy.deepcopy(d)
    l = next(x for x in d["listas"] if x["nombre"] == lista)
    l["campos"].append({"id": nombre.lower(), "nombre": nombre, "tipo": tipo, "calculo": calculo})
    return d


def _valores(d, lista, campo):
    l = next(x for x in calculos.con_calculos(d, HOY)["listas"] if x["nombre"] == lista)
    return [r["valores"].get(campo) for r in l["registros"]]


# ───────── Cálculo (funciones puras) ─────────

def test_dentro_del_registro_y_vacio_si_falta_un_dato(gym):
    d = _calc(gym, "Pedidos", "Total", {"op": "multiplicar", "campos": ["cantidad", "precio"]}, "dinero")
    assert _valores(d, "Pedidos", "total") == [76.5, None]  # la toalla no tiene precio: no se inventa
    d = _calc(gym, "Pedidos", "X", {"op": "dividir", "campos": ["precio", "cantidad"]})
    assert _valores(d, "Pedidos", "x") == [8.5, None]


def test_dividir_entre_cero_no_da_numero(gym):
    g = copy.deepcopy(gym)
    next(l for l in g["listas"] if l["nombre"] == "Pedidos")["registros"][0]["valores"]["cantidad"] = 0
    assert _valores(_calc(g, "Pedidos", "X", {"op": "dividir", "campos": ["precio", "cantidad"]}), "Pedidos", "x")[0] is None


def test_dias_desde_una_fecha(gym):
    assert _valores(_calc(gym, "Miembros", "Días", {"op": "dias_desde", "campo": "alta"}), "Miembros", "días") == [12, 30, 3]


def test_resumen_de_otra_seccion_por_nombre_sin_acentos_ni_mayusculas(gym):
    i = _ids(gym)
    d = calculos.enlazar(gym, i["Pagos"], "miembro", i["Miembros"])
    d = _calc(d, "Miembros", "Pagado", {"op": "resumen", "funcion": "suma", "seccion": i["Pagos"], "relacion": "miembro", "campo": "monto"}, "dinero")
    d = _calc(d, "Miembros", "Pagos", {"op": "resumen", "funcion": "cuenta", "seccion": i["Pagos"], "relacion": "miembro"})
    assert _valores(d, "Miembros", "pagado") == [350, 90.5, 0] and _valores(d, "Miembros", "pagos") == [2, 1, 0]


def test_un_calculado_puede_usar_otros_calculados(gym):
    i = _ids(gym)
    d = calculos.enlazar(gym, i["Pagos"], "miembro", i["Miembros"])
    d = _calc(d, "Miembros", "Saldo", {"op": "restar", "campos": ["cuota", "pagado"]}, "dinero")  # va ANTES de lo que usa
    d = _calc(d, "Miembros", "Pagado", {"op": "resumen", "funcion": "suma", "seccion": i["Pagos"], "relacion": "miembro", "campo": "monto"}, "dinero")
    d = _calc(d, "Miembros", "Cuota", {"op": "sumar", "campos": ["pagado", "pagado"]}, "dinero")
    assert _valores(d, "Miembros", "saldo") == [350, 90.5, 0]


def test_dos_con_el_mismo_nombre_no_se_enlazan_y_el_codigo_lo_dice(gym):
    i = _ids(gym)
    g = copy.deepcopy(gym)
    next(l for l in g["listas"] if l["nombre"] == "Miembros")["registros"].append({"id": "x", "valores": {"nombre": "ANA LÓPEZ"}})
    d = calculos.enlazar(g, i["Pagos"], "miembro", i["Miembros"])
    inf = calculos.informe_enlace(d, i["Pagos"], "miembro")
    assert inf == {"enlazados": 1, "total": 4, "sin_pareja": ["Pedro"], "ambiguos": ["Ana López", "ana lopez"]}
    d = _calc(d, "Miembros", "Pagado", {"op": "resumen", "funcion": "suma", "seccion": i["Pagos"], "relacion": "miembro", "campo": "monto"})
    assert _valores(d, "Miembros", "pagado")[0] is None  # ambiguo: no se le atribuye a ninguna de las dos


def test_lo_calculado_nunca_se_guarda(gym):
    d = _calc(gym, "Pedidos", "Total", {"op": "multiplicar", "campos": ["cantidad", "precio"]})
    antes = copy.deepcopy(d)
    calculos.con_calculos(d, HOY)
    assert d == antes


def test_el_renombre_se_propaga_a_los_que_lo_nombran(gym):
    i = _ids(gym)
    d = calculos.enlazar(gym, i["Pagos"], "miembro", i["Miembros"])
    despues = copy.deepcopy(d)
    next(l for l in despues["listas"] if l["nombre"] == "Miembros")["registros"][0]["valores"]["nombre"] = "Ana López de Paz"
    out = calculos.propagar_renombres(d, despues)
    assert [r["valores"]["miembro"] for r in next(l for l in out["listas"] if l["nombre"] == "Pagos")["registros"]] == \
        ["Ana López de Paz", "Ana López de Paz", "Luis Pérez", "Pedro"]
    assert calculos.propagar_renombres(d, d) is d


def test_escribir_en_un_calculado_es_un_error(gym):
    d = _calc(gym, "Pedidos", "Total", {"op": "multiplicar", "campos": ["cantidad", "precio"]})
    l = next(x for x in d["listas"] if x["nombre"] == "Pedidos")
    with pytest.raises(Exception, match="se calcula solo"):
        est.valores_validos(l["campos"], {"total": 5})


@pytest.mark.parametrize("calculo, error", [
    ({"op": "multiplicar", "campos": ["cantidad"]}, "2 o más campos"),
    ({"op": "multiplicar", "campos": ["cantidad", "producto"]}, "no son campos de número o dinero"),
    ({"op": "dias_desde", "campo": "precio"}, "necesita un campo de fecha"),
    ({"op": "potencia"}, "«op» debe ser una de"),
])
def test_definiciones_invalidas_dicen_que_si_se_puede(gym, calculo, error):
    assert error in calculos.revisar_calculo(gym, _ids(gym)["Pedidos"], calculo)


def test_resumen_sin_enlace_pide_enlazar_primero(gym):
    i = _ids(gym)
    e = calculos.revisar_calculo(gym, i["Miembros"], {"op": "resumen", "funcion": "suma", "seccion": i["Pagos"], "campo": "monto"})
    assert "enlazar_campo" in e


# ───────── Herramientas (agente con modelo falso) ─────────

@pytest.mark.asyncio
async def test_enlazar_y_calcular_por_el_chat(gym):
    r, modelo = await correr(gym, "conecta los pagos con los miembros y dime cuánto ha pagado cada uno",
                             dice("", llamar("enlazar_campo", seccion="Pagos", campo="Miembro", con="Miembros")),
                             dice("", llamar("calcular_campo", seccion="Miembros", nombre="Pagado", op="resumen", funcion="suma",
                                             de_seccion="Pagos", de_campo="Monto", formato="dinero")),
                             dice("Listo: Ana López lleva 350, Luis Pérez 90.5 y Rosa 0."))
    assert "3 de 4 registros enlazados" in _resultados(modelo, 1)[0] and "Sin pareja en Miembros (no existen allá): Pedro" in _resultados(modelo, 1)[0]
    assert "Ana López: 350" in _resultados(modelo, 2)[-1]
    campo = next(c for c in next(l for l in r["doc"]["listas"] if l["nombre"] == "Miembros")["campos"] if c["nombre"] == "Pagado")
    assert campo["tipo"] == "dinero" and campo["calculo"]["op"] == "resumen"
    assert [c["herramienta"] for c in r["cambios"]] == ["enlazar_campo", "calcular_campo"] and r["avisos"] == []


@pytest.mark.asyncio
async def test_consultar_y_estado_ven_lo_calculado(gym):
    d = _calc(gym, "Pedidos", "Total", {"op": "multiplicar", "campos": ["cantidad", "precio"]}, "dinero")
    r, modelo = await correr(d, "¿cuánto suman los totales de pedidos?", dice("", llamar("consultar_datos", seccion="Pedidos", sumar="Total")), dice("76.50"))
    assert "Suma de Total" in r["consultas"][0]["resultado"] and "76" in r["consultas"][0]["resultado"]
    pedidos = next(s for s in _estado(modelo)["secciones"] if s["titulo"] == "Pedidos")
    assert next(c for c in pedidos["campos"] if c["id"] == "total")["calculado"]["op"] == "multiplicar"


@pytest.mark.asyncio
async def test_calcular_resumen_sin_enlace_devuelve_el_error_que_guia(gym):
    r, modelo = await correr(gym, "pagado por miembro",
                             dice("", llamar("calcular_campo", seccion="Miembros", nombre="Pagado", op="resumen", funcion="suma", de_seccion="Pagos", de_campo="Monto")),
                             dice("Primero hay que conectar."))
    assert "enlazar_campo" in _resultados(modelo, 1)[0] and r["cambios"] == []


@pytest.mark.asyncio
async def test_no_pisa_un_campo_que_escribe_la_persona(gym):
    r, modelo = await correr(gym, "precio calculado", dice("", llamar("calcular_campo", seccion="Pedidos", nombre="Precio", op="multiplicar",
                                                                        campos=["Cantidad", "Cantidad"])), dice("No."))
    assert "ya existe y lo escribe la persona" in _resultados(modelo, 1)[0]


# ───────── La pantalla ─────────

def test_la_pantalla_recibe_los_valores_calculados(cli, db, monkeypatch):
    _con_modelo(monkeypatch, dice("", llamar("crear_seccion", titulo="Ventas", campos=[{"nombre": "Cantidad", "tipo": "numero"}, {"nombre": "Precio", "tipo": "dinero"}])),
                dice("Listo."),
                dice("", llamar("agregar_registro", seccion="Ventas", valores={"Cantidad": 3, "Precio": 10})), dice("Listo."),
                dice("", llamar("calcular_campo", seccion="Ventas", nombre="Total", op="multiplicar", campos=["Cantidad", "Precio"])), dice("Listo, 30."))
    for t in ("crea ventas", "agrega una venta de 3 a 10", "el total es cantidad por precio"):
        r = cli.post(f"{URL}/chat", json={"texto": t}, headers=H).json()
    ventas = next(l for l in r["crm"]["listas"] if l["nombre"] == "Ventas")
    assert ventas["registros"][0]["valores"]["total"] == 30
    guardado = next(l for l in db["crm_workspaces"].docs[0]["listas"] if l["nombre"] == "Ventas")
    assert "total" not in guardado["registros"][0]["valores"]  # en la base no se guarda


# ───────── consultar_datos: ordenar y el filtro que deja cero (banco_calculos, 21-oct) ─────────

@pytest.mark.asyncio
async def test_quien_debe_mas_lo_ordena_el_codigo(gym):
    d = _calc(gym, "Pedidos", "Total", {"op": "multiplicar", "campos": ["cantidad", "precio"]}, "dinero")
    r, _ = await correr(d, "¿cuál pedido es el más caro?", dice("", llamar("consultar_datos", seccion="Pedidos", ordenar={"campo": "Total", "orden": "mayor"})),
                        dice("La proteína."))
    t = r["consultas"][0]["resultado"]
    assert "Ordenados por Total, de mayor a menor" in t and t.index("Proteína") < t.index("Toalla")  # la toalla (sin total) va al final


@pytest.mark.asyncio
async def test_un_filtro_que_deja_cero_dice_cuanto_seria_sin_el(gym):
    d = _nueva(gym, "Cuotas", [("Socio", "texto"), ("Estado", "estado", ["Activa", "Pausada"]), ("Saldo", "dinero")],
               [{"Socio": "Ana", "Saldo": 300}, {"Socio": "Luis", "Saldo": 100}])
    r, _ = await correr(d, "¿cuánto me deben?", dice("", llamar("consultar_datos", seccion="Cuotas", sumar="Saldo", filtros={"Estado": "Activa"})),
                        dice("400."))
    t = r["consultas"][0]["resultado"]
    assert "0 de 2" in t and "sin el filtro de Estado serían 2" in t and "400" in t


# ───────── consultar_datos: agrupar («cuánto me paga cada miembro en promedio», banco2, 21-oct) ─────────

@pytest.mark.asyncio
async def test_promedio_por_cada_uno_lo_calcula_el_codigo(gym):
    d = _nueva(gym, "Cobros", [("Socio", "texto"), ("Monto", "dinero")],
               [{"Socio": "Ana", "Monto": 300}, {"Socio": "Ana", "Monto": 100}, {"Socio": "Luis", "Monto": 500}, {"Socio": "Eva"}])
    r, _ = await correr(d, "¿cuánto me paga cada socio en promedio?",
                        dice("", llamar("consultar_datos", seccion="Cobros", agrupar="Socio", funcion="promedio", valor="Monto")), dice("Luis 500, Ana 200."))
    t = r["consultas"][0]["resultado"].replace("\xa0", " ")
    assert "Por Socio (promedio de Monto, de mayor a menor)" in t
    assert t.index("Luis") < t.index("Ana: Q 200") < t.index("Eva: sin datos")  # Eva no tiene monto: no cuenta como 0


@pytest.mark.asyncio
async def test_agrupar_sin_valor_cuenta_y_errores_guian(gym):
    d = _nueva(gym, "Cobros", [("Socio", "texto"), ("Monto", "dinero")], [{"Socio": "Ana", "Monto": 1}, {"Socio": "Ana", "Monto": 2}])
    r, _ = await correr(d, "¿cuántos cobros por socio?", dice("", llamar("consultar_datos", seccion="Cobros", agrupar="Socio")), dice("Ana 2."))
    assert "Por Socio (cuántos, de mayor a menor): Ana: 2." in r["consultas"][0]["resultado"]  # sin valor: cuenta
    r, _ = await correr(d, "x", dice("", llamar("consultar_datos", seccion="Cobros", agrupar="Socio", funcion="suma")), dice("."))
    assert "Ana: Q 3 (2 registros)" in r["consultas"][0]["resultado"].replace("\xa0", " ")  # sin valor y un solo campo de dinero: ese
    r, _ = await correr(d, "x", dice("", llamar("consultar_datos", seccion="Cobros", agrupar="Ciudad")), dice("."))
    assert "ERROR: «Ciudad» no es un campo de Cobros" in r["consultas"][0]["resultado"]

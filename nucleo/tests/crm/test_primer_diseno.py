"""Primer diseño con piezas (lista 21–29, `app/crm/primer_diseno.py`). Nada llama al OpenAI de verdad: la IA es un modelo falso.

- El % por sección lo calcula el código con TODAS las respuestas (PepesCore ya no recibe piezas de gimnasio).
- La propuesta del modelo pasa por el cerco (tipos, opciones, vistas, bloques) antes de sembrarse con pocos ejemplos.
- Máximo 2 llamadas; si falla, respaldo honesto y nunca un CRM casi vacío.
- El resumen y los ejemplos del saludo los escribe el código con lo que de verdad se creó.
"""
import json
from datetime import datetime, timezone

import pytest

from assistant.packs.crm import diseno, ejemplos, primer_diseno as pd
from assistant.packs.crm import secciones_v as sv

AHORA = datetime(2026, 10, 19, 15, 0, tzinfo=timezone.utc)

PEPESCORE = {"nombre": "PepesCore", "rubro": "comercio",
             "que_vendes": "Me dedico a vender computadoras, laptops y accesorios y también a repararlas. Somos 15 empleados. Lo que hacemos: reparar, "
                           "revisar, vender, desarmar y comprar equipos usados. Quiero tener el control de mis números, datos y mi personal.",
             "seguimiento": [{"pregunta": "¿Qué quieres tener en orden primero?", "respuesta": "Ventas, Empleados, Reparaciones, Equipos"},
                             {"pregunta": "¿Qué se te complica?", "respuesta": "Reparaciones, Inventario, Turnos"}]}
COMIDA_PLANCHADO = {"nombre": "Doña Tere", "rubro": "servicios",
                    "que_vendes": "Vendo almuerzos caseros a domicilio y además tengo un servicio de planchado de ropa que cobro por docena."}


@pytest.fixture(autouse=True)
def sin_ia_real(monkeypatch):
    monkeypatch.setenv("CRM_IA", "0")


class Modelo:
    def __init__(self, *respuestas):
        self.respuestas, self.llamadas = list(respuestas), []

    async def ainvoke(self, mensajes):
        self.llamadas.append(mensajes)
        r = self.respuestas.pop(0) if len(self.respuestas) > 1 else self.respuestas[0]
        if isinstance(r, Exception):
            raise r
        return type("R", (), {"content": r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)})()


PROPUESTA = {
    "rubros": ["Venta y reparación de computadoras"],
    "secciones": [
        {"id": "reparaciones", "titulo": "Reparaciones", "pieza": "taller-mecanico.ordenes", "vista": "tablero",
         "opciones": {"por": "estado", "titulo": "equipo", "detalle": "cliente"},
         "campos": [["equipo", "Equipo", "texto", ["Laptop HP 240", "PC Dell Optiplex", "MacBook Air 2019"]], ["cliente", "Cliente", "texto", "persona"],
                    ["falla", "Falla", "texto", ["No enciende", "Pantalla rota"]], ["estado", "Estado", "estado", ["Recibido", "En reparación", "Listo", "Entregado"]],
                    ["entrega", "Entrega", "fecha", [-3, 10]], ["total", "Total", "dinero", [150, 2500]]]},
        {"id": "ventas", "titulo": "Ventas", "vista": "tabla",
         "campos": [["producto", "Producto", "texto", ["Laptop Lenovo IdeaPad", "Mouse Logitech"]], ["total", "Total", "dinero", [100, 9000]],
                    ["fecha", "Fecha", "fecha", [-20, 0]], ["estado", "Estado", "estado", ["Cotizada", "Pagada", "Entregada"]]]},
        {"id": "empleados", "titulo": "Empleados", "vista": "tabla",
         "campos": [["nombre", "Nombre", "texto", "persona"], ["puesto", "Puesto", "texto", ["Técnico", "Vendedor", "Cajera"]],
                    ["entrada", "Entrada", "hora"], ["salida", "Salida", "hora"]]},
    ],
    "inicio": [{"seccion": "reparaciones", "vista": "kpis", "opciones": {"por": "estado", "suma": "total"}},
               {"seccion": "ventas", "vista": "grafico", "opciones": {"tipo": "columnas"}},
               {"seccion": "empleados", "vista": "grafico", "opciones": {"tipo": "gantt"}},  # pide 2 fechas: no se puede, se quita
               {"seccion": "no_existe", "vista": "kpis", "opciones": {}}],
}


# ───────── El % por sección ─────────

def test_raiz_junta_las_formas_de_una_palabra_sin_mezclar_otras():
    assert pd.raiz("reparaciones") == pd.raiz("reparar") == pd.raiz("reparación".replace("ó", "o"))
    assert pd.raiz("repartidor") == pd.raiz("reparto") != pd.raiz("reparar")
    assert pd.raiz("computadoras") == pd.raiz("computo")
    assert pd.raiz("personal") != pd.raiz("personas")


def test_pepescore_no_recibe_piezas_de_gimnasio_y_si_de_taller_e_inventario():
    compat, rubros = pd.compatibilidad(PEPESCORE)
    al_modelo = [x["pieza"]["id"] for x in pd.piezas_para_el_modelo(compat)]
    assert not [i for i in al_modelo if i.startswith(("gimnasio.", "membresias."))]
    assert "taller-mecanico.ordenes" in al_modelo and "pestana.garantias" in al_modelo
    assert any("inventario" in i for i in al_modelo)
    por_id = {x["pieza"]["id"]: x["pct"] for x in compat}
    assert por_id["gimnasio.membresias"] < 30 < por_id["taller-mecanico.ordenes"]
    assert rubros[0]["rubro"] == "Venta y reparación de tecnología"


def test_cuentan_todas_las_respuestas_no_solo_el_rubro():
    solo = {"nombre": "X", "rubro": "comercio", "que_vendes": "Tengo una tienda"}
    con = {**solo, "seguimiento": [{"pregunta": "¿Qué quieres llevar?", "respuesta": "El inventario de mi bodega y lo que me queda"}]}
    pct = lambda b: next(x["pct"] for x in pd.compatibilidad(b)[0] if x["pieza"]["id"] == "pestana.inventario")  # noqa: E731
    assert pct(con) > pct(solo) + 30


def test_varios_rubros_a_la_vez_se_combinan():
    _, rubros = pd.compatibilidad(COMIDA_PLANCHADO)
    nombres = [r["rubro"] for r in rubros]
    assert "Lavandería y planchado" in nombres and "Restaurante y comida" in nombres
    msg = pd.mensaje_usuario(COMIDA_PLANCHADO, pd.piezas_para_el_modelo(pd.compatibilidad(COMIDA_PLANCHADO)[0]), rubros)
    assert "como_combinar" in msg and "planchado" in msg.lower()


def test_una_pieza_por_titulo_al_modelo():
    compat, _ = pd.compatibilidad({"nombre": "X", "que_vendes": "clientes clientes clientes"})
    titulos = [pd._clave_titulo(x["pieza"]["seccion"]["titulo"]) for x in pd.piezas_para_el_modelo(compat)]
    assert len(titulos) == len(set(titulos))


# ───────── El cerco ─────────

def test_la_propuesta_pasa_por_el_cerco():
    p = pd.plantilla_de_propuesta(PROPUESTA, pd.piezas_para_el_modelo(pd.compatibilidad(PEPESCORE)[0]), "medida-x", "PepesCore")
    rep, ven, emp = p["secciones"]
    assert rep["vista"] == "tablero" and rep["opciones"] == {"por": "estado", "titulo": "equipo", "detalle": "cliente"}
    assert rep["campos"][0]["ejemplos"][0] == "Laptop HP 240" and rep["campos"][1].get("persona") and "ejemplos" not in rep["campos"][1]
    assert rep["campos"][5]["rango"] == [150, 2500] and rep["_pieza"] == "taller-mecanico.ordenes"
    assert [b["vista"] for b in p["inicio"]] == ["kpis", "grafico"]  # el gantt sin 2 fechas y el bloque sin sección no entran
    assert p["inicio"][1]["opciones"] == {"tipo": "columnas"}


def test_el_cerco_corrige_o_descarta_lo_que_no_sirve():
    crudo = {"secciones": [
        {"titulo": "Pagos", "vista": "tablero", "campos": [["monto", "Monto", "moneda"], ["fecha", "Fecha", "fecha"], ["estado", "Estado", "estado", []]]},
        {"titulo": "Pagos", "campos": [["a", "A", "texto"], ["b", "B", "texto"]]},  # título repetido
        {"titulo": "Una sola cosa", "campos": [["a", "A", "texto"]]},  # menos de 2 campos
        {"titulo": "Muchos", "campos": [[f"c{i}", f"C{i}", "texto"] for i in range(12)]},
        "basura"]}
    p = pd.plantilla_de_propuesta(crudo, [], "medida-x", "X")
    pagos, muchos = p["secciones"]
    # «moneda» es dinero; el estado sin opciones no entra (sería el «Estado de texto» del informe); la primera columna es de texto;
    # tablero sin campo estado vuelve a tabla.
    assert [(c["nombre"], c["tipo"]) for c in pagos["campos"]] == [("Nombre", "texto"), ("Monto", "dinero"), ("Fecha", "fecha")]
    assert pagos["vista"] == "tabla" and pagos["opciones"] == {}
    assert len(muchos["campos"]) == pd.MAX_CAMPOS
    assert len(p["inicio"]) >= 2  # el modelo no dio bloques: los calcula el código
    assert pd.plantilla_de_propuesta({"secciones": []}, [], "m", "X") is None and pd.plantilla_de_propuesta("x", [], "m", "X") is None


def test_completar_opciones_pone_lo_obligatorio_y_quita_lo_que_no_existe():
    campos = [{"id": "t", "nombre": "T", "tipo": "texto"}, {"id": "f", "nombre": "F", "tipo": "fecha"}, {"id": "e", "nombre": "E", "tipo": "estado", "opciones": ["a", "b"]}]
    assert pd.completar_opciones("vencimientos", {"estado": "nada", "titulo": "t"}, campos) == {"titulo": "t", "fecha": "f"}
    assert pd.completar_opciones("tablero", {}, campos) == {"por": "e"}


# ───────── Crear ─────────

@pytest.mark.asyncio
async def test_crear_con_una_llamada_pocos_ejemplos_del_negocio_y_resumen_del_codigo(monkeypatch):
    async def ajuste(*_a, **_k):
        raise AssertionError("sin la llamada de ajuste vieja")

    monkeypatch.setattr(diseno, "ajustar_sembrado", ajuste)
    m = Modelo(PROPUESTA)
    doc = await pd.crear("u1", PEPESCORE, modelo=m, ahora=AHORA)
    assert len(m.llamadas) == 1 and doc["plantilla"]["llamadas"] == 1 and doc["plantilla"]["respaldo"] is False
    assert doc["plantilla"]["origen"] == "piezas" and doc["plantilla"]["piezas"]["Reparaciones"] == "taller-mecanico.ordenes"
    assert [l["nombre"] for l in doc["listas"]] == ["Reparaciones", "Ventas", "Empleados"]
    rep = doc["listas"][0]
    assert len(rep["registros"]) == ejemplos.NIVELES["pocos"] and all(r["ejemplo"] for r in rep["registros"])
    assert {r["valores"]["equipo"] for r in rep["registros"]} <= {"Laptop HP 240", "PC Dell Optiplex", "MacBook Air 2019"}
    assert all(r["valores"]["cliente"] in ejemplos.NOMBRES for r in rep["registros"])  # «persona»: nombres del generador
    assert all(150 <= r["valores"]["total"] <= 2500 for r in rep["registros"])
    emp = doc["listas"][2]
    assert all(r["valores"]["entrada"] <= r["valores"]["salida"] for r in emp["registros"])  # coherencia calculada
    assert "gimnas" not in json.dumps(doc, ensure_ascii=False, default=str).lower() and "membres" not in json.dumps(doc["listas"], ensure_ascii=False, default=str).lower()
    assert doc["resumen_ia"].startswith("Armé tu CRM con 3 secciones: Reparaciones, Ventas y Empleados.")
    assert "8 registros de ejemplo" in doc["resumen_ia"] and "inventario" not in doc["resumen_ia"].lower()
    nombres = [s["titulo"] for s in sv.secciones_de(doc)]
    assert len(doc["saludo_ejemplos"]) == 3 and all(any(n in e for n in nombres) for e in doc["saludo_ejemplos"])
    assert doc["inicio"][0]["uid"] == "b0" and {b["seccion"] for b in doc["inicio"]} <= {l["id"] for l in doc["listas"]}


@pytest.mark.asyncio
async def test_json_malo_se_reintenta_una_vez_y_luego_respaldo():
    m = Modelo("esto no es json", "tampoco")
    doc = await pd.crear("u1", PEPESCORE, modelo=m, ahora=AHORA)
    assert len(m.llamadas) == 2 and doc["plantilla"]["llamadas"] == 2  # nunca más de 2
    assert doc["plantilla"]["respaldo"] is True and doc["resumen_ia"].startswith("Te dejé una base con")
    assert len(doc["listas"]) >= 3 and all(l["registros"] for l in doc["listas"])


@pytest.mark.asyncio
async def test_json_malo_y_luego_bueno_usa_el_segundo():
    m = Modelo("no", PROPUESTA)
    doc = await pd.crear("u1", PEPESCORE, modelo=m, ahora=AHORA)
    assert len(m.llamadas) == 2 and doc["plantilla"]["respaldo"] is False


@pytest.mark.asyncio
async def test_si_la_llamada_falla_no_se_reintenta_y_queda_un_respaldo_util():
    m = Modelo(RuntimeError("sin saldo"))
    doc = await pd.crear("u1", PEPESCORE, modelo=m, ahora=AHORA)
    assert len(m.llamadas) == 1 and doc["plantilla"]["respaldo"] is True and "falló" in doc["plantilla"]["motivo"]
    titulos = " ".join(l["nombre"] for l in doc["listas"]).lower()
    assert len(doc["listas"]) >= 3 and "membres" not in titulos and "gimnas" not in titulos
    assert len(doc["inicio"]) >= 2


@pytest.mark.asyncio
async def test_sin_ia_y_sin_nada_parecido_nunca_queda_casi_vacio():
    doc = await pd.crear("u1", {"nombre": "Astral", "que_vendes": "cosas geek"}, ahora=AHORA)
    secs = [s for s in sv.secciones_de(doc) if s["id"] != sv.TAREAS]
    assert len(secs) >= 2 and len(doc["inicio"]) >= 2
    assert all(len(s["campos"]) >= 2 for s in secs)
    assert doc["resumen_ia"] and doc["saludo_ejemplos"]


def test_resumen_no_nombra_lo_que_no_existe():
    base = {"brief": {}, "secciones": {}, "ocultas": ["contactos", "desarrollo"], "contactos": [], "listas": [
        {"id": "l_a", "nombre": "Pedidos", "campos": [{"id": "p", "nombre": "Pedido", "tipo": "texto"}], "registros": [{"id": "1", "ejemplo": True, "valores": {"p": "Pizza"}}]}],
        "inicio": [{"uid": "b0", "vista": "tabla", "seccion": "l_a"}]}
    r = pd.resumen(base, False)
    assert r == ("Armé tu CRM con 1 sección: Pedidos. En el inicio tienes 1 bloque sobre Pedidos. Cada sección trae hasta 1 registro de "
                 "ejemplo para que veas cómo se usa; los quitas con «Quitar ejemplos». Lo demás lo vamos armando juntos.")
    assert pd.ejemplos_saludo(base) == ["en Pedidos, agrega «Pizza»", "agrega al inicio una gráfica de Pedidos"]


@pytest.mark.asyncio
async def test_un_texto_sin_ejemplos_queda_en_blanco_y_no_con_nombres_de_personas():
    propuesta = {"secciones": [{"id": "cobros", "titulo": "Cobros", "campos": [
        ["cliente", "Cliente", "texto", ["persona"]], ["pedido", "Pedido", "texto"], ["total", "Total", "dinero", [10, 90]], ["estado", "Estado", "estado", ["Pendiente", "Cobrado"]]]}],
        "inicio": []}
    doc = await pd.crear("u1", PEPESCORE, modelo=Modelo(propuesta), ahora=AHORA)
    assert len(doc["listas"]) == pd.MIN_SECCIONES and doc["listas"][0]["nombre"] == "Cobros"  # una sola sección: se completa con piezas claras
    regs = doc["listas"][0]["registros"]
    assert all("pedido" not in r["valores"] for r in regs)  # el modelo no dio valores de ese negocio: en blanco
    assert all(r["valores"]["cliente"] in ejemplos.NOMBRES for r in regs)  # ["persona"] también vale


def test_completar_opciones_deja_las_opciones_libres_de_la_vista():
    campos = [{"id": "m", "nombre": "M", "tipo": "dinero"}, {"id": "f", "nombre": "F", "tipo": "fecha"}]
    assert pd.completar_opciones("cifra", {"funcion": "suma", "valor": "m", "periodo": "mes", "nada": 1}, campos) == {"funcion": "suma", "valor": "m", "periodo": "mes"}

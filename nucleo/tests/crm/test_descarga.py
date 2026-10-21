"""La descarga que pide la persona (`descarga.py` + herramienta `descargar` + rutas /descargas y /exportar), con un modelo simulado:
no llama a OpenAI. Cubre el archivo (tipos en Excel, CSV con BOM, respaldo sin ids), los filtros de consultar_datos, los errores que
ve el modelo, que no cambia el CRM y que la pantalla recibe el botón y baja el archivo."""
import csv
import io
import json
from datetime import date

import pytest

pytest.importorskip("langchain_core")
openpyxl = pytest.importorskip("openpyxl")

from test_agente_diseno import AHORA, H, URL, _con_modelo, _resultados, cli, correr, db, dice, doc, llamar  # noqa: E402,F401

from assistant.packs.crm import descarga as dl  # noqa: E402
from assistant.packs.crm import estructura as est  # noqa: E402
from assistant.packs.crm import operaciones as op  # noqa: E402

CAMPOS = [{"id": "cliente", "nombre": "Cliente", "tipo": "texto"}, {"id": "costo", "nombre": "Costo", "tipo": "dinero"},
          {"id": "ingreso", "nombre": "Ingreso", "tipo": "fecha"}, {"id": "estado", "nombre": "Estado", "tipo": "estado", "opciones": ["Recibido", "Listo"]}]


@pytest.fixture(autouse=True)
def con_diseno(monkeypatch):
    from assistant.packs.crm import agente

    monkeypatch.setenv("CRM_DISENO", "1")
    monkeypatch.setattr(agente, "_pausa_hasta", 0.0)


@pytest.fixture
def taller(doc):
    """El CRM de prueba con una sección «Reparaciones» de 3 registros (dos en octubre, uno en septiembre)."""
    d = est.lista_crear(doc, "Reparaciones", [{"nombre": c["nombre"], "tipo": c["tipo"], "opciones": c.get("opciones")} for c in CAMPOS], ahora=AHORA)
    lista = d["listas"][-1]
    ids = {c["nombre"]: c["id"] for c in lista["campos"]}
    for cli_, costo, f, e in [("Sofía", 250, "2026-10-02", "Recibido"), ("Marco", 400.5, "2026-10-10", "Listo"), ("Ana", 90, "2026-09-20", "Listo")]:
        lista["registros"].append({"id": f"r{cli_}", "valores": {ids["Cliente"]: cli_, ids["Costo"]: costo, ids["Ingreso"]: f, ids["Estado"]: e},
                                   "creado": AHORA})
    return d


def _libro(contenido: bytes):
    return openpyxl.load_workbook(io.BytesIO(contenido))


# ───────── El archivo (funciones puras) ─────────

def test_excel_pone_numeros_y_fechas_con_su_tipo_y_una_hoja_por_seccion():
    regs = [{"valores": {"cliente": "Sofía", "costo": "250", "ingreso": "2026-10-02", "estado": "Listo"}}, {"valores": {"cliente": "Marco"}}]
    libro = _libro(dl.excel([{"titulo": "Reparaciones", "campos": CAMPOS, "registros": regs}, {"titulo": "Reparaciones", "campos": CAMPOS, "registros": []}]))
    assert libro.sheetnames == ["Reparaciones", "Reparaciones 2"]  # dos iguales no se permiten en Excel
    h = libro["Reparaciones"]
    assert [c.value for c in h[1]] == ["Cliente", "Costo", "Ingreso", "Estado"]
    assert h["B2"].value == 250 and h["B2"].number_format == "#,##0.00"
    assert h["C2"].value.date() == date(2026, 10, 2) and h["C2"].number_format == "dd/mm/yyyy"
    assert h["B3"].value is None and h.freeze_panes == "A2"


def test_nombre_de_hoja_sin_caracteres_prohibidos_ni_mas_de_31():
    libro = _libro(dl.excel([{"titulo": "Ventas: enero/febrero [2026] con un nombre larguísimo", "campos": CAMPOS, "registros": []}]))
    assert len(libro.sheetnames[0]) <= 31 and not any(ch in libro.sheetnames[0] for ch in "\\/?*[]:")


def test_csv_con_bom_y_numeros_sin_decimales_de_mas():
    t = dl.csv_de(CAMPOS, [{"valores": {"cliente": "Sofía, la de Mixco", "costo": 250, "ingreso": "2026-10-02"}}])
    assert t.startswith("﻿".encode("utf-8"))
    filas = list(csv.reader(io.StringIO(t.decode("utf-8-sig"))))
    assert filas == [["Cliente", "Costo", "Ingreso", "Estado"], ["Sofía, la de Mixco", "250", "2026-10-02", ""]]


def test_respaldo_completo_sin_ids_de_la_base(taller):
    d = {**taller, "_id": "abc", "user_id": "u1"}
    r = json.loads(dl.respaldo(d, AHORA))
    assert r["formato"] == "respaldo-crm" and r["version"] == 1 and r["creado"] == AHORA.isoformat()
    assert "_id" not in r["crm"] and "user_id" not in r["crm"]
    assert [x["nombre"] for x in r["crm"]["listas"]][-1] == "Reparaciones" and len(r["crm"]["listas"][-1]["registros"]) == 3


def test_nombre_de_archivo_sin_caracteres_que_el_sistema_no_acepta():
    assert dl.nombre_archivo("Taller: Pepe/2", "Clientes", "excel", date(2026, 10, 20)) == "Taller Pepe 2 - Clientes - 2026-10-20.xlsx"


# ───────── La herramienta (agente con modelo falso) ─────────

@pytest.mark.asyncio
async def test_excel_filtrado_por_mes_no_cambia_el_crm_y_sale_en_descargas(taller):
    r, modelo = await correr(taller, "pásame en Excel las reparaciones de octubre",
                             dice("", llamar("descargar", formato="excel", secciones=[{"seccion": "Reparaciones", "periodo": {"cuando": "octubre"}}])),
                             dice("Listo: tu Excel con 2 reparaciones de octubre."))
    assert r["doc"] is taller and r["cambios"] == []  # descargar no es un cambio: no deja punto de deshacer
    texto = _resultados(modelo)[0]
    assert "2 de 3" in texto and "no escribas enlaces" in texto
    (a,) = r["descargas"]
    assert a["formato"] == "excel" and a["nombre"].endswith("Reparaciones - 2026-10-13.xlsx")
    h = _libro(a["contenido"]).active
    assert sorted(h.cell(row=i, column=1).value for i in (2, 3)) == ["Marco", "Sofía"] and h.max_row == 3
    assert r["respuesta"] == "Listo: tu Excel con 2 reparaciones de octubre."  # las cifras salen del resultado: el cerco no la corrige


@pytest.mark.asyncio
async def test_columnas_pedidas_y_csv_de_una_seccion(taller):
    r, _ = await correr(taller, "un csv de reparaciones solo con cliente y costo",
                        dice("", llamar("descargar", formato="csv", secciones=[{"seccion": "Reparaciones", "columnas": ["Cliente", "costo"]}])), dice("Listo."))
    filas = list(csv.reader(io.StringIO(r["descargas"][0]["contenido"].decode("utf-8-sig"))))
    assert filas[0] == ["Cliente", "Costo"] and len(filas) == 4


@pytest.mark.asyncio
async def test_sin_secciones_van_todas_las_del_menu(taller):
    r, _ = await correr(taller, "descarga todo en excel", dice("", llamar("descargar", formato="excel")), dice("Listo."))
    nombres = _libro(r["descargas"][0]["contenido"]).sheetnames
    assert "Reparaciones" in nombres and r["descargas"][0]["nombre"].endswith("CRM - 2026-10-13.xlsx")


@pytest.mark.asyncio
async def test_una_seccion_oculta_se_puede_pedir_y_sin_secciones_no_sale(taller):
    d = est.seccion_ocultar(taller, "contactos", ahora=AHORA)
    r, _ = await correr(d, "pásame los contactos en excel", dice("", llamar("descargar", formato="excel", secciones=[{"seccion": "contactos"}])), dice("Listo."))
    h = _libro(r["descargas"][0]["contenido"]).active
    assert h.max_row == 4 and r["doc"]["ocultas"] == d["ocultas"]  # sus 3 contactos, y la sección sigue oculta
    r, _ = await correr(d, "descarga todo en excel", dice("", llamar("descargar", formato="excel")), dice("Listo."))
    assert len(_libro(r["descargas"][0]["contenido"]).sheetnames) == len(d["listas"]) + 1  # las del menú: tareas y las propias


@pytest.mark.asyncio
@pytest.mark.parametrize("args, error", [
    ({"formato": "pdf"}, "usa excel, csv o respaldo"),
    ({"formato": "excel", "secciones": [{"seccion": "Facturas"}]}, "no es una sección con registros"),
    ({"formato": "csv"}, "un CSV lleva UNA sola sección"),
    ({"formato": "excel", "secciones": [{"seccion": "Reparaciones", "columnas": ["Placa"]}]}, "«Placa» no es un campo de Reparaciones"),
    ({"formato": "excel", "secciones": [{"seccion": "Reparaciones", "periodo": {"cuando": "cuando llueva"}}]}, "no entendí el periodo"),
])
async def test_lo_que_no_se_puede_vuelve_como_error_y_no_hay_archivo(taller, args, error):
    r, modelo = await correr(taller, "descarga", dice("", llamar("descargar", **args)), dice("No pude."))
    assert error in _resultados(modelo)[0] and "descargas" not in r


@pytest.mark.asyncio
async def test_un_solo_archivo_por_mensaje(taller):
    r, modelo = await correr(taller, "excel y respaldo", dice("", llamar("descargar", formato="excel"), llamar("descargar", formato="respaldo")), dice("Listo."))
    assert len(r["descargas"]) == 1 and "ya preparaste un archivo" in _resultados(modelo)[1]


# ───────── Las rutas ─────────

def test_la_ruta_del_chat_guarda_el_archivo_y_la_pantalla_lo_baja(cli, monkeypatch):
    _con_modelo(monkeypatch, dice("", llamar("descargar", formato="respaldo")), dice("Listo, tu respaldo."))
    r = cli.post(f"{URL}/chat", json={"texto": "hazme un respaldo de todo"}, headers=H).json()
    (ficha,) = r["descargas"]
    assert set(ficha) == {"id", "nombre", "formato"} and ficha["formato"] == "respaldo"
    assert r["crm"]["puntos"] == []  # pedir un archivo no deja punto de deshacer
    b = cli.get(f"{URL}/descargas/{ficha['id']}", headers=H)
    assert b.status_code == 200 and b.headers["content-type"].startswith("application/json")
    assert "attachment" in b.headers["content-disposition"] and json.loads(b.content)["formato"] == "respaldo-crm"
    assert cli.get(f"{URL}/descargas/{ficha['id']}", headers={"X-Usuario": "otra"}).status_code == 404  # nadie baja el de otra persona


def test_si_no_se_pudo_guardar_la_respuesta_lo_dice(cli, db, monkeypatch):
    from assistant.packs.crm import repositorio

    async def falla(*_a, **_k):
        raise RuntimeError("sin base")

    monkeypatch.setattr(repositorio, "descarga_guardar", falla)
    _con_modelo(monkeypatch, dice("", llamar("descargar", formato="excel")), dice("Listo, tu Excel."))
    r = cli.post(f"{URL}/chat", json={"texto": "pásame todo en excel"}, headers=H).json()
    assert "descargas" not in r and r["respuesta"].endswith("Ojo: no pude preparar el archivo. Pídemelo de nuevo en un momento.")


def test_exportar_desde_ajustes(cli):
    x = cli.get(f"{URL}/exportar?formato=excel", headers=H)
    assert x.status_code == 200 and x.headers["content-type"].startswith(dl.MIME["excel"]) and _libro(x.content).sheetnames
    j = cli.get(f"{URL}/exportar?formato=respaldo", headers=H)
    assert json.loads(j.content)["crm"]["brief"]
    assert cli.get(f"{URL}/exportar?formato=pdf", headers=H).status_code == 422
    assert cli.get(f"{URL}/exportar", headers={"X-Usuario": "sin-crm"}).status_code == 404


# ───────── Cercos (casos del banco con IA real, 20-oct) ─────────

@pytest.mark.asyncio
async def test_decir_que_preparo_el_archivo_sin_llamar_la_herramienta_se_corrige(taller):
    # banco_descarga: «exporta todo mi CRM a Excel» → «Ya preparé el archivo Excel…» sin llamar a descargar (no había botón).
    r, modelo = await correr(taller, "exporta todo mi CRM a Excel", dice("Ya preparé el archivo Excel con todo tu CRM."),
                             dice("", llamar("descargar", formato="excel")), dice("Listo, tu Excel con todo."))
    assert r["avisos"] and len(r["descargas"]) == 1  # un cerco lo corrige (promesa o «dices que hiciste»): al final hay archivo


@pytest.mark.asyncio
async def test_preparar_no_se_confunde_con_una_promesa(taller):
    # (sin el archivo, la misma frase sí la atrapa el cerco: ver la prueba de arriba)
    # banco_descarga: «Preparé el Excel con las 5 reparaciones» se tomaba por futuro («-aré») y el código repetía la herramienta.
    r, modelo = await correr(taller, "pásame en Excel las reparaciones", dice("", llamar("descargar", formato="excel", secciones=[{"seccion": "Reparaciones"}])),
                             dice("Preparé el Excel con las 3 reparaciones que tienes."))
    assert r["avisos"] == [] and "todavía no está hecho" not in r["respuesta"] and len(modelo.recibidos) == 2
    # banco_descarga: «Preparé un CSV con cliente y equipo» (las columnas que pidió también son lo hecho)
    r, _ = await correr(taller, "csv de reparaciones con cliente y costo",
                        dice("", llamar("descargar", formato="csv", secciones=[{"seccion": "Reparaciones", "columnas": ["Cliente", "Costo"]}])),
                        dice("Preparé un CSV con cliente y costo de las 3 reparaciones."))
    assert "todavía no está hecho" not in r["respuesta"]


@pytest.mark.asyncio
async def test_mandarla_a_descargar_sin_archivo_se_corrige_con_cualquier_verbo(taller):
    # banco_descarga (3.ª corrida): «Ya armé el respaldo completo de tu CRM para que lo descargues en la pantalla.» sin llamar a descargar.
    r, _ = await correr(taller, "hazme un respaldo de todo", dice("Ya armé el respaldo completo de tu CRM para que lo descargues en la pantalla."),
                        dice("", llamar("descargar", formato="respaldo")), dice("Listo: tu respaldo, para que lo descargues."))
    assert "no preparaste ninguno" in r["avisos"][0]["aviso"] and r["descargas"][0]["formato"] == "respaldo"


@pytest.mark.asyncio
async def test_ofrecer_la_descarga_como_pregunta_no_es_mentira(taller):
    r, _ = await correr(taller, "mándamelo en PDF", dice("No puedo hacer PDF. ¿Quieres que lo prepare en Excel para que lo descargues?"))
    assert r["avisos"] == [] and "descargas" not in r

"""Documento de un registro (`documento.py` + herramienta documento_de + la ruta que numera y arma el PDF). Modelo simulado: sin OpenAI.
Cubre: la foto (datos con formato, registros enlazados con su total), el PDF que se abre y dice lo que debe (acentos, número, pie de
«no es factura fiscal»), el logo, el número consecutivo, la reimpresión idéntica aunque cambien los datos y el documento nuevo."""
import base64
import io

import pytest

pytest.importorskip("langchain_core")
pytest.importorskip("reportlab")
pymupdf = pytest.importorskip("pymupdf")

from test_agente_diseno import AHORA, H, URL, _con_modelo, _resultados, cli, correr, db, dice, doc, llamar  # noqa: E402,F401

from assistant.packs.crm import agente, documento, recetas  # noqa: E402
from assistant.packs.crm import secciones_v as sv  # noqa: E402
from datetime import date  # noqa: E402

HOY = date(2026, 10, 13)


@pytest.fixture(autouse=True)
def con_diseno(monkeypatch):
    monkeypatch.setenv("CRM_DISENO", "1")
    monkeypatch.setattr(agente, "_pausa_hasta", 0.0)


@pytest.fixture
def fiado(doc):
    """Cuentas por cobrar con Ana: un crédito de 500 y dos abonos (120 y 80)."""
    d, _ = recetas.aplicar(doc, "cuentas_por_cobrar", {}, AHORA, HOY)
    l = {x["nombre"]: x for x in d["listas"]}
    l["Clientes"]["registros"].append({"id": "c1", "valores": {"nombre": "Ana Ruiz", "telefono": "5555-1234"}})
    l["Clientes"]["registros"].append({"id": "c2", "valores": {"nombre": "Luis"}})
    l["Créditos"]["registros"].append({"id": "k1", "valores": {"cliente": "Ana Ruiz", "concepto": "Cemento", "monto": 500, "vence": "2026-11-01"}})
    for i, m in enumerate((120, 80)):
        l["Abonos"]["registros"].append({"id": f"a{i}", "valores": {"cliente": "ana ruiz", "monto": m, "fecha": "2026-10-10"}})
    return d


def _sec(d, nombre):
    return next(s for s in sv.secciones_de(d) if s["titulo"] == nombre)


def _texto_pdf(contenido: bytes) -> str:
    with pymupdf.open(stream=contenido, filetype="pdf") as p:
        return " ".join(pag.get_text() for pag in p)


def test_la_foto_lleva_datos_con_formato_y_lo_enlazado_con_total(fiado):
    s = _sec(fiado, "Clientes")
    f = documento.foto(fiado, s, {"id": "c1"}, "estado_de_cuenta", HOY)
    assert f["titulo"] == "Estado de cuenta" and f["registro"] == "Ana Ruiz"
    datos = dict(f["datos"])
    assert "300" in datos["Saldo"] and "500" in datos["Fiado"]  # 500 − (120 + 80)  # los calculados, ya en texto
    tablas = {t["titulo"]: t for t in f["tablas"]}
    assert len(tablas["Abonos"]["filas"]) == 2 and "200" in tablas["Abonos"]["total"][0]  # «ana ruiz» también es Ana Ruiz
    assert len(tablas["Créditos"]["filas"]) == 1


def test_el_pdf_se_abre_y_dice_lo_que_debe(fiado):
    f = documento.foto(fiado, _sec(fiado, "Clientes"), {"id": "c1"}, "estado_de_cuenta", HOY)
    t = _texto_pdf(documento.pdf(f, "EDC-0001", "#C0392B"))
    for x in ("Estado de cuenta", "EDC-0001", "Ana Ruiz", "Créditos", "Abonos", "Cemento", "No es una factura fiscal"):
        assert x in t, x


def test_logo_png_si_y_svg_se_ignora_sin_romper(fiado):
    from reportlab.graphics.shapes import Drawing, Rect
    from reportlab.graphics import renderPM  # noqa: F401  (solo para ver que hay PNG; si no, se arma a mano)
    png = io.BytesIO()
    try:
        d = Drawing(20, 20)
        d.add(Rect(0, 0, 20, 20))
        renderPM.drawToFile(d, png, fmt="PNG")
        url = "data:image/png;base64," + base64.b64encode(png.getvalue()).decode()
    except Exception:  # noqa: BLE001 — sin renderPM: un PNG mínimo de 1×1
        url = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
    f = documento.foto(fiado, _sec(fiado, "Clientes"), {"id": "c1"}, "recibo", HOY)
    con_logo = documento.pdf(f, "REC-0001", None, url)
    assert con_logo.startswith(b"%PDF") and len(con_logo) > len(documento.pdf(f, "REC-0001"))
    assert documento.pdf(f, "REC-0001", None, "data:image/svg+xml;base64,PHN2Zy8+").startswith(b"%PDF")


@pytest.mark.asyncio
async def test_la_herramienta_arma_la_foto_y_no_cambia_nada(fiado):
    r, modelo = await correr(fiado, "pásame el estado de cuenta de Ana", dice("", llamar("documento_de", seccion="Clientes", registro="Ana", tipo="estado_de_cuenta")),
                             dice("Listo, tu estado de cuenta de Ana Ruiz."))
    assert r["doc"] is fiado and r["cambios"] == [] and r["avisos"] == []
    (p,) = r["documentos"]
    assert p["tipo"] == "estado_de_cuenta" and p["registro"] == "c1" and "no lo digas ni lo inventes" in _resultados(modelo)[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("args, error", [
    ({"seccion": "Clientes", "registro": "Pedro", "tipo": "recibo"}, "no hay ningún registro"),
    ({"seccion": "Clientes", "registro": "Ana", "tipo": "factura"}, "usa recibo"),
])
async def test_errores_que_preguntan(fiado, args, error):
    r, modelo = await correr(fiado, "documento", dice("", llamar("documento_de", **args)), dice("¿Cuál?"))
    assert error in _resultados(modelo)[0] and "documentos" not in r


def _pedir(cli, monkeypatch, *args):
    _con_modelo(monkeypatch, dice("", llamar("documento_de", **args[0])), dice("Listo, tu documento."))
    r = cli.post(f"{URL}/chat", json={"texto": "pásame el recibo"}, headers=H).json()
    (ficha,) = r["descargas"]
    return ficha, cli.get(f"{URL}/descargas/{ficha['id']}", headers=H).content


def test_numero_consecutivo_reimpresion_identica_y_nuevo(cli, db, monkeypatch):
    _con_modelo(monkeypatch, dice("", llamar("crear_seccion", titulo="Pagos", campos=[{"nombre": "Cliente", "tipo": "texto"}, {"nombre": "Monto", "tipo": "dinero"}])),
                dice("Listo."), dice("", llamar("agregar_registro", seccion="Pagos", valores={"Cliente": "Ana", "Monto": 150})), dice("Listo."))
    cli.post(f"{URL}/chat", json={"texto": "crea pagos"}, headers=H)
    cli.post(f"{URL}/chat", json={"texto": "Ana pagó 150"}, headers=H)
    ficha, pdf1 = _pedir(cli, monkeypatch, {"seccion": "Pagos", "registro": "Ana", "tipo": "recibo"})
    assert ficha["nombre"].endswith(".pdf") and "REC-0001" in ficha["nombre"] and "REC-0001" in _texto_pdf(pdf1)
    # cambia el monto: la reimpresión sale con el mismo número y el monto de entonces
    pagos = next(l for l in db["crm_workspaces"].docs[0]["listas"] if l["nombre"] == "Pagos")
    pagos["registros"][0]["valores"]["monto"] = 999
    _, pdf2 = _pedir(cli, monkeypatch, {"seccion": "Pagos", "registro": "Ana", "tipo": "recibo"})
    assert "REC-0001" in _texto_pdf(pdf2) and "150" in _texto_pdf(pdf2) and "999" not in _texto_pdf(pdf2)
    # uno nuevo con los datos de hoy: otro número
    _, pdf3 = _pedir(cli, monkeypatch, {"seccion": "Pagos", "registro": "Ana", "tipo": "recibo", "nuevo": True})
    assert "REC-0002" in _texto_pdf(pdf3) and "999" in _texto_pdf(pdf3)
    assert len(db["crm_documentos"].docs) == 2


@pytest.mark.asyncio
async def test_decir_no_encontre_sin_buscar_se_corrige(fiado):
    # banco_documento: «dame la ficha de Luis en pdf» → «No encontré a Luis» sin llamar a nada (Luis sí estaba).
    r, _ = await correr(fiado, "dame la ficha de Luis en pdf", dice("No encontré a Luis en tus clientes. ¿Me confirmas el nombre?"),
                        dice("", llamar("documento_de", seccion="Clientes", registro="Luis", tipo="ficha")), dice("Listo, la ficha de Luis."))
    assert "no buscaste" in r["avisos"][0]["aviso"] and r["documentos"][0]["tipo"] == "ficha"


@pytest.mark.asyncio
async def test_no_encontre_despues_de_buscar_no_molesta(fiado):
    r, _ = await correr(fiado, "estado de cuenta de Pedro", dice("", llamar("documento_de", seccion="Clientes", registro="Pedro", tipo="estado_de_cuenta")),
                        dice("No encontré a Pedro en tus clientes. ¿Me confirmas el nombre?"))
    assert r["avisos"] == []


@pytest.mark.asyncio
async def test_estado_de_cuenta_sobre_un_credito_es_de_la_persona(fiado):
    # banco_documento: el modelo eligió el crédito de Ana (sección Créditos) y el PDF salía sin abonos ni saldo.
    r, _ = await correr(fiado, "pásame el estado de cuenta de Ana Ruiz",
                        dice("", llamar("documento_de", seccion="Créditos", registro="Ana Ruiz", tipo="estado_de_cuenta")), dice("Listo."))
    p = r["documentos"][0]
    assert p["registro"] == "c1" and {t["titulo"] for t in p["foto"]["tablas"]} == {"Créditos", "Abonos"}


def test_rango_iso_y_filtro_vacio_en_consultar():
    from assistant.packs.crm import registros
    from assistant.packs.crm.valores import parse_periodo
    assert parse_periodo("2026-10-28 a 2026-10-21", HOY) == {"desde": "2026-10-21", "hasta": "2026-10-28"}
    sec = {"id": "l", "titulo": "Miembros"}
    campos = [{"id": "nombre", "nombre": "Nombre", "tipo": "texto"}, {"id": "vence", "nombre": "Vence", "tipo": "fecha"}]
    regs = [{"id": "1", "valores": {"nombre": "Ana", "vence": "2026-10-15"}}, {"id": "2", "valores": {"nombre": "Luis", "vence": "2026-12-01"}}]
    t = registros.consultar(sec, campos, regs, {"periodo": {"cuando": "los próximos 7 días"}, "filtros": {"vence": ""}}, hoy=HOY)
    assert "1 de 2" in t and "Ana" in t
    t = registros.consultar(sec, campos, regs, {"filtros": {"vence": "2026-10-13 a 2026-10-20"}}, hoy=HOY)
    assert "1 de 2" in t

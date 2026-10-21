"""Documento de un registro (etapa 2, pieza 5): recibo, orden, cotización, estado de cuenta o ficha, en PDF con la marca del negocio.

El modelo elige el registro y el tipo (lista cerrada); el código arma todo. Dos pasos:
  - `foto`: los valores YA formateados del registro, sus registros enlazados (otras secciones cuyo campo enlazado lo nombra: los abonos de
    Ana) y sus totales. Es lo que se CONGELA: la ruta la guarda con su número (`crm_documentos`) y reimprimir sale idéntico.
  - `pdf`: dibuja una foto con el logo, el nombre y el color del negocio (ReportLab, licencia BSD).
No es una factura fiscal y el pie lo dice.
"""
from __future__ import annotations

import base64
import io
import math
import re
from datetime import date
from typing import Any

from assistant.packs.crm import calculos
from assistant.packs.crm import registros
from assistant.packs.crm import secciones_v as sv
from assistant.packs.crm.regional import region_de
from assistant.packs.crm.valores import campo_titulo, fecha_larga

# tipo → (título, prefijo del número)
TIPOS = {"recibo": ("Recibo", "REC"), "orden": ("Orden de servicio", "ORD"), "cotizacion": ("Cotización", "COT"),
         "estado_de_cuenta": ("Estado de cuenta", "EDC"), "ficha": ("Ficha", "FIC")}
MAX_RELACIONADOS = 40  # filas de la tabla de enlazados
MAX_COLUMNAS = 5
PIE = "Documento interno generado con Shifu. No es una factura fiscal."


def numero(tipo: str, folio: int) -> str:
    return f"{TIPOS[tipo][1]}-{folio:04d}"


def foto(doc: dict, sec: dict, registro: dict, tipo: str, hoy: date, pais: Any = None) -> dict:
    """Lo que lleva el documento, ya en texto (así reimprimirlo no cambia aunque cambien los datos o el formato)."""
    fmt = region_de(pais)
    calc = calculos.con_calculos({**doc, "ocultas": []}, hoy)
    r = next((x for x in sv.registros_de(calc, sec["id"]) if x["id"] == registro["id"]), registro)
    campos = sec["campos"]
    ct = campo_titulo(sec, campos)
    titulo_reg = registros.titulo_de(r, ct) if ct else ""
    datos = [[c["nombre"], registros.mostrar(c, (r.get("valores") or {}).get(c["id"]), fmt)] for c in campos
             if (r.get("valores") or {}).get(c["id"]) not in (None, "") and c is not ct]  # el nombre ya es el título
    tablas = []
    yo = calculos._norm(titulo_reg)
    for l in calc.get("listas") or []:
        rel = next((c for c in l["campos"] if c.get("relacion") == sec["id"]), None)
        if rel is None or not yo:
            continue
        mios = [x for x in l["registros"] if calculos._norm((x.get("valores") or {}).get(rel["id"])) == yo][:MAX_RELACIONADOS]
        if not mios:
            continue
        cols = [c for c in l["campos"] if c["id"] != rel["id"]][:MAX_COLUMNAS]
        filas = [[registros.mostrar(c, (x.get("valores") or {}).get(c["id"]), fmt) for c in cols] for x in mios]
        sumas = []
        for c in cols:
            if c.get("tipo") == "dinero":
                nums = [registros.numero_js((x.get("valores") or {}).get(c["id"])) for x in mios]
                total = sum(n for n in nums if not math.isnan(n))
                sumas.append(fmt.dinero(total))
            else:
                sumas.append("")
        tablas.append({"titulo": l["nombre"], "columnas": [c["nombre"] for c in cols], "filas": filas,
                       **({"total": sumas} if any(sumas) else {})})
    negocio = (doc.get("brief") or {}).get("nombre") or "Mi negocio"
    return {"tipo": tipo, "titulo": TIPOS[tipo][0], "negocio": negocio, "fecha": fecha_larga(hoy.isoformat()), "seccion": sec["titulo"],
            "registro": titulo_reg, "datos": datos, "tablas": tablas}


def _logo(data_url: str | None) -> tuple[io.BytesIO, int, int] | None:
    """El logo (bytes, ancho, alto), o None (SVG u otro formato que no se puede dibujar: el documento sale sin logo)."""
    m = re.match(r"data:image/(png|jpe?g|gif);base64,(.+)", data_url or "", re.S)
    if not m:
        return None
    from reportlab.lib.utils import ImageReader

    try:
        datos = base64.b64decode(m.group(2))
        w, h = ImageReader(io.BytesIO(datos)).getSize()
        return io.BytesIO(datos), w, h
    except Exception:  # noqa: BLE001 — una imagen rota no impide el documento
        return None


def pdf(f: dict, folio_txt: str, color: str | None = None, logo: str | None = None) -> bytes:
    """Dibuja la foto en una hoja carta: encabezado con logo, negocio y número; datos; tablas de enlazados con su total; pie."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    acento = colors.HexColor(color) if color and re.fullmatch(r"#[0-9a-fA-F]{6}", color) else colors.HexColor("#1F6F5B")
    st = getSampleStyleSheet()
    chico = ParagraphStyle("chico", parent=st["Normal"], fontSize=9, textColor=colors.HexColor("#555555"))
    normal = ParagraphStyle("normal", parent=st["Normal"], fontSize=10, leading=13)
    titulo = ParagraphStyle("titulo", parent=st["Title"], fontSize=18, textColor=acento, alignment=0, spaceAfter=2)
    esc = lambda t: str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")  # noqa: E731

    salida = io.BytesIO()
    hoja = SimpleDocTemplate(salida, pagesize=letter, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                             title=f"{f['titulo']} {folio_txt}", author=f["negocio"])
    ancho = letter[0] - 36 * mm
    partes: list = []
    img = _logo(logo)
    cabeza = [Paragraph(f"<b>{esc(f['negocio'])}</b>", ParagraphStyle("neg", parent=normal, fontSize=13)),
              Paragraph(f"{esc(f['titulo'])} <b>{esc(folio_txt)}</b><br/>{esc(f['fecha'])}", ParagraphStyle("num", parent=normal, alignment=2))]
    if img is not None:
        archivo, w, h = img
        alto = 16 * mm
        cabeza.insert(0, Image(archivo, width=alto * w / max(h, 1), height=alto))
        anchos = [ancho * 0.18, ancho * 0.47, ancho * 0.35]
    else:
        anchos = [ancho * 0.6, ancho * 0.4]
    t = Table([cabeza], colWidths=anchos)
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, 0), (-1, 0), 1.2, acento),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    partes += [t, Spacer(1, 6 * mm), Paragraph(esc(f["registro"] or f["titulo"]), titulo),
               Paragraph(esc(f["seccion"]), chico), Spacer(1, 4 * mm)]
    if f["datos"]:
        filas = [[Paragraph(f"<b>{esc(k)}</b>", normal), Paragraph(esc(v), normal)] for k, v in f["datos"]]
        td = Table(filas, colWidths=[ancho * 0.32, ancho * 0.68])
        td.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#DDDDDD")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        partes += [td, Spacer(1, 6 * mm)]
    for tb in f["tablas"]:
        partes.append(Paragraph(f"<b>{esc(tb['titulo'])}</b>", normal))
        filas = [[Paragraph(f"<b>{esc(c)}</b>", ParagraphStyle("enc", parent=normal, textColor=colors.white)) for c in tb["columnas"]]]
        filas += [[Paragraph(esc(v), normal) for v in fila] for fila in tb["filas"]]
        if tb.get("total"):
            filas.append([Paragraph(f"<b>{esc(('Total ' + v).strip() if i == 0 else v)}</b>", normal) for i, v in enumerate(tb["total"])])
        tt = Table(filas, colWidths=[ancho / len(tb["columnas"])] * len(tb["columnas"]), repeatRows=1)
        estilo = [("BACKGROUND", (0, 0), (-1, 0), acento), ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor("#DDDDDD"))]
        if tb.get("total"):
            estilo.append(("LINEABOVE", (0, -1), (-1, -1), 1, acento))
        tt.setStyle(TableStyle(estilo))
        partes += [Spacer(1, 2 * mm), tt, Spacer(1, 6 * mm)]
    partes.append(Paragraph(esc(PIE), chico))
    hoja.build(partes)
    return salida.getvalue()

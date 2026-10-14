"""La IA diseña el CRM de cada negocio a partir del cuestionario.

Dos momentos:
1. `preguntas_de_seguimiento`: después de las preguntas generales, la IA escribe de 3 a 4 preguntas propias del tipo de negocio
   (una panadería no se pregunta lo mismo que una empresa de tecnología). Si la IA no está disponible, se usan preguntas base por rubro.
2. `disenar`: con todas las respuestas, la IA propone las etapas, los campos de los contactos, las secciones propias y los nombres.
   Lo propuesto se aplica con las mismas funciones y límites del CRM (`estructura`, `operaciones`): lo que no sirva se descarta
   sin romper nada, y si la IA falla el CRM queda con la plantilla base de `generador`.

La IA nunca inventa datos de clientes: solo propone estructura (qué columnas, secciones y etapas tiene ese negocio).
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime
from typing import Any

from app.crm import automatizaciones
from app.crm import estructura as est
from app.crm import operaciones as op
from app.crm.secciones import IDS_SECCION, titulo_seccion

logger = logging.getLogger(__name__)

MAX_PREGUNTAS = 4
MAX_OPCIONES = 6
MAX_SECCIONES_INICIALES = 4
MAX_CAMPOS_CONTACTO_INICIALES = 4
MAX_CAMPOS_POR_SECCION = 7

_cache: dict[str, Any] = {}
_dia = ["", 0]  # [fecha, cantidad]: tope diario de preguntas generadas (la ruta no exige sesión, así que se limita el gasto)

# ───────── Etiquetas de las respuestas del cuestionario (para que la IA lea palabras, no códigos) ─────────

ETIQUETAS: dict[str, dict[str, str]] = {
    "rubro": {"servicios": "Servicios profesionales", "agencia": "Agencia o estudio creativo", "comercio": "Comercio y retail", "salud": "Salud y bienestar",
              "educacion": "Educación", "tecnologia": "Tecnología", "inmobiliaria": "Inmobiliaria y construcción", "otro": "Otro"},
    "tiempo": {"idea": "Solo es una idea", "nuevo": "Menos de 1 año", "medio": "1 a 3 años", "veterano": "Más de 3 años"},
    "canales": {"whatsapp": "WhatsApp", "correo": "Correo", "llamadas": "Llamadas", "redes": "Instagram o Facebook", "presencial": "En persona", "web": "Formulario web"},
    "cartera": {"k1": "Menos de 50", "k2": "50 a 200", "k3": "200 a 1,000", "k4": "Más de 1,000"},
    "ciclo": {"cotizacion": "Servicios con cotización", "rapida": "Ventas rápidas", "recurrente": "Clientes recurrentes", "mezcla": "Una mezcla de todo"},
    "problemas": {"olvido": "Se le olvida dar seguimiento", "info": "No encuentra los datos de un cliente", "equipo": "Cada quien lleva sus propios datos", "mensajes": "Pierde mensajes entre chats"},
    "equipo": {"solo": "Solo la persona", "chico": "2 a 5 personas", "medio": "6 a 20 personas", "grande": "Más de 20 personas"},
    "herramientas": {"excel": "Excel o Sheets", "crm": "Otro CRM", "cuaderno": "Cuaderno o notas", "nada": "Nada todavía"},
    "objetivos": {"seguimientos": "No perder ningún seguimiento", "contactos": "Ordenar sus contactos", "ia": "Que la IA responda y agende", "reportes": "Ver su pipeline y reportes",
                  "cotizaciones": "Enviar cotizaciones más rápido", "equipo": "Trabajar en equipo", "integraciones": "Conectar WhatsApp y correo"},
}

# Automatizaciones que existen en el CRM (por ahora son interruptores); la IA elige cuáles dejar encendidas.
AUTOMATIZACIONES = {i: automatizaciones.CATALOGO[i][1] for i in automatizaciones.DISPONIBLES}  # solo las que funcionan hoy


def _etq(grupo: str, v: Any) -> str:
    return ETIQUETAS.get(grupo, {}).get(str(v), str(v))


def resumen_del_brief(brief: dict) -> str:
    """Las respuestas del cuestionario como texto para la IA."""
    def lista(grupo: str) -> str:
        return ", ".join(_etq(grupo, x) for x in (brief.get(grupo) or [])) or "—"

    ubic = brief.get("ubicacion") or {}
    lineas = [
        f"Negocio: {brief.get('nombre') or '—'}",
        f"País/ciudad: {ubic.get('pais') or '—'} / {ubic.get('ciudad') or '—'}",
        f"Tipo de negocio: {_etq('rubro', brief.get('rubro')) if brief.get('rubro') else '—'}",
        f"Qué vende o qué servicio da (con sus palabras): {brief.get('que_vendes') or '—'}",
        f"Tiempo: {_etq('tiempo', brief.get('tiempo')) if brief.get('tiempo') else '—'}",
        f"Canales por donde le escriben: {lista('canales')}",
        f"Clientes que maneja: {_etq('cartera', brief.get('cartera')) if brief.get('cartera') else '—'}",
        f"Proceso de venta: {_etq('ciclo', brief.get('ciclo')) if brief.get('ciclo') else '—'}",
        f"Problemas con sus clientes: {lista('problemas')}",
        f"Equipo: {_etq('equipo', brief.get('equipo')) if brief.get('equipo') else '—'}",
        f"Qué usa hoy: {lista('herramientas')}",
        f"Qué quiere lograr: {lista('objetivos')}",
        f"Lo que más le complica (con sus palabras): {brief.get('dolor') or '—'}",
    ]
    for s in brief.get("seguimiento") or []:
        lineas.append(f"{s.get('pregunta')}: {s.get('respuesta')}")
    return "\n".join(lineas)


# ───────── Llamadas al modelo ─────────

def _modelo():
    if "m" not in _cache:
        from langchain_openai import ChatOpenAI  # import tardío: el resto del módulo no depende de langchain

        from app.crm import agente

        _cache["m"] = ChatOpenAI(model=agente.MODELO, temperature=0.3, max_tokens=1600, timeout=40, max_retries=0, api_key=agente.clave_openai())
    return _cache["m"]


def precalentar() -> None:
    """Importa la librería del modelo con anticipación (en frío tarda decenas de segundos y la primera persona no debería esperarla)."""
    try:
        import langchain_core.messages  # noqa: F401
        import langchain_openai  # noqa: F401
    except Exception:  # sin las dependencias completas el CRM funciona con reglas
        logger.info("No se pudo precalentar langchain; el chat usará reglas.")


def _json(texto: str) -> dict:
    t = re.sub(r"^```(?:json)?|```$", "", (texto or "").strip(), flags=re.M).strip()
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j <= i:
        raise ValueError("la IA no devolvió JSON")
    datos = json.loads(t[i:j + 1])
    if not isinstance(datos, dict):
        raise ValueError("la IA no devolvió un objeto")
    return datos


async def _preguntar(sistema: str, usuario: str, modelo: Any = None) -> dict:
    from langchain_core.messages import HumanMessage, SystemMessage

    ia = await (modelo or _modelo()).ainvoke([SystemMessage(content=sistema), HumanMessage(content=usuario)])
    return _json(ia.content if isinstance(ia.content, str) else "")


# ───────── 1 · Preguntas de seguimiento ─────────

def _q(titulo: str, tipo: str, opciones: list[tuple[str, str]] | None = None, emoji: str = "🧩", sub: str = "") -> dict:
    return {"titulo": titulo, "tipo": tipo, "emoji": emoji, "sub": sub, "opciones": [{"t": t, "e": e} for e, t in (opciones or [])]}


# Preguntas que se hacen si la IA no está disponible: pocas, pero propias del tipo de negocio.
PREGUNTAS_BASE: dict[str, list[dict]] = {
    "comercio": [
        _q("¿Cómo les vendes a tus clientes?", "varias", [("🏪", "En el local o mostrador"), ("📝", "Por encargo o pedido"), ("🛵", "Con entrega a domicilio"), ("🌐", "Por internet o redes")], "🛍️"),
        _q("¿Cómo te pagan?", "una", [("💵", "Pagan todo al momento"), ("🪙", "Dejan anticipo y pagan después"), ("📒", "A crédito o fiado")], "💵"),
    ],
    "servicios": [
        _q("¿Cómo cobras tu trabajo?", "una", [("📦", "Por proyecto"), ("⏱️", "Por hora"), ("🔄", "Mensualidad fija"), ("1️⃣", "Pago único")], "💼"),
        _q("¿Qué necesitas dar a cada cliente?", "varias", [("🧾", "Cotización"), ("📄", "Contrato"), ("📅", "Citas o reuniones"), ("📊", "Informes de avance")], "📄"),
    ],
    "agencia": [
        _q("¿Cómo cobras tus trabajos?", "una", [("📦", "Por proyecto"), ("🔄", "Mensualidad (retainer)"), ("⏱️", "Por hora")], "🎨"),
        _q("¿Qué suele necesitar cada proyecto?", "varias", [("📝", "Brief del cliente"), ("🖼️", "Entregas y revisiones"), ("📅", "Fechas de entrega"), ("🧾", "Cotización")], "🖼️"),
    ],
    "salud": [
        _q("¿Cómo atiendes a tus pacientes?", "varias", [("📅", "Con citas"), ("🚶", "Sin cita, por turno"), ("🏠", "A domicilio"), ("💻", "En línea")], "🩺"),
        _q("¿Qué necesitas recordar de cada paciente?", "varias", [("🎂", "Fecha de nacimiento"), ("📋", "Motivo de consulta"), ("🔁", "Próxima cita"), ("💊", "Tratamiento")], "📋"),
    ],
    "educacion": [
        _q("¿Qué ofreces?", "varias", [("📚", "Cursos o talleres"), ("🧑‍🏫", "Clases particulares"), ("🏫", "Programas largos"), ("🎥", "Contenido en línea")], "🎓"),
        _q("¿Cómo cobras?", "una", [("🔄", "Mensualidad"), ("📦", "Por curso completo"), ("1️⃣", "Por clase")], "💵"),
    ],
    "tecnologia": [
        _q("¿Cómo vendes tu tecnología?", "una", [("📦", "Por proyecto a la medida"), ("🔄", "Suscripción o licencia"), ("⏱️", "Por horas de desarrollo"), ("🛠️", "Soporte y mantenimiento")], "💻"),
        _q("¿Qué tienes que dar seguimiento en cada cliente?", "varias", [("🎬", "Demos"), ("🧾", "Cotizaciones"), ("📄", "Contratos"), ("🐞", "Tickets de soporte")], "🧾"),
    ],
    "inmobiliaria": [
        _q("¿Qué manejas?", "varias", [("🏠", "Venta de propiedades"), ("🔑", "Alquileres"), ("🏗️", "Proyectos de construcción")], "🏠"),
        _q("¿Qué necesitas dar seguimiento?", "varias", [("👀", "Visitas a propiedades"), ("🧾", "Ofertas y cotizaciones"), ("📄", "Contratos"), ("🏦", "Créditos y trámites")], "👀"),
    ],
    "otro": [
        _q("¿Cómo les cobras a tus clientes?", "una", [("💵", "Pagan al momento"), ("🪙", "Anticipo y saldo"), ("🔄", "Mensualidad"), ("📦", "Por proyecto")], "💵"),
        _q("¿Qué es lo que más debes dar seguimiento?", "varias", [("📅", "Citas o reuniones"), ("🧾", "Cotizaciones o pedidos"), ("📦", "Entregas"), ("💬", "Mensajes y consultas")], "📌"),
    ],
}

_SISTEMA_PREGUNTAS = """Eres el diseñador de Shifu, una plataforma que crea el CRM de cada negocio con IA. Una persona acaba de contarte de su negocio.
Escribe de 3 a 4 preguntas de seguimiento para conocer a ESE negocio y poder armar un CRM a su medida.
Mezcla así: 2 preguntas sobre CÓMO OPERA ese negocio en concreto (por encargo, a domicilio, por suscripción, con citas, por proyecto, con anticipo, con temporadas…) y 1 o 2 sobre QUÉ QUIERE LLEVAR REGISTRADO (qué datos guardar de cada cliente o qué otra lista necesita, como proveedores, inventario, contratos). Con eso se decidirán las etapas, los datos de cada cliente y las secciones extra.

Reglas:
- Español simple, de “tú”, sin jerga técnica. No uses las palabras “CRM”, “etapas” ni “campos”. Cada pregunta de máximo 90 caracteres.
- No repitas lo que ya respondió (tipo de negocio, canales, tamaño del equipo, herramientas, objetivos, lo que le complica).
- Pregunta cosas propias de su tipo de negocio. Ejemplos: panadería → ¿vendes por encargo?, ¿haces entregas a domicilio?, ¿atiendes pedidos para fiestas?; empresa de tecnología → ¿vendes por proyecto o por suscripción?, ¿das soporte?, ¿cotizas por horas?; clínica → ¿trabajas con citas?, ¿qué necesitas recordar de cada paciente?
- Usa lo que escribió con sus palabras (qué vende, lo que le complica) para ser específico.
- Tipos: "una" (elige una opción), "varias" (elige varias) o "texto" (respuesta abierta; úsala como máximo una vez y solo si es importante).
- Para "una" y "varias" da de 3 a 5 opciones concretas y propias de ESE negocio, cortas (máximo 40 caracteres), cada una con un emoji. Nada de opciones genéricas como “Otro” o “Todas”.

Responde SOLO con JSON, sin texto antes ni después:
{"preguntas":[{"titulo":"...","tipo":"una|varias|texto","emoji":"🧩","opciones":[{"t":"...","e":"🙂"}]}]}"""


def sanear_preguntas(crudo: Any) -> list[dict]:
    """Deja solo preguntas válidas, con ids y opciones limpias (lo que dice la IA nunca llega a la pantalla sin pasar por aquí)."""
    salida: list[dict] = []
    for p in (crudo if isinstance(crudo, list) else []):
        if not isinstance(p, dict) or len(salida) >= MAX_PREGUNTAS:
            continue
        titulo = " ".join(str(p.get("titulo") or "").split())[:120]
        tipo = str(p.get("tipo") or "").lower()
        if len(titulo) < 8 or tipo not in ("una", "varias", "texto"):
            continue
        emoji = str(p.get("emoji") or "")[:4] or "🧩"
        n = len(salida) + 1
        if tipo == "texto":
            salida.append({"id": f"s{n}", "tipo": "parrafo", "titulo": titulo, "emoji": emoji, "sub": "Opcional. Con tus palabras.", "opciones": []})
            continue
        opciones: list[dict] = []
        for o in (p.get("opciones") if isinstance(p.get("opciones"), list) else [])[:MAX_OPCIONES]:
            t = " ".join(str((o or {}).get("t") or "").split())[:60] if isinstance(o, dict) else ""
            if t and not any(x["t"].lower() == t.lower() for x in opciones):
                opciones.append({"v": f"o{len(opciones) + 1}", "e": (str(o.get("e") or "")[:4] or "🔹"), "t": t})
        if len(opciones) >= 2:
            salida.append({"id": f"s{n}", "tipo": tipo, "titulo": titulo, "emoji": emoji,
                           "sub": "Elige todas las que apliquen." if tipo == "varias" else "Elige la que más se parezca.", "opciones": opciones})
    return salida


def _preguntas_base(brief: dict) -> list[dict]:
    return sanear_preguntas(PREGUNTAS_BASE.get(brief.get("rubro") or "otro") or PREGUNTAS_BASE["otro"])


def _bajo_el_tope_diario() -> bool:
    hoy = time.strftime("%Y-%m-%d")
    if _dia[0] != hoy:
        _dia[0], _dia[1] = hoy, 0
    if _dia[1] >= int(os.getenv("CRM_SEGUIMIENTO_DIARIO", "3000")):
        return False
    _dia[1] += 1
    return True


async def preguntas_de_seguimiento(brief: dict, modelo: Any = None) -> tuple[list[dict], str]:
    """(preguntas, modo): "ia" si las escribió el modelo o "base" si se usaron las del rubro."""
    from app.crm import agente

    if (modelo is not None or agente.activo()) and _bajo_el_tope_diario():
        try:
            datos = await _preguntar(_SISTEMA_PREGUNTAS, f"Lo que contó la persona:\n{resumen_del_brief(brief)}", modelo)
            preguntas = sanear_preguntas(datos.get("preguntas"))
            if preguntas:
                return preguntas, "ia"
        except Exception as e:  # sin saldo, tiempo agotado, JSON malo…: se siguen con las del rubro
            agente.marcar_fallo(e)
            logger.warning("No se pudieron generar las preguntas de seguimiento con IA: %s", type(e).__name__)
    return _preguntas_base(brief), "base"


# ───────── 2 · Diseño del CRM ─────────

_SISTEMA_DISENO = """Eres el diseñador de Shifu, una plataforma que crea el CRM de cada negocio con IA. Con las respuestas de la persona, propón la estructura de SU CRM, distinta a la de cualquier otro tipo de negocio. Una panadería, una empresa de tecnología y una clínica deben recibir CRMs muy diferentes.

Cómo funciona el CRM (respeta estos límites):
- Contactos: la lista de clientes, cada uno en una ETAPA. Tú defines las etapas (de 3 a 7, máximo 24 caracteres cada una, en el orden real del proceso de ese negocio) y los CAMPOS EXTRA que se guardan de cada cliente (máximo 4; tipos: texto, numero, fecha). Ya existen nombre, detalle (teléfono o correo), canal y responsable: NO los repitas.
- Secciones propias: listas extra con sus campos, para lo que ese negocio necesita llevar (pedidos, proyectos, proveedores, productos, inventario, citas, contratos, tickets…). Entre 0 y 4 secciones, máximo 7 campos cada una, tipos texto, numero o fecha. Cada sección debe justificarse por lo que contó la persona: no crees secciones de relleno.
- Secciones integradas (puedes cambiarles el nombre para que suenen a ese negocio): "contactos" (lista de clientes), "desarrollo" (tablero de tareas Por hacer / En curso / Hecho: ahí se llevan pedidos, proyectos o citas), "cobros" (todavía no activa), "actividad" (historial) y "rrhh" (el equipo). Nombres de máximo 28 caracteres.
- Automatizaciones que funcionan hoy: "recordatorios" (crea una tarea cuando un contacto lleva 3 días sin avanzar de etapa), "reparto" (asigna los contactos nuevos por turnos entre el equipo; solo sirve si hay más de una persona) y "resumen" (resumen semanal en Actividad). Enciende solo las que sirvan según lo que contó. Las demás todavía no existen: no las menciones.

Reglas:
- Usa el vocabulario del negocio (una panadería habla de pedidos y encargos; una empresa de tecnología, de proyectos, demos y contratos; una clínica, de pacientes y citas).
- No inventes clientes, cifras ni datos: solo estructura.
- Español simple. Nada de jerga técnica.
- "resumen": 2 frases cortas, hablándole a la persona de “tú” (por ejemplo: “Armé tu CRM para vender pasteles por encargo: cada pedido avanza desde que lo recibes hasta la entrega. Agregué proveedores e inventario para que no te falte nada.”), con el vocabulario del negocio, sin listas. Máximo 300 caracteres.

Responde SOLO con JSON, sin texto antes ni después:
{"resumen":"...","etapas":["..."],"campos_contacto":[{"nombre":"...","tipo":"texto"}],
 "secciones":[{"nombre":"...","campos":[{"nombre":"...","tipo":"texto|numero|fecha"}]}],
 "nombres":{"contactos":"...","desarrollo":"...","rrhh":"..."},"automatizaciones":["recordatorios"]}"""


def _limpia(texto: Any, largo: int) -> str:
    return " ".join(str(texto or "").split())[:largo]


def aplicar_propuesta(doc: dict, propuesta: dict, ahora: datetime | None = None) -> tuple[dict, dict]:
    """Aplica lo que propuso la IA con las operaciones normales del CRM. Cada pieza inválida se descarta sola.
    Devuelve (doc, lo que sí se aplicó)."""
    ahora = ahora or op.ahora_utc()
    aplicado: dict[str, Any] = {"etapas": [], "campos_contacto": [], "secciones": [], "nombres": {}, "automatizaciones": []}
    if not isinstance(propuesta, dict):
        return doc, aplicado

    etapas = [e for e in (propuesta.get("etapas") if isinstance(propuesta.get("etapas"), list) else []) if isinstance(e, str)]
    if len(etapas) >= est.MIN_ETAPAS:
        try:
            doc = est.etapas_definir(doc, etapas[:est.MAX_ETAPAS], ahora)
            aplicado["etapas"] = list(doc["etapas"])
        except op.ErrorCrm:
            pass

    for c in (propuesta.get("campos_contacto") if isinstance(propuesta.get("campos_contacto"), list) else [])[:MAX_CAMPOS_CONTACTO_INICIALES]:
        if not isinstance(c, dict):
            continue
        try:
            doc = est.campo_agregar(doc, "contactos", c.get("nombre"), c.get("tipo") or "texto", ahora)
            aplicado["campos_contacto"].append(doc["campos_contacto"][-1]["nombre"])
        except op.ErrorCrm:
            continue

    for s in (propuesta.get("secciones") if isinstance(propuesta.get("secciones"), list) else [])[:MAX_SECCIONES_INICIALES]:
        if not isinstance(s, dict):
            continue
        campos = [c for c in (s.get("campos") if isinstance(s.get("campos"), list) else []) if isinstance(c, dict)][:MAX_CAMPOS_POR_SECCION]
        try:
            doc = est.lista_crear(doc, s.get("nombre"), campos or None, ahora)
            aplicado["secciones"].append(doc["listas"][-1]["nombre"])
        except op.ErrorCrm:
            continue

    nombres = propuesta.get("nombres") if isinstance(propuesta.get("nombres"), dict) else {}
    for sid, nombre in nombres.items():
        n = _limpia(nombre, est.LARGO_NOMBRE)
        if sid in IDS_SECCION and sid not in ("importar", "automatizaciones") and len(n) >= 2:
            n = n[:1].upper() + n[1:]
            rubro = (doc.get("brief") or {}).get("rubro")
            ocupados = [titulo_seccion(rubro, i, doc["secciones"]) for i in IDS_SECCION if i != sid] + [l["nombre"] for l in doc["listas"]]
            if any(n.lower() == o.lower() for o in ocupados):
                continue
            try:
                doc = op.seccion_renombrar(doc, sid, n, ahora)
                aplicado["nombres"][sid] = n
            except op.ErrorCrm:
                continue

    encendidas = {a for a in (propuesta.get("automatizaciones") if isinstance(propuesta.get("automatizaciones"), list) else []) if a in AUTOMATIZACIONES}
    if encendidas or isinstance(propuesta.get("automatizaciones"), list):
        doc = op._copia(doc)
        for a in doc["automatizaciones"]:
            a["on"] = a["id"] in encendidas
        aplicado["automatizaciones"] = sorted(encendidas)

    resumen = _limpia(propuesta.get("resumen"), 320)
    if resumen:
        doc = op._copia(doc)
        doc["resumen_ia"] = resumen
    return doc, aplicado


async def disenar(doc: dict, brief: dict, modelo: Any = None, ahora: datetime | None = None) -> dict:
    """Devuelve el CRM con la estructura que diseñó la IA. Si la IA no está disponible o falla, devuelve el `doc` tal cual (plantilla base)."""
    from app.crm import agente

    if modelo is None and not agente.activo():
        return doc
    try:
        propuesta = await _preguntar(_SISTEMA_DISENO, f"Respuestas de la persona:\n{resumen_del_brief(brief)}", modelo)
    except Exception as e:
        agente.marcar_fallo(e)
        logger.warning("La IA no pudo diseñar el CRM; se usa la plantilla base: %s", type(e).__name__)
        return doc
    nuevo, aplicado = aplicar_propuesta(doc, propuesta, ahora)
    logger.info("CRM diseñado por la IA: %s", {k: len(v) for k, v in aplicado.items()})
    return nuevo

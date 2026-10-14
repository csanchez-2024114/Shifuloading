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
MAX_SECCIONES_INICIALES = 6
MAX_CAMPOS_CONTACTO_INICIALES = 4
MAX_CAMPOS_POR_SECCION = 7
MAX_RECOMENDACIONES = 5

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

        _cache["m"] = ChatOpenAI(model=agente.MODELO, temperature=0.4, max_tokens=3200, timeout=45, max_retries=0, api_key=agente.clave_openai())
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

_SISTEMA_DISENO = """Eres el diseñador de Shifu, una plataforma que crea el CRM de cada negocio con IA. Tu trabajo es armar el CRM de ESTA persona, no uno genérico.
Si dos negocios del mismo tipo (por ejemplo dos de “comercio”) te cuentan cosas distintas, sus CRM deben verse MUY distintos: una taquería y una tienda de tecnología no pueden compartir casi nada. Si la persona leyera su CRM y pensara “esto se lo darían a cualquiera”, fallaste.

Cómo piensas (escríbelo en "analisis" ANTES de diseñar):
- Repasa UNA POR UNA las respuestas, desde la primera, también las de abajo en la lista (país, tiempo, tamaño del equipo, qué usa hoy, canales). Para cada una que cambie algo, escribe qué decides. Ejemplos de cómo se traduce una respuesta (con negocios inventados, no los copies): “da cortes y tintes con citas por WhatsApp” → sección de servicios con precios y una agenda de citas; “trabajan 2 a 5 personas” → sección de trabajadores con puesto y turno; “no sé cuánto gasto al día” → sección de gastos del día; “alquila equipo para eventos” → catálogo con disponibilidad y reservas por fecha; “lo lleva en un cuaderno” → todo simple y desde cero; “el negocio es solo una idea” → menos secciones y consejos para validar y conseguir los primeros clientes; “está en Guatemala” → quetzales y WhatsApp como canal natural.
- Lo que escribió con sus palabras (qué vende, lo que le complica, sus respuestas de seguimiento) pesa más que las casillas marcadas.
- Casi todo negocio necesita estas piezas; arma las que apliquen y llámalas como las llamaría esa persona: (1) el CATÁLOGO de lo que vende, con precio (“Menú” si vende comida, “Catálogo” o “Productos” si vende objetos, “Servicios y precios” si da servicios, “Planes” si cobra suscripciones); (2) dónde apunta sus PEDIDOS, CITAS o TRABAJOS, con su estado y por qué canal llegaron; (3) sus FINANZAS si las mencionó (gastos del día, ingresos, cobros pendientes, garantías por vencer…); (4) su PERSONAL, si tiene equipo (nombre, puesto, turno, teléfono); (5) lo PROPIO de su giro que ningún otro negocio tendría (garantías, recetas, rutas de entrega, permisos, rentas, cursos, contratos…). Cada una con campos y nombres de ese negocio, no de uno genérico.
- Piensa en lo que ESE negocio mira cada día para decidir, no en lo que tiene cualquier negocio.

Cómo funciona el CRM (respeta estos límites):
- Contactos: la lista de clientes, cada uno en una ETAPA. Tú defines las etapas (de 3 a 7, máximo 24 caracteres cada una, en el orden real de ese negocio) y los CAMPOS EXTRA que se guardan de cada cliente (máximo 4; tipos: texto, numero, fecha). Ya existen nombre, detalle (teléfono o correo), canal y responsable: NO los repitas.
- Secciones propias: listas extra con sus campos. SIEMPRE entre 4 y 6 (si es una idea o trabaja solo, 4; con equipo y más trayectoria, hasta 6), de 3 a 7 campos cada una, tipos texto, numero o fecha (usa numero para precios y montos, fecha para entregas, vencimientos o turnos). CADA una debe nacer de algo que la persona dijo: escribe en "por_que" la respuesta que la motivó. Prohibido rellenar con secciones genéricas (“Proveedores”, “Inventario”, “Clientes VIP”, “Ventas”) si nada de lo que contó las justifica; si las usas, personalízalas con el vocabulario y los campos de ese negocio.
- Si el negocio maneja pedidos como lista (cliente, qué pidió, total, estado, por qué canal llegó), créalos como sección propia "Pedidos" y renombra el tablero integrado a otra cosa (ver abajo) para que no choquen.
- Secciones integradas (puedes cambiarles el nombre para que suenen a ese negocio): "contactos" (la lista de clientes), "desarrollo" (tablero de tareas Por hacer / En curso / Hecho; úsalo con un nombre como “Pendientes del día” o “Tareas”, o “Proyectos” si trabajan por proyectos), "cobros" (todavía no funciona: la ocultará el sistema; si el negocio necesita llevar gastos, ventas del día o cobros, créalo como sección propia), "actividad" (historial) y "rrhh" (la lista de quienes venden y a quienes se les asignan clientes). Si necesita datos de su personal (puesto, turno, teléfono), crea una sección propia de trabajadores. Nombres de máximo 28 caracteres.
- Automatizaciones que funcionan hoy: "recordatorios" (crea una tarea cuando un contacto lleva 3 días sin avanzar de etapa), "reparto" (asigna los contactos nuevos por turnos entre el equipo; solo sirve si hay más de una persona) y "resumen" (resumen semanal en Actividad). Enciende solo las que sirvan según lo que contó. Las demás todavía no existen: no las menciones.

Reglas:
- Usa el vocabulario del negocio y de su país, no jerga de CRM.
- No inventes clientes, cifras ni datos: solo estructura (columnas, secciones y etapas) y las recomendaciones.
- "recomendaciones": de 3 a 5 consejos de NEGOCIO (cómo vender más, gastar menos o cuidar a sus clientes), NO de cómo usar el CRM: prohibido “registra tus pedidos”, “usa los recordatorios” o “guarda tus datos”. Deben salir de lo que contó: su tipo de negocio, su país, cuánto lleva y cuántos son (alguien que apenas empieza necesita validar y conseguir sus primeros clientes; alguien con equipo grande necesita orden y metas), y al menos uno debe atacar lo que dijo que le complica. Máximo 150 caracteres cada uno, accionables esta semana. Ejemplos para una peluquería con citas por WhatsApp (solo como guía de tono; escribe los tuyos para ESTE negocio y no los repitas): “Ofrece un paquete corte + tinte a precio cerrado para subir lo que gasta cada clienta.” y “Escríbele a cada clienta la víspera de su cita para evitar que falte.”
- "resumen": 2 frases cortas, hablándole a la persona de “tú” (por ejemplo: “Armé tu CRM para tu peluquería: cada cita avanza desde que la agendas hasta que la clienta vuelve. Agregué servicios con precios y a tu equipo con sus turnos.”), con el vocabulario del negocio y mencionando lo más propio que armaste, sin listas. Máximo 300 caracteres.

Responde SOLO con JSON, sin texto antes ni después:
{"analisis":[{"respuesta":"...","decision":"..."}],"resumen":"...","etapas":["..."],"campos_contacto":[{"nombre":"...","tipo":"texto"}],
 "secciones":[{"nombre":"...","por_que":"...","campos":[{"nombre":"...","tipo":"texto|numero|fecha"}]}],
 "nombres":{"contactos":"...","desarrollo":"...","rrhh":"..."},"automatizaciones":["recordatorios"],"recomendaciones":["..."]}"""


def _limpia(texto: Any, largo: int) -> str:
    return " ".join(str(texto or "").split())[:largo]


def aplicar_propuesta(doc: dict, propuesta: dict, ahora: datetime | None = None) -> tuple[dict, dict]:
    """Aplica lo que propuso la IA con las operaciones normales del CRM. Cada pieza inválida se descarta sola.
    Devuelve (doc, lo que sí se aplicó)."""
    ahora = ahora or op.ahora_utc()
    aplicado: dict[str, Any] = {"etapas": [], "campos_contacto": [], "secciones": [], "nombres": {}, "automatizaciones": [], "recomendaciones": 0, "ocultas": []}
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

    # Los nombres de las secciones integradas van PRIMERO: así una sección propia puede llamarse "Pedidos" si el tablero ya se renombró.
    nombres = propuesta.get("nombres") if isinstance(propuesta.get("nombres"), dict) else {}
    for sid, nombre in nombres.items():
        n = _limpia(nombre, est.LARGO_NOMBRE)
        if sid in IDS_SECCION and sid not in ("importar", "automatizaciones") and len(n) >= 2:
            n = n[:1].upper() + n[1:]
            rubro = (doc.get("brief") or {}).get("rubro")
            propias = [s.get("nombre") for s in (propuesta.get("secciones") if isinstance(propuesta.get("secciones"), list) else []) if isinstance(s, dict)]
            ocupados = [titulo_seccion(rubro, i, doc["secciones"]) for i in IDS_SECCION if i != sid] + [l["nombre"] for l in doc["listas"]] + [_limpia(x, 40) for x in propias]
            if any(n.lower() == o.lower() for o in ocupados):
                continue
            try:
                doc = op.seccion_renombrar(doc, sid, n, ahora)
                aplicado["nombres"][sid] = n
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

    # Los cobros integrados todavía no funcionan: no se le deja a la persona una pantalla vacía. Si el negocio lleva gastos o cobros, ya tiene su sección propia.
    if "cobros" not in doc["ocultas"]:
        try:
            doc = est.seccion_ocultar(doc, "cobros", ahora)
            aplicado["ocultas"].append("cobros")
        except op.ErrorCrm:
            pass

    encendidas = {a for a in (propuesta.get("automatizaciones") if isinstance(propuesta.get("automatizaciones"), list) else []) if a in AUTOMATIZACIONES}
    if encendidas or isinstance(propuesta.get("automatizaciones"), list):
        doc = op._copia(doc)
        for a in doc["automatizaciones"]:
            a["on"] = a["id"] in encendidas
        aplicado["automatizaciones"] = sorted(encendidas)

    # Consejos propios del negocio: una sección con un registro por consejo (no son datos de clientes, son sugerencias para la persona).
    consejos = [_limpia(r, 150) for r in (propuesta.get("recomendaciones") if isinstance(propuesta.get("recomendaciones"), list) else [])]
    consejos = [c for c in consejos if len(c) >= 15][:MAX_RECOMENDACIONES]
    if consejos:
        try:
            doc = est.lista_crear(doc, "Recomendaciones de Shifu", [{"nombre": "Recomendación", "tipo": "texto"}, {"nombre": "Estado", "tipo": "texto"}], ahora)
            lista = doc["listas"][-1]
            por_nombre = {c["nombre"]: c["id"] for c in lista["campos"]}
            for c in consejos:
                doc = est.registro_agregar(doc, lista["id"], {por_nombre["Recomendación"]: c, por_nombre["Estado"]: "Por probar"}, ahora)
            aplicado["recomendaciones"] = len(consejos)
        except op.ErrorCrm:
            pass

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
    logger.info("CRM diseñado por la IA: %s", {k: (len(v) if hasattr(v, "__len__") else v) for k, v in aplicado.items()})
    return nuevo

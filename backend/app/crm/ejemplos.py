"""Datos de ejemplo de una plantilla: copia exacta de `laboratorio/src/plantillas/datosEjemplo.js`.

Deterministas (misma semilla, mismos datos) y con fechas relativas a `hoy`, así la agenda y los vencimientos siempre tienen algo que
mostrar. Mismo generador (mulberry32) y mismo hash (FNV-1a) que el laboratorio: para una plantilla, un nivel y un `hoy`, los registros
salen IGUALES a los del JS (lo verifican los fixtures de `test/crm/fixtures/lab/ejemplos_*.json`).

Cada registro va marcado con `ejemplo: True`: «quitar ejemplos» borra solo esos y nunca un registro real.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any, Callable

from app.crm import plantillas as catalogo

NIVELES = {"vacio": 0, "pocos": 8, "muchos": 220}

_M32 = 0xFFFFFFFF


def _imul(a: int, b: int) -> int:
    """`Math.imul` sobre enteros sin signo de 32 bits (los bits son los mismos; el signo no importa porque todo termina en `>>> 0`)."""
    return (a * b) & _M32


def azar(semilla: int) -> Callable[[], float]:
    """mulberry32: el mismo generador del laboratorio. Devuelve una función que da números en [0, 1)."""
    a = semilla & _M32

    def r() -> float:
        nonlocal a
        a = (a + 0x6D2B79F5) & _M32
        t = a
        t = _imul(t ^ (t >> 15), t | 1)
        t = (t ^ ((t + _imul(t ^ (t >> 7), t | 61)) & _M32)) & _M32
        return ((t ^ (t >> 14)) & _M32) / 4294967296

    return r


def hash_texto(s: str) -> int:
    """FNV-1a de 32 bits como el JS: un paso por cada carácter, con su primera unidad UTF-16 (`[...s]` + `charCodeAt(0)`)."""
    h = 2166136261
    for ch in s:
        cu = ord(ch)
        if cu > 0xFFFF:  # fuera del plano básico: el JS toma el primer sustituto
            cu = 0xD800 + ((cu - 0x10000) >> 10)
        h = _imul(h ^ cu, 16777619)
    return h


NOMBRES = ["Ana López", "Carlos Pérez", "María José Castillo", "Luis Hernández", "Sofía Ramírez", "Diego Morales", "Valentina Cruz",
           "Jorge Méndez", "Camila Ortiz", "Andrés Rivera", "Lucía Fernández", "Pablo Gómez", "Daniela Reyes", "Fernando Ruiz", "Gabriela Torres",
           "Ricardo Vásquez Aldana de la Peña", "Isabel Juárez", "Héctor Paz", "Natalia Soto", "Emilio Barrios"]
# Con 220 registros y 20 nombres, cada nombre salía ~11 veces: «cambia el plan de Ana López» nunca sabría cuál. El campo «nombre» (quien es
# el registro) lleva un nombre ÚNICO: los 20 de arriba y después combinaciones de nombre y dos apellidos.
PILA = ["Ana", "Carlos", "María", "Luis", "Sofía", "Diego", "Valentina", "Jorge", "Camila", "Andrés", "Lucía", "Pablo", "Daniela", "Fernando",
        "Gabriela", "Ricardo", "Isabel", "Héctor", "Natalia", "Emilio"]
APELLIDOS = ["García", "Rodríguez", "Martínez", "Sánchez", "Ramírez", "Flores", "Castillo", "Morales", "Ortiz", "Silva", "Rojas", "Vargas", "Mejía",
             "Aguilar", "Herrera", "Medina", "Castro", "Guzmán", "Navarro", "Ríos"]
EMPRESAS = ["Café Luna", "Dental Sonrisa", "Grupo Andino", "Estudio Norte", "Panadería La Espiga", "TecnoSur", "Inmobiliaria Roble", "Moda Ixchel"]
COSAS = {
    "producto": ["Pastel de chocolate", "Pan de muerto (docena)", "Cheesecake de fresa", "Café de altura 1 lb", "Galletas de mantequilla", "Pastel de bodas 3 pisos"],
    "servicio": ["Masaje relajante", "Facial hidratante", "Limpieza dental", "Paquete parejas", "Consulta de valoración", "Ortodoncia (control)"],
    "paquete": ["10 masajes", "Facial mensual", "Tratamiento ortodoncia", "Plan detox 4 semanas"],
    "plan": ["Mensual", "Trimestral", "Anual", "Estudiante"],
    "proyecto": ["Rediseño de marca", "Campaña Día de la Madre", "Sitio web corporativo", "Manejo de redes (octubre)", "App de pedidos"],
    "campana": ["Anuncios Instagram", "Promo 2x1", "Lanzamiento producto", "Black Friday", "Remarketing"],
    "tarea": ["Llamar a proveedor", "Enviar propuesta", "Revisar inventario", "Publicar en redes", "Cobrar factura pendiente"],
    "nota": ["Pidió factura", "Prefiere WhatsApp", "Volver a llamar el lunes", "Interesada en el paquete anual"],
}
RANGO_FECHA = {"entrega": [-3, 10], "fecha": [-2, 9], "vence": [-12, 45], "cuando": [-5, 15], "fin": [-3, 30], "alta": [-330, 0]}


def nombre_unico(i: int) -> str:
    if i < len(NOMBRES):
        return NOMBRES[i]
    k = i - len(NOMBRES)
    g = k // 20
    return f"{PILA[k % 20]} {APELLIDOS[g % 20]} {APELLIDOS[(k + 7 * g + 3) % 20]}"


def iso_dia(d: date) -> str:
    return d.isoformat()


def _redondear(x: float) -> int:
    """`Math.round` de JS (los medios suben), no el redondeo bancario de Python."""
    return math.floor(x + 0.5)


def _valor(campo: dict, r: Callable[[], float], hoy: date, i: int = 0, n: int = len(NOMBRES)) -> Any:
    def ent(a: int, b: int) -> int:
        return math.floor(a + r() * (b - a + 1))

    def de(lista: list) -> Any:
        return lista[math.floor(r() * len(lista))]

    tipo, cid = campo.get("tipo"), campo.get("id")
    if tipo == "estado":  # sin opciones (una sección recién creada), vacío: como `undefined` en ejemplos.js
        return de(campo["opciones"]) if campo.get("opciones") else None
    if tipo == "fecha":
        a, b = campo.get("rango") or RANGO_FECHA.get(cid) or [-60, 30]
        return iso_dia(hoy + timedelta(days=ent(a, b)))
    if tipo == "hora":
        h = ent(9, 18)
        return f"{h:02d}:{'00' if r() < 0.5 else '30'}"
    if tipo == "numero":
        return ent(*campo["rango"]) if campo.get("rango") else ent(1, 60)
    if tipo == "dinero":
        return _redondear(ent(*campo["rango"]) / 10) * 10 if campo.get("rango") else ent(15, 900) * 10
    if campo.get("ejemplos"):
        return de(campo["ejemplos"])
    if cid in COSAS:
        return de(COSAS[cid])
    if cid == "telefono":
        a = ent(3000, 5999)
        return f"+502 {a} {ent(1000, 9999)}"
    if cid == "empresa":
        return de(EMPRESAS)
    # r() se consume igual que antes: así el resto de los valores de ejemplo no cambia.
    if cid == "nombre":
        r()
        return nombre_unico(i)
    # Quien aparece en otra sección (el miembro de un pago, el cliente de una cita) es alguien que existe.
    return NOMBRES[math.floor(r() * min(max(n, 1), len(NOMBRES)))]


def datos_ejemplo(plantilla: dict | str, nivel: str = "pocos", hoy: date | None = None, pais: str | None = None) -> dict:
    """Datos para una plantilla y un nivel: {registros: {seccion_id: [{id, ejemplo, valores}]}, eventos, equipo, automatizaciones}.

    `plantilla` es el id de una plantilla del catálogo (`plantillas.plantilla_por_id`) o un dict con `id` y `secciones` (cada una con
    `id`, `campos` y, si muestra los registros de otra, `fuente`).
    `hoy` fija las fechas relativas (por defecto, la fecha de hoy). `pais` no cambia nada, igual que en el laboratorio (el teléfono es de
    Guatemala); queda para cuando los ejemplos se escriban según el país.
    """
    if isinstance(plantilla, str):
        p = catalogo.plantilla_por_id(plantilla)
        if p is None:
            raise KeyError(f"no existe la plantilla «{plantilla}»")
        plantilla = p
    hoy = hoy or date.today()
    n = NIVELES.get(nivel, NIVELES["pocos"])
    r = azar(hash_texto(f"{plantilla['id']}:{nivel}"))
    registros: dict[str, list[dict]] = {}
    for s in plantilla.get("secciones") or []:
        if not s.get("campos") or s.get("fuente"):
            continue
        campos = s["campos"]
        fechas = {c.get("id") for c in campos if c.get("tipo") == "fecha"}
        lista = []
        for i in range(n):
            valores: dict[str, Any] = {}
            for c in campos:
                valores[c["id"]] = _valor(c, r, hoy, i, n)
            # Coherencia: una campaña termina DESPUÉS de empezar. Solo si los dos son FECHAS (en Turnos «inicio» y «fin» son horas).
            if "inicio" in fechas and "fin" in fechas and valores.get("inicio") and valores.get("fin") and valores["fin"] < valores["inicio"]:
                valores["fin"] = iso_dia(date.fromisoformat(valores["inicio"]) + timedelta(days=3 + math.floor(r() * 28)))
            lista.append({"id": f"{s['id']}-{i}", "ejemplo": True, "valores": valores})
        registros[s["id"]] = lista
    if n == 0:
        eventos = [{"id": "e0", "e": "🤖", "t": "Shifu creó tu CRM", "h": "ahora"}]
    else:
        iconos = ["➕", "🔁", "📅", "💬", "✅"]
        verbos = ["Agregaste a", "Actualizaste a", "Agendaste a", "Escribiste a", "Cerraste con"]
        eventos = [{"id": f"e{i}", "e": iconos[i % 5], "t": f"{verbos[i % 5]} {NOMBRES[i % len(NOMBRES)]}", "h": "hace 5 min" if i == 0 else f"hace {i} h"}
                   for i in range(min(n, 12))]
    equipo = ["Tú"] if n == 0 else ["Tú", "Andrea", "Kevin", "Rosa"][: 4 if n > 50 else 2]
    automatizaciones = [
        {"id": "recordatorios", "pilar": "Estructura", "t": "Recordatorios de seguimiento", "d": "Te avisa cuando alguien lleva 3 días sin respuesta.", "on": True},
        {"id": "bienvenida", "pilar": "Estructura", "t": "Bienvenida por WhatsApp", "d": "Responde al instante el primer mensaje.", "on": n > 0},
        {"id": "resumen", "pilar": "Medición y equipo", "t": "Resumen semanal", "d": "Cada lunes, cuánto vendiste y qué falta.", "on": False},
    ]
    return {"registros": registros, "eventos": eventos, "equipo": equipo, "automatizaciones": automatizaciones}


def registros_ejemplo(plantilla: dict | str, nivel: str = "pocos", hoy: date | None = None, pais: str | None = None) -> dict[str, list[dict]]:
    """Solo los registros: {seccion_id: [{id, ejemplo: True, valores}]}."""
    return datos_ejemplo(plantilla, nivel, hoy, pais)["registros"]


def registros_de(seccion: dict, datos: dict) -> list[dict]:
    """Registros que ve una sección (las secciones con `fuente` muestran los de otra)."""
    return datos["registros"].get(seccion.get("fuente") or seccion["id"]) or []


def sin_ejemplos(datos: dict | None) -> dict | None:
    """Quita SOLO los registros marcados como ejemplo (los reales quedan intactos), y también el historial y el equipo de ejemplo."""
    if not datos:
        return datos
    return {**datos, "registros": {k: [r for r in rs if not r.get("ejemplo")] for k, rs in datos["registros"].items()},
            "eventos": [{"id": "e0", "e": "🤖", "t": "Shifu creó tu CRM", "h": "hoy"}], "equipo": ["Tú"]}


def _mapear_estados(registros: list[dict], por_campo: dict) -> list[dict]:
    out = []
    for r in registros:
        valores = r["valores"]
        for cid, mapa in por_campo.items():
            v, n = valores.get(cid), 0
            while _clave_js(v) in mapa and mapa[_clave_js(v)] and n < 10:
                n += 1
                v = mapa[_clave_js(v)]
            if v != valores.get(cid):
                valores = {**valores, cid: v}
        out.append(r if valores is r["valores"] else {**r, "valores": valores})
    return out


def _clave_js(v: Any) -> str:
    """Cómo el JS usa un valor como clave de objeto (`mapa[v]`)."""
    return "undefined" if v is None else str(v)


def extender_datos(datos: dict | None, base: dict, est: dict, nivel: str, hoy: date | None = None) -> dict | None:
    """Datos de ejemplo para lo que Shifu agregó: cada sección nueva y cada campo nuevo tiene su propia semilla, así los datos que ya
    estaban no cambian al agregar algo. `est` = {secciones: [sección], campos: {sec_id: [campo]}, mapeoEstado: {sec_id: {campo: {viejo: nuevo}}}}."""
    if not datos or (not est.get("secciones") and not est.get("campos") and not est.get("mapeoEstado")):
        return datos
    registros = dict(datos["registros"])
    for sec in est.get("secciones") or []:
        registros[sec["id"]] = datos_ejemplo({"id": f"{base['id']}:{sec['id']}", "secciones": [sec]}, nivel, hoy)["registros"].get(sec["id"]) or []
    for sid, extras in (est.get("campos") or {}).items():
        extra = datos_ejemplo({"id": f"{base['id']}:{sid}:campos", "secciones": [{"id": sid, "campos": extras}]}, nivel, hoy)["registros"].get(sid) or []
        registros[sid] = [{**r, "valores": {**r["valores"], **(extra[i]["valores"] if i < len(extra) else {})}} for i, r in enumerate(registros.get(sid) or [])]
    # Opciones de estado renombradas o quitadas: cada registro pasa a su nueva opción (nunca queda sin estado).
    for sid, por_campo in (est.get("mapeoEstado") or {}).items():
        registros[sid] = _mapear_estados(registros.get(sid) or [], por_campo)
    return {**datos, "registros": registros}

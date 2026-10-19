"""Vocabulario del CRM de Shifu: etapas, columnas de tareas y nombres de las secciones por rubro.

Es el mismo vocabulario que usa el frontend (`src/crm/secciones.js`): si se cambia aquí, hay que cambiarlo allá.
"""
from __future__ import annotations

ETAPAS = ["Nuevo", "En contacto", "Interesado", "Cliente"]
COLUMNAS = [("porHacer", "Por hacer"), ("enCurso", "En curso"), ("hecho", "Hecho")]
IDS_COLUMNA = [c for c, _ in COLUMNAS]

# Cada CRM nombra sus secciones con el lenguaje del rubro.
# Orden: contactos, cobros, trabajo del día a día, actividad y equipo.
# En comercio el tablero de tareas se llama «Pendientes» (antes «Pedidos»): los pedidos de verdad son registros con cliente, productos
# y total (y en el ERP serán documentos); un tablero de tareas con ese nombre los confundía (prueba del 19-oct, pendientes 2 y 43).
_SECCIONES = {
    "servicios": ["Clientes", "Facturación", "Proyectos", "Bitácora", "Equipo"],
    "agencia": ["Clientes", "Presupuestos y pagos", "Campañas", "Línea de tiempo", "Talento"],
    "comercio": ["Compradores", "Caja", "Pendientes", "Movimiento", "Vendedores"],
    "salud": ["Pacientes", "Pagos y consultas", "Tratamientos", "Historial", "Especialistas"],
    "educacion": ["Alumnos", "Mensualidades", "Clases", "Novedades", "Docentes"],
    "tecnologia": ["Cuentas", "Suscripciones", "Desarrollo", "Registro", "Equipo técnico"],
    "inmobiliaria": ["Interesados", "Comisiones y pagos", "Propiedades", "Visitas", "Asesores"],
    "otro": ["Contactos", "Cobros", "Proyectos", "Actividad", "Equipo"],
}
_ORDEN = {"contactos": 0, "cobros": 1, "desarrollo": 2, "actividad": 3, "rrhh": 4}
_FIJAS = {"importar": "Importar datos", "automatizaciones": "Automatizaciones"}

IDS_SECCION = ["contactos", "cobros", "desarrollo", "actividad", "rrhh", "importar", "automatizaciones"]


def titulo_seccion(rubro: str | None, seccion_id: str, sobrescritos: dict | None = None) -> str:
    """Nombre de una sección: el que la persona le puso (`sobrescritos`) o el que corresponde a su rubro."""
    sobrescritos = sobrescritos or {}
    if sobrescritos.get(seccion_id):
        return sobrescritos[seccion_id]
    if seccion_id in _FIJAS:
        return _FIJAS[seccion_id]
    return _SECCIONES.get(rubro or "", _SECCIONES["otro"])[_ORDEN[seccion_id]]

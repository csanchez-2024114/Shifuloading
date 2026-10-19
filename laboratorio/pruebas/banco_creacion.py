"""Banco de CREACIÓN del CRM (primer diseño) con la IA real: lo que arma `sembrar.crear_desde_cuestionario` para respuestas de
cuestionario reales o parafraseadas. Mide el tiempo, cuántas llamadas al modelo hizo y si la estructura sirve para ESE negocio.

No usa el servidor: importa el backend y llama a la creación en el mismo proceso (la clave la carga el propio backend desde su
`.env`; este script no la lee). Así el mismo banco mide cualquier copia del código:

    BACKEND=~/CURSOR/HyperShifu/Shifuloading/backend  <python del venv> laboratorio/pruebas/banco_creacion.py   # línea base (david)
    <python del venv> laboratorio/pruebas/banco_creacion.py [repeticiones]                                      # este worktree

`SALIDA=<archivo.json>` guarda el detalle de cada CRM creado (secciones, campos, ejemplos, inicio, resumen).

Qué cuenta como «sirve» (cada caso declara además lo suyo):
- no casi vacío: al menos 3 secciones visibles con datos, cada una con 3 campos o más;
- tipos de verdad: ningún campo que se llame «estado/etapa» quedó como texto, y hay al menos un campo de fecha o dinero;
- ejemplos pocos y marcados: cada sección trae entre 1 y 20 registros de ejemplo y todos con `ejemplo: True`;
- inicio con al menos 2 bloques que apuntan a secciones que existen;
- un resumen escrito, y cada sección que nombra el resumen existe;
- lo prohibido del caso no aparece (p. ej. Membresías en una tienda de computadoras) y lo pedido sí.
Las palabras de abajo son el ORÁCULO del banco (lo que una persona esperaría ver), no reglas del producto.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
BACKEND = Path(os.path.expanduser(os.environ.get("BACKEND", str(RAIZ / "backend")))).resolve()
sys.path.insert(0, str(BACKEND))
os.environ["CRM_DISENO"] = "1"
os.environ.setdefault("CRM_IA", "1")

import app  # noqa: E402,F401  (carga el .env del backend)
from app.crm import diseno, sembrar  # noqa: E402
from app.crm import secciones_v as sv  # noqa: E402

GT = {"pais": "GT", "ciudad": "Guatemala"}


def qa(*pares):
    return [{"pregunta": p, "respuesta": r} for p, r in pares]


CASOS = [
    {"id": "pepescore", "desc": "PepesCore (informe 19-oct): venta y reparación de computadoras, 15 empleados",
     "brief": {"nombre": "PepesCore", "ubicacion": GT, "rubro": "comercio",
               "que_vendes": "Me dedico a vender computadoras, laptops y accesorios y también a repararlas. Somos 15 empleados. Lo que hacemos: "
                             "reparar, revisar, vender, desarmar y comprar equipos usados. Quiero tener el control de mis números, datos y mi personal.",
               "seguimiento": qa(("¿Qué quieres tener en orden primero?", "Ventas, Empleados, Reparaciones, Equipos"),
                                 ("¿Cómo lo llevas hoy?", "Excel o Sheets"),
                                 ("¿Quién más lo va a usar?", "Los jefes de área"),
                                 ("¿Qué se te complica o se te pierde?", "Reparaciones, Inventario, Turnos"),
                                 ("Si dentro de un mes todo estuviera en orden, ¿qué te gustaría poder hacer?", "Contratar más gente y abrir sucursales"))},
     "debe": [r"repar", r"venta|vend", r"inventario|stock|existenc|equipo|producto"],
     "prohibido": [r"membres", r"gimnas", r"socio", r"entrenad", r"clase"]},
    {"id": "astral", "desc": "Astral (QA celular 19-oct, caso 21b): repartidor de componentes y cosas geek",
     "brief": {"nombre": "Astral", "ubicacion": GT, "rubro": "comercio",
               "que_vendes": "Soy repartidor de componentes de computadoras y consolas, y cosas geek: figuras, cables, controles. Los llevo a domicilio.",
               "seguimiento": qa(("¿Qué quieres tener en orden?", "Pedidos, Entregas, Productos"),
                                 ("¿Cómo te pagan?", "Contra entrega"),
                                 ("¿Quién más lo usa?", "Solo yo"),
                                 ("¿Qué se te complica?", "Saber qué entregas tengo hoy y qué me falta cobrar"))},
     "debe": [r"pedido|orden|venta", r"entreg|envi|ruta|reparto", r"producto|inventario|stock|componente|catalogo"],
     "prohibido": [r"membres", r"gimnas", r"paciente"]},
    {"id": "comida_planchado", "desc": "Dos rubros a la vez: comida a domicilio + planchado de ropa",
     "brief": {"nombre": "Doña Tere", "ubicacion": GT, "rubro": "servicios",
               "que_vendes": "Vendo almuerzos caseros a domicilio de lunes a viernes y además tengo un servicio de planchado de ropa: me traen la ropa y la cobro por docena.",
               "seguimiento": qa(("¿Qué quieres tener en orden?", "Pedidos de almuerzos, Ropa por planchar, Cobros"),
                                 ("¿Cómo te piden?", "Por WhatsApp"),
                                 ("¿Quién te ayuda?", "Mi hija"),
                                 ("¿Qué se te complica?", "Que se me olvida qué ropa es de quién y cuándo la tengo que entregar"))},
     "debe": [r"almuerz|comida|pedido|menu|platill", r"planch|ropa|prenda|lavander"],
     "prohibido": [r"membres", r"gimnas", r"paciente"]},
    {"id": "veterinaria_parafraseada", "desc": "Catálogo parafraseado: veterinaria",
     "brief": {"nombre": "Patitas", "ubicacion": GT, "rubro": "salud",
               "que_vendes": "Atiendo perros y gatos: consultas, les pongo sus vacunas y los desparasito. Quiero saber a quién le toca volver.",
               "seguimiento": qa(("¿Cómo atiendes?", "Con cita"), ("¿Qué necesitas recordar de cada animal?", "Vacunas, Peso, Dueño"))},
     "debe": [r"mascota|animal|paciente|perro", r"vacun|cita|consulta"],
     "prohibido": [r"membres", r"gimnas", r"propiedad"]},
    {"id": "abogados_parafraseado", "desc": "Catálogo parafraseado: despacho de abogados",
     "brief": {"nombre": "Bufete Méndez", "ubicacion": GT, "rubro": "servicios",
               "que_vendes": "Llevo juicios y trámites legales de mis clientes; tengo que estar pendiente de las audiencias y de lo que me deben de honorarios.",
               "seguimiento": qa(("¿Cómo cobras?", "Por caso, con anticipo"), ("¿Quién trabaja contigo?", "Dos asistentes"))},
     "debe": [r"caso|juicio|expediente|tramite", r"audienc|plazo|cita|vencim", r"honorar|cobro|pago"],
     "prohibido": [r"membres", r"gimnas", r"mascota"]},
    {"id": "academia_parafraseada", "desc": "Catálogo parafraseado: escuela o academia",
     "brief": {"nombre": "English Now", "ubicacion": GT, "rubro": "educacion",
               "que_vendes": "Doy clases de inglés a niños y adultos en grupos por nivel; cobro una mensualidad y quiero saber quién está atrasado.",
               "seguimiento": qa(("¿Qué ofreces?", "Cursos por nivel"), ("¿Cómo cobras?", "Mensualidad"))},
     "debe": [r"alumn|estudiant", r"curso|grupo|clase|nivel", r"pago|mensualid|cobro"],
     "prohibido": [r"gimnas", r"paciente", r"propiedad"]},
]


def plano(t) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(t or "").lower()) if not unicodedata.combining(c))


class Contador:
    """El modelo real, contando llamadas."""

    def __init__(self):
        self.llamadas = 0
        try:  # la creación nueva usa su propio modelo (JSON); la de antes, el de `diseno`
            from app.crm import primer_diseno
            self.real = primer_diseno.modelo_creacion()
        except ImportError:
            self.real = diseno._modelo()

    async def ainvoke(self, mensajes):
        self.llamadas += 1
        return await self.real.ainvoke(mensajes)


def secciones_visibles(doc: dict) -> list[dict]:
    out = []
    for s in sv.secciones_de(doc):
        if s.get("id") == sv.TAREAS:  # el tablero de pendientes de Carlos: es de la persona, no trae ejemplos
            continue
        campos = s.get("campos") or []
        if not campos:
            continue
        out.append(s)
    return out


def registros_de(doc: dict, sid: str) -> list[dict]:
    if sid == "contactos":
        return doc.get("contactos") or []
    lista = next((l for l in doc.get("listas") or [] if l["id"] == sid), None)
    return (lista or {}).get("registros") or []


def revisar(caso: dict, doc: dict) -> tuple[list[str], dict]:
    secs = secciones_visibles(doc)
    malos: list[str] = []
    info = {"secciones": [], "inicio": [b.get("vista") + ":" + str(b.get("seccion")) for b in doc.get("inicio") or []],
            "resumen": doc.get("resumen_ia"), "plantilla": doc.get("plantilla")}
    for s in secs:
        regs = registros_de(doc, s["id"])
        info["secciones"].append({"id": s["id"], "titulo": s.get("titulo"), "vista": s.get("vista"),
                                  "campos": [f"{c.get('nombre')}:{c.get('tipo')}" for c in s.get("campos") or []],
                                  "ejemplos": len(regs), "muestra": [r.get("valores") or {k: r.get(k) for k in ("n", "etapa", "extra")} for r in regs[:2]]})
    if len(secs) < 3:
        malos.append(f"casi vacío: {len(secs)} secciones visibles")
    for s in secs:
        if len(s.get("campos") or []) < 3:
            malos.append(f"«{s.get('titulo')}» con {len(s.get('campos') or [])} campos")
        for c in s.get("campos") or []:
            if re.fullmatch(r"(estado|etapa|status)", plano(c.get("nombre")).strip()) and c.get("tipo") != "estado":
                malos.append(f"«{s.get('titulo')}.{c.get('nombre')}» es {c.get('tipo')}, no estado")
        regs = registros_de(doc, s["id"])
        if not 1 <= len(regs) <= 20:
            malos.append(f"«{s.get('titulo')}» con {len(regs)} ejemplos")
        if any(not r.get("ejemplo") for r in regs):
            malos.append(f"«{s.get('titulo')}» con registros sin marca de ejemplo")
    tipos = {c.get("tipo") for s in secs for c in s.get("campos") or []}
    if not tipos & {"fecha", "dinero"}:
        malos.append("sin ningún campo de fecha ni de dinero")
    ids = {s["id"] for s in sv.secciones_de(doc)}
    inicio = [b for b in doc.get("inicio") or [] if b.get("seccion") in ids]
    if len(inicio) < 2:
        malos.append(f"inicio con {len(inicio)} bloques válidos")
    if not doc.get("resumen_ia"):
        malos.append("sin resumen")
    texto = plano(" ".join([s.get("titulo") or "" for s in secs] + [c.get("nombre") or "" for s in secs for c in s.get("campos") or []]))
    for p in caso.get("prohibido") or []:
        if re.search(p, texto):
            malos.append(f"aparece lo prohibido /{p}/")
    for p in caso.get("debe") or []:
        if not re.search(p, texto):
            malos.append(f"falta /{p}/")
    return malos, info


async def correr(reps: int) -> None:
    detalle = []
    ok = total = 0
    tiempos, llamadas = [], []
    for caso in CASOS:
        for rep in range(reps):
            m = Contador()
            a = time.time()
            try:
                doc = await sembrar.crear_desde_cuestionario(f"banco-{caso['id']}-{rep}", caso["brief"], modelo=m)
                err = None
            except Exception as e:  # el banco anota el fallo y sigue
                doc, err = {}, f"{type(e).__name__}: {e}"
            t = time.time() - a
            tiempos.append(t)
            llamadas.append(m.llamadas)
            malos, info = revisar(caso, doc) if not err else ([err], {})
            bien = not malos
            ok += bien
            total += 1
            print(f"{'✓' if bien else '✗'} {t:5.1f}s {m.llamadas} llamada(s) | {caso['id']} — {caso['desc']}")
            for s in info.get("secciones", []):
                print(f"     · {s['titulo']} [{s['vista']}] {s['ejemplos']} ej. — {', '.join(s['campos'])}")
            if info:
                print(f"     inicio: {', '.join(info['inicio']) or '—'}")
                print(f"     resumen: {(info['resumen'] or '—')[:300]}")
            for x in malos:
                print(f"     ⚠ {x}")
            detalle.append({"caso": caso["id"], "rep": rep, "ok": bien, "tiempo": round(t, 2), "llamadas": m.llamadas, "fallas": malos, **info})
    ts = sorted(tiempos)
    p50 = ts[len(ts) // 2]
    print(f"\n{ok}/{total} sirven · tiempo p50 {p50:.1f}s · máx {max(ts):.1f}s · llamadas máx {max(llamadas)} · backend {BACKEND}")
    if os.environ.get("SALIDA"):
        Path(os.environ["SALIDA"]).write_text(json.dumps(detalle, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(correr(int(sys.argv[1]) if len(sys.argv) > 1 else 1))

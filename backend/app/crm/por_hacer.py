"""Lo que quedó POR HACER al terminar un turno del chat, anotado por el CÓDIGO (nunca redactado por el modelo), para el turno siguiente.

(No confundir con `pendiente`, la confirmación de un borrado que espera un «sí».)

Tres clases, todas calculadas con lo que corrió en el turno:
- `registros`: datos que no alcanzaron a guardarse (la llamada llegó tras el tope de acciones, o pasó del tope por llamada). Se guardan con
  sus valores tal como los mandó el modelo: el turno siguiente los puede agregar aunque el mensaje original ya no esté en la ventana.
- `accion`: cualquier otra herramienta que no alcanzó a correr por el tope (crear una sección, un campo…).
- `promesa`: lo que la respuesta dijo que HARÍA («crearé la sección Ventas») sin hacerlo en el turno ni estar ya pendiente.

Cada turno: lo anterior que ya quedó hecho se quita (registros: el código lo busca en el CRM; acciones y promesas: si algún cambio del turno
nombra lo mismo); lo demás sigue hasta `MAX_TURNOS` turnos. Al modelo le llega como contexto (`bloque`) y a la persona, una línea que escribe
el código (`linea`). Prueba del 19-oct: «Por límite no pude agregar todas» y al «ya te los pasé» el turno siguiente ya no tenía los datos.
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.crm import secciones_v as sv
from app.crm.valores import campo_titulo, sin_acentos

MAX_TURNOS = 3          # turnos en que se sigue mostrando lo pendiente si nadie lo retoma
MAX_ITEMS = 12
MAX_BLOQUE = 3_000      # caracteres de lo pendiente en el prompt
_PALABRA = re.compile(r"[0-9a-zñ]{4,}")
_DE_DATOS = {"agregar_registro": "valores", "agregar_registros": "registros", "agregar_contactos": "contactos"}


def palabras(x: Any) -> set[str]:
    """Las palabras de 4 letras o más (sin acentos) de un texto o de cualquier estructura con textos."""
    if isinstance(x, dict):
        return set().union(*(palabras(v) for v in x.values())) if x else set()
    if isinstance(x, (list, tuple, set)):
        return set().union(*(palabras(v) for v in x)) if x else set()
    return set(_PALABRA.findall(sin_acentos(x))) if x not in (None, "") else set()


def _seccion(doc: dict, q: Any) -> dict | None:
    """La sección con registros por id o por título (sin acentos)."""
    k = sin_acentos(q)
    secs = sv.secciones_de(doc)
    return next((s for s in secs if s["id"] == q), None) or next((s for s in secs if sin_acentos(s.get("titulo")) == k), None)


def titulo_de(valores: dict, sec: dict | None) -> str:
    """Cómo se llama un registro pendiente: el valor de su campo título (por id o por nombre) o, si no se sabe, su primer texto."""
    valores = valores if isinstance(valores, dict) else {}
    if sec:
        ct = campo_titulo(sec, sec.get("campos") or []) or {}
        for k, v in valores.items():
            if k == ct.get("id") or sin_acentos(k) == sin_acentos(ct.get("nombre")):
                return str(v)
    return next((str(v) for v in valores.values() if isinstance(v, str) and v.strip()), "")


def de_llamada(doc: dict, nombre: str, args: Any) -> dict:
    """Lo pendiente de una llamada que no alcanzó a correr."""
    args = args if isinstance(args, dict) else {}
    if nombre == "agregar_registro":
        regs = args.get("registros")
        if not (isinstance(regs, list) and regs) and isinstance(args.get("valores"), list):
            regs = args["valores"]
        if isinstance(regs, list) and regs:
            return de_registros(doc, args.get("seccion"), regs)
    if nombre in _DE_DATOS:
        lista = args.get(_DE_DATOS[nombre])
        lista = [lista] if nombre == "agregar_registro" else (lista if isinstance(lista, list) else [])
        return de_registros(doc, "contactos" if nombre == "agregar_contactos" else args.get("seccion"), lista)
    return {"tipo": "accion", "herramienta": nombre, "args": args, "turnos": 0}


def de_registros(doc: dict, seccion: Any, registros: list) -> dict:
    sec = _seccion(doc, seccion)
    regs = [r for r in registros if isinstance(r, dict) and r]
    return {"tipo": "registros", "seccion": sec["id"] if sec else str(seccion or ""), "titulo": sec["titulo"] if sec else str(seccion or ""),
            "registros": regs, "nombres": [titulo_de(r, sec) for r in regs], "turnos": 0}


def promesa(texto: str) -> dict:
    return {"tipo": "promesa", "texto": " ".join(str(texto).split())[:200], "turnos": 0}


def juntar(items: list[dict]) -> list[dict]:
    """Los registros de una misma sección, en un solo pendiente (en el orden en que llegaron); lo vacío se descarta."""
    salida: list[dict] = []
    for it in items:
        if it.get("tipo") == "registros":
            if not it.get("registros"):
                continue
            mismo = next((x for x in salida if x.get("tipo") == "registros" and x["seccion"] == it["seccion"]), None)
            if mismo:
                for r, n in zip(it["registros"], it.get("nombres") or [""] * len(it["registros"])):
                    if r not in mismo["registros"]:
                        mismo["registros"].append(r)
                        mismo.setdefault("nombres", []).append(n)
                mismo["turnos"] = min(mismo.get("turnos", 0), it.get("turnos", 0))
                continue
        elif it.get("tipo") == "promesa" and any(x.get("tipo") == "promesa" and x["texto"] == it["texto"] for x in salida):
            continue
        salida.append(json.loads(json.dumps(it, ensure_ascii=False, default=str)))  # copia propia (se guarda en Mongo)
    return salida[:MAX_ITEMS]


def _ya_esta(doc: dict, it: dict, r: dict) -> bool:
    sec = _seccion(doc, it["seccion"]) or _seccion(doc, it.get("titulo"))
    if not sec:
        return False
    t = sin_acentos(titulo_de(r, sec))
    ct = campo_titulo(sec, sec.get("campos") or []) or {}
    return bool(t) and any(sin_acentos((x.get("valores") or {}).get(ct.get("id"))) == t for x in sv.registros_de(doc, sec["id"]))


def texto_de(it: dict) -> str:
    if it.get("tipo") == "registros":
        return f"{it.get('titulo')} " + " ".join(json.dumps(r, ensure_ascii=False) for r in it.get("registros") or [])
    if it.get("tipo") == "accion":
        return f"{it.get('herramienta')} {json.dumps(it.get('args') or {}, ensure_ascii=False)}"
    return str(it.get("texto") or "")


def seguir(previos: list[dict] | None, doc: dict, cambios: list[dict], nuevos: list[dict] | None = None) -> list[dict]:
    """Lo pendiente al cerrar el turno: lo anterior que sigue sin hacerse (un turno más viejo) y lo nuevo de este turno.
    Registros: se quitan los que ya están en el CRM. Acciones y promesas: se quitan si un cambio del turno nombra lo mismo."""
    hecho = palabras([c.get("args") for c in cambios]) | palabras([c.get("etiqueta") for c in cambios])
    quedan: list[dict] = []
    for it in previos or []:
        if not isinstance(it, dict) or it.get("turnos", 0) >= MAX_TURNOS:
            continue
        if it.get("tipo") == "registros":
            pares = [(r, n) for r, n in zip(it.get("registros") or [], it.get("nombres") or [""] * len(it.get("registros") or []))
                     if not _ya_esta(doc, it, r)]
            if pares:
                quedan.append({**it, "registros": [r for r, _ in pares], "nombres": [n for _, n in pares], "turnos": it.get("turnos", 0) + 1})
        elif it.get("tipo") == "accion":
            if not (it.get("herramienta") in {c.get("herramienta") for c in cambios} and palabras(it.get("args")) & hecho):
                quedan.append({**it, "turnos": it.get("turnos", 0) + 1})
        elif it.get("tipo") == "promesa":
            if not palabras(it.get("texto")) & hecho:
                quedan.append({**it, "turnos": it.get("turnos", 0) + 1})
    return juntar([*quedan, *(nuevos or [])])


def _registro_corto(r: dict) -> str:
    return ", ".join(f"{k}: {v}" for k, v in r.items() if v not in (None, ""))


def bloque(items: list[dict] | None) -> str | None:
    """Lo pendiente, para el prompt del turno siguiente (contexto, no órdenes)."""
    lineas = []
    for it in items or []:
        if it.get("tipo") == "registros":
            regs = "; ".join(f"[{_registro_corto(r)}]" for r in it["registros"])
            lineas.append(f"- Faltaron {len(it['registros'])} registro(s) en {it.get('titulo') or it['seccion']} (seccion: {it['seccion']}): {regs}")
        elif it.get("tipo") == "accion":
            lineas.append(f"- No alcanzó a correr: {it['herramienta']} {json.dumps(it.get('args') or {}, ensure_ascii=False)}")
        elif it.get("tipo") == "promesa":
            lineas.append(f"- Dijiste que harías: «{it['texto']}» y todavía no está hecho.")
    if not lineas:
        return None
    texto = "\n".join(lineas)[:MAX_BLOQUE]
    return ("Pendiente de mensajes anteriores (lo anotó el CÓDIGO; todavía NO está hecho):\n" + texto +
            "\nSi la persona pide seguir («sigue», «sí», «ya te los pasé», «lo que falta»), hazlo ahora con las herramientas (varios registros de una "
            "sección: una sola llamada a agregar_registro con la lista en registros). Si pide otra cosa, atiende eso. No digas que ya está hecho.")


def linea(items: list[dict], respuesta: str) -> str | None:
    """Lo pendiente de ESTE turno dicho por el código a la persona (si la respuesta no lo dice ya). Solo registros y acciones: las promesas
    las agrega `agente_diseno` con su propia línea."""
    t = sin_acentos(respuesta)
    partes = []
    acciones: dict[str, int] = {}
    for it in items:
        if it.get("tipo") == "registros":
            nombres = it.get("nombres") or [titulo_de(r, None) for r in it["registros"]]
            dicho = sin_acentos(it.get("titulo")) in t and str(len(nombres)) in t
            if not dicho:
                muestra = ", ".join(f"«{n}»" for n in nombres[:5] if n) + ("…" if len(nombres) > 5 else "")
                partes.append(f"{len(nombres)} registro(s) en {it.get('titulo') or it['seccion']}" + (f" ({muestra})" if muestra else ""))
        elif it.get("tipo") == "accion":
            acciones[it["herramienta"]] = acciones.get(it["herramienta"], 0) + 1
    partes += [f"{h.replace('_', ' ')}" + (f" (×{n})" if n > 1 else "") for h, n in acciones.items()]
    if not partes:
        return None
    return f"Quedó pendiente por el límite de este mensaje: {'; '.join(partes)}. Escríbeme «sigue» y lo hago."

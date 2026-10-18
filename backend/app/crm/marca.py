"""Branding del negocio (D19-D21): port de lo que usa la edición de `laboratorio/src/plantillas/marca.js`.

La marca solo reemplaza tokens (colores, fondos, tipografías). El código cuida que siempre se lea: cada color que va como texto o
debajo del texto se ajusta (más claro u oscuro) hasta llegar al contraste mínimo, y se dice qué se ajustó para que Shifu lo cuente
con honestidad. Funciones puras; los textos de `ajustes` y de `revisar_logo` son LITERALES del laboratorio.

`FUENTES` son las 12 tipografías que la marca acepta (las de `marca.js`); el catálogo grande de tipografías es `plantillas.fuentes()`.
En el documento el logo vive aparte (`marca.logo_id`); aquí cuenta como el `logo` del laboratorio.
"""
from __future__ import annotations

import math
import re
from typing import Any

# Nombre → familia de Google Fonts, en el orden de marca.js (el enum de cambiar_marca sale de este orden).
FUENTES: dict[str, str] = {
    "Inter": "Inter:wght@400;500;600;700;800", "Poppins": "Poppins:wght@400;500;600;700", "Nunito": "Nunito:wght@400;600;700;800",
    "Montserrat": "Montserrat:wght@400;500;600;700", "DM Sans": "DM+Sans:wght@400;500;700", "Rubik": "Rubik:wght@400;500;600;700",
    "Work Sans": "Work+Sans:wght@400;500;600;700", "Lato": "Lato:wght@400;700", "Playfair Display": "Playfair+Display:wght@500;600;700",
    "Lora": "Lora:wght@400;500;600;700", "Merriweather": "Merriweather:wght@400;700", "Outfit": "Outfit:wght@400;500;600;700",
}

# La base: los tokens del CRM por tema.
BASE = {
    "oscuro": {"bg": "#070b0a", "bgTop": "#0a0f0e", "card": "#0c1211", "tx": "#ffffff", "acento": "#22d3a6", "secundario": "#7c5cff"},
    "claro": {"bg": "#eef3f1", "bgTop": "#ffffff", "card": "#ffffff", "tx": "#14211d", "acento": "#22d3a6", "secundario": "#7c5cff"},
}
_LOGO = ("logo", "logo_id")  # lo que no es color ni letra: no cuenta como «tiene marca»

_HEX = re.compile(r"#?([0-9a-f]{3}|[0-9a-f]{6})", re.IGNORECASE)


def es_hex(c: Any) -> bool:
    return isinstance(c, str) and _HEX.fullmatch(c.strip()) is not None


def es_fuente(f: Any) -> bool:
    """Una de las 12 tipografías permitidas."""
    return isinstance(f, str) and f in FUENTES


def _rgb(c: str) -> list[int]:
    h = c.strip().replace("#", "", 1)
    if len(h) == 3:
        h = "".join(x + x for x in h)
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def _redondear(v: float) -> int:
    return math.floor(v + 0.5)  # Math.round de JS (las mitades suben)


def _hex(rgb: list[float]) -> str:
    return "#" + "".join(format(max(0, min(255, _redondear(v))), "02x") for v in rgb)


def _lum(c: str) -> float:
    def canal(v: int) -> float:
        v = v / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(v) for v in _rgb(c))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a: str, b: str) -> float:
    x, y = sorted([_lum(a), _lum(b)], reverse=True)
    return (x + 0.05) / (y + 0.05)


def _mezclar(a: str, b: str, t: float) -> str:
    ra, rb = _rgb(a), _rgb(b)
    return _hex([v + (rb[i] - v) * t for i, v in enumerate(ra)])


def _legible(color: str, fondo: str, minimo: float) -> tuple[str, bool]:
    """Acerca `color` a blanco o negro (lo que más contraste dé contra `fondo`) hasta llegar a `minimo`. → (color, ajustado)."""
    if contraste(color, fondo) >= minimo:
        return color, False
    meta = "#000000" if _lum(fondo) > 0.4 else "#ffffff"
    t = 0.05
    while t <= 1.0001:  # mismo paso acumulado que el for de JS (mismos flotantes)
        c = _mezclar(color, meta, t)
        if contraste(c, fondo) >= minimo:
            return c, True
        t += 0.05
    return meta, True


def _triplete(c: str) -> str:
    return ", ".join(str(v) for v in _rgb(c))


def tokens_de_marca(marca: dict | None = None, tema: str = "oscuro") -> dict:
    """Tokens finales de un tema: base + marca, con los ajustes de legibilidad. → {vars: {'--acento': …}, ajustes: [frases]}."""
    marca = marca or {}
    if not any(k not in _LOGO and k != "nombre" and marca[k] for k in marca):
        return {"vars": {}, "ajustes": []}  # sin marca: la base tal cual
    b = BASE.get(tema) or BASE["oscuro"]
    ajustes: list[str] = []
    bg = marca["fondo"] if es_hex(marca.get("fondo")) else b["bg"]
    if es_hex(marca.get("superficie")):
        card = marca["superficie"]
    elif es_hex(marca.get("fondo")):
        card = _mezclar(bg, "#ffffff", 0.05 if tema == "oscuro" else 0.7)
    else:
        card = b["card"]
    tx = marca["texto"] if es_hex(marca.get("texto")) else b["tx"]
    t1, t1_ajustado = _legible(tx, card, 7)

    def tono(c: str) -> str:
        return "claro" if _lum(c) > 0.4 else "oscuro"
    if t1_ajustado and es_hex(marca.get("texto")):
        ajustes.append(f"en tema {tema} el texto {marca['texto']} no se lee sobre {card}: quedó {t1} ({tono(t1)}), no {marca['texto']}")
    tx = t1
    prim = marca["primario"] if es_hex(marca.get("primario")) else b["acento"]
    a, a_ajustado = _legible(prim, card, 4.5)
    if a_ajustado and es_hex(marca.get("primario")):
        ajustes.append(f"en tema {tema} el color principal {marca['primario']} se {'aclaró' if _lum(a) > _lum(prim) else 'oscureció'} a {a} "
                       "para que los números se lean")
    sec = marca["secundario"] if es_hex(marca.get("secundario")) else b["secundario"]
    vars_ = {
        "--bg": bg, "--bg-top": _mezclar(bg, card, 0.5) if es_hex(marca.get("fondo")) else b["bgTop"], "--card": card,
        "--tx": tx, "--tx2": _mezclar(tx, card, 0.22), "--tx3": _legible(_mezclar(tx, card, 0.42), card, 4.5)[0],
        "--ink": _triplete(tx), "--morado": sec,
    }
    if es_hex(marca.get("primario")):  # sin color propio, cada plantilla conserva su color de firma
        vars_.update({"--acento": a, "--verde": a})
    if es_fuente(marca.get("fuenteTexto")):
        vars_["--fuente"] = f"'{marca['fuenteTexto']}', system-ui, sans-serif"
    if es_fuente(marca.get("fuenteTitulos")):
        vars_["--fuente-titulos"] = f"'{marca['fuenteTitulos']}', system-ui, sans-serif"
    return {"vars": vars_, "ajustes": ajustes}


def revisar_logo(data_url: Any) -> str | None:
    """Formato del logo (D20): imagen SVG, PNG o WebP (fondo transparente), máximo 1.5 MB. Devuelve un error legible o None."""
    if not isinstance(data_url, str) or not data_url.startswith("data:image/"):
        return "no llegó ninguna imagen: pídele a la persona que adjunte su logo en el chat (cámara o pegar)."
    tipo = data_url[5:data_url.find(";")] if ";" in data_url else data_url[5:-1]
    if tipo not in ("image/svg+xml", "image/png", "image/webp"):
        return (f"el logo llegó como {tipo.replace('image/', '', 1).upper()}; pide el logo en SVG o PNG con fondo transparente (un JPG trae fondo "
                "blanco y se ve como un recuadro).")
    if len(data_url) > 2_000_000:
        return "el logo pesa más de 1.5 MB; pide una versión más liviana (PNG de 512 px de ancho alcanza)."
    return None

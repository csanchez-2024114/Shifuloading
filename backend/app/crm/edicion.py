"""El cerco de la edición por IA: las ÚNICAS operaciones de diseño que Shifu puede hacer sobre el CRM (port de `edicion.js`).

Funciones puras: reciben el documento y devuelven uno nuevo con el texto que lee el modelo, o un error legible («ERROR: …») sin
cambiar nada. Lo que el modelo pide fuera de esto (una vista que no existe, un campo equivocado) se rechaza aquí, no se dibuja mal.
Los textos y los esquemas de las herramientas son LITERALES del laboratorio (el prompt es frágil, medido).

    ejecutar(doc, nombre, args, contexto) -> {ok, doc, resultado, etiqueta, vista[, logo]}

`contexto` (todo opcional): `vista` (la pestaña que mira la persona; «inicio» si no), `texto` (su mensaje: nombres literales y
cerrar_toma), `confirmado` (dijo «sí» a una pieza repetida, D55), `digresion`, `imagen` (data URL adjunta: usar_logo), `logo_id`
(dónde ya se guardó esa imagen) y `ahora`. `vista` sale actualizada (abrir_seccion la cambia). Con usar_logo sin `logo_id` el resultado
trae `logo: {id, imagen}` para que quien llama guarde la imagen con ese id.

Cómo se traduce el estado del laboratorio al documento: `bloques` = `doc["inicio"]`, `estructura.paginas` = `doc["paginas"]`,
`marca` = `doc["marca"]` (el logo en `logo_id`), `estado.vista` = `contexto.vista`. Las secciones salen de `secciones_v`; los cambios de
estructura van por las funciones de Carlos (`estructura.*`, `operaciones.seccion_renombrar`) y luego se valida la plantilla completa
resultante: si queda inválida, no se aplica.

Diferencias con el laboratorio (a propósito; ver `test_herramientas_paridad.py`):
- En el laboratorio quitar un campo o una sección solo los oculta; con las funciones de Carlos se borran con sus datos. El texto lo
  dice con verdad («se puede deshacer»: el punto de deshacer guarda la foto de esos datos) en vez de «sus datos se conservan».
- Las secciones nuevas llevan id `l_<slug>`; un campo nuevo de una lista lleva el slug de su nombre (como en el laboratorio); uno de
  los contactos lleva el `f_…` de Carlos y el texto dice su id. Los nombres se guardan como los normaliza Carlos (mayúscula inicial).
- Contactos y tareas son secciones virtuales: sus campos fijos no se quitan ni se renombran, las tareas no llevan campos nuevos ni
  cambian sus estados, y su ficha/tarjeta todavía no tiene dónde guardarse (error claro en cada caso).

Las herramientas de datos (`registros.HERR_DATOS`, consultar_datos), `deshacer` (puntos.py) y `leer_enlace` no pasan por aquí: las
despacha el chat. Las de la toma de diseño sí (van a `toma.ejecutar_toma`).
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import random
import time
from datetime import datetime
from typing import Any

from app.crm import estructura, plantillas, secciones_v, topes
from app.crm import operaciones as op
from app.crm import toma as tm
from app.crm.lienzo import ALTO_MAX, ANCHO_COMPLETO, ANCHOS_COL, VISTAS_INICIO, acomodar, ajustar_ancho, ubicacion, ubicar, ubicar_todo
from app.crm.marca import FUENTES, es_fuente, es_hex, revisar_logo, tokens_de_marca
from app.crm.operaciones import ErrorCrm
from app.crm.pantalla import (FALTA, arg, catalogo_toma, con_registros, entero, etiqueta_cambio, js, js_num, nombre_literal, pagina_de,
                              paginable, plantilla_efectiva, seccion_de, slug, lienzo_de_bloque)
from app.crm.registros import HERRAMIENTAS_DATOS
from app.crm.validar import TIPOS_CAMPO, campos_de, normalizar_opciones, revisar_vista, validar_plantilla, verdad

HERR_BLOQUE = frozenset(["agregar_bloque", "quitar_bloque", "mover_bloque", "cambiar_tamano", "cambiar_visual", "cambiar_rangos"])
VISTAS_SECCION = ("tabla", "tablero", "agenda", "vencimientos")
MAX_CAMPOS_SECCION = topes.CAMPOS_POR_SECCION  # el mismo tope que `estructura` (antes 8 aquí y 15 allá)
_FIJOS_CONTACTO = ("nombre", "detalle", "canal", "etapa", "responsable")
_HUELLA_GRAFICO = ("tipo", "por", "agrupar", "valor", "fecha", "estado", "x", "y")


def _pestanas() -> dict[str, dict]:
    return {p["id"]: p for p in plantillas.pestanas()}


def _base36(n: int) -> str:
    dig = "0123456789abcdefghijklmnopqrstuvwxyz"
    s = ""
    while True:
        n, r = divmod(n, 36)
        s = dig[r] + s
        if not n:
            return s


def nuevo_uid(doc: dict) -> str:
    """Id nuevo e irrepetible (como `nuevoUid`): si se reusara el de un bloque quitado, la animación lo confundiría con el viejo."""
    usados = set(ubicar_todo(doc))
    while True:
        uid = "n" + _base36(int(time.time() * 1000)) + "".join(random.choice("0123456789abcdefghijklmnopqrstuvwxyz") for _ in range(3))
        if uid not in usados:
            return uid


def _min_max(v: float, lo: float, hi: float) -> float:
    """Math.max(lo, Math.min(hi, v)) de JS (NaN se queda NaN)."""
    return v if math.isnan(v) else max(lo, min(hi, v))


def _o(*xs: Any) -> Any:
    """`a || b || c` de JS."""
    for x in xs[:-1]:
        if verdad(x) and x is not FALTA:
            return x
    return xs[-1]


def _lista(doc: dict, sec_id: str) -> dict:
    return next(l for l in doc["listas"] if l["id"] == sec_id)


def _huella(x: dict) -> list:
    """Igual = misma vista y sección; gráfica: mismo tipo y campos; lista: mismo filtro y orden (D55)."""
    o = x.get("opciones") or {}
    vista = "grafico" if x.get("vista") == "grafica" else x.get("vista")
    return [vista, x.get("seccion"),
            *([o.get(k) for k in _HUELLA_GRAFICO] if x.get("vista") in ("grafico", "grafica") else []),
            *([o.get("filtro"), o.get("orden")] if x.get("vista") == "tabla" else [])]


# ───────── Ejecutar ─────────

def ejecutar(doc: dict, nombre: str, args: dict | None = None, contexto: dict | None = None) -> dict:
    """Ejecuta UNA herramienta de diseño. Devuelve {ok, doc, resultado, etiqueta, vista}: `resultado` es el texto que lee el modelo."""
    args0 = args if isinstance(args, dict) else {}
    ctx = contexto or {}
    r = _ejecutar(doc, nombre, dict(args0), ctx)
    r.setdefault("vista", ctx.get("vista") or "inicio")
    r["etiqueta"] = etiqueta_cambio({"herramienta": nombre, "args": args0}) if r["ok"] else None
    return r


# Las que despacha el chat, no este módulo (datos: registros.py; deshacer: puntos.py; leer_enlace: red).
DEL_CHAT = frozenset([*(h["function"]["name"] for h in HERRAMIENTAS_DATOS), "deshacer", "leer_enlace"])


def _ejecutar(doc: dict, nombre: str, args: dict, ctx: dict) -> dict:
    if nombre in DEL_CHAT:
        raise ValueError(f"«{nombre}» la despacha el chat (registros.py / puntos.py), no edicion.ejecutar")
    vista = ctx.get("vista") or "inicio"
    if nombre in HERR_BLOQUE:
        # Si la persona está MIRANDO una pestaña, las piezas van ahí por defecto; tocar el inicio desde ahí exige decirlo
        # (pestana="inicio"). Medido: «aquí pon un resumen» mirando Miembros cambiaba el inicio y decía «en la pestaña Miembros».
        mirando = vista if vista != "inicio" else None
        if mirando and not verdad(args.get("pestana")):
            if nombre == "agregar_bloque":
                args = {**args, "pestana": mirando}
            elif verdad(args.get("bloque")) and not lienzo_de_bloque(doc, args["bloque"]):
                return _no(doc, f"la persona está mirando la pestaña «{mirando}» y «{js(args['bloque'])}» es un bloque del INICIO (no se ve aquí). Usa "
                                f"los bloques de esta pestaña (pestanas_con_piezas, o p_{mirando} si no tiene) o, si pidió el inicio, pon pestana=\"inicio\".",
                           sin_prefijo=False)
        p = args.get("pestana")
        pid = p if verdad(p) and p != "inicio" else lienzo_de_bloque(doc, arg(args, "bloque"))
        if pid:
            efectiva = plantilla_efectiva(doc)
            sec = next((x for x in efectiva["secciones"] if x["id"] == pid), None) \
                or next((x for x in efectiva["secciones"] if x["id"] == f"l_{js(pid)}"), None)  # «miembros» → l_miembros
            if not sec:
                return _no(doc, f"la pestaña «{js(pid)}» no existe. Pestañas: inicio, {', '.join(x['id'] for x in efectiva['secciones'] if paginable(x))}.")
            if args.get("bloque") == f"p_{js(pid)}" and pid != sec["id"]:
                args = {**args, "bloque": f"p_{sec['id']}"}  # la pieza por defecto nombrada sin `l_` (p_miembros → p_l_miembros)
            pid = sec["id"]
            pagina = pagina_de(efectiva, doc, pid)
            if pagina is None:
                return _no(doc, f"«{sec['titulo']}» no admite piezas (es una pestaña fija del sistema).")
            # La MISMA lógica del inicio sobre el lienzo de la pestaña (validación, acomodo, ubicación), con la vista neutra.
            interno = {k: v for k, v in args.items() if k != "pestana"}
            if nombre == "agregar_bloque" and not verdad(args.get("seccion")):
                interno["seccion"] = pid
            r = _ejecutar({**doc, "inicio": pagina}, nombre, interno, {**ctx, "vista": "inicio"})
            if not r["ok"]:
                return {**r, "doc": doc, "vista": vista}
            d = r["doc"]
            return {**r, "vista": vista, "doc": {**d, "inicio": doc.get("inicio") or [], "paginas": {**(d.get("paginas") or {}), pid: d.get("inicio") or []}},
                    "resultado": f"En la pestaña «{sec['titulo']}»: {r['resultado']}"}

    if nombre in tm.NOMBRES_TOMA:
        efectiva = plantilla_efectiva(doc)
        t = tm.ejecutar_toma(doc, nombre, args, catalogo_toma(efectiva), ctx.get("texto") or "", bool(ctx.get("digresion")))
        r0, nuevos = {"ok": t["ok"], "doc": t["doc"], "resultado": t["resultado"]}, False
    else:
        r0, nuevos = _ejecutar_sin(doc, nombre, args, ctx)
    if not r0["ok"]:
        return r0
    r = r0
    if nuevos:
        # Acomodo automático tras cada cambio de bloques; lo que la persona acaba de redimensionar queda como lo pidió.
        antes = r0["doc"].get("inicio") or []
        acomodados = acomodar(antes, {args.get("bloque")} if nombre == "cambiar_tamano" else set())
        tocados = [b["uid"] for b, a in zip(acomodados, antes) if b.get("ancho") != a.get("ancho") or b.get("alto") != a.get("alto")]
        # Hecho calculado, no instrucción: el modelo sabe que el acomodo ya ocurrió (antes «compensaba» achicando otro bloque).
        r = {**r0, "doc": {**r0["doc"], "inicio": acomodados},
             "resultado": f"{r0['resultado']} El código ya acomodó solo {', '.join(js(x) for x in tocados)} para que no quede hueco." if tocados else r0["resultado"]}
    # Cada resultado dice dónde quedó TODO de verdad: el modelo describe eso, no lo que supone.
    return {**r, "resultado": f"{r['resultado']} Así se ve ahora: {asi_se_ve(r['doc'].get('inicio') or [])}."}


def construir_desde_ficha(doc: dict, ahora_ms: int | None = None) -> dict:
    """«Sí» a la ficha de diseño: el CÓDIGO arma el inicio desde la ficha (toma.py) con el acomodo del lienzo y la validación de la
    plantilla completa con esos bloques como inicio (como `construirDesdeFicha`). Devuelve {doc, errores}; con errores no cambia nada."""
    return tm.construir_desde_ficha(doc, acomodar, lambda d: validar_plantilla({**plantilla_efectiva(d), "inicio": d.get("inicio") or []}),
                                    list(FUENTES), ahora_ms=ahora_ms)


def asi_se_ve(bs: list[dict]) -> str:
    """«b0 (kpis) → fila 1, ancho completo; …»: dónde cae cada pieza del lienzo."""
    u = ubicar(bs)
    return "; ".join(f"{js(b.get('uid'))} ({js(b.get('vista'))}) → {ubicacion(u.get(b.get('uid')))}" for b in bs)


def _no(doc: dict, texto: str, sin_prefijo: bool = False) -> dict:
    return {"ok": False, "doc": doc, "resultado": texto if sin_prefijo else f"ERROR: {texto}"}


def _si(doc: dict, texto: str, **extra: Any) -> dict:
    return {"ok": True, "doc": doc, "resultado": texto, **extra}


# ───────── Cada herramienta ─────────

def _ejecutar_sin(doc: dict, nombre: str, args: dict, ctx: dict) -> tuple[dict, bool]:
    """Una herramienta sobre el inicio (o sobre el lienzo de una pestaña puesto como inicio). → (resultado, ¿cambió la lista de bloques?)."""
    doc = doc if doc.get("toma") else {**doc, "toma": tm.toma_vacia()}
    bloqueo = tm.bloqueo_en_toma(doc, nombre, bool(ctx.get("digresion")))
    if bloqueo:
        return _no(doc, bloqueo, sin_prefijo=True), False
    efectiva = plantilla_efectiva(doc)
    secciones = efectiva["secciones"]
    por_id = {s["id"]: s for s in secciones}
    inicio = doc.get("inicio") or []
    ahora = ctx.get("ahora")

    def no(texto: str) -> tuple[dict, bool]:
        return _no(doc, texto), False

    def con_bloques(bs: list[dict], texto: str) -> tuple[dict, bool]:
        return _si({**doc, "inicio": bs}, texto), True

    def con_estructura(escribir, texto) -> tuple[dict, bool]:
        """Cambio de estructura con las funciones de Carlos; se valida la plantilla COMPLETA resultante: si algo queda inválido, no se
        aplica. `texto` puede ser una función del documento nuevo (para decir lo que de verdad quedó guardado)."""
        try:
            nuevo = escribir()
        except ErrorCrm as e:
            return no(e.mensaje)
        errores = validar_plantilla(plantilla_efectiva(nuevo))
        if errores:
            return no(" ".join(errores))
        return _si(nuevo, texto(nuevo) if callable(texto) else texto), False

    def lista_de_campos(sec: dict) -> str:
        return ", ".join(js(x.get("id")) for x in sec.get("campos") or [])

    def ids_con_registros() -> str:
        return ", ".join(x["id"] for x in secciones if con_registros(x))

    if nombre == "quitar_bloque":
        b = next((x for x in inicio if x.get("uid") == arg(args, "bloque")), None)
        if not b:
            return no(f"no existe el bloque «{js(arg(args, 'bloque'))}». Usa los id de \"bloques\".")
        # Quitar es lo único que borra algo de la pantalla (es reversible con los puntos de deshacer).
        titulo = js((por_id.get(b.get("seccion")) or {}).get("titulo", FALTA))
        return con_bloques([x for x in inicio if x is not b], f"Quitado el bloque {js(b.get('uid'))} ({js(b.get('vista'))} de {titulo}).")

    if nombre in ("agregar_bloque", "cambiar_visual"):
        viejo = next((x for x in inicio if x.get("uid") == arg(args, "bloque")), None) if nombre == "cambiar_visual" else None
        if nombre == "cambiar_visual" and not viejo:
            return no(f"no existe el bloque «{js(arg(args, 'bloque'))}».")
        s = seccion_de(secciones, _o(args.get("seccion"), (viejo or {}).get("seccion", FALTA)))
        if not s:
            return no(f"la sección «{js(arg(args, 'seccion'))}» no existe. Secciones: {ids_con_registros()}.")
        vista = arg(args, "vista")
        if vista not in VISTAS_INICIO:
            return no(f"la vista «{js(vista)}» no existe en el inicio. Vistas posibles: {', '.join(VISTAS_INICIO)}.")
        crudas = args.get("opciones")
        opciones = normalizar_opciones(vista, crudas if verdad(crudas) and isinstance(crudas, dict) else {})
        campos = campos_de(s, por_id)
        errores = revisar_vista(vista, opciones, campos, f"«{s['titulo']}»")
        if vista == "grafico":
            graficos = plantillas.graficos()
            posibles = [g["id"] for g in plantillas.compatibles(campos)]
            tipo = opciones.get("tipo", FALTA)
            if not isinstance(tipo, str) or tipo not in graficos:
                errores.append(f"el gráfico «{js(tipo)}» no existe. Con {s['titulo']} se pueden: {', '.join(posibles)}.")
            elif tipo not in posibles:
                errores.append(f"«{graficos[tipo]['nombre']}» no se puede dibujar con los campos de {s['titulo']}. Posibles: {', '.join(posibles)}.")
            for k in ("valor", "agrupar", "estado", "fecha", "texto", "x", "y"):
                v = opciones.get(k)
                if verdad(v) and v != "mes" and not any(c["id"] == v for c in campos):
                    errores.append(f"«{k}» apunta al campo «{js(v)}», que no existe en {s['titulo']}.")
        if errores:
            return no(" ".join(errores))
        ancho_def = 12 if vista in ANCHO_COMPLETO else 6
        alto_def = 1 if vista == "kpis" else 2
        b = {**(viejo or {}), "uid": (viejo or {}).get("uid") or nuevo_uid(doc), "seccion": s["id"], "vista": vista, "opciones": opciones,
             "ancho": ajustar_ancho(_o(js_num(arg(args, "ancho")), (viejo or {}).get("ancho"), ancho_def)),
             "alto": entero(_min_max(_o(js_num(arg(args, "alto")), (viejo or {}).get("alto"), alto_def), 1, ALTO_MAX))}
        if viejo:
            return con_bloques([b if x is viejo else x for x in inicio], f"El bloque {b['uid']} ahora es {b['vista']} de {s['titulo']}.")
        # Una pieza igual a otra que ya está en este lienzo (D55): medido, «en el inicio quiero ver las clases» agregaba una 2.ª agenda.
        igual = next((x for x in inicio if _huella(x) == _huella(b)), None)
        if igual and not ctx.get("confirmado"):
            return no(f"ya hay una pieza igual en este lienzo ({js(igual.get('uid'))}). No la dupliques: si quería verla más grande o en otro lugar, usa "
                      "cambiar_tamano o mover_bloque; si de verdad quiere otra igual, pregúntale.")
        n = js_num(arg(args, "posicion"))
        pos = int(_min_max((_o(n, len(inicio) + 1)) - 1, 0, len(inicio)))
        bs = [*inicio]
        bs.insert(pos, b)
        return con_bloques(bs, f"Agregado el bloque {b['uid']}: {b['vista']} de {s['titulo']}, ancho {js(b['ancho'])}, alto {js(b['alto'])}, posición {pos + 1}.")

    if nombre == "cambiar_tamano":
        b = next((x for x in inicio if x.get("uid") == arg(args, "bloque")), None)
        if not b:
            return no(f"no existe el bloque «{js(arg(args, 'bloque'))}».")
        ancho = ajustar_ancho(js_num(args["ancho"])) if args.get("ancho") is not None else b.get("ancho")
        alto = entero(_min_max(js_num(args["alto"]), 1, ALTO_MAX)) if args.get("alto") is not None else b.get("alto")
        if b.get("vista") == "kpis" and alto != b.get("alto"):
            return no("el resumen (kpis) siempre mide una fila; solo se le puede cambiar el ancho.")
        # fijo: el acomodo de órdenes SIGUIENTES no deshace un tamaño que la persona pidió.
        return con_bloques([{**b, "ancho": ancho, "alto": alto, "fijo": True} if x is b else x for x in inicio],
                           f"Bloque {js(b.get('uid'))}: ancho {js(ancho)}, alto {js(alto)}.")

    if nombre == "mover_bloque":
        b = next((x for x in inicio if x.get("uid") == arg(args, "bloque")), None)
        if not b:
            return no(f"no existe el bloque «{js(arg(args, 'bloque'))}».")
        resto = [x for x in inicio if x is not b]
        pos = int(_min_max(_o(js_num(arg(args, "posicion")), 1) - 1, 0, len(resto)))
        resto.insert(pos, b)
        return con_bloques(resto, f"Bloque {js(b.get('uid'))} movido a la posición {pos + 1}.")

    if nombre == "cambiar_rangos":
        b = next((x for x in inicio if x.get("uid") == arg(args, "bloque")), None)
        if not b:
            return no(f"no existe el bloque «{js(arg(args, 'bloque'))}».")
        if b.get("vista") != "vencimientos":
            return no(f"el bloque {js(b.get('uid'))} es {js(b.get('vista'))}; los rangos solo existen en vencimientos.")
        rangos = []
        for r in args.get("rangos") or []:
            r = r if isinstance(r, dict) else {}
            vencidos = verdad(r.get("vencidos"))
            rangos.append({"desde": None if vencidos else entero(js_num(arg(r, "desde"))), "hasta": -1 if vencidos else entero(js_num(arg(r, "hasta")))})
        if not rangos or len(rangos) > 5:
            return no("da entre 1 y 5 rangos.")
        for r in rangos:
            d, h = r["desde"], r["hasta"]
            if d is not None and not (math.isfinite(d) and math.isfinite(h) and h >= d and d >= 0 and h <= 365):
                return no("cada rango es {desde, hasta} en días (0 a 365, hasta ≥ desde), o {vencidos: true}.")
        dias = sorted([r for r in rangos if r["desde"] is not None], key=lambda r: r["desde"])
        pisados = [f"{js(dias[i]['desde'])}-{js(dias[i]['hasta'])} y {js(r['desde'])}-{js(r['hasta'])}" for i, r in enumerate(dias[1:]) if r["desde"] <= dias[i]["hasta"]]
        texto = f"Rangos del bloque {js(b.get('uid'))}: {', '.join(_rango(r) for r in rangos)}."
        if pisados:
            texto += f" AVISO: se pisan ({'; '.join(pisados)}): quien vence en esos días aparece en los dos grupos. Díselo a la persona en una línea y ofrece ajustarlo."
        return con_bloques([{**b, "opciones": {**(b.get("opciones") or {}), "rangos": rangos}} if x is b else x for x in inicio], texto)

    if nombre == "cambiar_marca":
        m = dict(doc.get("marca") or {})
        for k in ("primario", "secundario", "fondo", "superficie", "texto"):
            v = arg(args, k)
            if v is None or v == "":
                m.pop(k, None)
            elif v is not FALTA:
                if not es_hex(v):
                    return no(f"«{k}» debe ser un color hexadecimal como #1E40AF (llegó «{js(v)}»).")
                m[k] = v if v.startswith("#") else f"#{v}"
        for k in ("fuenteTitulos", "fuenteTexto"):
            v = arg(args, k)
            if v is None or v == "":
                m.pop(k, None)
            elif v is not FALTA:
                if not es_fuente(v):
                    return no(f"la tipografía «{js(v)}» no está disponible. Disponibles: {', '.join(FUENTES)}.")
                m[k] = v
        if "nombre" in args:
            m["nombre"] = js(args["nombre"])[:40]
        # El código prueba la marca en los dos temas y dice qué tuvo que ajustar para que se lea.
        ajustes = [*tokens_de_marca(m, "claro")["ajustes"], *tokens_de_marca(m, "oscuro")["ajustes"]]
        aplicada = ", ".join(f"{k} {js(v)}" for k, v in m.items() if k not in ("logo", "logo_id")) or "base de Shifu"
        return _si({**doc, "marca": m}, f"Marca aplicada: {aplicada}." + (f" AJUSTES para que se lea: {'; '.join(ajustes)}. Díselo en una línea." if ajustes else "")), False

    if nombre == "usar_logo":
        imagen = ctx.get("imagen")
        err = revisar_logo(imagen)
        if err:
            return no(err)
        logo_id = ctx.get("logo_id") or "logo_" + hashlib.sha256(imagen.encode()).hexdigest()[:16]
        extra = {} if ctx.get("logo_id") else {"logo": {"id": logo_id, "imagen": imagen}}
        return _si({**doc, "marca": {**(doc.get("marca") or {}), "logo_id": logo_id}},
                   "Logo puesto en el encabezado. En tema oscuro, si el logo es oscuro, se muestra una versión clara automática.", **extra), False

    if nombre == "restablecer_marca":
        return _si({**doc, "marca": {}}, "Volvió el diseño base de Shifu (colores, fondos y tipografía originales, sin logo)."), False

    if nombre == "crear_seccion":
        return _crear_seccion(doc, args, ctx, secciones, no, con_estructura)

    if nombre == "agregar_campo":
        sec = seccion_de(secciones, arg(args, "seccion"))
        if not sec or sec.get("campos") is None:
            return no(f"la sección «{js(arg(args, 'seccion'))}» no existe o no tiene campos.")
        tipo = arg(args, "tipo")
        if tipo not in TIPOS_CAMPO:
            return no(f"tipo «{js(tipo)}» no existe ({', '.join(TIPOS_CAMPO)}).")
        c = {"id": slug(arg(args, "nombre")), "nombre": nombre_literal(arg(args, "nombre"), ctx.get("texto"))[:24], "tipo": tipo,
             **({"opciones": [js(o) for o in args["opciones"][:7]]} if verdad(args.get("opciones")) else {}),
             **({"ejemplos": [js(o) for o in args["ejemplos"][:12]]} if verdad(args.get("ejemplos")) else {})}
        if any(x["id"] == c["id"] or x["nombre"].lower() == c["nombre"].lower() for x in sec["campos"]):
            return no(f"«{sec['titulo']}» ya tiene el campo «{c['nombre']}».")
        if sec.get("virtual") == "tareas":
            return no(f"«{sec['titulo']}» no admite campos nuevos: sus campos son fijos ({lista_de_campos(sec)}).")
        if sec.get("virtual") != "contactos" and len(sec["campos"]) >= MAX_CAMPOS_SECCION:
            return no(f"«{sec['titulo']}» ya tiene {MAX_CAMPOS_SECCION} campos (el máximo).")
        candidata = {**efectiva, "secciones": [{**x, "campos": [*x["campos"], c]} if x is sec else x for x in secciones]}
        errores = validar_plantilla(candidata)
        if errores:
            return no(" ".join(errores))
        ambito = "contactos" if sec.get("virtual") == "contactos" else sec["id"]

        def escribir() -> dict:
            out = estructura.campo_agregar(doc, ambito, c["nombre"], tipo, ahora, opciones=c.get("opciones"))
            campos_guardados = out["campos_contacto"] if ambito == "contactos" else _lista(out, ambito)["campos"]
            nuevo = campos_guardados[-1]
            if ambito != "contactos":
                nuevo["id"] = c["id"]  # como en el laboratorio: el id es el nombre en minúsculas sin acentos con _
                if c.get("ejemplos"):
                    nuevo["ejemplos"] = c["ejemplos"]
            return out

        def texto(out: dict) -> str:
            g = (out["campos_contacto"] if ambito == "contactos" else _lista(out, ambito)["campos"])[-1]
            return f"Campo «{g['nombre']}» ({tipo}) agregado a «{sec['titulo']}»." + (f" Su id es {g['id']}." if g["id"] != c["id"] else "")
        return con_estructura(escribir, texto)

    if nombre == "renombrar_seccion":
        sec = seccion_de(secciones, arg(args, "seccion"))
        if not sec:
            return no(f"la sección «{js(arg(args, 'seccion'))}» no existe.")
        titulo = js(_o(args.get("titulo"), "")).strip()[:28]
        if not titulo:
            return no("falta el nuevo nombre.")

        def texto(out: dict) -> str:
            nuevo = next((x["titulo"] for x in plantilla_efectiva(out)["secciones"] if x["id"] == sec["id"]), titulo)
            return f"«{sec['titulo']}» ahora se llama «{nuevo}»."
        return con_estructura(lambda: op.seccion_renombrar(doc, sec["id"], titulo, ahora), texto)

    if nombre == "quitar_seccion":
        sec = seccion_de(secciones, arg(args, "seccion"))
        if not sec:
            return no(f"la sección «{js(arg(args, 'seccion'))}» no existe.")
        es_lista = not sec.get("virtual") and not sec.get("fija")
        if es_lista:
            texto = (f"Sección «{sec['titulo']}» quitada del menú con sus registros (se puede deshacer). "
                     "También se quitaron sus bloques del inicio.")
            r, _ = con_estructura(lambda: estructura.lista_eliminar(doc, sec["id"], ahora), texto)
        else:
            texto = (f"Sección «{sec['titulo']}» quitada del menú (sus datos se conservan; se puede volver a mostrar). "
                     "También se quitaron sus bloques del inicio.")
            r, _ = con_estructura(lambda: estructura.seccion_ocultar(doc, sec["id"], ahora), texto)
        if not r["ok"]:
            return r, False
        # También se va su lienzo y las piezas que la usan en otras pestañas (si no, quedarían bloques sin sección).
        d = r["doc"]
        paginas = {pid: [b for b in bs if b.get("seccion") != sec["id"]] for pid, bs in (d.get("paginas") or {}).items() if pid != sec["id"]}
        return {**r, "doc": {**d, "inicio": [b for b in d.get("inicio") or [] if b.get("seccion") != sec["id"]], "paginas": paginas}}, True

    # ── Ficha, tarjeta y campos (D28): todo editable por chat; el código cuida que nada quede huérfano ──
    if nombre in ("cambiar_ficha", "cambiar_tarjeta"):
        sec = seccion_de(secciones, arg(args, "seccion"))
        if not con_registros(sec):
            return no(f"la sección «{js(arg(args, 'seccion'))}» no existe o no tiene registros.")
        campos = campos_de(sec, por_id)
        if sec.get("virtual"):
            que = "la ficha" if nombre == "cambiar_ficha" else "las tarjetas"
            return no(f"{que} de «{sec['titulo']}» todavía no se puede cambiar (es una sección del sistema).")
        nombre_de = {c["id"]: c.get("nombre") for c in campos}
        if nombre == "cambiar_ficha":
            grupos = [{"titulo": js(_o((g if isinstance(g, dict) else {}).get("titulo"), "Datos"))[:28],
                       "campos": [js(x) for x in (g if isinstance(g, dict) else {}).get("campos") or []]} for g in args.get("grupos") or []]
            if not grupos:
                return no("la ficha necesita al menos un grupo con campos.")
            malos = [i for g in grupos for i in g["campos"] if i not in nombre_de]
            if malos:
                return no(f"estos campos no existen en {sec['titulo']}: {', '.join(malos)}. Campos: {_campos_txt(campos)}.")
            usados = [i for g in grupos for i in g["campos"]]
            repetido = next((i for k, i in enumerate(usados) if usados.index(i) != k), None)
            if repetido:
                return no(f"el campo «{repetido}» aparece en dos grupos: cada campo va en un solo grupo.")
            ficha = {"grupos": grupos, "relacionados": True if args.get("relacionados") is None else args["relacionados"],
                     "linea_tiempo": True if args.get("linea_tiempo") is None else args["linea_tiempo"]}
            fuera = [c.get("nombre") for c in campos if c["id"] not in usados]
            texto = (f"Ficha de {sec['titulo']}: {' · '.join(_grupo_txt(g, nombre_de) for g in grupos)}"
                     + (f". No se muestran: {', '.join(js(x) for x in fuera)}" if fuera else "")
                     + f". Relacionados: {'sí' if verdad(ficha['relacionados']) else 'no'}. Línea de tiempo: {'sí' if verdad(ficha['linea_tiempo']) else 'no'}.")

            def escribir() -> dict:
                out = op._copia(doc)
                _lista(out, sec["id"])["ficha"] = ficha
                return out
            return con_estructura(escribir, texto)
        ids = [js(x) for x in args.get("campos") or []]
        if not ids or len(ids) > 4:
            return no("la tarjeta lleva de 1 a 4 campos (el primero es el título).")
        malos = [i for i in ids if i not in nombre_de]
        if malos:
            return no(f"estos campos no existen en {sec['titulo']}: {', '.join(malos)}.")

        def escribir_t() -> dict:
            out = op._copia(doc)
            _lista(out, sec["id"])["tarjeta"] = {"campos": ids}
            return out
        return con_estructura(escribir_t, f"Las tarjetas de {sec['titulo']} ahora muestran: {', '.join(js(nombre_de[i]) for i in ids)} (el primero como título).")

    if nombre in ("quitar_campo", "renombrar_campo", "cambiar_opciones_estado"):
        sec = seccion_de(secciones, arg(args, "seccion"))
        if not sec or sec.get("campos") is None:
            return no(f"la sección «{js(arg(args, 'seccion'))}» no existe o no tiene campos propios.")
        c = next((x for x in sec["campos"] if x["id"] == arg(args, "campo")), None)
        if nombre == "cambiar_opciones_estado":
            return _cambiar_opciones_estado(doc, sec, c, args, ahora, no, con_estructura)
        if not c:
            return no(f"«{sec['titulo']}» no tiene el campo «{js(arg(args, 'campo'))}». Campos: {lista_de_campos(sec)}.")
        fijo = sec.get("virtual") == "tareas" or (sec.get("virtual") == "contactos" and c["id"] in _FIJOS_CONTACTO)
        if nombre == "quitar_campo":
            if len(sec["campos"]) <= 1:
                return no(f"«{sec['titulo']}» se quedaría sin campos.")
            en_bloques = [b for b in inicio if b.get("seccion") == sec["id"] and f'"{c["id"]}"' in json.dumps(b.get("opciones") or {}, ensure_ascii=False)]
            if en_bloques:
                return no(f"el campo «{c['nombre']}» lo usan estos bloques del inicio: {_bloques_txt(en_bloques)}. Cámbialos o quítalos primero "
                          "(con permiso de la persona).")
            if fijo:
                return no(f"el campo «{c['nombre']}» es fijo de «{sec['titulo']}»: no se puede quitar.")
            ambito = "contactos" if sec.get("virtual") == "contactos" else sec["id"]

            def escribir_q() -> dict:
                out = estructura.campo_eliminar(doc, ambito, c["id"], ahora)
                if ambito != "contactos":
                    l = _lista(out, ambito)
                    if l.get("ficha"):
                        l["ficha"] = {**l["ficha"], **({"grupos": [{**g, "campos": [x for x in g.get("campos") or [] if x != c["id"]]} for g in l["ficha"]["grupos"]]}
                                                     if l["ficha"].get("grupos") else {})}
                    if l.get("tarjeta"):
                        l["tarjeta"] = {**l["tarjeta"], **({"campos": [x for x in l["tarjeta"]["campos"] if x != c["id"]]} if l["tarjeta"].get("campos") else {})}
                return out
            return con_estructura(escribir_q, f"Campo «{c['nombre']}» quitado de «{sec['titulo']}» con sus datos (se puede deshacer).")
        # renombrar_campo
        nuevo = js(_o(args.get("nombre"), "")).strip()[:24]
        if not nuevo:
            return no("falta el nuevo nombre.")
        if any(x is not c and x["nombre"].lower() == nuevo.lower() for x in sec["campos"]):
            return no(f"«{sec['titulo']}» ya tiene un campo «{nuevo}».")
        if fijo:
            return no(f"el campo «{c['nombre']}» es fijo de «{sec['titulo']}»: no se puede renombrar.")
        ambito = "contactos" if sec.get("virtual") == "contactos" else sec["id"]

        def texto_r(out: dict) -> str:
            guardado = next(x["nombre"] for x in (out["campos_contacto"] if ambito == "contactos" else _lista(out, ambito)["campos"]) if x["id"] == c["id"])
            return f"El campo «{c['nombre']}» de «{sec['titulo']}» ahora se llama «{guardado}»."
        return con_estructura(lambda: estructura.campo_renombrar(doc, ambito, c["id"], nuevo, ahora), texto_r)

    if nombre == "abrir_seccion":
        s = seccion_de(secciones, arg(args, "seccion"))
        if not s and arg(args, "seccion") != "inicio":
            return no(f"la sección «{js(arg(args, 'seccion'))}» no existe.")
        return _si(doc, f"Abierta la sección {s['titulo'] if s else 'Inicio'}.", vista=s["id"] if s else "inicio"), False

    return no(f"la herramienta «{js(nombre)}» no existe.")


def _rango(r: dict) -> str:
    return "Vencidos" if r["desde"] is None else f"{js(r['desde'])}-{js(r['hasta'])} días"


def _campos_txt(campos: list[dict]) -> str:
    return ", ".join(f"{c['id']} ({js(c.get('nombre'))})" for c in campos)


def _grupo_txt(g: dict, nombre_de: dict) -> str:
    return f"«{g['titulo']}» ({', '.join(js(nombre_de[i]) for i in g['campos'])})"


def _bloques_txt(bs: list[dict]) -> str:
    return ", ".join(f"{js(b.get('uid'))} ({js(b.get('vista'))})" for b in bs)


def _crear_seccion(doc: dict, args: dict, ctx: dict, secciones: list[dict], no, con_estructura) -> tuple[dict, bool]:
    """Sección NUEVA en el menú. Desde la biblioteca de pestañas (`desde`): campos, vista y piezas ya probados (la IA no inventa campos
    cuando existe la pestaña). Se guarda con `estructura.lista_crear` y se completa con lo del esquema 2 (vista, opciones, ícono…)."""
    pestanas = _pestanas()
    desde = arg(args, "desde")
    base = pestanas.get(desde) if verdad(desde) and isinstance(desde, str) else None
    if verdad(desde) and not base:
        return no(f"no hay una pestaña base «{js(desde)}». Las que hay: {', '.join(pestanas)}. O créala con sus campos sin «desde».")
    if base:
        args = {**args, "titulo": _o(args.get("titulo"), base["seccion"]["titulo"]), "vista": base["seccion"].get("vista", FALTA),
                "opciones": base["seccion"].get("opciones", FALTA), "campos": base["seccion"].get("campos", FALTA)}
    titulo = js(_o(args.get("titulo"), "")).strip()[:28]
    if not titulo:
        return no("falta el título de la sección.")
    if any(str(x.get("titulo") or "").lower() == titulo.lower() for x in secciones):
        return no(f"ya existe una sección «{titulo}»: úsala o agrégale campos en vez de duplicarla.")
    campos = []
    for c in (_o(args.get("campos"), []) if isinstance(args.get("campos"), list) else [])[:MAX_CAMPOS_SECCION]:
        c = c if isinstance(c, dict) else {}
        campo = {"id": c.get("id") if base else slug(arg(c, "nombre")),
                 "nombre": (js(arg(c, "nombre")) if base else nombre_literal(arg(c, "nombre"), ctx.get("texto")))[:24], "tipo": arg(c, "tipo")}
        if verdad(c.get("opciones")):
            campo["opciones"] = [js(o) for o in c["opciones"][:7]]
        if verdad(c.get("ejemplos")):
            campo["ejemplos"] = [js(o) for o in c["ejemplos"][:12]]
        if verdad(c.get("rango")):
            campo["rango"] = c["rango"]
        campos.append(campo)
    if not campos:
        return no("una sección necesita al menos un campo.")
    malo = next((c for c in campos if c["tipo"] not in TIPOS_CAMPO), None)
    if malo:
        return no(f"el campo «{malo['nombre']}» tiene tipo «{js(malo['tipo'])}»; tipos posibles: {', '.join(TIPOS_CAMPO)}.")
    usados = {x["id"] for x in secciones} | {l["id"] for l in doc.get("listas") or []}
    sid = f"l_{slug(titulo)}"
    while sid in usados:
        sid += "_2"
    vista = args.get("vista") if args.get("vista") in VISTAS_SECCION else "tabla"
    icono = (base or {}).get("seccion", {}).get("icono") or {"tablero": "tablero", "agenda": "calendario", "vencimientos": "reloj"}.get(vista) or "tabla"
    opciones = args.get("opciones") if verdad(args.get("opciones")) and args.get("opciones") is not FALTA else None
    secc = {"id": sid, "titulo": titulo, "grupo": 1 if args.get("grupo") == 1 else 0, "icono": icono, "vista": vista,
            **({"opciones": opciones} if opciones is not None else {}), "campos": campos}
    # Se valida como el laboratorio (sobre la plantilla completa con la sección nueva) ANTES de escribir: mismos textos de error.
    efectiva = plantilla_efectiva(doc)
    errores = validar_plantilla({**efectiva, "secciones": [*efectiva["secciones"], secc]})
    if errores:
        return no(" ".join(errores))

    def escribir() -> dict:
        # Una integrada oculta (p. ej. «Cobros» de Carlos, que aún no guarda datos) no ocupa el nombre: la persona no la ve.
        out = estructura.lista_crear(doc, titulo, [{"nombre": c["nombre"], "tipo": c["tipo"], "opciones": c.get("opciones")} for c in campos], ctx.get("ahora"),
                                     libres=set(doc.get("ocultas") or []))
        l = out["listas"].pop()
        l["id"] = sid
        for guardado, c in zip(l["campos"], campos):
            guardado["id"] = c["id"]
            for k in ("ejemplos", "rango"):
                if k in c:
                    guardado[k] = c[k]
        l.update({"vista": vista, "icono": icono, "grupo": secc["grupo"], **({"opciones": opciones} if opciones is not None else {}),
                  **({"origen": base["id"]} if base else {})})
        # En el menú va antes de las secciones de abajo (grupo > 0), como la plantilla efectiva del laboratorio.
        i = next((k for k, x in enumerate(out["listas"]) if (x.get("grupo") or 0) > 0), len(out["listas"]))
        out["listas"].insert(i, l)
        return out

    def texto(out: dict) -> str:
        l = _lista(out, sid)
        desde_txt = f" desde la pestaña base «{base['id']}»" if base else ""
        return f"Sección «{l['nombre']}» creada (id {sid}){desde_txt} con {len(l['campos'])} campos: {_campos_tipos(l['campos'])}. Vista: {vista}."
    r, _ = con_estructura(escribir, texto)
    if not r["ok"]:
        return r, False
    if not base or not verdad(args.get("con_piezas")):
        return {**r, "resultado": f"{r['resultado']} Puedes ponerla en el inicio con agregar_bloque{' o creándola con con_piezas' if base else ''}."}, False
    # Sus piezas sugeridas van al inicio (el acomodo automático tapa los huecos).
    d = r["doc"]
    nuevas = []
    for w in base.get("piezas") or []:
        uid = nuevo_uid({**d, "inicio": [*(d.get("inicio") or []), *nuevas]})
        nuevas.append({**w, "uid": uid, "seccion": sid, "ancho": w.get("ancho") or (12 if w.get("vista") in ANCHO_COMPLETO else 6),
                       "alto": 1 if w.get("vista") == "kpis" else (w.get("alto") or 2)})
    lista_txt = ", ".join(f"{b['uid']} ({'gráfico ' + js((b.get('opciones') or {}).get('tipo', FALTA)) if b.get('vista') == 'grafico' else b.get('vista')})" for b in nuevas)
    return {**r, "doc": {**d, "inicio": [*(d.get("inicio") or []), *nuevas]},
            "resultado": f"{r['resultado']} En el inicio se agregaron {len(nuevas)} bloques: {lista_txt}."}, True


def _campos_tipos(campos: list[dict]) -> str:
    return ", ".join(f"{c['nombre']} ({c['tipo']})" for c in campos)


def _cambiar_opciones_estado(doc: dict, sec: dict, c: dict | None, args: dict, ahora: datetime | None, no, con_estructura) -> tuple[dict, bool]:
    """Opciones de un campo de estado. Ninguna opción desaparece sin destino: sus registros pasan a la renombrada o a `pasar_a`, y el
    código los mueve de verdad (en las listas y en las etapas de los contactos)."""
    if not c or c.get("tipo") != "estado":
        estados = ", ".join(x["id"] for x in sec["campos"] if x.get("tipo") == "estado") or "ninguno"
        return no(f"«{js(arg(args, 'campo'))}» no es un campo de estado de «{sec['titulo']}». Estados: {estados}.")
    opciones: list[str] = []
    for o in args.get("opciones") or []:
        t = js(o).strip()[:24]
        if t and t not in opciones:
            opciones.append(t)
    if len(opciones) < 2 or len(opciones) > 8:
        return no("un estado lleva de 2 a 8 opciones.")
    previas = c.get("opciones") or []
    renombrar = {v: n for v, n in (args.get("renombrar") or {}).items() if v in previas and n in opciones} if isinstance(args.get("renombrar"), dict) else {}
    sin_destino = [o for o in previas if o not in opciones and not verdad(renombrar.get(o))]
    if sin_destino and args.get("pasar_a") not in opciones:
        return no(f"las opciones {', '.join(f'«{o}»' for o in sin_destino)} desaparecerían y sus registros quedarían sin estado. Di a cuál pasan con pasar_a "
                  f"(una de: {', '.join(opciones)}) o usa renombrar {{vieja: nueva}}.")
    ahora_mapa = {**renombrar, **{o: args["pasar_a"] for o in sin_destino}}
    virtual = sec.get("virtual")
    if virtual == "tareas":
        return no(f"los estados de «{sec['titulo']}» son fijos ({', '.join(previas)}).")
    anterior = {} if virtual else ((_lista(doc, sec["id"]).get("mapeo_estado") or {}).get(c["id"]) or {})
    mapa = {**anterior, **ahora_mapa}

    def a_guardada(guardadas: list[str], n: str) -> str:
        return next((g for g in guardadas if g.strip().lower() == n.strip().lower()), n)

    def escribir() -> dict:
        if virtual == "contactos" and c["id"] == "etapa":
            out = estructura.etapas_definir(doc, opciones, ahora)
            antes = {x["id"]: x.get("etapa") for x in doc["contactos"]}
            for x in out["contactos"]:
                e0 = antes.get(x["id"])
                if e0 in ahora_mapa:
                    x["etapa"] = a_guardada(out["etapas"], ahora_mapa[e0])
                elif any(e0 == g for g in opciones):
                    x["etapa"] = a_guardada(out["etapas"], e0)
            return out
        ambito = "contactos" if virtual == "contactos" else sec["id"]
        out = estructura.campo_hacer_lista(doc, ambito, c["id"], opciones, ahora)
        campos = out["campos_contacto"] if ambito == "contactos" else _lista(out, ambito)["campos"]
        guardado = next(x for x in campos if x["id"] == c["id"])
        original = next(x for x in (doc["campos_contacto"] if ambito == "contactos" else _lista(doc, ambito)["campos"]) if x["id"] == c["id"])
        guardado["tipo"] = original["tipo"]  # campo_hacer_lista lo deja como "lista": se conserva como estaba ("estado" o "lista")
        filas = [x.setdefault("extra", {}) for x in out["contactos"]] if ambito == "contactos" else [r["valores"] for r in _lista(out, ambito)["registros"]]
        for valores in filas:
            v = valores.get(c["id"])
            if isinstance(v, str) and v in ahora_mapa:
                valores[c["id"]] = a_guardada(guardado["opciones"], ahora_mapa[v])
        if ambito != "contactos":
            l = _lista(out, ambito)
            l["opciones_estado"] = {**(l.get("opciones_estado") or {}), c["id"]: list(guardado["opciones"])}
            l["mapeo_estado"] = {**(l.get("mapeo_estado") or {}), c["id"]: mapa}
        return out

    def texto(out: dict) -> str:
        s2 = next(x for x in plantilla_efectiva(out)["secciones"] if x["id"] == sec["id"])
        guardadas = next(x for x in s2["campos"] if x["id"] == c["id"]).get("opciones") or []
        pasan = f" Los registros pasan así: {', '.join(f'{v} → {js(n)}' for v, n in mapa.items())}." if mapa else ""
        return f"«{c['nombre']}» de «{sec['titulo']}» ahora tiene: {', '.join(guardadas)}.{pasan}"
    return con_estructura(escribir, texto)


# ───────── Esquemas para el modelo (formato OpenAI), LITERALES de edicion.js ─────────

def _herramienta(nombre: str, descripcion: str, propiedades: dict, requeridas: list[str]) -> dict:
    return {"type": "function", "function": {"name": nombre, "description": descripcion,
                                              "parameters": {"type": "object", "properties": propiedades, "required": requeridas}}}


_TIPOS_ENUM = ["texto", "numero", "dinero", "fecha", "hora", "estado"]

HERRAMIENTAS_EDICION: list[dict] = [
    _herramienta("quitar_bloque", "Quita un bloque (del inicio o de una pestaña: el código sabe dónde está por su id).",
                 {"bloque": {"type": "string", "description": "id del bloque, ej. b2"}}, ["bloque"]),
    _herramienta("agregar_bloque", "Agrega una pieza (bloque) al inicio o a cualquier pestaña, con una vista del catálogo sobre una sección. Cada pestaña es "
                 "un cuaderno en blanco: puede llevar varias piezas.", {
                     "pestana": {"type": "string", "description": "dónde va: \"inicio\" (por defecto) o el id de una sección. Si la persona está mirando "
                                 "una pestaña (pestana_abierta) y dice «aquí» o «en esta pestaña», es esa."},
                     "seccion": {"type": "string"}, "vista": {"type": "string", "enum": VISTAS_INICIO},
                     "opciones": {"type": "object", "description": "opciones de la vista: ids de campos (ver \"vistas\" y \"secciones\"). calendario_mes {fecha, "
                                  "titulo?, estado?}: el mes en rejilla con los registros de cada día (distinto del gráfico «calendario» de calor). "
                                  "tablero_dinero {por: estado, suma: dinero}: columnas con total. cifra {funcion: conteo|suma|promedio, valor?, meta?: "
                                  "número, fecha?: para comparar con el periodo anterior, periodo?: mes|semana, ayuda?: texto}. atencion {fecha, estado?, "
                                  "excluir?}: vencidos y por vencer. franjas {fecha, estado?, urgentes?: [opciones]}: bandeja por prioridad. matriz {filas: "
                                  "texto, columnas: estado}. Para grafico: {tipo: uno de graficos_posibles de esa sección, ...}. Para tabla: {filtro: "
                                  "{campo, menorOIgual: número o id de otro campo | mayorOIgual | igual}, orden: {campo, dir: asc|desc}, limite}",
                                  "additionalProperties": True},
                     "ancho": {"type": "integer", "enum": ANCHOS_COL}, "alto": {"type": "integer", "minimum": 1, "maximum": ALTO_MAX},
                     "posicion": {"type": "integer", "minimum": 1}}, ["seccion", "vista"]),
    _herramienta("cambiar_visual", "Cambia la vista o sus opciones de un bloque existente (mantiene su lugar y tamaño).", {
        "bloque": {"type": "string"}, "vista": {"type": "string", "enum": VISTAS_INICIO}, "opciones": {"type": "object", "additionalProperties": True},
        "seccion": {"type": "string"}}, ["bloque", "vista"]),
    _herramienta("cambiar_tamano", "Cambia el ancho (columnas de 12) y/o el alto (filas) de un bloque, SOLO cuando la persona pidió cambiar ese tamaño. No la "
                 "uses para acomodar después de quitar o agregar: el código tapa los huecos solo (acomodo automático).",
                 {"bloque": {"type": "string"}, "ancho": {"type": "integer", "enum": ANCHOS_COL}, "alto": {"type": "integer", "minimum": 1, "maximum": ALTO_MAX}},
                 ["bloque"]),
    _herramienta("mover_bloque", "Cambia el orden: pone el bloque en esa posición (1 = primero). Para que algo quede a la derecha de otro, va justo después y "
                 "la suma de anchos de la fila debe ser ≤ 12.", {"bloque": {"type": "string"}, "posicion": {"type": "integer", "minimum": 1}},
                 ["bloque", "posicion"]),
    _herramienta("cambiar_rangos", "Define los grupos de un bloque de vencimientos. Reemplaza TODOS los rangos: incluye los que se quedan.", {
        "bloque": {"type": "string"}, "rangos": {"type": "array", "items": {"type": "object", "properties": {
            "vencidos": {"type": "boolean"}, "desde": {"type": "integer"}, "hasta": {"type": "integer"}}}}}, ["bloque", "rangos"]),
    _herramienta("abrir_seccion", "Muestra una sección del menú (o \"inicio\").", {"seccion": {"type": "string"}}, ["seccion"]),
    _herramienta("cambiar_marca", "Cambia el branding del CRM: colores en hex (primario = color de marca principal, secundario, fondo, superficie = tarjetas, "
                 "texto), tipografías y nombre. Solo manda lo que cambia; \"\" para volver al de base en ese punto.", {
                     "primario": {"type": "string"}, "secundario": {"type": "string"}, "fondo": {"type": "string"}, "superficie": {"type": "string"},
                     "texto": {"type": "string"}, "fuenteTitulos": {"type": "string", "enum": list(FUENTES)},
                     "fuenteTexto": {"type": "string", "enum": list(FUENTES)}, "nombre": {"type": "string"}}, []),
    _herramienta("usar_logo", "Pone como logo del negocio la imagen que la persona adjuntó EN ESTE mensaje (SVG/PNG/WebP con fondo transparente).", {}, []),
    _herramienta("crear_seccion", "Crea una sección NUEVA en el menú. Si lo que pide está en \"pestanas_base\", usa desde = ese id (trae campos, vista y piezas "
                 "probados; no pases campos) y con_piezas = true si quiere verla también en el inicio. Si no está, pásale sus campos (máx. 8). Úsala "
                 "cuando la persona quiere llevar algo que hoy no existe (inventario, cobros, proveedores, lo que sea). Para tablero/vencimientos/agenda "
                 "pasa opciones (por: id campo estado / fecha: id campo fecha…); los id de campo son el nombre en minúsculas sin acentos con _ .", {
                     "desde": {"type": "string", "description": "id de pestanas_base"}, "con_piezas": {"type": "boolean"},
                     "titulo": {"type": "string"}, "vista": {"type": "string", "enum": ["tabla", "tablero", "agenda", "vencimientos"]},
                     "opciones": {"type": "object", "additionalProperties": True}, "grupo": {"type": "integer", "enum": [0, 1]},
                     "campos": {"type": "array", "items": {"type": "object", "properties": {
                         "nombre": {"type": "string"}, "tipo": {"type": "string", "enum": _TIPOS_ENUM}, "opciones": {"type": "array", "items": {"type": "string"}},
                         "ejemplos": {"type": "array", "items": {"type": "string"}}}, "required": ["nombre", "tipo"]}}}, []),
    _herramienta("agregar_campo", "Agrega un campo a una sección existente.", {
        "seccion": {"type": "string"}, "nombre": {"type": "string"}, "tipo": {"type": "string", "enum": _TIPOS_ENUM},
        "opciones": {"type": "array", "items": {"type": "string"}}, "ejemplos": {"type": "array", "items": {"type": "string"}}}, ["seccion", "nombre", "tipo"]),
    _herramienta("cambiar_ficha", "Define cómo se ve la FICHA de un registro (lo que se abre al tocar un cliente, una cita, un pedido…): grupos con título y "
                 "los campos de cada uno, en orden. Campos que no pongas no se muestran. relacionados = mostrar lo de otras secciones ligado a este "
                 "registro; linea_tiempo = sus fechas en orden.", {
                     "seccion": {"type": "string"}, "grupos": {"type": "array", "items": {"type": "object", "properties": {
                         "titulo": {"type": "string"}, "campos": {"type": "array", "items": {"type": "string"}, "description": "ids de campos"}},
                         "required": ["titulo", "campos"]}},
                     "relacionados": {"type": "boolean"}, "linea_tiempo": {"type": "boolean"}}, ["seccion", "grupos"]),
    _herramienta("cambiar_tarjeta", "Elige qué campos muestran las TARJETAS del tablero de una sección (1 a 4; el primero es el título).",
                 {"seccion": {"type": "string"}, "campos": {"type": "array", "items": {"type": "string"}}}, ["seccion", "campos"]),
    _herramienta("quitar_campo", "Deja de mostrar un campo de una sección (sus datos se conservan). Solo si la persona lo pidió.",
                 {"seccion": {"type": "string"}, "campo": {"type": "string", "description": "id del campo"}}, ["seccion", "campo"]),
    _herramienta("renombrar_campo", "Cambia el nombre visible de un campo.",
                 {"seccion": {"type": "string"}, "campo": {"type": "string"}, "nombre": {"type": "string"}}, ["seccion", "campo", "nombre"]),
    _herramienta("cambiar_opciones_estado", "Cambia las opciones de un campo de estado (agregar, quitar, renombrar o reordenar etapas). Pasa la lista COMPLETA "
                 "nueva. Si una opción desaparece, di a dónde pasan sus registros: renombrar {vieja: nueva} o pasar_a.", {
                     "seccion": {"type": "string"}, "campo": {"type": "string"}, "opciones": {"type": "array", "items": {"type": "string"}},
                     "renombrar": {"type": "object", "additionalProperties": {"type": "string"}}, "pasar_a": {"type": "string"}},
                 ["seccion", "campo", "opciones"]),
    _herramienta("renombrar_seccion", "Cambia el nombre de una sección.", {"seccion": {"type": "string"}, "titulo": {"type": "string"}}, ["seccion", "titulo"]),
    _herramienta("quitar_seccion", "Quita una sección del menú (y sus bloques del inicio). Solo si la persona lo pidió.", {"seccion": {"type": "string"}}, ["seccion"]),
    _herramienta("deshacer", "Anula UN pedido anterior de la persona (ver pedidos_anteriores: qué dijo y qué cambió). El código revierte solo lo que ese "
                 "pedido cambió y conserva lo demás. Úsalo para \"eso no\", \"como estaba antes\", \"deshaz lo del color\", \"deshaz también X\". Nunca lo uses "
                 "sin que la persona lo pida.", {"pedido": {"type": "integer", "minimum": 1, "description": "número de pedidos_anteriores"}}, ["pedido"]),
    _herramienta("restablecer_marca", "Vuelve al diseño base de Shifu (quita colores, tipografías y logo propios).", {}, []),
]

# La de chat.js (no está en edicion.js): leer un enlace público para el branding. La ejecuta el chat (red), no este módulo.
HERR_ENLACE = _herramienta("leer_enlace", "Abre un enlace público que pegó la persona (página web, Notion público, archivo de Google Drive compartido, imagen "
                           "o PDF) para leer su branding: colores, logo, textos. Figma privado no se puede abrir.", {"url": {"type": "string"}}, ["url"])

# El arreglo HERRAMIENTAS de edicion.js, en su orden: diseño, toma de diseño (toma.py) y datos (registros.py).
HERRAMIENTAS: list[dict] = [*HERRAMIENTAS_EDICION, *tm.TOMA_HERRAMIENTAS, *HERRAMIENTAS_DATOS]


def herramientas_para(doc: dict, imagen: Any = None, enlace: bool = True) -> list[dict]:
    """Las herramientas que tienen sentido en ESTE momento, según el ESTADO (nunca por lo que dice la persona): las de la ficha de
    diseño solo con la ficha abierta, usar_logo solo con una imagen. Medido: cada herramienta de más le quita atención al catálogo
    (con las 4 de datos, «quiero ver los vencimientos en un calendario» bajó de 16/16 a ~10/16). Como `herramientasPara` de chat.js."""
    activa = bool((doc.get("toma") or {}).get("activa"))
    out = [h for h in HERRAMIENTAS if (activa or h["function"]["name"] not in tm.SOLO_EN_TOMA) and (verdad(imagen) or h["function"]["name"] != "usar_logo")]
    return [*out, HERR_ENLACE] if enlace else out

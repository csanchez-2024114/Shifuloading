"""Meter, editar, borrar y consultar datos POR CHAT (port de la lógica pura de `laboratorio/src/plantillas/registros.js`, D50/D54).

El modelo copia lo que dijo la persona; el CÓDIGO entiende cada valor (`valores`), encuentra el registro y valida. Si un valor no se
entiende o dos registros coinciden, no adivina: devuelve ERROR con lo que hay que preguntar. Contar, sumar y filtrar lo hace el código.

A diferencia del laboratorio, aquí NO se toca ningún documento: `ejecutar_dato` devuelve la `operacion` que hay que aplicar y quien la
llama la aplica con `secciones_v` (registro_agregar / registro_actualizar / registro_eliminar):

    {"tipo": "agregar", "valores": {...}, "id": <id que nombra el texto>}
    {"tipo": "editar", "id": rid, "cambios": {...}}     # "" = dejar el campo vacío
    {"tipo": "borrar", "id": rid}

Las entradas tienen la forma de `secciones_v` (contrato §2): `sec` = {id, titulo, campos, tarjeta?, …}, `campos` = [{id, nombre, tipo,
opciones?}], `regs` = [{id, valores}]. Los textos de resultado y de error son LITERALES del laboratorio (el modelo se midió con ellos).
"""
from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any

from assistant.packs.crm.operaciones import nuevo_id
from assistant.packs.crm.regional import Region, region_de
from assistant.packs.crm.valores import (
    a_js,
    buscar_registro,
    campo_titulo,
    es_numero,
    fecha_larga,
    iso,
    numero_js,
    opcion_de,
    parse_fecha,
    parse_hora,
    parse_numero,
    parse_periodo,
    plantilla_js,
    recortar,
    sin_acentos,
    texto_js,
)

MAX_LISTA = 10
HERR_DATOS = frozenset({"agregar_registro", "editar_registro", "borrar_registro"})


def _tipo(c: dict) -> Any:
    t = c.get("tipo")
    return "estado" if t == "lista" else t  # "lista" (Carlos) = alias de "estado"


def _clave(t: Any) -> str:
    return re.sub(r"^_|_$", "", re.sub(r"[^a-z0-9]+", "_", sin_acentos(t)))


def _vals(r: dict) -> dict:
    return r.get("valores") or {}


def _vacio(v: Any) -> bool:
    return v is None or (isinstance(v, str) and v == "")


def _hoy(hoy: date | datetime) -> date:
    return date(hoy.year, hoy.month, hoy.day)


def mostrar(c: dict, v: Any, fmt: Region) -> str:
    """Un valor como lo lee la persona: la fecha larga, el monto con su moneda, «—» si está vacío."""
    if _vacio(v):
        return "—"
    t = _tipo(c)
    if t == "fecha":
        return fecha_larga(v)
    if t == "dinero":
        return fmt.dinero(numero_js(v))
    if t == "numero":
        return fmt.numero(numero_js(v))
    return texto_js(v)


def titulo_de(r: dict, ct: dict) -> str:
    v = _vals(r).get(ct["id"])
    return "(sin nombre)" if _falso(v) else texto_js(v)


def describir(r: dict, campos: list[dict], fmt: Region, ct: dict) -> str:
    """Un registro en una línea, con su id al final (para que el modelo lo nombre sin ambigüedad; nunca se le dice a la persona)."""
    resto = " · ".join(f"{c.get('nombre')}: {mostrar(c, _vals(r).get(c['id']), fmt)}" for c in campos if c is not ct)
    return f"{titulo_de(r, ct)} — {resto} (id {plantilla_js(r.get('id'))})"


def campo_por_clave(campos: list[dict], k: Any) -> dict | None:
    """El campo que nombró el modelo: por id, por nombre (sin acentos) o por su forma de clave («fecha_de_pago»)."""
    return (next((c for c in campos if c.get("id") == k), None)
            or next((c for c in campos if sin_acentos(c.get("nombre")) == sin_acentos(k)), None)
            or next((c for c in campos if _clave(c.get("id")) == _clave(k) or _clave(c.get("nombre")) == _clave(k)), None))


def _cortar_120(t: str) -> str:
    """`String(v).slice(0, 120)`: 120 unidades UTF-16, como JS (sin dejar media letra de un emoji)."""
    if len(t) <= 60:
        return t
    unidades = t.encode("utf-16-le")
    return unidades[:240].decode("utf-16-le", errors="ignore")


def leer_valores(sec: dict, campos: list[dict], regs: list[dict], valores: Any, *, vaciar: bool = False,
                 hoy: date | datetime) -> tuple[dict, list[str]]:
    """Lo que dijo la persona → valores guardables, campo por campo. En editar (`vaciar`), un valor vacío deja el campo vacío.

    Devuelve (listos, errores): `listos` va por id de campo; cada error es un texto que dice qué preguntar.
    """
    hoy = _hoy(hoy)
    listos: dict[str, Any] = {}
    errores: list[str] = []
    for k, v0 in (valores.items() if isinstance(valores, dict) else []):
        c = campo_por_clave(campos, k)
        if not c:
            errores.append(f"«{k}» no es un campo de {sec.get('titulo')} (sus campos: {', '.join(texto_js(x.get('nombre')) for x in campos)}). "
                           "Si quiere guardar ese dato, pregúntale si agregas el campo.")
            continue
        v = recortar(v0) if isinstance(v0, str) else v0
        if _vacio(v):
            if vaciar:
                listos[c["id"]] = ""
            continue
        t = _tipo(c)
        if t == "fecha":
            f = parse_fecha(v, hoy)
            if f:
                listos[c["id"]] = f
            else:
                errores.append(f"no entendí la fecha «{plantilla_js(v)}» para {c.get('nombre')}: hoy es {fecha_larga(iso(hoy))}; pregúntale cuál es "
                               f"(por ejemplo «30 de octubre» o «30 de octubre de {hoy.year + 1}»).")
        elif t in ("numero", "dinero"):
            n = parse_numero(v)
            if n is not None:
                listos[c["id"]] = n
            else:
                errores.append(f"«{plantilla_js(v)}» no es un número para {c.get('nombre')}.")
        elif t == "hora":
            h = parse_hora(v)
            if h:
                listos[c["id"]] = h
            else:
                errores.append(f"no entendí la hora «{plantilla_js(v)}» para {c.get('nombre')} (por ejemplo «9:30» o «3 de la tarde»).")
        elif t == "estado":
            o = opcion_de(c, v)
            if o:
                listos[c["id"]] = o
            else:
                errores.append(f"«{plantilla_js(v)}» no es una opción de {c.get('nombre')} (opciones: {', '.join(c.get('opciones') or [])}). "
                               "Pregúntale cuál, o si quiere agregar esa opción.")
        else:
            # Si ese texto ya existe escrito de otra forma («mensual» y «Mensual»), se usa el que ya está: así se agrupa igual.
            txt = _cortar_120(texto_js(v))
            existentes = [*(c.get("ejemplos") or []), *(_vals(r).get(c["id"]) for r in regs)]
            listos[c["id"]] = next((x for x in existentes if isinstance(x, str) and x != txt and sin_acentos(x) == sin_acentos(txt)), None) or txt
    return listos, errores


# ¿A qué registro se refiere? Si son varios o ninguno, el error dice qué preguntar (nunca adivina).
# Palabras (sin acentos, de 3+ letras) y si una aparece en lo que escribió la persona, por raíz (López/lopez, Pérez/perez).
def _palabras_de(t: Any) -> list[str]:
    return [w for w in re.split(r"[^a-z0-9ñ]+", sin_acentos(t)) if len(w) > 2]


def _dicha(w: str, dichos: Any) -> bool:
    raiz = w[:max(3, len(w) - 2)]
    return any(d.startswith(raiz) for d in _palabras_de(dichos))


def _unicos(xs: list) -> list:
    return list(dict.fromkeys(xs))


def encontrar(sec: dict, campos: list[dict], regs: list[dict], consulta: Any, fmt: Region, dichos: Any = None) -> dict:
    """{"r": registro} o {"error": texto}.

    `dichos` = todo lo que escribió la persona (este mensaje y los anteriores). Si se pasa, el registro debe ser uno que ELLA nombró
    (D54): medido, con dos «Ana» el modelo elegía «Ana López» por su cuenta en un mensaje sobre otra cosa.
    """
    ct = campo_titulo(sec, campos)
    b = buscar_registro(regs, sec, campos, texto_js(consulta))
    if b.get("registro") is not None and dichos is not None:
        r = b["registro"]
        tit = titulo_de(r, ct)
        # Lo que la persona dijo del nombre (con id o con nombre) debe señalar a ese registro y solo a ese: «Ana» con una sola Ana
        # basta; con dos, no.
        dijo = _unicos([w for w in [*_palabras_de(tit), *([] if r.get("id") == consulta else _palabras_de(consulta))] if _dicha(w, dichos)])
        otra = buscar_registro(regs, sec, campos, " ".join(dijo)) if dijo else {}
        if not (dijo and otra.get("registro") is not None and otra["registro"].get("id") == r.get("id")):
            c = otra.get("candidatos")
            extra = f" (dijo «{' '.join(dijo)}» y coinciden: {', '.join(titulo_de(x, ct) for x in c[:5])})" if c else ""
            return {"error": f"la persona no nombró a «{tit}»{extra}. No elijas por ella: pregúntale a quién se refiere."}
    if b.get("registro") is not None:
        return {"r": b["registro"]}
    if b.get("candidatos"):
        cs = b["candidatos"]
        lista = " | ".join(describir(x, campos, fmt, ct) for x in cs[:5])
        return {"error": f"hay {len(cs)} registros en {sec.get('titulo')} que coinciden con «{plantilla_js(consulta)}»: {lista}{' | …' if len(cs) > 5 else ''}. "
                         "No cambies nada: pregúntale cuál (por un dato que los distinga)."}
    palabras = [w for w in re.split(r"\s+", sin_acentos(consulta)) if len(w) > 2]
    parecidos = _unicos([titulo_de(x, ct) for x in regs if any(w in sin_acentos(_vals(x).get(ct["id"])) for w in palabras)])[:3]
    sigue = f" Se parecen: {', '.join(parecidos)}. Pregúntale si es alguno." if parecidos else " Pregúntale cómo se llama exactamente o si quiere agregarlo."
    return {"error": f"no encontré «{plantilla_js(consulta)}» en {sec.get('titulo')} (tiene {len(regs)} registros).{sigue}"}


def _ms_dia(v: Any) -> float | None:
    """`Date.parse` de una fecha guardada, en días (solo 'AAAA-MM-DD', como las que escribe el código)."""
    if isinstance(v, datetime):
        return float(v.date().toordinal())
    if isinstance(v, date):
        return float(v.toordinal())
    m = re.fullmatch(r"([0-9]{4})-([0-9]{2})-([0-9]{2})", texto_js(v)) if isinstance(v, str) else None
    if not m:
        return None
    try:
        return float(date(int(m[1]), int(m[2]), int(m[3])).toordinal())
    except ValueError:
        return None


def _estricto(a: Any, b: Any) -> bool:
    """`a === b` de JS entre valores guardados (350 no es «350»; None se toma como lo que no está)."""
    if es_numero(a) and es_numero(b):
        return a == b
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, str) and isinstance(b, str):
        return a == b
    return a is None and b is None


def _no(texto: str) -> dict:
    return {"ok": False, "resultado": f"ERROR: {texto}", "etiqueta": None, "operacion": None}


def ejecutar_dato(nombre: str, sec: dict, campos: list[dict], regs: list[dict], args: dict, *, hoy: date | datetime,
                  pais: Any = None, confirmado: bool = False, dichos: Any = None, id_nuevo: str | None = None) -> dict:
    """Agregar, editar o borrar UN registro. No cambia nada: dice qué cambiar.

    `sec` = la sección dueña de los datos; `campos` = los que ve la persona; `regs` = los registros de AHORA; `dichos` = lo que escribió
    la persona (None = no se revisa la procedencia); `id_nuevo` = el id que tendrá un registro agregado (si no se da, se crea uno y va en
    la operación para que quien la aplica lo use).

    Devuelve {ok, resultado, etiqueta, operacion}: `resultado` es el texto para el modelo; `etiqueta`, el cambio dicho en simple para la
    línea «Cambios:» del chat (None si no cambió nada).
    """
    hoy = _hoy(hoy)
    fmt = region_de(pais)
    ct = campo_titulo(sec, campos)
    args = args or {}
    titulo = sec.get("titulo")

    if nombre == "agregar_registro":
        listos, errores = leer_valores(sec, campos, regs, args.get("valores"), hoy=hoy)
        if _falso(listos.get(ct["id"])) and not errores:
            errores.append(f"falta {ct.get('nombre')}: es lo que identifica al registro. Pregúntaselo.")
        if errores:
            return _no(" ".join(errores))
        dados = dict(listos)  # lo que dio la persona (antes de los valores por defecto)
        # Un estado sin decir: la primera opción (sin estado no se vería en el tablero). Se dice.
        por_defecto = []
        for c in campos:
            if _tipo(c) == "estado" and c["id"] not in listos and c.get("opciones"):
                listos[c["id"]] = c["opciones"][0]
                por_defecto.append(f"{c.get('nombre')}: {c['opciones'][0]}")
        mismos = sum(1 for r in regs if sin_acentos(_vals(r).get(ct["id"])) == sin_acentos(listos[ct["id"]]))
        # Duplicado exacto: mismo nombre y TODO lo que se dio igual a un registro que ya existe. Casi siempre es repetir el pedido
        # (prueba de cliente: «Juan Pérez» quedó dos veces). Se agrega solo si la persona lo confirma. Un pago nuevo de la misma persona
        # (otro monto u otra fecha) no es duplicado. Fechas con ±3 días: el modelo dice «en un mes» una vez y «en 30 días» la otra
        # (medido: 17 y 16 de noviembre).
        tipo_de = {c["id"]: _tipo(c) for c in campos}

        def igual(k: str, a: Any, b: Any) -> bool:
            if tipo_de.get(k) == "fecha":
                da, db = _ms_dia(a), _ms_dia(b)
                return not _falso(a) and da is not None and db is not None and abs(da - db) <= 3
            if es_numero(a) or es_numero(b):
                return numero_js(a) == numero_js(b)
            return sin_acentos(a) == sin_acentos(b)

        duplicado = next((r for r in regs if all(igual(k, _vals(r).get(k), v) for k, v in dados.items())), None)
        if duplicado is not None and not confirmado:
            return _no(f"ya existe «{texto_js(listos[ct['id']])}» en {titulo} con esos mismos datos. No lo agregué. Si quería cambiar ese, usa "
                       "editar_registro; si de verdad es OTRO con los mismos datos, pregúntaselo y agrégalo cuando diga que sí.")
        rid = id_nuevo or nuevo_id()
        reg = {"id": rid, "valores": listos}
        vacios = [texto_js(c.get("nombre")) for c in campos if c["id"] not in listos]
        nombre_reg = texto_js(listos[ct["id"]])
        texto = f"Agregado a {titulo}: {describir(reg, campos, fmt, ct)}."
        if por_defecto:
            texto += f" {', '.join(por_defecto)} por defecto (dilo)."
        if vacios:
            texto += f" Sin llenar: {', '.join(vacios)} (dilo y ofrece completarlo; no lo inventes)."
        if mismos:
            cuantos = "otro registro" if mismos == 1 else f"{mismos} registros"
            como = " con los mismos datos (la persona confirmó que es otro)" if duplicado is not None else " con otros datos"
            texto += f" Ya había {cuantos} «{nombre_reg}»{como}; díselo en una línea."
        texto += f" Ahora hay {len(regs) + 1} en {titulo}."
        return {"ok": True, "resultado": texto, "etiqueta": f"agregó «{nombre_reg}» a {titulo}",
                "operacion": {"tipo": "agregar", "valores": listos, "id": rid}}

    if nombre == "editar_registro":
        e = encontrar(sec, campos, regs, args.get("registro"), fmt, dichos)
        if "error" in e:
            return _no(e["error"])
        valores = args.get("valores")
        if not (isinstance(valores, dict) and valores):
            return _no("falta qué cambiar (valores).")
        listos, errores = leer_valores(sec, campos, regs, valores, vaciar=True, hoy=hoy)
        if errores:
            return _no(" ".join(errores))
        if listos.get(ct["id"]) == "":
            return _no(f"un registro no puede quedar sin {ct.get('nombre')}.")
        r = e["r"]
        antes = _vals(r)
        nombre_antes = titulo_de(r, ct)
        cambiados = [c for c in campos if c["id"] in listos and not _estricto(listos[c["id"]], "" if antes.get(c["id"]) is None else antes.get(c["id"]))]
        if not cambiados:
            por_id = {c["id"]: c for c in campos}
            ya = " · ".join(f"{por_id[i].get('nombre')}: {mostrar(por_id[i], v, fmt)}" for i, v in listos.items())
            return {"ok": True, "resultado": f"«{nombre_antes}» ya tenía eso ({ya}): no cambió nada. Díselo.", "etiqueta": None, "operacion": None}
        cambio = {c["id"]: listos[c["id"]] for c in cambiados}
        detalle = " · ".join(f"{c.get('nombre')}: {mostrar(c, antes.get(c['id']), fmt)} → {mostrar(c, listos[c['id']], fmt)}" for c in cambiados)
        etiqueta = ", ".join(f"{c.get('nombre')} → {mostrar(c, listos[c['id']], fmt)}" for c in cambiados)
        return {"ok": True, "resultado": f"Cambiado «{nombre_antes}» en {titulo}: {detalle}.", "etiqueta": f"cambió «{nombre_antes}»: {etiqueta}",
                "operacion": {"tipo": "editar", "id": r.get("id"), "cambios": cambio}}

    if nombre == "borrar_registro":
        e = encontrar(sec, campos, regs, args.get("registro"), fmt, dichos)
        if "error" in e:
            return _no(e["error"])
        r = e["r"]
        return {"ok": True, "resultado": f"Borrado de {titulo}: {describir(r, campos, fmt, ct)}. Se puede deshacer. Quedan {len(regs) - 1}.",
                "etiqueta": f"borró «{titulo_de(r, ct)}» de {titulo}", "operacion": {"tipo": "borrar", "id": r.get("id")}}

    return _no(f"la herramienta «{nombre}» no existe.")


def _falso(v: Any) -> bool:
    """`!v` de JS."""
    return v is None or v is False or v == "" or (es_numero(v) and (v == 0 or math.isnan(v)))


def filtrar(sec: dict, campos: list[dict], regs: list[dict], args: dict | None = None, *, hoy: date | datetime,
            pais: Any = None) -> tuple[list[dict], list[str]] | str:
    """Los registros que cumplen `buscar`, `filtros` y `periodo` (como en consultar_datos) y la descripción de cada filtro.
    Devuelve el texto de ERROR si un filtro no se entiende. Lo usan consultar y la descarga: el mismo filtro para las dos."""
    hoy = _hoy(hoy)
    args = args or {}
    fmt = region_de(pais)
    titulo = sec.get("titulo")
    filtros: list[str] = []
    lista = list(regs)
    buscar = args.get("buscar")
    if not _falso(buscar):
        b = buscar_registro(regs, sec, campos, texto_js(buscar))
        if b.get("ninguno"):
            return f"En {titulo} no hay ningún registro que coincida con «{plantilla_js(buscar)}» (tiene {len(regs)}). Díselo; no inventes."
        lista = [b["registro"]] if b.get("registro") is not None else b["candidatos"]
        filtros.append(f"que coinciden con «{plantilla_js(buscar)}»")

    def por_fecha(c: dict, cuando: Any) -> str | None:
        nonlocal lista
        p = parse_periodo(cuando, hoy)
        if not p:
            return (f"ERROR: no entendí el periodo «{plantilla_js(cuando)}». Se entiende: hoy, esta semana, la semana pasada, este mes, el mes pasado, "
                    "los próximos 7 días, los últimos 30 días, vencidos, octubre, del 1 al 15 de octubre, una fecha.")
        desde, hasta = p["desde"], p["hasta"]

        def dentro(r: dict) -> bool:
            v = _vals(r).get(c["id"])
            return isinstance(v, str) and v != "" and (not desde or v >= desde) and (not hasta or v <= hasta)

        lista = [r for r in lista if dentro(r)]
        if desde and hasta:
            cuando_txt = f"el {fecha_larga(desde)}" if desde == hasta else f"del {fecha_larga(desde)} al {fecha_larga(hasta)}"
        else:
            cuando_txt = f"hasta el {fecha_larga(hasta)}" if hasta else f"desde el {fecha_larga(desde)}"
        filtros.append(f"{c.get('nombre')} {cuando_txt}")
        return None

    filtros_args = args.get("filtros")
    for k, v in (filtros_args.items() if isinstance(filtros_args, dict) else []):
        c = campo_por_clave(campos, k)
        if not c:
            todos = ", ".join(f"{x.get('id')} ({x.get('nombre')})" for x in campos)
            return f"ERROR: «{k}» no es un campo de {titulo}. Campos: {todos}."
        t = _tipo(c)
        if t == "estado":
            o = opcion_de(c, v)
            if not o:
                return f"ERROR: «{plantilla_js(v)}» no es una opción de {c.get('nombre')} (opciones: {', '.join(c.get('opciones') or [])})."
            lista = [r for r in lista if _estricto(_vals(r).get(c["id"]), o)]
            filtros.append(f"{c.get('nombre')}: {o}")
        elif t == "fecha":
            err = por_fecha(c, v)
            if err:
                return err
        elif t in ("numero", "dinero"):
            n = parse_numero(v)
            if n is None:
                return f"ERROR: «{plantilla_js(v)}» no es un número."
            lista = [r for r in lista if numero_js(_vals(r).get(c["id"])) == n]
            filtros.append(f"{c.get('nombre')}: {mostrar(c, n, fmt)}")
        else:
            q = sin_acentos(v)
            lista = [r for r in lista if q in sin_acentos(_vals(r).get(c["id"]))]
            filtros.append(f"{c.get('nombre')} con «{plantilla_js(v)}»")

    periodo = args.get("periodo") if isinstance(args.get("periodo"), dict) else {}
    if not _falso(periodo.get("cuando")):
        fechas = [c for c in campos if _tipo(c) == "fecha"]
        c = campo_por_clave(campos, periodo["campo"]) if not _falso(periodo.get("campo")) else (fechas[0] if len(fechas) == 1 else None)
        if not c or _tipo(c) != "fecha":
            tiene = ", ".join(f"{x.get('id')} ({x.get('nombre')})" for x in fechas) or "ninguna fecha"
            return f"ERROR: ¿por cuál fecha? {titulo} tiene: {tiene}. Pon periodo.campo."
        err = por_fecha(c, periodo["cuando"])
        if err:
            return err

    return lista, filtros


def consultar(sec: dict, campos: list[dict], regs: list[dict], args: dict | None = None, *, hoy: date | datetime, pais: Any = None) -> str:
    """Lee los datos para responder una pregunta: el CÓDIGO filtra, cuenta y suma (el modelo solo repite). Nunca cambia nada."""
    hoy = _hoy(hoy)
    args = args or {}
    fmt = region_de(pais)
    ct = campo_titulo(sec, campos)
    titulo = sec.get("titulo")
    r = filtrar(sec, campos, regs, args, hoy=hoy, pais=pais)
    if isinstance(r, str):
        return r
    lista, filtros = r
    suma = ""
    if not _falso(args.get("sumar")):
        c = campo_por_clave(campos, args["sumar"])
        sumables = [x for x in campos if _tipo(x) in ("numero", "dinero")]
        if not c or not any(x is c for x in sumables):
            se_puede = ", ".join(f"{x.get('id')} ({x.get('nombre')})" for x in sumables) or "nada (no tiene números)"
            return f"ERROR: «{plantilla_js(args['sumar'])}» no se puede sumar en {titulo}. Se pueden sumar: {se_puede}."
        total = 0.0
        for r in lista:
            n = numero_js(_vals(r).get(c["id"]))
            total += 0.0 if math.isnan(n) or n == 0 else n
        suma = f" Suma de {c.get('nombre')}: {mostrar(c, a_js(total), fmt)}."

    muestra = ""
    if lista:
        cuales = f"Los primeros {MAX_LISTA}" if len(lista) > MAX_LISTA else "Son"
        muestra = f" {cuales}: {' | '.join(describir(r, campos, fmt, ct) for r in lista[:MAX_LISTA])}."
    filtros_txt = f" ({'; '.join(filtros)})" if filtros else ""
    registros_txt = "registro" if len(regs) == 1 else "registros"
    return (f"Hoy es {fecha_larga(iso(hoy))}. En {titulo}{filtros_txt}: {len(lista)} de {len(regs)} {registros_txt}.{suma}{muestra} "
            "Responde SOLO con estos números y datos (sin decir ids).")


# Esquemas para el modelo: los de `registros.js`, LITERALES (nombres, descripciones y parámetros), en el formato de OpenAI.
def _herramienta(nombre: str, descripcion: str, propiedades: dict, requeridos: list[str]) -> dict:
    return {"type": "function", "function": {"name": nombre, "description": descripcion,
                                             "parameters": {"type": "object", "properties": propiedades, "required": requeridos}}}


HERRAMIENTAS_DATOS: list[dict] = [
    _herramienta(
        "agregar_registro",
        "Agrega UN registro (un cliente, un pago, una cita…) a una sección con los datos que dijo la persona. Copia cada valor TAL COMO lo dijo "
        "(«30 de octubre», «Q1,200», «3 de la tarde»): el código lo entiende y lo valida. No inventes lo que no dijo: queda vacío.",
        {"seccion": {"type": "string"}, "valores": {"type": "object", "description": "campo (id o nombre) → valor como lo dijo la persona"}},
        ["seccion", "valores"]),
    _herramienta(
        "editar_registro",
        "Cambia datos de UN registro que ya existe. registro = cómo lo nombró la persona («Ana López») o su id. Pasa solo los campos que cambian.",
        {"seccion": {"type": "string"}, "registro": {"type": "string"},
         "valores": {"type": "object", "description": 'campo → valor nuevo como lo dijo; "" para dejarlo vacío'}},
        ["seccion", "registro", "valores"]),
    _herramienta(
        "borrar_registro",
        "Borra UN registro que la persona pidió borrar (se puede deshacer).",
        {"seccion": {"type": "string"}, "registro": {"type": "string"}},
        ["seccion", "registro"]),
    # Medido: con «¿cuándo vence Ana?» y «vencidos» como ejemplos, «quiero VER los vencimientos en un calendario» se confundía con consultar
    # (el calendario bajó de 16/16 a ~10/16). La frontera va en la descripción: responder EN EL CHAT ≠ ver en pantalla.
    _herramienta(
        "consultar_datos",
        "Responde EN EL CHAT una pregunta sobre sus datos («¿cuántos clientes activos tengo?», «¿cuánto me pagaron este mes?», «¿qué teléfono "
        "tiene Ana?»). El código filtra, cuenta y suma. No cambia la pantalla: para VER algo en pantalla se agrega una pieza.",
        {"seccion": {"type": "string"}, "buscar": {"type": "string", "description": "nombre o texto de un registro"},
         "filtros": {"type": "object", "description": "campo → valor (estado: Activa; plan: Mensual)"},
         "periodo": {"type": "object", "properties": {"campo": {"type": "string", "description": "campo de fecha"},
                                                      "cuando": {"type": "string", "description": "como lo dijo: «este mes», «esta semana», «los próximos 7 días»"}}},
         "sumar": {"type": "string", "description": "campo de número o dinero a sumar"}},
        ["seccion"]),
]

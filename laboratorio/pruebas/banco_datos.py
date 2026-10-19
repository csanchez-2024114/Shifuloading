"""Banco D50 con la IA real: meter, cambiar, borrar y consultar datos POR CHAT. Verifica los REGISTROS que quedaron
(estado.datos) y que la respuesta use los números del código, no solo qué herramienta llamó.
Datos: membresías con 8 ejemplos (Ana López = miembros-0, Carlos Pérez = miembros-1, Luis Hernández = miembros-3…).
Uso: python3 laboratorio/pruebas/banco_datos.py [repeticiones=1]"""
import datetime, json, re, sys, time, urllib.request
import os
CHAT = os.environ.get("BASE", "http://localhost:5190") + os.environ.get("RUTA_CHAT", "/api/lab/chat")  # D61: el mismo banco mide el laboratorio o el CRM
N = int(sys.argv[1]) if len(sys.argv) > 1 else 1
HOY = datetime.date.today()
MUESTRA = {"nivel": "pocos", "ejemplos": True, "pais": "gt"}
B = [{"uid": "b0", "vista": "kpis", "seccion": "miembros", "opciones": {"por": "estado"}, "ancho": 12, "alto": 1},
     {"uid": "b1", "vista": "vencimientos", "seccion": "miembros", "opciones": {"fecha": "vence", "titulo": "nombre", "dias": 30}, "ancho": 12, "alto": 2}]
def E(vista="inicio", datos=None):
    return {"vista": vista, "bloques": B, **({"datos": datos} if datos else {})}
UN_JUAN = {"n": 1, "nuevos": {"miembros": [{"id": "miembros-p1", "valores": {"nombre": "Juan Pérez", "plan": "Mensual", "alta": HOY.isoformat(), "estado": "Activa"}}]}}
DOS_ANAS = {"n": 1, "nuevos": {"miembros": [{"id": "miembros-p1", "valores": {"nombre": "Ana Martínez", "plan": "Trimestral", "estado": "Activa"}}]}}
def pide(est, txt, hist=None):  # noqa
    a = time.time()
    d = json.load(urllib.request.urlopen(urllib.request.Request(CHAT, data=json.dumps({"plantilla": "membresias", "estado": est, "texto": txt, "muestra": MUESTRA, **({"historial": hist} if hist else {})}).encode(), headers={"Content-Type": "application/json"}), timeout=120))
    return d, time.time() - a
datos = lambda d: (d.get("estado") or {}).get("datos") or {}
nuevos = lambda d, s="miembros": datos(d).get("nuevos", {}).get(s, [])
cambio = lambda d, rid, s="miembros": datos(d).get("cambios", {}).get(s, {}).get(rid, {})
borrados = lambda d, s="miembros": datos(d).get("borrados", {}).get(s, [])
sin_cambios = lambda d: not datos(d).get("nuevos", {}).get("miembros") and not datos(d).get("cambios") and not datos(d).get("borrados")
def numeros_de(t): return set(re.findall(r"\d[\d,.]*", t))
def usa_numero_del_codigo(d, patron):
    """La cifra que calculó el código (en la consulta) aparece en la respuesta."""
    for c in d.get("consultas", []):
        m = re.search(patron, c["resultado"])
        if m and m.group(1) in d["respuesta"].replace(" ", " "): return True
    return False
def nombres_consultados(d):
    """Los registros que listó el código en la consulta (lo que la respuesta debe repetir, sin inventar otros)."""
    out = []
    for c in d.get("consultas", []):
        m = re.search(r"(?:Son|Los primeros \d+): (.*)\. Responde", c["resultado"])
        if m: out += [x.split(" — ")[0].strip() for x in m.group(1).split(" | ")]
    return out
def opciones_estado(d):
    return ((d["estado"].get("estructura") or {}).get("opcionesEstado") or {}).get("miembros", {}).get("estado")
def un_registro(d, **esperado):
    rs = nuevos(d)
    return len(rs) == 1 and all(rs[0]["valores"].get(k) == v for k, v in esperado.items())
ANIO = HOY.year
CASOS = [  # (descripción, estado, texto, verificación)
    ("agregar con fecha en palabras", E(), "agrega a María López como miembro, plan mensual, vence el 30 de octubre",
     lambda d: un_registro(d, nombre="María López", plan="Mensual", vence=f"{ANIO}-10-30", estado="Activa") and "alta" not in nuevos(d)[0]["valores"]),
    ("cambiar el estado de un ejemplo", E(), "cambia el estado de Ana López a Pausada", lambda d: cambio(d, "miembros-0").get("estado") == "Pausada" and len(datos(d).get("cambios", {}).get("miembros", {})) == 1),
    ("cambiar una fecha", E(), "cambia la fecha de vencimiento de Luis Hernández al 15 de noviembre", lambda d: cambio(d, "miembros-3").get("vence") == f"{ANIO}-11-15"),
    ("borrar uno", E(), "borra a Carlos Pérez de mis miembros", lambda d: borrados(d) == ["miembros-1"]),
    ("un pago dicho en simple va a Pagos", E(), "Ana López me pagó 350 hoy",
     lambda d: len(nuevos(d, "pagos")) == 1 and nuevos(d, "pagos")[0]["valores"].get("monto") == 350 and nuevos(d, "pagos")[0]["valores"].get("miembro") == "Ana López" and nuevos(d, "pagos")[0]["valores"].get("fecha") == HOY.isoformat() and not nuevos(d)),
    ("contar: usa el número del código", E(), "¿cuántos miembros activos tengo?", lambda d: sin_cambios(d) and usa_numero_del_codigo(d, r"\): (\d+) de")),
    ("sumar: usa el total del código", E(), "¿cuánto me pagaron este mes?", lambda d: sin_cambios(d) and usa_numero_del_codigo(d, r"Suma de Monto: Q\s?([\d,.]*\d)")),
    ("quiénes vencen: los nombres que dio el código", E(), "¿qué miembros vencen en los próximos 7 días?",
     lambda d: sin_cambios(d) and d.get("consultas") and ((nombres_consultados(d) and all(n in d["respuesta"] for n in nombres_consultados(d))) or (not nombres_consultados(d) and re.search(r"\bning[uú]n|\bnadie|\bno hay", d["respuesta"], re.I)))),
    ("solo el nombre: no inventa lo demás", E(), "agrega a Pedro Ruiz",
     lambda d: (un_registro(d, nombre="Pedro Ruiz") and set(nuevos(d)[0]["valores"]) <= {"nombre", "estado"}) or (sin_cambios(d) and "?" in d["respuesta"])),
    # Opción nueva: o pregunta, o la crea y LO DICE (como Notion; visible en «Cambios:» y se deshace). Nunca en silencio.
    ("opción que no existe: pregunta o la crea diciéndolo", E(), "cambia el estado de Ana López a Congelada",
     lambda d: (sin_cambios(d) and "?" in d["respuesta"]) or ("Congelada" in (opciones_estado(d) or []) and cambio(d, "miembros-0").get("estado") == "Congelada" and re.search(r"agregu|cre[eé]|nueva|a[ñn]ad", d["respuesta"], re.I))),
    ("error de tipeo en una opción: nunca crea «Pausda»", E(), "cambia el estado de Ana López a pausda",
     lambda d: "Pausda" not in (opciones_estado(d) or []) and (cambio(d, "miembros-0").get("estado") == "Pausada" or (sin_cambios(d) and "?" in d["respuesta"]))),
    ("dos que coinciden: pregunta cuál", E(datos=DOS_ANAS), "cambia el plan de Ana a Anual", lambda d: not datos(d).get("cambios") and nuevos(d)[0]["valores"]["plan"] == "Trimestral" and "?" in d["respuesta"]),
    ("borrar varios pide confirmación", E(), "borra a todos los miembros cancelados", lambda d: not borrados(d) and "?" in d["respuesta"]),
    ("fecha imposible: no inventa una", E(), "agrega a Rosa Gómez, vence el 31 de febrero",
     lambda d: all(not r["valores"].get("vence") for r in nuevos(d)) and re.search(r"\?|\bdime\b|ind[ií]came|\bcu[aá]l\b", d["respuesta"], re.I)),  # pide la fecha (con o sin «?»)
    ("mirando la pestaña: agrega ahí", E("miembros"), "agrega a Rosa Gómez, plan anual", lambda d: un_registro(d, nombre="Rosa Gómez") and nuevos(d)[0]["valores"].get("plan", "").lower() == "anual"),  # tal como lo dijo
    # Prueba de cliente con IA (2026-10-17): cada falla, un caso fijo.
    ("fecha relativa: «vence en un mes»", E(), "agrega a Juan Pérez, plan mensual, se inscribió hoy y vence en un mes",
     lambda d: un_registro(d, nombre="Juan Pérez", alta=HOY.isoformat()) and nuevos(d)[0]["valores"].get("vence", "").startswith(f"{(HOY.replace(day=1) + datetime.timedelta(days=32)).strftime('%Y-%m')}")),
    ("no duplica a quien ya está", E(datos=UN_JUAN), "agrega a Juan Pérez, plan mensual",
     lambda d: len(nuevos(d)) == 1 and "?" in d["respuesta"]),
    ("pregunta por el mes: responde, no cambia la pantalla", E(), "¿quiénes vencen este mes?",
     lambda d: sin_cambios(d) and not d["cambios"] and d.get("consultas")),
    ("el diseño sigue igual: no toca registros", E(), "agrega una gráfica de dona por estado", lambda d: sin_cambios(d) and any(b["vista"] == "grafico" for b in d["estado"]["bloques"])),
]
ok = tot = 0; tiempos = []
for _ in range(N):
    for desc, est, txt, verif in CASOS:
        d, t = pide(est, txt); tiempos.append(t)
        try: b = bool(verif(d))
        except Exception as e: b = False; print("   (verificación falló:", e, ")")
        ok += b; tot += 1
        print(f"{'✓' if b else '✗'} {t:4.1f}s | {desc} | «{txt}»")
        if not b: print(f"     hizo: {[(c['herramienta'], c['args']) for c in d['cambios']]} consultas={[c['args'] for c in d.get('consultas', [])]} fallos={[f[:140] for f in d['fallos'][:2]]}\n     datos={json.dumps(datos(d), ensure_ascii=False)[:300]}\n     dijo: {d['respuesta'][:220]}")
# Deshacer un cambio de datos: el registro vuelve como estaba y lo demás no cambia.
for _ in range(N):
    d1, _t = pide(E(), "cambia el estado de Ana López a Pausada")
    d2, t = pide(d1["estado"], "deshaz eso", [{"de": "yo", "t": "cambia el estado de Ana López a Pausada"}, {"de": "shifu", "t": d1["respuesta"]}]); tiempos.append(t)
    b = cambio(d1, "miembros-0").get("estado") == "Pausada" and not cambio(d2, "miembros-0") and [c["herramienta"] for c in d2["cambios"]] == ["deshacer"]
    ok += b; tot += 1
    print(f"{'✓' if b else '✗'} {t:4.1f}s | deshacer un cambio de datos | «deshaz eso»")
    if not b: print(f"     hizo: {[c['herramienta'] for c in d2['cambios']]} datos={json.dumps(datos(d2), ensure_ascii=False)[:200]}\n     dijo: {d2['respuesta'][:200]}")
# Un pedido viejo sin resolver no se ejecuta en un mensaje que pide otra cosa (prueba de cliente: «ponle a Ana el teléfono»
# también creó una sección y agregó a otro; «borra a Ana» también intentó pausar a Juan).
for _ in range(N):
    h = [{"de": "yo", "t": "pasa a Ana a Pausada"}, {"de": "shifu", "t": "Hay dos registros que coinciden con Ana: Ana López y Ana Martínez. ¿Cuál quieres pasar a Pausada?"}]
    d, t = pide(E(datos=DOS_ANAS), "ponle a Carlos Pérez el plan Anual", h); tiempos.append(t)
    b = [c["herramienta"] for c in d["cambios"]] == ["editar_registro"] and cambio(d, "miembros-1").get("plan") == "Anual" and not cambio(d, "miembros-0")
    ok += b; tot += 1
    print(f"{'✓' if b else '✗'} {t:4.1f}s | no retoma un pedido viejo | «ponle a Carlos Pérez el plan Anual»")
    if not b: print(f"     hizo: {[(c['herramienta'], c['args']) for c in d['cambios']]}\n     dijo: {d['respuesta'][:200]}")
print(f"\n{ok}/{tot} correctos · tiempo medio {sum(tiempos)/len(tiempos):.1f}s · máx {max(tiempos):.1f}s")

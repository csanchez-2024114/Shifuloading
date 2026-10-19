"""Banco de conceptos (lista 19-oct: puntos 7, 8, 12, 13, 14, 19 y 20) con la IA real. Verifica el ESTADO que quedó y lo que dijo:
- 19: la IA sabe qué es cada cosa (una cita va en la agenda, no como tarea; «llevar inventario», «cobros a crédito»).
- 13/14: gráficas: sobre una sección vacía avisa y ofrece cargar datos; «¿qué gráficas puedo poner?» propone 2–3, no 30.
- 7: un «sí» suelto tras una pregunta acepta la recomendada (o la más razonable), no repite la pregunta.
- 8: sin jerga interna («propia», «integrada», nombres de herramientas, ids).
- 12: la descripción del negocio pesa más que la plantilla.
- 20: lo que tiene deshacer se hace directo; el borrado masivo sigue pidiendo «sí».
Uso: python3 laboratorio/pruebas/banco_conceptos.py [repeticiones=1]"""
import json, os, re, sys, time, urllib.request

CHAT = os.environ.get("BASE", "http://localhost:5190") + os.environ.get("RUTA_CHAT", "/api/lab/chat")
N = int(sys.argv[1]) if len(sys.argv) > 1 else 1
POCOS = {"nivel": "pocos", "ejemplos": True, "pais": "gt"}
VACIO = {"nivel": "vacio", "ejemplos": False, "pais": "gt"}
B = [{"uid": "b0", "vista": "kpis", "seccion": "miembros", "opciones": {"por": "estado"}, "ancho": 12, "alto": 1},
     {"uid": "b1", "vista": "vencimientos", "seccion": "miembros", "opciones": {"fecha": "vence", "titulo": "nombre", "dias": 30}, "ancho": 12, "alto": 2}]
DONA = {"uid": "b2", "vista": "grafico", "seccion": "miembros", "opciones": {"tipo": "dona", "agrupar": "estado"}, "ancho": 6, "alto": 2}
PEPES = {"nombre": "PepesCore", "rubro": "comercio",
         "que_vendes": "Tengo un taller donde reparo computadoras y celulares, y también vendo laptops y repuestos. Quiero tener control de las reparaciones y de mis números."}


def E(vista="inicio", bloques=None):
    return {"vista": vista, "bloques": B if bloques is None else bloques}


def pide(plantilla, est, txt, hist=None, muestra=POCOS, brief=None):
    a = time.time()
    cuerpo = {"plantilla": plantilla, "estado": est, "texto": txt, "muestra": muestra, **({"historial": hist} if hist else {}), **({"brief": brief} if brief else {})}
    d = json.load(urllib.request.urlopen(urllib.request.Request(CHAT, data=json.dumps(cuerpo).encode(), headers={"Content-Type": "application/json"}), timeout=120))
    return d, time.time() - a


hechas = lambda d: [c["herramienta"] for c in d["cambios"]]
datos = lambda d: (d.get("estado") or {}).get("datos") or {}
nuevos = lambda d, s: datos(d).get("nuevos", {}).get(s, [])
borrados = lambda d, s: datos(d).get("borrados", {}).get(s, [])
bloques = lambda d: (d.get("estado") or {}).get("bloques") or []
secciones_nuevas = lambda d: ((d.get("estado") or {}).get("estructura") or {}).get("secciones") or []
tipos_nuevos = lambda d: {c["tipo"] for s in secciones_nuevas(d) for c in s["campos"]}
pregunta = lambda d: "?" in d["respuesta"]

# Nombres de las gráficas del catálogo (para contar cuántas propone). El más largo primero: «columnas apiladas» no cuenta también «columnas».
GRAFICAS = ["columnas apiladas", "columnas 100", "barras horizontales", "barras apiladas", "barra 100", "línea con área", "linea con area", "área apilada",
            "línea con tendencia", "anillos concéntricos", "anillo de meta", "mapa de árbol", "caja y bigotes", "mapa de calor", "tabla de posiciones",
            "columnas + acumulado", "múltiplos pequeños", "media dona", "rosa polar", "puntos por categoría", "línea de tiempo", "barras de progreso",
            "bala contra meta", "dos kpis", "kpi con tendencia", "columnas", "barras", "línea", "linea", "dona", "pastel", "medidor", "embudo", "radar",
            "dispersión", "burbujas", "histograma", "cascada", "estadísticas", "paleta", "pareto", "escalones", "pendiente", "waffle", "sol", "gantt", "kpi"]


def cuantas_graficas(texto):
    t, n = texto.lower(), 0
    for g in GRAFICAS:
        patron = r"(?<![\wáéíóúñ])" + re.escape(g) + r"(?![\wáéíóúñ])"
        if re.search(patron, t):
            n += 1
            t = re.sub(patron, " ", t)
    return n


JERGA = re.compile(r"integrad|\bpropia\b|\bl_\w+|\bp_\w+|\bb\d+\b|\b[a-z]+_[a-z_]+\b|pestanas_base|graficos_posibles", re.I)
VACIA = re.compile(r"no (tiene|tienes|hay)\b|vac[ií]a|sin (datos|registros)|todav[ií]a no|a[uú]n no|ning[uú]n (registro|pago|dato)", re.I)

H_RECOMENDADA = [{"de": "yo", "t": "¿qué gráficas puedo poner?"},
                 {"de": "shifu", "t": "Con tus miembros puedo ponerte una dona por estado (te la recomiendo), columnas por mes de alta o barras por plan. ¿Cuál quieres?"}]
H_ABIERTA = [{"de": "yo", "t": "¿qué gráficas puedo poner?"},
             {"de": "shifu", "t": "Puedes poner muchas: dona, columnas, barras, línea, embudo, medidor, pastel, histograma y más. ¿Cuál te gustaría?"}]

CASOS = [  # (descripción, plantilla, estado, texto, historial, muestra, brief, verificación)
    ("19 cita en la agenda (hay sección)", "agenda", E(bloques=[]), "agenda una cita con Pedro Ramírez mañana a las 3 de la tarde", None, POCOS, None,
     lambda d: "agregar_tarea" not in hechas(d) and len(nuevos(d, "citas")) == 1),
    ("19 cita sin sección de agenda", "taller-mecanico", E(bloques=[]), "agéndame una cita con Pedro Ramírez el viernes a las 10 para revisar su carro", None, POCOS, None,
     lambda d: "agregar_tarea" not in hechas(d) and (("crear_seccion" in hechas(d) and any(nuevos(d, s["id"]) for s in secciones_nuevas(d))) or pregunta(d))),
    ("14 ¿qué gráficas puedo poner? → 2 o 3", "membresias", E(), "¿qué gráficas puedo poner?", None, POCOS, None,
     lambda d: not d["cambios"] and 2 <= cuantas_graficas(d["respuesta"]) <= 3),
    ("13 gráfica sobre sección vacía: avisa y ofrece", "membresias", E(bloques=[]), "ponme una gráfica de mis pagos por mes", None, VACIO, None,
     lambda d: bool(VACIA.search(d["respuesta"])) and pregunta(d)),
    ("19 quiero llevar inventario", "membresias", E(), "quiero llevar el inventario de los productos que vendo", None, POCOS, None,
     lambda d: "crear_seccion" in hechas(d) and "numero" in tipos_nuevos(d)),
    ("19 cobros a crédito", "pedidos", E(bloques=[]), "vendo a crédito y quiero llevar quién me debe, cuánto y cuándo me tiene que pagar", None, POCOS, None,
     lambda d: "crear_seccion" in hechas(d) and {"dinero", "fecha"} <= tipos_nuevos(d)),
    ("7 «sí» suelto acepta la recomendada", "membresias", E(), "sí", H_RECOMENDADA, POCOS, None,
     lambda d: any(b["vista"] == "grafico" and (b.get("opciones") or {}).get("tipo") == "dona" for b in bloques(d)) and not pregunta(d)),
    ("7 «sí» suelto a una pregunta abierta no la repite", "membresias", E(), "sí", H_ABIERTA, POCOS, None,
     lambda d: any(b["vista"] == "grafico" for b in bloques(d)) or bool(re.search(r"recomiend", d["respuesta"], re.I))),
    ("8 sin jerga: ¿por qué no veo nada?", "membresias", E("pagos"), "¿por qué no veo nada aquí?", None, VACIO, None,
     lambda d: bool(d["respuesta"].strip()) and not JERGA.search(d["respuesta"])),
    ("8 sin jerga: qué es cada pestaña", "membresias", E(), "¿para qué sirve cada pestaña de mi CRM?", None, POCOS, None,
     lambda d: bool(d["respuesta"].strip()) and not JERGA.search(d["respuesta"])),
    ("20 quitar una pieza: directo", "membresias", E(), "quita los vencimientos del inicio", None, POCOS, None,
     lambda d: [b["uid"] for b in bloques(d)] == ["b0"] and not pregunta(d)),
    ("20 «todos» en el texto no pide sí para una pieza", "membresias", E(bloques=[*B, DONA]), "quita la dona de todos los miembros", None, POCOS, None,
     lambda d: [b["uid"] for b in bloques(d)] == ["b0", "b1"] and not pregunta(d)),
    ("20 borrado masivo sigue pidiendo sí", "membresias", E(), "borra a todos los miembros", None, POCOS, None,
     lambda d: not borrados(d, "miembros") and pregunta(d)),
    ("12 recomienda sobre el negocio, no la plantilla", "membresias", E(), "¿qué me recomiendas para ordenar mi negocio?", None, POCOS, PEPES,
     lambda d: bool(re.search(r"repar|comput|celular|repuest|laptop", d["respuesta"], re.I))),
]

ok = tot = 0
tiempos = []
for _ in range(N):
    for desc, plantilla, est, txt, hist, muestra, brief, verif in CASOS:
        try:
            d, t = pide(plantilla, est, txt, hist, muestra, brief)
        except Exception as e:  # noqa: BLE001
            print(f"✗  error | {desc} | {e}")
            tot += 1
            continue
        tiempos.append(t)
        b = bool(verif(d))
        ok += b
        tot += 1
        print(f"{'✓' if b else '✗'} {t:4.1f}s | {desc} | «{txt}»")
        if not b:
            print(f"     hizo: {hechas(d)} fallos={d['fallos'][:1]}\n     dijo: {d['respuesta'][:300]}")
tiempos.sort()
print(f"\n{ok}/{tot} correctos · tiempo medio {sum(tiempos)/len(tiempos):.1f}s · mediana {tiempos[len(tiempos)//2]:.1f}s · máx {max(tiempos):.1f}s")

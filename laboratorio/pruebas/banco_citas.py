"""Banco de citas, borrados y objetivos que no están en pantalla, con la IA real. Cada caso sale de la prueba manual del 19-oct
(INFORME_PRUEBA_MANUAL_2026-10-19.md) y verifica el ESTADO que devuelve el servidor, no solo qué herramienta llamó:
- cita de mañana a las 3 y cada jueves por 3 semanas → registros en la agenda con ESAS fechas (no una tarea, no «Pedidos»);
- cita sin ninguna agenda → no la guarda como tarea: propone crear la agenda y pregunta;
- «borra todas las pestañas» → propone solo lo que se ve (nunca las ocultas) y no borra nada todavía; el «sí» borra justo eso;
- «borra la tabla» sin tabla en la pestaña abierta → no toca nada y lo dice o pregunta;
- «quita el campo que creas menos importante» → no elige solo: propone y espera;
- «agrega 40 empleados» con Equipo oculta → no los mete en otra sección ni crea una igual: pregunta «¿la muestro o creo otra?».
Uso: python3 laboratorio/pruebas/banco_citas.py [repeticiones=1]"""
import datetime, json, os, re, sys, time, urllib.request

CHAT = os.environ.get("BASE", "http://localhost:5190") + os.environ.get("RUTA_CHAT", "/api/lab/chat")
N = int(sys.argv[1]) if len(sys.argv) > 1 else 1
HOY = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-6))).date()  # la hora del negocio (operaciones.ZONA)
MANANA = HOY + datetime.timedelta(days=1)
JUEVES = [MANANA + datetime.timedelta(days=(3 - MANANA.weekday()) % 7 or 7)]  # el primer jueves DESPUÉS de mañana
JUEVES += [JUEVES[0] + datetime.timedelta(days=7 * k) for k in (1, 2)]

B_MEMB = [{"uid": "b0", "vista": "kpis", "seccion": "miembros", "opciones": {"por": "estado"}, "ancho": 12, "alto": 1},
          {"uid": "b1", "vista": "vencimientos", "seccion": "miembros", "opciones": {"fecha": "vence", "titulo": "nombre", "dias": 30}, "ancho": 12, "alto": 2}]
B_AGENDA = [{"uid": "b0", "vista": "agenda", "seccion": "citas", "opciones": {"fecha": "fecha", "hora": "hora", "titulo": "cliente", "detalle": "servicio", "dias": 14}, "ancho": 12, "alto": 2}]


def pide(plantilla, est, txt, hist=None, pendiente=None):
    a = time.time()
    cuerpo = {"plantilla": plantilla, "estado": est, "texto": txt, **({"historial": hist} if hist else {}), **({"pendiente": pendiente} if pendiente else {})}
    d = json.load(urllib.request.urlopen(urllib.request.Request(CHAT, data=json.dumps(cuerpo).encode(), headers={"Content-Type": "application/json"}), timeout=120))
    return d, time.time() - a


herr = lambda d: [c["herramienta"] for c in d["cambios"]]
nuevos = lambda d, s: (((d.get("estado") or {}).get("datos") or {}).get("nuevos") or {}).get(s, [])
estructura = lambda d: (d.get("estado") or {}).get("estructura") or {}
TAREA = ("agregar_tarea",)


def es_tarea(d):
    """¿Guardó algo en el tablero de tareas (la sección que en comercio se llamaba «Pedidos»)?"""
    return any(c["herramienta"] in TAREA or (c["herramienta"] in ("agregar_registro", "agendar") and (c.get("args") or {}).get("seccion") == "desarrollo")
               for c in d["cambios"])


def citas_ok(d):
    fechas = sorted(r["valores"].get("fecha") for r in nuevos(d, "citas"))
    horas = {r["valores"].get("hora") for r in nuevos(d, "citas")}
    return fechas == sorted([MANANA.isoformat(), *(j.isoformat() for j in JUEVES)]) and horas == {"15:00"} and not es_tarea(d)


def sin_cambios(d):
    return not d["cambios"] and not estructura(d).get("ocultas") and not estructura(d).get("camposQuitados")


OCULTAS_MEMB = ("Contactos", "Proyectos", "Importar datos", "Cobros")  # lo que la siembra de membresías deja oculto (rubro sin decir)


def propone_visibles(d):
    """No borra nada todavía, no nombra ninguna oculta y nombra las que se ven (Miembros y Pagos)."""
    r = d["respuesta"]
    return (not d["cambios"] and not any(o.lower() in r.lower() for o in OCULTAS_MEMB)
            and "miembros" in r.lower() and "pagos" in r.lower() and ("?" in r or "sí" in r.lower()))


CASOS = []  # (descripción, función que corre el caso y devuelve (ok, d, t, detalle))


def caso(desc):
    def deco(f):
        CASOS.append((desc, f))
        return f
    return deco


@caso("cita mañana a las 3 + cada jueves 3 semanas → 4 registros en Citas con esas fechas")
def _():
    d, t = pide("agenda", {"vista": "inicio", "bloques": B_AGENDA}, "agéndame una cita con Ramires mañana a las 3 y luego cada jueves por 3 semanas a la misma hora")
    return citas_ok(d), d, t, f"citas={[(r['valores'].get('fecha'), r['valores'].get('hora')) for r in nuevos(d, 'citas')]} tarea={es_tarea(d)}"


@caso("cita sin agenda → no la guarda como tarea; propone crear la agenda y pregunta")
def _():
    d, t = pide("membresias", {"vista": "inicio", "bloques": B_MEMB}, "agéndame una cita con Ramires mañana a las 3")
    return not es_tarea(d) and not d["cambios"] and "?" in d["respuesta"], d, t, f"tarea={es_tarea(d)}"


@caso("«borra todas las pestañas» → propone solo las visibles y no borra nada todavía")
def _():
    d, t = pide("membresias", {"vista": "inicio", "bloques": B_MEMB}, "borra todas las pestañas, quiero empezar de cero")
    return propone_visibles(d), d, t, f"pendiente={d.get('pendiente')}"


@caso("«sí» a borrar todas → quita exactamente las que se veían")
def _():
    est = {"vista": "inicio", "bloques": B_MEMB}
    d1, t1 = pide("membresias", est, "borra todas las pestañas, quiero empezar de cero")
    hist = [{"de": "yo", "t": "borra todas las pestañas, quiero empezar de cero"}, {"de": "shifu", "t": d1["respuesta"]}]
    d, t = pide("membresias", est, "sí", hist, d1.get("pendiente"))
    e = estructura(d)
    nuevas = {s["id"] for s in e.get("secciones") or []}
    # Miembros y Pagos (listas) se van con sus datos; Historial y Equipo (fijas) se ocultan. Nada se crea.
    quitadas = set(e.get("camposQuitados") or {}) | set(e.get("ocultas") or [])
    datos = (d.get("estado") or {}).get("datos") or {}
    borradas = set((datos.get("borrados") or {}).keys())
    ok = {"actividad", "equipo"} <= set(e.get("ocultas") or []) and {"miembros", "pagos"} <= (borradas | quitadas) and not nuevas
    return ok, d, t1 + t, f"ocultas={e.get('ocultas')} borrados={sorted(borradas)}"


@caso("«borra la tabla» sin tabla en el inicio → no toca nada y lo dice o pregunta")
def _():
    d, t = pide("membresias", {"vista": "inicio", "bloques": B_MEMB}, "borra la tabla")
    return sin_cambios(d) and not re.search(r"\b(quité|borré|eliminé)\b", d["respuesta"], re.I), d, t, ""


@caso("«quita el calendario» sin calendario en la pestaña Miembros → no toca nada")
def _():
    d, t = pide("membresias", {"vista": "miembros", "bloques": B_MEMB}, "quita el calendario de aquí")
    return sin_cambios(d) and not re.search(r"\b(quité|borré|eliminé)\b", d["respuesta"], re.I), d, t, ""


@caso("«quita el campo que creas menos importante» → propone cuál y por qué, y espera")
def _():
    d, t = pide("membresias", {"vista": "miembros", "bloques": B_MEMB}, "a miembros quítale el campo que tú creas menos importante")
    return sin_cambios(d) and "?" in d["respuesta"], d, t, ""


@caso("«agrega 40 empleados» con Equipo oculta → pregunta si la muestra o crea otra; no los mete en Miembros")
def _():
    d, t = pide("membresias", {"vista": "inicio", "bloques": B_MEMB, "estructura": {"ocultas": ["equipo"]}}, "agrega 40 empleados")
    return (not nuevos(d, "miembros") and "crear_seccion" not in herr(d) and "equipo" in d["respuesta"].lower()), d, t, ""


@caso("empleados con nombre y Equipo oculta → no crea «Empleados» sin preguntar")
def _():
    d, t = pide("membresias", {"vista": "inicio", "bloques": B_MEMB, "estructura": {"ocultas": ["equipo"]}},
                "agrega a mis empleados: Ana López cajera y Luis Pérez técnico")
    return (not nuevos(d, "miembros") and "crear_seccion" not in herr(d) and "equipo" in d["respuesta"].lower()), d, t, ""


ok = tot = 0
tiempos = []
for _ in range(N):
    for desc, f in CASOS:
        bien, d, t, detalle = f()
        tiempos.append(t)
        ok += bool(bien)
        tot += 1
        print(f"{'✓' if bien else '✗'} {t:4.1f}s | {desc}")
        if os.environ.get("VER"):  # VER=1: también lo que dijo en los casos que pasan (para revisar a ojo)
            print(f"     dijo: {d['respuesta'][:300]}")
        if not bien:
            print(f"     hizo: {[(c['herramienta'], c.get('args')) for c in d['cambios']][:6]} fallos={d['fallos'][:2]}\n     {detalle}\n     dijo: {d['respuesta'][:240]}")
print(f"\n{ok}/{tot} correctos · tiempo medio {sum(tiempos)/len(tiempos):.1f}s · máx {max(tiempos):.1f}s")

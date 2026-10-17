"""Banco D49 con la IA real: herramientas que se piden por chat (calendario, cifra, tablero con montos…) y pestañas como
cuaderno en blanco. Verifica el ESTADO final (dónde quedó cada pieza), no solo qué herramienta llamó.
Uso: python3 laboratorio/pruebas/banco_pestanas.py [repeticiones=1]"""
import json, re, sys, time, urllib.request
N = int(sys.argv[1]) if len(sys.argv) > 1 else 1
B = [{"uid": "b0", "vista": "kpis", "seccion": "miembros", "opciones": {"por": "estado"}, "ancho": 12, "alto": 1},
     {"uid": "b1", "vista": "vencimientos", "seccion": "miembros", "opciones": {"fecha": "vence", "titulo": "nombre", "dias": 30}, "ancho": 12, "alto": 2}]
def E(vista="inicio", paginas=None):
    return {"vista": vista, "bloques": B, **({"estructura": {"paginas": paginas}} if paginas else {})}
def pide(est, txt, sel=None):
    a = time.time()
    d = json.load(urllib.request.urlopen(urllib.request.Request("http://localhost:5190/api/lab/chat", data=json.dumps({"plantilla": "membresias", "estado": est, "texto": txt, **({"seleccion": sel} if sel else {})}).encode(), headers={"Content-Type": "application/json"}), timeout=120))
    return (d["estado"] if (d["cambios"] or d.get("estadoCambio")) else est), d, time.time() - a
pag = lambda e, pid: ((e.get("estructura") or {}).get("paginas") or {}).get(pid) or []
inicio_v = lambda e: [b["vista"] for b in e["bloques"]]
PAG = {"miembros": [{"uid": "p_miembros", "seccion": "miembros", "vista": "tabla", "opciones": {}, "ancho": 12, "alto": 3},
                    {"uid": "pz1", "seccion": "miembros", "vista": "grafico", "opciones": {"tipo": "dona"}, "ancho": 6, "alto": 2}]}
CASOS = [  # (descripción, estado, texto, selección, verificación)
    ("calendario en el inicio", E(), "quiero ver los vencimientos de mis miembros en un calendario", None, lambda e, d: "calendario_mes" in inicio_v(e)),
    ("cifra con meta", E(), "ponme una cifra de cuántos miembros tengo con meta de 300", None, lambda e, d: any(b["vista"] == "cifra" and str((b.get("opciones") or {}).get("meta")) in ("300", "300.0") for b in e["bloques"])),
    ("tablero con montos", E(), "quiero un tablero de mis pagos por estado con el total de cada columna", None, lambda e, d: ("tablero_dinero" in inicio_v(e) or any(b["vista"] == "tablero_dinero" for p in ((e.get("estructura") or {}).get("paginas") or {}).values() for b in p)) or (not d["cambios"] and not re.search(r"\\b(listo|agregu[ée]|puse)\\b", d["respuesta"], re.I))),  # Pagos no tiene estado: hacerlo bien o decir con honestidad que falta
    ("pieza en la pestaña que está mirando", E("miembros"), "aquí pon arriba un resumen por estado", None, lambda e, d: any(b["vista"] == "kpis" for b in pag(e, "miembros")) and inicio_v(e) == ["kpis", "vencimientos"]),
    ("pieza en otra pestaña nombrándola", E(), "en la pestaña de pagos agrega una gráfica de columnas", None, lambda e, d: any(b["vista"] == "grafico" for b in pag(e, "pagos")) and inicio_v(e) == ["kpis", "vencimientos"]),
    ("quitar lo elegido dentro de una pestaña", E("miembros", PAG), "quita esto", [{"tipo": "bloque", "id": "pz1", "nombre": "Dona · Miembros"}], lambda e, d: [b["uid"] for b in pag(e, "miembros")] == ["p_miembros"] and inicio_v(e) == ["kpis", "vencimientos"]),
    ("cambiar la vista base de una pestaña", E("miembros"), "cambia esta lista por un tablero por estado", None, lambda e, d: any(b["vista"] == "tablero" for b in pag(e, "miembros"))),
    ("algo que no existe: no inventa", E(), "quiero un mapa de calor de mis miembros por ciudad", None, lambda e, d: inicio_v(e) == ["kpis", "vencimientos"] and not pag(e, "miembros")),
    # Compuesto: lo que existe se hace y lo que no se dice (el cerco de sustitutos no debe deshacer la dona pedida).
    ("compuesto: una existe y otra no", E(), "agrega una dona por estado y una gráfica de radar de los planes", None,
     lambda e, d: any(b["vista"] == "grafico" and (b.get("opciones") or {}).get("tipo") == "dona" for b in e["bloques"]) and not any((b.get("opciones") or {}).get("tipo") == "radar" for b in e["bloques"]) and re.search(r"radar", d["respuesta"], re.I)),
]
ok = tot = 0; tiempos = []
for _ in range(N):
    for desc, est, txt, sel, verif in CASOS:
        e2, d, t = pide(est, txt, sel); tiempos.append(t)
        b = bool(verif(e2, d)); ok += b; tot += 1
        print(f"{'✓' if b else '✗'} {t:4.1f}s | {desc} | «{txt}»")
        if not b: print(f"     hizo: {[(c['herramienta'], c['args'].get('pestana'), c['args'].get('vista')) for c in d['cambios']]} fallos={d['fallos'][:1]}\n     inicio={inicio_v(e2)} paginas={ {k: [x['vista'] for x in v] for k, v in ((e2.get('estructura') or {}).get('paginas') or {}).items()} }\n     dijo: {d['respuesta'][:160]}")
print(f"\n{ok}/{tot} correctos · tiempo medio {sum(tiempos)/len(tiempos):.1f}s · máx {max(tiempos):.1f}s")

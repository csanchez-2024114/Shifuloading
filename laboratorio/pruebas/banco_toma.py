"""Banco de la toma de diseño (D26, D27), con la IA real. Rehecho el 2026-10-16: el original se perdió con el scratchpad.
Verifica el ESTADO por paso (fase de la ficha, bloques anotados y bloques construidos), no solo lo que dice la IA.
Uso: python3 laboratorio/pruebas/banco_toma.py [repeticiones=1]"""
import json, sys, time, urllib.request
import os
CHAT = os.environ.get("BASE", "http://localhost:5190") + os.environ.get("RUTA_CHAT", "/api/lab/chat")  # D61: el mismo banco mide el laboratorio o el CRM
N = int(sys.argv[1]) if len(sys.argv) > 1 else 1
E = {"vista": "inicio", "bloques": [{"uid": "b0", "vista": "kpis", "seccion": "miembros", "opciones": {"por": "estado"}, "ancho": 12, "alto": 1}]}
def pide(est, txt, h):
    a = time.time()
    d = json.load(urllib.request.urlopen(urllib.request.Request(CHAT, data=json.dumps({"plantilla": "membresias", "estado": est, "texto": txt, "historial": h}).encode(), headers={"Content-Type": "application/json"}), timeout=120))
    est2 = d["estado"] if (d["cambios"] or d.get("estadoCambio")) else est
    return est2, h + [{"de": "yo", "t": txt}, {"de": "shifu", "t": d["respuesta"]}], d, time.time() - a
toma = lambda e: e.get("toma") or {}
fbloques = lambda e: (toma(e).get("ficha") or {}).get("bloques", [])
vistas = lambda e: [b.get("vista") + (":" + (b.get("opciones") or {}).get("tipo", "") if b.get("vista") == "grafico" else "") for b in e["bloques"]]
GUIONES = [
    ("pedir, anotar, cambiar y confirmar", [
        ("Diséñame un inicio nuevo para controlar mis pagos", lambda e, d: toma(e).get("activa") and toma(e).get("fase") == "juntando"),
        ("Quiero un resumen de pagos y una dona de los estados de los miembros", lambda e, d: len(fbloques(e)) >= 2),
        ("No, mejor barras en vez de dona", lambda e, d: not any((b.get("opciones") or {}).get("tipo") == "dona" for b in fbloques(e)) and any("barras" in json.dumps(b) for b in fbloques(e))),
        ("Sí", lambda e, d: not toma(e).get("activa") and len(e["bloques"]) >= 2 and any("barras" in v for v in vistas(e))),
    ]),
    ("abandonar sin cambiar nada", [
        ("Quiero rediseñar mi inicio", lambda e, d: toma(e).get("activa")),
        ("mejor olvídalo, déjalo como está", lambda e, d: not toma(e).get("activa") and [b["uid"] for b in e["bloques"]] == ["b0"]),
    ]),
    ("pedir varias cosas en un mensaje", [
        ("diséñame un inicio con una lista de pagos, un tablero de miembros por estado y lo que vence", lambda e, d: len(fbloques(e)) >= 3 or toma(e).get("fase") == "confirmando"),
    ]),
    ("digresión en medio de la toma", [
        ("Diséñame un inicio nuevo para mis miembros", lambda e, d: toma(e).get("activa")),
        ("oye, ¿qué hora es en Guatemala?", lambda e, d: toma(e).get("activa") and not fbloques(e)),
    ]),
    ("pedido vago: abre la ficha y NO inventa piezas", [
        ("Diséñame un inicio nuevo para mis miembros", lambda e, d: toma(e).get("activa") and not fbloques(e)),
    ]),
    ("cambio puntual NO abre la toma", [
        ("haz el resumen más chico", lambda e, d: not toma(e).get("activa")),
    ]),
]
ok = tot = 0; tiempos = []
for _ in range(N):
    for nombre, pasos in GUIONES:
        est, h = E, []
        bien_guion = True
        for txt, verif in pasos:
            est, h, d, t = pide(est, txt, h); tiempos.append(t)
            b = bool(verif(est, d)); tot += 1; ok += b; bien_guion &= b
            if not b: print(f"   ✗ «{txt}» fase={toma(est).get('fase')} activa={toma(est).get('activa')} ficha={[x.get('vista') for x in fbloques(est)]} inicio={vistas(est)}\n      dijo: {d['respuesta'][:160]}")
        print(f"{'✓' if bien_guion else '✗'} {nombre}")
print(f"\n{ok}/{tot} pasos correctos · tiempo medio {sum(tiempos)/len(tiempos):.1f}s")

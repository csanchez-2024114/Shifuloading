"""Banco de deshacer y de cambios no pedidos (D46), con la IA real. Cada caso nació de una falla medida el 2026-10-16.
Mide POR PASO: antes solo se miraba el final, y errores que se cancelaban entre sí pasaban como acierto.
Uso: python3 laboratorio/pruebas/banco_deshacer.py [repeticiones=3]"""
import json, urllib.request, re, sys
import os
CHAT = os.environ.get("BASE", "http://localhost:5190") + os.environ.get("RUTA_CHAT", "/api/lab/chat")  # D61: el mismo banco mide el laboratorio o el CRM
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3
E = {"vista": "inicio", "bloques": [{"uid": "b0", "vista": "kpis", "seccion": "miembros", "opciones": {"por": "estado"}, "ancho": 12, "alto": 1},
     {"uid": "b1", "vista": "vencimientos", "seccion": "miembros", "opciones": {"fecha": "vence", "titulo": "nombre", "dias": 30}, "ancho": 6, "alto": 2},
     {"uid": "b2", "vista": "grafica", "seccion": "miembros", "opciones": {"tipo": "linea", "fecha": "alta"}, "ancho": 6, "alto": 2}]}
def pide(est, txt, h=[], sel=None):
    d = json.load(urllib.request.urlopen(urllib.request.Request(CHAT, data=json.dumps({"plantilla": "membresias", "estado": est, "texto": txt, "historial": h, **({"seleccion": sel} if sel else {})}).encode(), headers={"Content-Type": "application/json"}), timeout=120))
    return (d["estado"] if (d["cambios"] or d.get("estadoCambio")) else est), h + [{"de": "yo", "t": txt}, {"de": "shifu", "t": d["respuesta"]}], d
uids = lambda e: [b["uid"] for b in e["bloques"]]
marca = lambda e: (e.get("marca", {}) or {}).get("primario")
herr = lambda d: [x["herramienta"] for x in d["cambios"]]
res = {}
def anota(caso, ok): res.setdefault(caso, [0, 0]); res[caso][0] += bool(ok); res[caso][1] += 1

for _ in range(N):
    # 1. Cadena: dona → rojo → "eso del color no" (solo la marca) → "deshaz también la dona"
    est, h, _ = pide(E, "agrega una dona de los estados de los miembros"); dona = [u for u in uids(est) if u not in ("b0", "b1", "b2")]
    est, h, _ = pide(est, "pon mis colores: rojo #DC2626", h)
    est, h, d = pide(est, "eso del color no, déjalo como antes", h)
    anota("deshacer solo el color", herr(d) == ["deshacer"] and not marca(est) and dona and dona[0] in uids(est) and "deshice" in d["respuesta"])
    est, h, d = pide(est, "deshaz también la dona", h)
    anota("deshacer también la dona", herr(d) == ["deshacer"] and uids(est) == ["b0", "b1", "b2"])
    # 2. Compuesto: deshacer y reemplazar lo mismo en un mensaje
    est, h, _ = pide(E, "pon mis colores: rojo #DC2626")
    est, h, d = pide(est, "eso del rojo no, mejor ponlo azul #2563EB", h)
    anota("eso no, mejor azul", (marca(est) or "").lower() == "#2563eb")
    # 3. Nada que deshacer: no inventar cambios
    est, h, d = pide(E, "deshaz lo último")
    anota("nada que deshacer", not d["cambios"] and uids(est) == ["b0", "b1", "b2"])
    # 4. Quitar lo elegido: no achicar otro bloque de más
    est, h, d = pide(E, "quita esto", [], [{"tipo": "bloque", "id": "b2", "nombre": "Gráfica · Miembros"}])
    anota("quitar sin achicar otro", herr(d) == ["quitar_bloque"] and [b["ancho"] for b in est["bloques"]] == [12, 12])
    # 5. "agrega" agrega (no reemplaza)
    est, h, d = pide(E, "agrega una dona de los estados de los miembros")
    anota("agregar no reemplaza", herr(d) == ["agregar_bloque"] and len(est["bloques"]) == 4)

tot = [sum(v[0] for v in res.values()), sum(v[1] for v in res.values())]
for k, (a, b) in res.items(): print(f"{'✓' if a == b else '✗'} {a}/{b}  {k}")
print(f"\n{tot[0]}/{tot[1]} pasos correctos")

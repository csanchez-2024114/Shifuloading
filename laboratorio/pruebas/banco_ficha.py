"""Banco F2 (D28): ficha, tarjeta y campos editables por chat, con la IA real. Cada caso verifica el ESTADO final
(no solo qué herramienta llamó) y que la respuesta no afirme algo que no pasó."""
import json, time, urllib.request, re
E = {"vista":"inicio","bloques":[{"uid":"b0","vista":"kpis","seccion":"miembros","opciones":{"por":"estado"},"ancho":12,"alto":1},
 {"uid":"b1","vista":"vencimientos","seccion":"miembros","opciones":{"fecha":"vence","titulo":"nombre","dias":30},"ancho":6,"alto":2},
 {"uid":"b2","vista":"grafica","seccion":"miembros","opciones":{"tipo":"linea","fecha":"alta"},"ancho":6,"alto":2}]}

def est(d): return d["estado"].get("estructura", {}) or {}
def grupos(d): return (est(d).get("ficha", {}).get("miembros") or {}).get("grupos", [])
CASOS = [  # (texto, verificación del estado final, descripción)
 ("en la ficha de los miembros pon arriba el plan y el estado, y abajo las fechas en otro grupo que se llame Fechas",
  lambda d: len(grupos(d)) >= 2 and any("fecha" in g["titulo"].lower() and set(g["campos"]) >= {"alta", "vence"} for g in grupos(d)) and "plan" in grupos(d)[0]["campos"],
  "ficha con grupo Fechas"),
 ("que la ficha de los miembros ya no muestre lo relacionado",
  lambda d: (est(d).get("ficha", {}).get("miembros") or {}).get("relacionados") is False, "relacionados apagado"),
 ("en las tarjetas de miembros muestra el nombre y el plan",
  lambda d: (est(d).get("tarjeta", {}).get("miembros") or {}).get("campos") == ["nombre", "plan"], "tarjeta nombre+plan"),
 ("cambia el nombre del campo Vence a Fecha de vencimiento",
  lambda d: "vencimiento" in (est(d).get("nombresCampo", {}).get("miembros", {}).get("vence", "")).lower(), "campo renombrado"),
 ("agrega el estado Congelada a los miembros",
  lambda d: set(est(d).get("opcionesEstado", {}).get("miembros", {}).get("estado", [])) == {"Activa", "Pausada", "Cancelada", "Congelada"}, "opción agregada sin perder las otras"),
 ("quita el estado Pausada; los que estén pausados pásalos a Activa",
  lambda d: "Pausada" not in est(d).get("opcionesEstado", {}).get("miembros", {}).get("estado", ["Pausada"]) and est(d).get("mapeoEstado", {}).get("miembros", {}).get("estado", {}).get("Pausada") == "Activa", "opción quitada con destino"),
 # El campo «alta» lo usa la gráfica b2: el código lo frena. La IA NO debe decir que lo quitó.
 ("quita el campo alta de los miembros",
  lambda d: "alta" in est(d).get("camposQuitados", {}).get("miembros", []) or not re.search(r"\b(quité|eliminé|listo)\b", d["respuesta"], re.I), "honesto si el código lo frena"),
]
ok = 0; tiempos = []
for texto, verif, desc in CASOS:
    a = time.time()
    d = json.load(urllib.request.urlopen(urllib.request.Request("http://localhost:5190/api/lab/chat", data=json.dumps({"plantilla":"membresias","estado":E,"texto":texto}).encode(), headers={"Content-Type":"application/json"}), timeout=120))
    t = time.time() - a; tiempos.append(t)
    bien = bool(verif(d)); ok += bien
    print(f"{'✓' if bien else '✗'} {t:4.1f}s | {desc} | {texto}\n     hizo: {[c['herramienta'] for c in d['cambios']] or '—'}{'  FALLOS:'+str(d['fallos'])[:200] if d['fallos'] else ''}\n     dijo: {d['respuesta'][:200]}")
    if not bien: print(f"     estructura: {json.dumps(est(d), ensure_ascii=False)[:400]}")
print(f"\n{ok}/{len(CASOS)} correctos · tiempo medio {sum(tiempos)/len(tiempos):.1f}s · máx {max(tiempos):.1f}s")

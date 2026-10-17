"""Jornada completa con la IA real: lo que una persona haría en su CRM, de crear a borrar. Incluye A PROPÓSITO cosas que
hoy no existen (importar o exportar Excel, reordenar pestañas, tema, avisos…) para medir si la IA es honesta cuando no puede.
Meter, cambiar, borrar y consultar datos por chat existe desde D50.
Guarda TODO (herramientas, argumentos, fallos, respuesta) en un JSON para etiquetar a mano (método de Alan).
Uso: python3 laboratorio/pruebas/jornada.py [salida.json]"""
import json, sys, time, urllib.request
SALIDA = sys.argv[1] if len(sys.argv) > 1 else "/tmp/jornada.json"
B = [{"uid": "b0", "vista": "kpis", "seccion": "miembros", "opciones": {"por": "estado"}, "ancho": 12, "alto": 1},
     {"uid": "b1", "vista": "vencimientos", "seccion": "miembros", "opciones": {"fecha": "vence", "titulo": "nombre", "dias": 30}, "ancho": 6, "alto": 2},
     {"uid": "b2", "vista": "grafica", "seccion": "miembros", "opciones": {"tipo": "linea", "fecha": "alta"}, "ancho": 6, "alto": 2}]
E = lambda vista="inicio": {"vista": vista, "bloques": B}
CASOS = [  # (área, qué existe hoy, estado, texto)
    ("estructura", "existe", E(), "agrega una pestaña de cobros"),
    ("estructura", "existe", E(), "quiero llevar mis proveedores con nombre, teléfono y qué me venden"),
    ("estructura", "existe", E(), "cambia el nombre de la pestaña pagos a Cobranza"),
    ("estructura", "NO existe", E(), "pon la pestaña de pagos antes que la de miembros en el menú"),
    ("estructura", "NO existe", E(), "cámbiale el ícono a la pestaña miembros por una estrella"),
    ("campos", "existe", E(), "agrega el campo correo a miembros"),
    ("campos", "NO existe", E(), "cambia el campo plan para que sea una lista con Mensual, Trimestral y Anual"),
    ("datos", "existe", E(), "agrega a María López como miembro, plan mensual, vence el 30 de octubre"),
    ("datos", "existe", E(), "cambia el estado de Ana López a Pausada"),
    ("datos", "existe", E(), "borra a Carlos Pérez de mis miembros"),
    ("datos", "NO existe", E(), "quiero subir mi Excel con mis clientes"),
    ("datos", "NO existe", E(), "exporta mis miembros a Excel"),
    ("analizar", "existe", E(), "¿cuántos miembros activos tengo?"),
    ("analizar", "existe", E(), "¿cuánto me pagaron este mes?"),
    ("analizar", "existe", E(), "¿qué miembros vencen esta semana?"),
    ("vistas", "existe", E(), "muestra la pestaña de pagos como un calendario"),
    ("vistas", "existe", E(), "en el inicio pon una cifra del total de pagos del mes con meta de 5000 comparada con el mes pasado"),
    ("vistas", "existe", E("miembros"), "aquí agrega un tablero de miembros por estado"),
    ("diseño", "existe", E(), "haz el resumen más chico y ponlo a la derecha"),
    ("diseño", "NO existe", E(), "pon el tema oscuro"),
    ("diseño", "existe (marca)", E(), "usa la letra Montserrat"),
    ("asignar", "NO existe", E(), "asigna los miembros vencidos a Andrea del equipo"),
    ("asignar", "parcial", E(), "agrega un campo de responsable a pagos"),
    ("automatizar", "NO existe", E(), "avísame por WhatsApp cuando un miembro esté por vencer"),
    ("ficha", "existe", E(), "en la ficha de miembros pon arriba el plan y el estado"),
]
res = []
for area, existe, est, txt in CASOS:
    a = time.time()
    d = json.load(urllib.request.urlopen(urllib.request.Request("http://localhost:5190/api/lab/chat", data=json.dumps({"plantilla": "membresias", "estado": est, "texto": txt, "muestra": {"nivel": "pocos", "ejemplos": True, "pais": "gt"}}).encode(), headers={"Content-Type": "application/json"}), timeout=120))
    t = round(time.time() - a, 1)
    fila = {"area": area, "existe": existe, "texto": txt, "seg": t, "hizo": [{"h": c["herramienta"], "args": c["args"]} for c in d["cambios"]], "intentos": d.get("intentos", []), "consultas": d.get("consultas", []), "datos": (d.get("estado") or {}).get("datos"), "respuesta": d["respuesta"]}
    res.append(fila)
    print(f"[{area:11}] {existe:13} {t:4.1f}s «{txt}»\n   hizo: {[c['h'] for c in fila['hizo']] or '—'}{'  intentos fallidos: ' + str([i['herramienta'] for i in fila['intentos']]) if fila['intentos'] else ''}\n   dijo: {d['respuesta'][:230]}")
json.dump(res, open(SALIDA, "w"), ensure_ascii=False, indent=1)
print(f"\n{len(res)} pedidos · guardado en {SALIDA}")

"""Banco de memoria y cargas grandes (lista 4, 5, 6 y 11), con la IA real y la RUTA REAL del chat (`/api/v1/crm/chat`): el historial
lo guarda y lo lee el servidor (crm_conversaciones), como en la app. Caso real del INFORME_PRUEBA_MANUAL §4 (19-oct): un mensaje largo
con 5 empleados, 5 productos, 5 reparaciones y 3 ventas; luego «ya te los pasé». Verifica en el CRM (no en lo que dice la IA):
- cuántos de los 18 registros quedaron guardados al final (cada uno se reconoce por sus datos, en cualquier sección);
- si los productos quedaron parejos (marca y modelo en todos o en ninguno: punto 11);
- si cada respuesta dice la verdad: si faltan registros de un grupo, lo nombra; si no falta nada, no dice que falta; nunca «no veo los
  datos» teniéndolos.
Necesita el servidor de desarrollo (scripts/crm_dev_server.py) con CRM_DISENO=1: crea una cuenta nueva por repetición.
Uso: BASE=http://localhost:5203 python3 laboratorio/pruebas/banco_memoria.py [repeticiones=1]"""
import json, os, re, secrets, sys, time, unicodedata, urllib.error, urllib.request

API = os.environ.get("BASE", "http://localhost:5203") + "/api/v1"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 1

MENSAJE = ("Te paso todo para que lo registres, créale su sección a lo que no tenga. "
           "Empleados: Juan Pérez, técnico, tel 5555-1234, sueldo 4500; María López, vendedora, tel 5555-2345, sueldo 3800; "
           "Carlos Ruiz, cajero, tel 5555-3456, sueldo 3500; Ana Gómez, técnica, tel 5555-4567, sueldo 4200; "
           "Luis Martínez, bodeguero, tel 5555-5678, sueldo 3200. "
           "Productos del inventario: laptop HP Pavilion 15, costo 4500, precio 5800, 3 unidades; laptop Dell Inspiron 14, costo 4200, "
           "precio 5500, 2 unidades; monitor Samsung S24C, costo 1100, precio 1500, 6 unidades; teclado Logitech K120, costo 90, precio 150, "
           "15 unidades; impresora Epson L3250, costo 1300, precio 1800, 4 unidades. "
           "Reparaciones: laptop Lenovo de Pedro Sánchez, cambio de pantalla, la trajo ayer, cobro 650; PC de escritorio de Rosa Díaz, "
           "limpieza y formateo, la trajo hoy, cobro 250; laptop Acer de Mario Torres, no enciende, la trajo ayer, cobro 400; "
           "impresora Canon de Lucía Castro, atasco de papel, la trajo hoy, cobro 150; laptop Asus de Jorge Flores, cambio de teclado, "
           "la trajo hoy, cobro 350. "
           "Ventas: 2 monitores Samsung a Andrea Morales por 3000 hoy; 1 laptop HP a Roberto Silva por 5800 hoy; "
           "3 teclados Logitech a Sofía Herrera por 450 ayer.")
SEGUIR = "ya te los pasé, agrega lo que falte"
# Cada registro esperado: las piezas que deben estar juntas en UN registro (sin acentos, minúsculas).
ESPERADOS = {
    "empleados": [["juan perez"], ["maria lopez"], ["carlos ruiz"], ["ana gomez"], ["luis martinez"]],
    "productos": [["pavilion"], ["inspiron"], ["s24c"], ["k120"], ["l3250"]],
    "reparaciones": [["pedro sanchez", "650"], ["rosa diaz", "250"], ["mario torres", "400"], ["lucia castro", "150"], ["jorge flores", "350"]],
    "ventas": [["andrea morales", "3000"], ["roberto silva", "5800"], ["sofia herrera", "450"]],
}
TOTAL = sum(len(v) for v in ESPERADOS.values())
NO_VE = re.compile(r"no (veo|tengo|encuentro|encontr[eé]|recib[ií])[^.?!]{0,40}(datos|informaci[oó]n|lista|mensaje)", re.I)
# Cómo se nombra cada grupo en una respuesta (raíz, sin acentos) y lo que identifica a cada registro que falta.
GRUPO = {"empleados": "emplead|personal|trabajador", "productos": "product|inventario", "reparaciones": "repar", "ventas": "venta"}


def dice_lo_que_falta(r, p):
    """Verdad: por cada grupo al que le faltan registros, la respuesta lo nombra (o nombra lo que falta). «Solo falta el monitor»
    con 10 registros sin guardar no es verdad."""
    t = plano(r)
    for g, piezas in ESPERADOS.items():
        if p[g] < len(piezas) and not re.search(GRUPO[g], t) and not any(x[0] in t for x in piezas):
            return False
    return True


def plano(t):
    return "".join(c for c in unicodedata.normalize("NFD", str(t)) if unicodedata.category(c) != "Mn").lower()


def num(v):
    return str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)


def pedir(metodo, ruta, cuerpo=None, token=None):
    cab = {"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})}
    req = urllib.request.Request(API + ruta, data=json.dumps(cuerpo).encode() if cuerpo is not None else None, headers=cab, method=metodo)
    return json.load(urllib.request.urlopen(req, timeout=180))


def registros_de(crm):
    """Todos los registros del CRM como texto plano (secciones propias y contactos)."""
    out = []
    for l in crm.get("listas") or []:
        for r in l.get("registros") or []:
            out.append((l["nombre"], plano(" ".join(num(v) for v in (r.get("valores") or {}).values() if v not in (None, "")))))
    for c in crm.get("contactos") or []:
        out.append(("Contactos", plano(" ".join([c.get("n") or "", c.get("det") or "", *(num(v) for v in (c.get("extra") or {}).values() if v not in (None, ""))]))))
    return out


def presentes(crm):
    regs = registros_de(crm)
    return {k: sum(1 for piezas in v if any(all(p in t for p in piezas) for _, t in regs)) for k, v in ESPERADOS.items()}


def parejos(crm):
    """Punto 11: en la sección de los productos, ¿todos tienen los mismos campos llenos? (solo HP con marca/modelo = disparejo)."""
    for l in crm.get("listas") or []:
        prods = [r for r in l.get("registros") or [] if any(k in plano(json.dumps(r.get("valores"), ensure_ascii=False)) for k in ("pavilion", "inspiron", "s24c", "k120", "l3250"))]
        if len(prods) >= 2:
            llenos = [frozenset(k for k, v in (r.get("valores") or {}).items() if v not in (None, "")) for r in prods]
            return len(set(llenos)) == 1, l["nombre"], [len(x) for x in llenos]
    return None, None, []


def una_corrida(i):
    correo = f"banco-memoria-{secrets.token_hex(4)}@prueba.dev"
    s = pedir("POST", "/auth/register", {"name": "Pepe", "last_name": "Core", "email": correo, "password": "prueba1234"})
    tok = s["access_token"]
    brief = {"nombre": "PepesCore", "rubro": "comercio", "que_vendes": "Vendo y reparo computadoras, laptops e impresoras; tengo empleados",
             "equipo": "chico", "ubicacion": {"pais": "gt"}}
    pedir("POST", "/crm", {"brief": brief}, tok)
    pasos, verdad, tiempos = [], True, []
    for texto in (MENSAJE, SEGUIR):
        a = time.time()
        d = pedir("POST", "/crm/chat", {"texto": texto}, tok)
        tiempos.append(time.time() - a)
        crm = d["crm"]
        p = presentes(crm)
        falta = TOTAL - sum(p.values())
        r = d["respuesta"]
        ok = not NO_VE.search(r) and ((falta == 0 and not re.search(r"\bfalt(a|an|aron)\b|no pude", r, re.I)) or (falta > 0 and dice_lo_que_falta(r, p)))
        verdad &= ok
        pasos.append((texto[:30], tiempos[-1], p, falta, ok, r, len(d.get("cambios") or []), [c["herramienta"] for c in d.get("cambios") or []]))
    final = pedir("GET", "/crm", None, tok)
    p = presentes(final)
    par, sec_prod, llenos = parejos(final)
    hist = pedir("GET", "/crm/chat/historial", None, tok)["mensajes"]
    guardado_completo = any(m["de"] == "yo" and m["t"] == MENSAJE for m in hist)
    return {"pasos": pasos, "presentes": p, "total": sum(p.values()), "verdad": verdad, "parejos": par, "sec_prod": sec_prod, "llenos": llenos,
            "tiempos": tiempos, "completo": guardado_completo, "secciones": [l["nombre"] for l in final.get("listas") or []]}


res = []
for i in range(N):
    try:
        r = una_corrida(i)
    except urllib.error.HTTPError as e:
        print(f"✗ corrida {i + 1}: HTTP {e.code} {e.read()[:300]!r}")
        continue
    res.append(r)
    print(f"\n── corrida {i + 1}: {r['total']}/{TOTAL} registros · verdad {'✓' if r['verdad'] else '✗'} · productos parejos {r['parejos']} "
          f"({r['sec_prod']}: campos llenos {r['llenos']}) · mensaje guardado completo {r['completo']}")
    print(f"   secciones: {r['secciones']}")
    for texto, t, p, falta, ok, resp, nc, herr in r["pasos"]:
        print(f"   {'✓' if ok else '✗'} {t:4.1f}s «{texto}…» → {p} (faltan {falta}) · {nc} cambios {herr}")
        print(f"      dijo: {resp[:400]}")
if res:
    tiempos = [t for r in res for t in r["tiempos"]]
    print(f"\nRegistros al final: {sum(r['total'] for r in res) / len(res):.1f}/{TOTAL} de media ({[r['total'] for r in res]}) · "
          f"dice la verdad {sum(r['verdad'] for r in res)}/{len(res)} · productos parejos {sum(1 for r in res if r['parejos'])}/{len(res)} · "
          f"mensaje guardado completo {sum(r['completo'] for r in res)}/{len(res)} · tiempo medio {sum(tiempos) / len(tiempos):.1f}s · máx {max(tiempos):.1f}s")

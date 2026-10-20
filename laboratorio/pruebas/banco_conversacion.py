"""Banco de conversación larga: ¿Shifu recuerda al final lo dicho al principio (más allá de los 16 mensajes
enviados al modelo)? IA real y ruta `/api/v1/crm/chat`; el historial lo guarda el servidor (crm_conversaciones).
Mismo patrón que banco_memoria.py: cuenta y CRM nuevos por repetición (rubro gimnasio), guion de 16 mensajes y
5 puntos de recuerdo (horario, socio, precio, «la primera clienta» → Ximena Barrios Pausada en el CRM, trato de usted).
Uso: BASE=http://localhost:5203 python3 laboratorio/pruebas/banco_conversacion.py [repeticiones=1]"""
import json, os, re, secrets, sys, time, unicodedata, urllib.error, urllib.request

API = os.environ.get("BASE", "http://localhost:5203") + "/api/v1"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 1

M1 = ("Para que lo sepas: abro de lunes a sábado de 6 de la mañana a 10 de la noche, mi socio se llama Ricardo Méndez, "
      "la membresía mensual cuesta 350 quetzales y prefiero que me hables de usted.")
M2 = "agrega a los clientes Ximena Barrios, Pedro Díaz y Marta Ruiz"  # nombres que no están en los datos de ejemplo
GUION = [
    M1, M2,
    "agrega una tarea de limpiar las máquinas para el viernes",
    "¿cuántos clientes tengo?",
    "agrega a Jorge Castillo",
    "agrega una gráfica de clientes por etapa en el inicio",
    "cambia el color a verde",
    "agrega una tarea de pagar la luz el lunes",
    "¿qué tareas tengo?",
    "agrega a Lucía Torres y a Mario Vega",
    "pon a Pedro Díaz en etapa Contactado",
    "¿quiénes están en etapa Nuevo?",
    "agrega una nota a Jorge: quiere clases de spinning",
    "mueve la tarea de la luz a En curso",
    "agrega una tarea de renovar el seguro el 30",
    "¿cuántas tareas tengo pendientes?",
]
RECUERDO = [
    ("R1", "¿de qué hora a qué hora abro?"),
    ("R2", "¿cómo se llama mi socio?"),
    ("R3", "¿cuánto cuesta la membresía mensual?"),
    ("R4", "a la primera clienta que te pasé márcala como Pausada"),
]
TUTEAR = re.compile(r"\b(tienes|quieres|puedes|tu|te gustaria|dime)\b")


def plano(t):
    return "".join(c for c in unicodedata.normalize("NFD", str(t)) if unicodedata.category(c) != "Mn").lower()


def pedir(metodo, ruta, cuerpo=None, token=None):
    cab = {"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})}
    data = json.dumps(cuerpo).encode() if cuerpo is not None else None
    ultimo = None
    for intento in range(2):
        try:
            req = urllib.request.Request(API + ruta, data=data, headers=cab, method=metodo)
            return json.load(urllib.request.urlopen(req, timeout=180))
        except urllib.error.HTTPError as e:
            ultimo = e
            if intento == 0:
                time.sleep(3)
            else:
                raise ultimo
    raise ultimo  # pragma: no cover


def chat_o_vacio(tok, texto):
    a = time.time()
    try:
        d = pedir("POST", "/crm/chat", {"texto": texto}, tok)
        return (d.get("respuesta") or ""), time.time() - a, False
    except urllib.error.HTTPError:
        return "", 0.0, True


def recorta(s, n=150):
    s = (s or "").replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


def ok_r1(r):
    t = plano(r)  # números completos: «16» o «2026» no cuentan como 6
    return bool(re.search(r"(?<!\d)6(?!\d)", t)) and bool(re.search(r"(?<!\d)(10|22)(?!\d)", t))


def ok_r2(r):
    return "ricardo" in plano(r)


def ok_r3(r):
    return "350" in plano(r)


def _registros(x):
    """Todo dict del CRM (contactos o registros de cualquier sección), recorrido entero."""
    if isinstance(x, dict):
        yield x
        for v in x.values():
            yield from _registros(v)
    elif isinstance(x, list):
        for v in x:
            yield from _registros(v)


def ok_r4(tok, _respuesta):
    """Ximena Barrios (la primera clienta) quedó «Pausada» en la sección donde esté (en un gimnasio los clientes suelen ir en Membresías)."""
    try:
        crm = pedir("GET", "/crm", None, tok)
    except urllib.error.HTTPError:
        return False, "HTTP al leer CRM"
    for r in _registros(crm):
        if r.get("ejemplo"):
            continue  # los datos de ejemplo del rubro traen sus propios nombres y estados
        # solo lo propio del registro (textos y dicts como `valores`), no listas de otros registros
        propio = " ".join(plano(json.dumps(v, ensure_ascii=False)) for v in r.values() if isinstance(v, (str, dict)))
        if "ximena barrios" in propio and "pausad" in propio:
            return True, "Ximena Barrios → Pausada"
    return False, "Ximena Barrios no quedó Pausada"


def sin_tuteo(r):
    return not TUTEAR.search(plano(r))


def ok_r5(respuestas, http_fallo):
    if http_fallo:
        return False
    return all(sin_tuteo(r) for r in respuestas)


def una_corrida(i):
    correo = f"banco-conversacion-{secrets.token_hex(4)}@prueba.dev"
    s = pedir("POST", "/auth/register", {"name": "Pepe", "last_name": "Gym", "email": correo, "password": "prueba1234"})
    tok = s["access_token"]
    brief = {"nombre": "PowerFit", "rubro": "gimnasio", "que_vendes": "Membresías y clases de fitness, spinning y pesas",
             "equipo": "chico", "ubicacion": {"pais": "gt"}}
    pedir("POST", "/crm", {"brief": brief}, tok)

    tiempos = []
    for texto in GUION:
        resp, t, _ = chat_o_vacio(tok, texto)
        tiempos.append(t)

    resultados = []
    respuestas_r = []
    http_fallo_r = False
    for clave, pregunta in RECUERDO:
        resp, t, http_err = chat_o_vacio(tok, pregunta)
        tiempos.append(t)
        respuestas_r.append(resp)
        if http_err:
            http_fallo_r = True
        if clave == "R1":
            ok = ok_r1(resp) if not http_err else False
            det = recorta(resp) if not http_err else "HTTP error"
        elif clave == "R2":
            ok = ok_r2(resp) if not http_err else False
            det = recorta(resp) if not http_err else "HTTP error"
        elif clave == "R3":
            ok = ok_r3(resp) if not http_err else False
            det = recorta(resp) if not http_err else "HTTP error"
        elif clave == "R4":
            if http_err:
                ok, det = False, "HTTP error"
            else:
                ok, crm_det = ok_r4(tok, resp)
                det = (recorta(resp) + " · " + crm_det) if resp else crm_det
        resultados.append((clave, ok, det))

    ok5 = ok_r5(respuestas_r, http_fallo_r)
    n_sin = sum(1 for r in respuestas_r if r and sin_tuteo(r))
    det5 = f"{n_sin}/4 sin tuteo" if not http_fallo_r else "HTTP en alguna R1–R4"
    resultados.append(("R5", ok5, det5))

    puntos = sum(1 for _, ok, _ in resultados if ok)
    t_med = sum(tiempos) / len(tiempos) if tiempos else 0.0
    return {"resultados": resultados, "puntos": puntos, "t_med": t_med}


res = []
for i in range(N):
    try:
        r = una_corrida(i)
    except urllib.error.HTTPError as e:
        print(f"✗ corrida {i + 1}: HTTP {e.code} {e.read()[:300]!r}")
        continue
    res.append(r)
    print(f"\n── corrida {i + 1}: {r['puntos']}/5 · tiempo medio por mensaje {r['t_med']:.1f}s")
    for clave, ok, det in r["resultados"]:
        print(f"   {'✓' if ok else '✗'} {clave}: {det}")

if res:
    puntos = [r["puntos"] for r in res]
    t_all = [r["t_med"] for r in res]
    print(f"\nRecuerda: {sum(puntos) / len(puntos):.1f}/5 de media ({puntos}) · tiempo medio {sum(t_all) / len(t_all):.1f}s")

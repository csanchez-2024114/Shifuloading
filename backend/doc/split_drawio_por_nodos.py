import copy
import math
import re
import xml.etree.ElementTree as E

SRC = "doc/arquitectura_sistema_nuevo.drawio"
DST = "doc/arquitectura_sistema_nuevo_por_nodos.drawio"

src = E.parse(SRC).getroot()
dg = src.find("diagram")
model_attrs = dict(dg.find("mxGraphModel").attrib)
root = dg.find("mxGraphModel/root")
cells = {x.get("id"): x for x in root.iter("mxCell")}
kids = {}
for x in root.iter("mxCell"):
    kids.setdefault(x.get("parent"), []).append(x)


def subtree(i):
    out = [i]
    for ch in kids.get(i, []):
        if ch.get("edge") != "1":
            out += subtree(ch.get("id"))
    return out


PAGES = [
    ("A · Sistema anterior (agente_v3)", ["old"]),
    ("1 · prompt_refiner", ["n1", "noteA", "noteB", "noteLang"]),
    ("1b · context_loader", ["nctx", "noteGeo", "noteRisk"]),
    ("M · Memoria y retención", ["noteMem"]),
    ("2 · intent_detector", ["n2", "noteC", "noteD"]),
    ("3 · router", ["n3", "noteE"]),
    ("4 · tareas (grafo)", ["nxt", "noteTasks"]),
    ("4a · modo investigador (flow)", ["req"]),
    ("F · Funciones y conexiones", ["fn", "noteCat"]),
    ("R · Fallos, evaluador y respuesta", ["noteSup", "noteResp"]),
    ("P · Principios y decisiones", ["noteOK", "noteBase", "noteOut", "leg1", "leg2", "leg3"]),
    ("Q · Modelos y LangGraph", ["noteF", "noteG", "noteH", "noteI", "noteJ"]),
    ("T · Pendientes, tareas y medición", ["noteK", "noteTareas", "noteMed"]),
]
DROP_EDGES = {"ln1", "ln2", "ln3", "ln4", "ln5", "es1", "es2a", "es2b", "es3", "es4", "eu", "fe6"}
CONTAINERS = {"old", "n1", "nctx", "n2", "n3", "req", "fn"}

# cobertura: todo vértice de primer nivel debe estar en alguna página (salvo los del resumen)
covered = {i for _, ids in PAGES for i in ids}
top = [x.get("id") for x in root.iter("mxCell") if x.get("vertex") == "1" and x.get("parent") in ("1", "new")]
missing = [i for i in top if i not in covered and i not in ("new", "user", "n_start")]
print("sin página:", missing)

W = 760
GAP = 40
MARGIN = 40


def font_size(style):
    m = re.search(r"fontSize=(\d+)", style or "")
    return int(m.group(1)) if m else 11


def est_h(value, width, fs):
    cpl = max(10, (width - 24) / (fs * 0.56))
    lines = 0
    for par in (value or "").split("<br>"):
        plain = re.sub(r"<[^>]+>", "", par)
        lines += max(1, math.ceil(len(plain) / cpl))
    return int(lines * fs * 1.45 + 30)


def new_model(name, idx):
    d = E.Element("diagram", {"name": name, "id": f"page-{idx}"})
    m = E.SubElement(d, "mxGraphModel", model_attrs)
    rt = E.SubElement(m, "root")
    E.SubElement(rt, "mxCell", {"id": "0"})
    E.SubElement(rt, "mxCell", {"id": "1", "parent": "0"})
    return d, rt


def geom(cell):
    g = cell.find("mxGeometry")
    return g


out = E.Element("mxfile", dict(src.attrib))
report = []

# ---- Página 0: vista general (construida a mano)
d0, r0 = new_model("0 · Vista general", 0)


def box(i, text, x, y, w, h, fill, stroke, extra=""):
    c = E.SubElement(r0, "mxCell", {"id": i, "value": text, "vertex": "1", "parent": "1",
                                    "style": f"rounded=1;whiteSpace=wrap;html=1;fillColor={fill};strokeColor={stroke};fontSize=12;{extra}"})
    g = E.SubElement(c, "mxGeometry", {"x": str(x), "y": str(y), "width": str(w), "height": str(h)})
    g.set("as", "geometry")


def arrow(i, a, b, label="", dashed=False):
    c = E.SubElement(r0, "mxCell", {"id": i, "value": label, "edge": "1", "parent": "1", "source": a, "target": b,
                                    "style": "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;endArrow=block;endFill=1;fontSize=10;strokeColor=#666666;"
                                    + ("dashed=1;" if dashed else "")})
    g = E.SubElement(c, "mxGeometry", {"relative": "1"})
    g.set("as", "geometry")


u = copy.deepcopy(cells["user"])
u.set("id", "ov_user")
u.set("parent", "1")
ug = u.find("mxGeometry")
ug.set("x", "335")
ug.set("y", "20")
r0.append(u)
box("ov_start", "START", 300, 110, 100, 36, "#f5f5f5", "#666666", "arcSize=50;")
steps = [
    ("ov1", "<b>1 · prompt_refiner</b><br>limpia, adapta el idioma, marca riesgos<br><i>página «1 · prompt_refiner»</i>", "#dae8fc", "#6c8ebf"),
    ("ov2", "<b>1b · context_loader</b><br>núcleo, historial y recuerdos<br><i>páginas «1b» y «M»</i>", "#dae8fc", "#6c8ebf"),
    ("ov3", "<b>2 · intent_detector</b><br>qué pide el usuario<br><i>página «2»</i>", "#dae8fc", "#6c8ebf"),
    ("ov4", "<b>3 · router</b><br>arma las tareas con dependencias<br><i>página «3»</i>", "#d5e8d4", "#82b366"),
    ("ov5", "<b>4 · tareas</b> (paralelo o secuencia)<br>chat · act · flow · lecturas<br><i>página «4»</i>", "#d5e8d4", "#82b366"),
    ("ov6", "<b>responder</b><br>compone el informe de turno<br><i>página «R»</i>", "#fff2cc", "#d6b656"),
    ("ov7", "<b>evaluador</b> (centinela)<br>valida la respuesta y las acciones<br><i>página «R»</i>", "#fff2cc", "#d6b656"),
    ("ov8", "<b>emisor</b><br>entrega el texto validado al usuario", "#fff2cc", "#d6b656"),
    ("ov9", "<b>escritor de recuerdos</b><br>tras entregar, por eventos<br><i>página «M»</i>", "#e1d5e7", "#9673a6"),
]
y = 190
for i, txt, f, s_ in steps:
    box(i, txt, 230, y, 240, 72, f, s_)
    y += 104
arrow("oa0", "ov_user", "ov_start")
arrow("oa1", "ov_start", "ov1")
for a, b in zip(["ov1", "ov2", "ov3", "ov4", "ov5", "ov6", "ov7", "ov8"], ["ov2", "ov3", "ov4", "ov5", "ov6", "ov7", "ov8", "ov9"]):
    arrow(f"oa_{a}", a, b)
arrow("oa_rej", "ov7", "ov6", "rechaza")
box("ov_flow", "<b>4a · modo investigador (flow)</b><br>detective que arma workflows, finito y con vigilante<br><i>página «4a»</i>", 600, 398, 280, 72, "#d5e8d4", "#82b366")
box("ov_fn", "<b>F · funciones y conexiones</b><br>catálogo de apps, vault, funciones versionadas, selector por búsqueda y canario<br><i>página «F»</i>", 600, 502, 280, 90, "#e1d5e7", "#9673a6")
box("ov_sup", "<b>supervisor de fallos</b><br>recibe los informes de los centinelas de cada nodo y decide la recuperación<br><i>página «R»</i>", 600, 624, 280, 90, "#ffe6cc", "#d79b00")
box("ov_pr", "<b>P · principios y decisiones</b> · <b>Q</b> modelos y LangGraph · <b>T</b> pendientes, tareas y medición<br>(páginas de referencia, sin flujo)", 600, 190, 280, 90, "#f5f5f5", "#666666")
arrow("oa_flow", "ov5", "ov_flow", "modo flow", True)
arrow("oa_fn", "ov5", "ov_fn", "funciones", True)
arrow("oa_sup", "ov5", "ov_sup", "fallos", True)
arrow("oa_sup2", "ov7", "ov_sup", "rechazo", True)
tx = E.SubElement(r0, "mxCell", {"id": "ov_note", "vertex": "1", "parent": "1",
                                 "value": "Cada recuadro tiene su propia página. El diagrama completo en una sola página sigue en arquitectura_sistema_nuevo.drawio; esta versión por nodos es para trabajar cada pieza por separado y juntarlas después.",
                                 "style": "text;html=1;whiteSpace=wrap;align=left;verticalAlign=top;fontSize=11;"})
tg = E.SubElement(tx, "mxGeometry", {"x": "230", "y": "1130", "width": "650", "height": "50"})
tg.set("as", "geometry")
out.append(d0)

# ---- Páginas por nodo
for n, (name, ids) in enumerate(PAGES, start=1):
    d, rt = new_model(name, n)
    page_ids = set()
    placed = []
    containers = [i for i in ids if i in CONTAINERS]
    cards = [i for i in ids if i not in CONTAINERS]
    y = MARGIN
    for i in containers:
        for sid in subtree(i):
            page_ids.add(sid)
            cell = copy.deepcopy(cells[sid])
            if sid == i:
                cell.set("parent", "1")
                g = geom(cell)
                g.set("x", str(MARGIN))
                g.set("y", str(y))
                w, h = float(g.get("width")), float(g.get("height"))
                placed.append((i, MARGIN, y, w, h))
                y += int(h) + GAP
            rt.append(cell)
    cols = [y, y]
    colx = [MARGIN, MARGIN + W + GAP]
    for i in cards:
        page_ids.add(i)
        cell = copy.deepcopy(cells[i])
        cell.set("parent", "1")
        g = geom(cell)
        fs = font_size(cell.get("style"))
        h = max(est_h(cell.get("value"), W, fs), 60)
        k = 0 if cols[0] <= cols[1] else 1
        g.set("x", str(colx[k]))
        g.set("y", str(cols[k]))
        g.set("width", str(W))
        g.set("height", str(h))
        placed.append((i, colx[k], cols[k], W, h))
        cols[k] += h + GAP
        rt.append(cell)
    # aristas con ambos extremos en la página
    for e in root.iter("mxCell"):
        if e.get("edge") == "1" and e.get("id") not in DROP_EDGES and e.get("source") in page_ids and e.get("target") in page_ids:
            ec = copy.deepcopy(e)
            if ec.get("parent") not in page_ids:
                ec.set("parent", "1")
            rt.append(ec)
    # comprobación de solapes entre elementos de primer nivel
    ov = []
    for a in range(len(placed)):
        for b in range(a + 1, len(placed)):
            ia, xa, ya, wa, ha = placed[a]
            ib, xb, yb, wb, hb = placed[b]
            if xa < xb + wb and xb < xa + wa and ya < yb + hb and yb < ya + ha:
                ov.append((ia, ib))
    report.append((name, len(page_ids), ov))
    out.append(d)

tree = E.ElementTree(out)
tree.write(DST, encoding="utf-8", xml_declaration=False)
chk = E.parse(DST).getroot()
print("páginas:", [d.get("name") for d in chk.iter("diagram")])
for name, nc, ov in report:
    print(f"{name}: {nc} celdas, solapes={ov}")

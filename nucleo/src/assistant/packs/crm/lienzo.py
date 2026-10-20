"""El lienzo: la rejilla de 12 columnas donde viven las piezas del inicio y de cada pestaña (port de `edicion.js`).

Lo calcula el código, nunca el modelo:
- `colocar` simula el acomodo «dense» del CSS (dónde cae de verdad cada pieza);
- `ubicar` lo dice en palabras («fila 2, derecha») para que Shifu no diga «a la derecha» si quedó abajo a la izquierda;
- `acomodar` (D38) tapa los huecos que dejan los cambios sin cambiar el orden ni quitar nada.

Funciones puras: reciben listas de bloques ({uid, vista, seccion, opciones, ancho, alto, fijo?}) y devuelven copias.
Se verifican contra `test/crm/fixtures/lab/acomodar.json` (788 casos grabados del laboratorio).
"""
from __future__ import annotations

from typing import Any, Iterable

ANCHOS_COL = [3, 4, 6, 8, 12]
ALTO_MAX = 4
VISTAS_INICIO = ["kpis", "tablero", "agenda", "vencimientos", "grafico", "tabla", "calendario_mes", "tablero_dinero", "cifra", "atencion",
                 "franjas", "matriz"]
ANCHO_COMPLETO = ("kpis", "tablero", "agenda")  # las que nacen a lo ancho


def ajustar_ancho(a: float) -> int:
    """El ancho permitido más cercano (en empate gana el primero desde 6, como el reduce de JS)."""
    m = 6
    for x in ANCHOS_COL:
        if abs(x - a) < abs(m - a):
            m = x
    return m


def rangos_de(opciones: dict | None = None) -> list[dict]:
    """Los rangos que dibuja un bloque de vencimientos (la misma regla que la vista)."""
    opciones = opciones or {}
    if opciones.get("rangos"):
        return opciones["rangos"]
    dias = opciones.get("dias") or 30
    return [{"desde": None, "hasta": -1}, {"desde": 0, "hasta": 7}, *([{"desde": 8, "hasta": dias}] if dias > 7 else [])]


class _Celdas:
    """celdas[fila][col] = uid o None; las filas nacen al tocarlas (como el arreglo disperso de JS)."""

    def __init__(self) -> None:
        self.filas: list[list[Any]] = []

    def __len__(self) -> int:
        return len(self.filas)

    def en(self, y: int, x: int) -> Any:
        return self.filas[y][x] if 0 <= y < len(self.filas) and 0 <= x < 12 else None

    def poner(self, y: int, x: int, uid: Any) -> None:
        while len(self.filas) <= y:
            self.filas.append([None] * 12)
        self.filas[y][x] = uid


def _medidas(b: dict) -> tuple[int, int]:
    w = max(1, min(12, b.get("ancho") or 6))
    h = 1 if b.get("vista") == "kpis" else (b.get("alto") or 1)
    return w, h


def colocar(bloques: list[dict]) -> tuple[dict, _Celdas]:
    """Simula el acomodo «dense» del CSS: ({uid: {f, c, w, h}}, celdas)."""
    celdas = _Celdas()

    def libre(f: int, c: int, w: int, h: int) -> bool:
        for y in range(f, f + h):
            for x in range(c, c + w):
                if celdas.en(y, x):
                    return False
        return c + w <= 12

    pos: dict = {}
    for b in bloques:
        w, h = _medidas(b)
        f = 0
        while True:
            c = next((x for x in range(13 - w) if libre(f, x, w, h)), None)
            if c is not None:
                break
            f += 1
        for y in range(f, f + h):
            for x in range(c, c + w):
                celdas.poner(y, x, b.get("uid"))
        pos[b.get("uid")] = {"f": f, "c": c, "w": w, "h": h}
    return pos, celdas


def ubicar(bloques: list[dict]) -> dict:
    """Dónde cae de verdad cada bloque: {uid: {fila, lado}} (lado = izquierda | centro | derecha | ancho completo)."""
    out = {}
    for uid, p in colocar(bloques)[0].items():
        centro = p["c"] + p["w"] / 2
        lado = "ancho completo" if p["w"] == 12 else "izquierda" if centro <= 4.5 else "derecha" if centro >= 7.5 else "centro"
        out[uid] = {"fila": p["f"] + 1, "lado": lado}
    return out


def ubicacion(u: dict | None) -> str:
    return f"fila {u['fila']}, {u['lado']}" if u else ""


def acomodar(bloques: list[dict], fijos0: Iterable[str] = ()) -> list[dict]:
    """Acomodo automático (D38): tapa los huecos. Cada hueco lo llena el bloque vecino: el de la IZQUIERDA se ensancha (si todas sus
    filas tienen ese espacio libre) o, si no, el de ARRIBA crece una fila hacia abajo. Si nadie lo tapa creciendo, el primer bloque que
    viene DESPUÉS del hueco y no cabe en él se angosta al ancho del hueco (mínimo 3) para subir a ocuparlo. Los bloques en `fijos` (los
    que la persona acaba de redimensionar) y los `fijo` no se tocan. No cambia el orden ni quita nada."""
    fijos = set(fijos0) | {b.get("uid") for b in bloques if b.get("fijo")}
    bs = [dict(b) for b in bloques]
    imposibles: set = set()
    for _ in range(40):
        pos, celdas = colocar(bs)
        hueco = None
        for f in range(len(celdas)):
            for c in range(12):
                if not celdas.en(f, c) and (f, c) not in imposibles:
                    hueco = (f, c)
                    break
            if hueco:
                break
        if not hueco:
            break
        f, c = hueco
        largo = 0
        while c + largo < 12 and not celdas.en(f, c + largo):
            largo += 1
        izq = celdas.en(f, c - 1) if c > 0 else None
        arriba = celdas.en(f - 1, c) if f > 0 else None

        def libre_en(y: int, x0: int, n: int) -> bool:
            return all(not celdas.en(y, x) for x in range(x0, x0 + n))

        hecho = False
        if izq and izq not in fijos:
            p = pos[izq]
            if all(libre_en(p["f"] + dy, c, largo) for dy in range(p["h"])):
                bs = [{**b, "ancho": p["w"] + largo} if b.get("uid") == izq else b for b in bs]
                hecho = True
        if not hecho and arriba and arriba not in fijos:
            p = pos[arriba]
            b = next(x for x in bs if x.get("uid") == arriba)
            if b.get("vista") != "kpis" and p["h"] < ALTO_MAX and p["f"] + p["h"] == f and libre_en(f, p["c"], p["w"]):
                bs = [{**x, "alto": p["h"] + 1} if x.get("uid") == arriba else x for x in bs]
                hecho = True
        if not hecho and largo >= 3:
            i = next((k for k, b in enumerate(bs) if b.get("uid") not in fijos and b.get("vista") != "kpis"
                      and (pos[b.get("uid")]["f"] > f or (pos[b.get("uid")]["f"] == f and pos[b.get("uid")]["c"] > c))
                      and pos[b.get("uid")]["w"] > largo), None)
            if i is not None:
                bs[i] = {**bs[i], "ancho": largo}
                hecho = True
        if not hecho:
            imposibles.add((f, c))
    return bs


def ubicar_todo(doc: dict) -> dict:
    """Dónde se ve cada bloque en TODOS los lienzos (inicio y pestañas)."""
    out = ubicar(doc.get("inicio") or [])
    for bs in (doc.get("paginas") or {}).values():
        out.update(ubicar(bs))
    return out

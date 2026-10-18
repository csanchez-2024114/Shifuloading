"""Catálogos compartidos con el laboratorio (D61, contrato §5) y el port de compatibles() contra sus fixtures (§6).

- Estructura: 6 semillas, 21 de biblioteca, 35 pestañas, cada gráfico con nombre/familia/requiere, tipos de campo válidos.
- Frescura: vuelve a correr `laboratorio/servidor/exportar-catalogos.mjs` en una carpeta temporal y exige los mismos bytes
  (se salta si no hay node o no están instaladas las dependencias del laboratorio).
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.crm import plantillas as pl

RAIZ = Path(__file__).resolve().parents[3]  # backend/test/crm → raíz del repo
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "lab"
ARCHIVOS = ("plantillas", "pestanas", "graficos", "vistas", "iconos", "fuentes")
TIPOS_CAMPO = {"texto", "numero", "dinero", "fecha", "hora", "estado"}  # TIPOS_CAMPO de validar.js
CLASES = {"estado", "estado3", "fecha", "hora", "medida", "texto", "categoria"}
FUNCIONES_FIXTURES = ("parseFecha", "parseNumero", "parseHora", "opcionDe", "parsePeriodo", "fechaLarga", "buscarRegistro", "acomodar",
                      "compatibles", "afirmaCambio", "revertirDatos")


def _secciones_con_campos():
    for p in [*pl.semillas(), *pl.biblioteca()]:
        for s in p["secciones"]:
            yield f"{p['id']}/{s['id']}", s
    for p in pl.pestanas():
        yield f"pestana {p['id']}", p["seccion"]


def test_cuantas_plantillas_y_pestanas():
    assert len(pl.semillas()) == 6
    assert len(pl.biblioteca()) == 21
    assert len(pl.pestanas()) == 35
    ids = [p["id"] for p in [*pl.semillas(), *pl.biblioteca()]]
    assert len(ids) == len(set(ids)), "ids de plantilla repetidos"
    assert len({p["id"] for p in pl.pestanas()}) == 35


def test_cada_grafico_tiene_lo_que_pide_compatibles():
    g = pl.graficos()
    assert len(g) >= 40
    for tipo, d in g.items():
        assert d.get("nombre") and d.get("familia"), tipo
        assert isinstance(d.get("opciones"), dict), tipo
        alternativas = d["requiere"] if isinstance(d["requiere"], list) else [d["requiere"]]
        assert alternativas, tipo
        for alt in alternativas:
            assert set(alt) <= CLASES and all(isinstance(n, int) and n >= 1 for n in alt.values()), (tipo, alt)
        assert "Componente" not in d and "calcular" not in d


def test_campos_de_las_plantillas_con_tipo_valido():
    for donde, s in _secciones_con_campos():
        for c in s.get("campos", []):
            assert c["tipo"] in TIPOS_CAMPO, (donde, c)
            if c["tipo"] == "estado":
                assert len(c.get("opciones") or []) >= 2, (donde, c)


def test_vistas_de_las_plantillas_existen():
    vistas = pl.vistas()
    for donde, s in _secciones_con_campos():
        assert s["vista"] in vistas, (donde, s["vista"])
    for p in [*pl.semillas(), *pl.biblioteca()]:
        for w in p.get("inicio", []):
            assert w["vista"] in vistas, (p["id"], w)
            if w["vista"] == "grafico":
                assert w["opciones"]["tipo"] in pl.graficos(), (p["id"], w)


def test_iconos_y_fuentes():
    assert len(pl.iconos()["iconos"]) > 400 and pl.iconos()["familias"]["lu"]["nombre"] == "Lucide"
    assert all(i.get("lu") for i in pl.iconos()["iconos"].values())
    ids = {f["id"] for f in pl.fuentes()["fuentes"]}
    assert len(ids) == len(pl.fuentes()["fuentes"]) >= 100
    assert all(p["titulo"] in ids and p["texto"] in ids for p in pl.fuentes()["pares"])


def test_plantilla_por_id_es_una_copia():
    p = pl.plantilla_por_id("membresias")
    assert p and p["nombre"] and any(s["id"] == "miembros" for s in p["secciones"])
    p["secciones"].clear()
    assert pl.plantilla_por_id("membresias")["secciones"], "plantilla_por_id debe devolver una copia"
    assert pl.plantilla_por_id("gimnasio")["id"] == "gimnasio"
    assert pl.plantilla_por_id("no-existe") is None


def test_pestana_vista_sola():
    p = pl.plantilla_por_id("pestana-cobros")
    assert p["interna"] == "pestana" and p["secciones"][0]["id"] == "cobros" and p["secciones"][0]["grupo"] == 0
    assert [s["id"] for s in p["secciones"][1:]] == ["actividad", "equipo", "automatizaciones"]
    assert p["inicio"] and all(w["seccion"] == "cobros" for w in p["inicio"])


def test_fixtures_bien_formados():
    for nombre in FUNCIONES_FIXTURES:
        casos = json.loads((FIXTURES / f"{nombre}.json").read_text(encoding="utf-8"))
        assert len(casos) >= 100, nombre
        assert all(set(c) == {"caso", "entrada", "salida"} and isinstance(c["entrada"], dict) for c in casos), nombre


def test_compatibles_igual_que_el_laboratorio():
    casos = json.loads((FIXTURES / "compatibles.json").read_text(encoding="utf-8"))
    mal = [c["caso"] for c in casos if pl.compatibles(c["entrada"]["campos"]) != c["salida"]]
    assert not mal, f"{len(mal)} de {len(casos)} difieren: {mal[:5]}"


def test_opciones_por_defecto_de_tipo_desconocido_es_base():
    campos = [{"id": "n", "tipo": "texto"}, {"id": "m", "tipo": "dinero"}, {"id": "k", "tipo": "numero"}]
    assert pl.opciones_por_defecto("no-existe", campos) == {"texto": "n", "agrupar": "n", "valor": "m", "valor2": "k"}
    assert pl.opciones_por_defecto("caja", campos)["agrupar"] is None  # null explícito se queda
    assert pl.opciones_por_defecto("caja", []) == {"agrupar": None}  # como JS: b.estado || null
    assert pl.opciones_por_defecto("arbol", []) == {"funcion": "conteo", "top": 12}  # agrupar sin definir tapa la de base


def test_catalogos_frescos(tmp_path):
    """Los JSON commiteados son exactamente lo que genera hoy el laboratorio."""
    if not shutil.which("node") or not (RAIZ / "node_modules" / "vite").exists():
        pytest.skip("sin node o sin node_modules: no se puede regenerar")
    r = subprocess.run(["node", "laboratorio/servidor/exportar-catalogos.mjs", str(tmp_path)], cwd=RAIZ, capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stderr[-2000:]
    viejos = [n for n in ARCHIVOS if (tmp_path / f"{n}.json").read_bytes() != (pl.CARPETA / f"{n}.json").read_bytes()]
    assert not viejos, f"catálogos viejos: {viejos}. Corre: node laboratorio/servidor/exportar-catalogos.mjs"

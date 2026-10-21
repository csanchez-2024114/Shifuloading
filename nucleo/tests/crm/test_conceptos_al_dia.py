"""El catálogo de conceptos no dice «todavía no está» de lo que ya se puede (relación, calculado, movimientos): lo decide el código.
Con el «falta» escrito a mano, el modelo ofrecía en vez de hacer (banco_erp, banco_calculos, conceptos; 21-oct)."""
from assistant.packs.crm import conceptos


def _c(cid):
    return next(c for c in conceptos._catalogo() if c["id"] == cid)


def test_lo_que_ya_existe_no_se_marca_como_faltante():
    for cid, herramienta in (("campo_calculado", "calcular_campo"), ("relacion", "enlazar_campo"), ("movimiento_inventario", "aplicar_receta")):
        c = _c(cid)
        assert "todavía no" not in conceptos._linea_compacta(c)
        assert f"Ya se puede: hazlo con {herramienta}" in conceptos._detalle(c) and "Todavía no está" not in conceptos._detalle(c)


def test_lo_que_de_verdad_falta_se_sigue_diciendo():
    assert "todavía no: regla" in conceptos._linea_compacta(_c("regla_cuando_entonces"))
    assert "Todavía no está en el producto (documento_pdf)" in conceptos._detalle(_c("documento_pdf"))


def test_con_el_interruptor_apagado_vuelve_a_faltar(monkeypatch):
    monkeypatch.setenv("CRM_CONECTAR", "0")
    assert "todavía no: calculado" in conceptos._linea_compacta(_c("campo_calculado"))

"""Filtro de veracidad por código (`SesionDiseno.afirma_sin_respaldo`): lo que la respuesta dice haber hecho tiene que estar en lo que
corrió en el turno. Casos de la prueba manual del 19-oct (PepesCore). Sin IA real: el modelo es un guion."""
import pytest

from test_agente_diseno import con_diseno, correr, dice, doc, llamar  # noqa: F401  (con_diseno y doc son fixtures)

# AHORA en test_agente_diseno = martes 13-oct-2026 09:00 en Guatemala: «mañana» = 2026-10-14, «el jueves» = 2026-10-15.
CITA = dict(texto="Cita con Ramires", fecha="2026-10-14", hora="15:00")
PIDE = "agéndame una cita con Ramires mañana a las 3 y también cada jueves a la misma hora"


@pytest.mark.asyncio
async def test_afirmar_las_citas_de_los_jueves_con_una_sola_tarea_pide_la_verdad(doc):
    r, modelo = await correr(doc, PIDE, dice("", llamar("agregar_tarea", **CITA)),
                             dice("Ya estaba la cita de mañana a las 3 con Ramires, pero puse las de los jueves a la misma hora."),
                             dice("Agendé la cita de mañana a las 3 con Ramires. Las de los jueves todavía no las agendé: ¿las agrego?"))
    assert len(r["avisos"]) == 1 and "ningún cambio de este mensaje tiene esa fecha" in r["avisos"][0]["aviso"]
    assert r["respuesta"].startswith("Agendé la cita de mañana")


@pytest.mark.asyncio
async def test_lo_que_si_se_hizo_pasa_sin_corregir_ni_llamar_otra_vez(doc):
    r, modelo = await correr(doc, PIDE, dice("", llamar("agregar_tarea", **CITA)), dice("Agendé la cita de mañana a las 3 con Ramires."))
    assert r["avisos"] == [] and len(modelo.recibidos) == 2  # el camino normal no agrega llamadas


@pytest.mark.asyncio
async def test_una_cifra_que_no_salio_de_ningun_lado_se_corrige(doc):
    dos = [llamar("agregar_tarea", texto="Llamar a Ana"), llamar("agregar_tarea", texto="Llamar a Luis")]
    r, _ = await correr(doc, "pon tareas de llamar a Ana y a Luis", dice("", *dos), dice("Agregué 3 tareas."), dice("Agregué 2 tareas."))
    assert len(r["avisos"]) == 1 and "«3»" in r["avisos"][0]["aviso"] and r["respuesta"] == "Agregué 2 tareas."


@pytest.mark.asyncio
async def test_la_cuenta_de_lo_hecho_y_las_cifras_de_la_persona_si_valen(doc):
    dos = [llamar("agregar_tarea", texto="Llamar a Ana"), llamar("agregar_tarea", texto="Llamar a Luis")]
    r, _ = await correr(doc, "pon 2 tareas: llamar a Ana y a Luis a las 4", dice("", *dos), dice("Listo, agregué 2 tareas para las 4."))
    assert r["avisos"] == []


@pytest.mark.asyncio
async def test_hablar_de_hoy_sin_cambios_con_fecha_no_es_mentira(doc):
    r, _ = await correr(doc, "pon una tarea de llamar a Ana", dice("", llamar("agregar_tarea", texto="Llamar a Ana")), dice("Hoy agregué la tarea de llamar a Ana."))
    assert r["avisos"] == []


@pytest.mark.asyncio
async def test_preguntas_y_planes_no_cuentan_como_afirmar(doc):
    r, _ = await correr(doc, PIDE, dice("", llamar("agregar_tarea", **CITA)),
                        dice("Agendé la de mañana. ¿Quieres que ponga también las de los jueves?"))
    assert r["avisos"] == []


@pytest.mark.asyncio
async def test_si_tras_corregir_sigue_sin_respaldo_responde_el_codigo(doc):
    mala = "Puse las citas de los jueves con Ramires."
    r, _ = await correr(doc, PIDE, dice("", llamar("agregar_tarea", **CITA)), dice(mala), dice(mala), dice(mala))
    assert r["respuesta"] != mala and "jueves" not in r["respuesta"]
    assert any(a["aviso"].startswith("sin respaldo tras corregir") for a in r["avisos"])


@pytest.mark.asyncio
async def test_un_digito_dentro_de_un_id_no_respalda_una_cifra(doc, monkeypatch):
    # Los resultados de herramientas traen ids aleatorios («a3f9…»); sus dígitos no cuentan como cifras dichas (antes el cerco pasaba al azar).
    from app.crm import agente_diseno
    original = agente_diseno.SesionDiseno.ejecutar
    monkeypatch.setattr(agente_diseno.SesionDiseno, "ejecutar", lambda self, n, a: original(self, n, a) + " (id a3f9)")
    dos = [llamar("agregar_tarea", texto="Llamar a Ana"), llamar("agregar_tarea", texto="Llamar a Luis")]
    r, _ = await correr(doc, "pon tareas de llamar a Ana y a Luis", dice("", *dos), dice("Agregué 3 tareas."), dice("Agregué 2 tareas."))
    assert len(r["avisos"]) == 1 and "«3»" in r["avisos"][0]["aviso"]

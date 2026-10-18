"""Datos por chat (registros.py): agregar, editar, borrar y consultar registros, con el código entendiendo y validando. Sin IA.

Port de los casos de `laboratorio/pruebas/registros.test.mjs` que son de la lógica de datos, con la API nueva: `ejecutar_dato` no toca un
documento, devuelve la `operacion` que aplica `secciones_v`. Los registros son los de ejemplo de la plantilla «membresias» (nivel «pocos»),
escritos a mano con hoy fijo (16 de octubre de 2026). Los textos esperados son los que da el laboratorio con esas mismas entradas.

No se portan (son de otros frentes): nombres únicos del generador de ejemplos, punto de deshacer (`conPunto`) y deshacer en 3 vías
(`revertirDatos`) → puntos.py; la pestaña con `fuente` y la opción renombrada → secciones_v/estructura; `describirPantalla`, «sin
ejemplos» y `creadoSinDecir` → chat/vista.
"""
from datetime import date

import pytest

from app.crm.registros import HERRAMIENTAS_DATOS, consultar, ejecutar_dato

HOY = date(2026, 10, 16)
D = " "

CM = [{"id": "nombre", "nombre": "Nombre", "tipo": "texto"}, {"id": "plan", "nombre": "Plan", "tipo": "texto"},
      {"id": "alta", "nombre": "Alta", "tipo": "fecha"}, {"id": "vence", "nombre": "Vence", "tipo": "fecha"},
      {"id": "estado", "nombre": "Estado", "tipo": "estado", "opciones": ["Activa", "Pausada", "Cancelada"]}]
CP = [{"id": "miembro", "nombre": "Miembro", "tipo": "texto"}, {"id": "monto", "nombre": "Monto", "tipo": "dinero"},
      {"id": "fecha", "nombre": "Fecha", "tipo": "fecha"}]
MIEMBROS = {"id": "miembros", "titulo": "Miembros", "campos": CM}
PAGOS = {"id": "pagos", "titulo": "Pagos", "campos": CP}


def _m(i, nombre, plan, alta, vence, estado):
    return {"id": f"miembros-{i}", "valores": {"nombre": nombre, "plan": plan, "alta": alta, "vence": vence, "estado": estado}}


M = [_m(0, "Ana López", "Trimestral", "2026-01-21", "2026-11-25", "Cancelada"), _m(1, "Carlos Pérez", "Mensual", "2026-10-12", "2026-10-21", "Pausada"),
     _m(2, "María José Castillo", "Estudiante", "2026-10-07", "2026-10-14", "Pausada"), _m(3, "Luis Hernández", "Estudiante", "2026-07-12", "2026-10-07", "Cancelada"),
     _m(4, "Sofía Ramírez", "Mensual", "2025-12-06", "2026-10-13", "Activa"), _m(5, "Diego Morales", "Trimestral", "2026-10-02", "2026-10-24", "Cancelada"),
     _m(6, "Valentina Cruz", "Mensual", "2026-08-21", "2026-10-17", "Pausada"), _m(7, "Jorge Méndez", "Estudiante", "2026-01-31", "2026-10-28", "Cancelada")]
P = [{"id": f"pagos-{i}", "valores": {"miembro": m, "monto": v, "fecha": f}} for i, (m, v, f) in enumerate([
    ("Diego Morales", 3370, "2026-10-15"), ("Luis Hernández", 8030, "2026-10-16"), ("Valentina Cruz", 2590, "2026-10-17"), ("Diego Morales", 300, "2026-10-21"),
    ("Ana López", 5040, "2026-10-19"), ("Luis Hernández", 2990, "2026-10-16"), ("Diego Morales", 1940, "2026-10-21"), ("Ana López", 6860, "2026-10-25")])]


def ejecutar(nombre, sec, regs, args, **kw):
    """Como `ejecutar` del laboratorio para una sección: el id del agregado es el que pondría él (`<sección>-p1`)."""
    return ejecutar_dato(nombre, sec, sec["campos"], regs, args, hoy=HOY, pais="gt", id_nuevo=f"{sec['id']}-p1", **kw)


def aplicar(regs, r):
    """Lo que hará `secciones_v` con la operación (aquí, sobre la lista de registros)."""
    op = r["operacion"]
    if op["tipo"] == "agregar":
        return [*regs, {"id": op["id"], "valores": op["valores"]}]
    if op["tipo"] == "editar":
        return [{**x, "valores": {**x["valores"], **op["cambios"]}} if x["id"] == op["id"] else x for x in regs]
    return [x for x in regs if x["id"] != op["id"]]


def de(regs, nombre):
    return next((r for r in regs if r["valores"].get("nombre") == nombre), None)


def test_agregar_entiende_la_fecha_normaliza_y_pone_el_estado_por_defecto():
    r = ejecutar("agregar_registro", MIEMBROS, M, {"seccion": "Miembros", "valores": {"nombre": "María López", "plan": "mensual", "vence": "30 de octubre"}})
    assert r["ok"], r["resultado"]
    assert r["operacion"] == {"tipo": "agregar", "id": "miembros-p1",
                              "valores": {"nombre": "María López", "plan": "Mensual", "vence": "2026-10-30", "estado": "Activa"}}
    assert r["resultado"] == ("Agregado a Miembros: María López — Plan: Mensual · Alta: — · Vence: 30 de octubre de 2026 · Estado: Activa (id miembros-p1). "
                              "Estado: Activa por defecto (dilo). Sin llenar: Alta (dilo y ofrece completarlo; no lo inventes). Ahora hay 9 en Miembros.")
    assert r["etiqueta"] == "agregó «María López» a Miembros"
    assert len(aplicar(M, r)) == 9


def test_sin_id_nuevo_se_crea_uno_y_va_en_la_operacion():
    r = ejecutar_dato("agregar_registro", MIEMBROS, CM, M, {"valores": {"nombre": "Rosa"}}, hoy=HOY)
    rid = r["operacion"]["id"]
    assert rid and f"(id {rid})" in r["resultado"]


def test_duplicado_exacto_no_se_agrega_sin_confirmacion_y_otro_pago_si():
    a = ejecutar("agregar_registro", MIEMBROS, M, {"seccion": "miembros", "valores": {"nombre": "Juan Pérez", "plan": "Mensual", "alta": "hoy"}})
    assert a["ok"], a["resultado"]
    con_juan = aplicar(M, a)
    b = ejecutar("agregar_registro", MIEMBROS, con_juan, {"seccion": "miembros", "valores": {"nombre": "Juan Pérez", "plan": "mensual"}})
    assert not b["ok"] and b["operacion"] is None
    assert b["resultado"] == ("ERROR: ya existe «Juan Pérez» en Miembros con esos mismos datos. No lo agregué. Si quería cambiar ese, usa editar_registro; "
                              "si de verdad es OTRO con los mismos datos, pregúntaselo y agrégalo cuando diga que sí.")
    c = ejecutar("agregar_registro", MIEMBROS, con_juan, {"seccion": "miembros", "valores": {"nombre": "Juan Pérez", "plan": "Anual"}})
    assert c["ok"], "mismo nombre con otro plan: es otro dato, se agrega"
    assert "Ya había otro registro «Juan Pérez» con otros datos; díselo en una línea." in c["resultado"]
    d = ejecutar("agregar_registro", MIEMBROS, con_juan, {"seccion": "miembros", "valores": {"nombre": "Juan Pérez", "plan": "mensual"}}, confirmado=True)
    assert d["ok"], "con «sí» de la persona se agrega"
    assert "Ya había otro registro «Juan Pérez» con los mismos datos (la persona confirmó que es otro)" in d["resultado"]
    v1 = ejecutar("agregar_registro", MIEMBROS, M, {"seccion": "miembros", "valores": {"nombre": "Luis Mora", "plan": "Mensual", "vence": "en un mes"}})
    otra_vez = ejecutar("agregar_registro", MIEMBROS, aplicar(M, v1), {"seccion": "miembros", "valores": {"nombre": "Luis Mora", "plan": "mensual", "vence": "en 30 días"}})
    assert not otra_vez["ok"], "la misma fecha dicha de otra forma (±3 días) sigue siendo duplicado"
    p1 = ejecutar("agregar_registro", PAGOS, P, {"seccion": "pagos", "valores": {"miembro": "Ana López", "monto": "350", "fecha": "hoy"}})
    assert p1["ok"], p1["resultado"]
    p2 = ejecutar("agregar_registro", PAGOS, aplicar(P, p1), {"seccion": "pagos", "valores": {"miembro": "Ana López", "monto": "400", "fecha": "hoy"}})
    assert p2["ok"], "otro monto: otro pago"


DICHOS = "pasa a Ana a Pausada\nponle a Carlos Pérez el plan Anual"
DOS_ANAS = [*M, {"id": "miembros-p1", "valores": {"nombre": "Ana Martínez", "plan": "Anual", "estado": "Activa"}}]


def test_procedencia_con_dos_anas_no_elige_por_la_persona():
    a = ejecutar("editar_registro", MIEMBROS, DOS_ANAS, {"seccion": "miembros", "registro": "Ana López", "valores": {"estado": "Pausada"}}, dichos=DICHOS)
    assert not a["ok"]
    assert a["resultado"] == ("ERROR: la persona no nombró a «Ana López» (dijo «ana» y coinciden: Ana López, Ana Martínez). "
                              "No elijas por ella: pregúntale a quién se refiere.")
    b = ejecutar("editar_registro", MIEMBROS, DOS_ANAS, {"seccion": "miembros", "registro": "miembros-0", "valores": {"estado": "Pausada"}}, dichos=DICHOS)
    assert not b["ok"], "por id tampoco: «Ana» no la señala solo a ella"
    assert ejecutar("editar_registro", MIEMBROS, DOS_ANAS, {"seccion": "miembros", "registro": "Carlos Pérez", "valores": {"plan": "Anual"}}, dichos=DICHOS)["ok"]
    assert ejecutar("editar_registro", MIEMBROS, DOS_ANAS, {"seccion": "miembros", "registro": "miembros-1", "valores": {"plan": "Anual"}}, dichos=DICHOS)["ok"], \
        "por id, si lo que dijo lo señala solo a él"
    assert ejecutar("borrar_registro", MIEMBROS, DOS_ANAS, {"seccion": "miembros", "registro": "Ana López"}, dichos="borra a ana lopez")["ok"], "sin acentos ni mayúsculas"
    assert not ejecutar("borrar_registro", MIEMBROS, DOS_ANAS, {"seccion": "miembros", "registro": "Ana López"}, dichos="borra a Ana")["ok"]
    assert ejecutar("editar_registro", MIEMBROS, M, {"seccion": "miembros", "registro": "Carlos Pérez", "valores": {"plan": "Anual"}},
                    dichos="a Carlos ponle plan anual")["ok"], "una sola persona con ese nombre: basta el nombre de pila"
    assert not ejecutar("editar_registro", MIEMBROS, M, {"registro": "Carlos Pérez", "valores": {"plan": "Anual"}}, dichos="")["ok"], "dichos vacío: nadie nombró a nadie"


def test_a_mano_los_valores_del_formulario_pasan_por_el_mismo_codigo():
    r = ejecutar("agregar_registro", PAGOS, P, {"seccion": "pagos", "valores": {"miembro": "Rosa Gómez", "monto": "1,250.50", "fecha": "2026-10-30"}}, confirmado=True)
    assert r["ok"], r["resultado"]
    assert r["operacion"]["valores"] == {"miembro": "Rosa Gómez", "monto": 1250.5, "fecha": "2026-10-30"}
    assert r["resultado"] == f"Agregado a Pagos: Rosa Gómez — Monto: Q{D}1,250.50 · Fecha: 30 de octubre de 2026 (id pagos-p1). Ahora hay 9 en Pagos."


def test_agregar_sin_el_nombre_no_inventa():
    r = ejecutar("agregar_registro", MIEMBROS, M, {"seccion": "miembros", "valores": {"plan": "Anual"}})
    assert not r["ok"] and r["resultado"] == "ERROR: falta Nombre: es lo que identifica al registro. Pregúntaselo."


def test_agregar_con_opcion_inexistente_fecha_imposible_o_campo_que_no_existe():
    a = ejecutar("agregar_registro", MIEMBROS, M, {"seccion": "miembros", "valores": {"nombre": "Rosa", "estado": "Congelada"}})
    assert a["resultado"] == ("ERROR: «Congelada» no es una opción de Estado (opciones: Activa, Pausada, Cancelada). "
                              "Pregúntale cuál, o si quiere agregar esa opción.")
    b = ejecutar("agregar_registro", MIEMBROS, M, {"seccion": "miembros", "valores": {"nombre": "Rosa", "vence": "31 de febrero"}})
    assert b["resultado"] == ("ERROR: no entendí la fecha «31 de febrero» para Vence: hoy es 16 de octubre de 2026; pregúntale cuál es "
                              "(por ejemplo «30 de octubre» o «30 de octubre de 2027»).")
    c = ejecutar("agregar_registro", MIEMBROS, M, {"seccion": "miembros", "valores": {"nombre": "Rosa", "correo": "rosa@x.com"}})
    assert c["resultado"] == ("ERROR: «correo» no es un campo de Miembros (sus campos: Nombre, Plan, Alta, Vence, Estado). "
                              "Si quiere guardar ese dato, pregúntale si agregas el campo.")
    assert not any(x["ok"] for x in (a, b, c))


def test_agregar_un_pago_entiende_el_monto():
    r = ejecutar("agregar_registro", PAGOS, P, {"seccion": "pagos", "valores": {"miembro": "Ana López", "monto": "Q1,200.50", "fecha": "hoy"}})
    assert r["ok"], r["resultado"]
    assert r["operacion"]["valores"]["monto"] == 1200.5
    assert r["resultado"] == (f"Agregado a Pagos: Ana López — Monto: Q{D}1,200.50 · Fecha: 16 de octubre de 2026 (id pagos-p1). "
                              "Ya había 2 registros «Ana López» con otros datos; díselo en una línea. Ahora hay 9 en Pagos.")
    es = ejecutar_dato("agregar_registro", PAGOS, CP, P, {"valores": {"miembro": "Ana López", "monto": "Q1,200.50", "fecha": "hoy"}}, hoy=HOY, pais="es", id_nuevo="x")
    assert f"Monto: 1200,50{D}€" in es["resultado"]


def test_editar_guarda_solo_lo_que_cambio_y_dice_antes_y_despues():
    r = ejecutar("editar_registro", MIEMBROS, M, {"seccion": "miembros", "registro": "ana lopez", "valores": {"estado": "pausada"}})
    assert r["ok"], r["resultado"]
    assert r["operacion"] == {"tipo": "editar", "id": "miembros-0", "cambios": {"estado": "Pausada"}}
    assert r["resultado"] == "Cambiado «Ana López» en Miembros: Estado: Cancelada → Pausada."
    assert r["etiqueta"] == "cambió «Ana López»: Estado → Pausada"
    assert de(aplicar(M, r), "Ana López")["valores"]["estado"] == "Pausada"


def test_editar_varios_y_vaciar_un_campo():
    r = ejecutar("editar_registro", MIEMBROS, M, {"registro": "Carlos Pérez", "valores": {"plan": "Anual", "vence": "", "estado": "activa"}})
    assert r["operacion"] == {"tipo": "editar", "id": "miembros-1", "cambios": {"plan": "Anual", "vence": "", "estado": "Activa"}}
    assert r["resultado"] == "Cambiado «Carlos Pérez» en Miembros: Plan: Mensual → Anual · Vence: 21 de octubre de 2026 → — · Estado: Pausada → Activa."
    assert r["etiqueta"] == "cambió «Carlos Pérez»: Plan → Anual, Vence → —, Estado → Activa"
    sin = ejecutar("editar_registro", MIEMBROS, M, {"registro": "Carlos Pérez", "valores": {"nombre": ""}})
    assert sin["resultado"] == "ERROR: un registro no puede quedar sin Nombre."
    assert ejecutar("editar_registro", MIEMBROS, M, {"registro": "Carlos Pérez", "valores": {}})["resultado"] == "ERROR: falta qué cambiar (valores)."


def test_editar_lo_que_agrego_la_persona():
    con_maria = [*M, {"id": "miembros-p1", "valores": {"nombre": "María López", "plan": "Mensual", "vence": "2026-10-30", "estado": "Activa"}}]
    r = ejecutar("editar_registro", MIEMBROS, con_maria, {"seccion": "miembros", "registro": "María López", "valores": {"vence": "15/11/2026"}})
    assert r["ok"], r["resultado"]
    assert r["operacion"] == {"tipo": "editar", "id": "miembros-p1", "cambios": {"vence": "2026-11-15"}}


def test_editar_sin_cambio_real_no_cuenta_como_cambio():
    r = ejecutar("editar_registro", MIEMBROS, M, {"seccion": "miembros", "registro": "Carlos Pérez", "valores": {"plan": "Mensual"}})
    assert r["ok"] and r["etiqueta"] is None and r["operacion"] is None
    assert r["resultado"] == "«Carlos Pérez» ya tenía eso (Plan: Mensual): no cambió nada. Díselo."


def test_dos_que_coinciden_no_adivina():
    r = ejecutar("editar_registro", MIEMBROS, DOS_ANAS, {"seccion": "miembros", "registro": "Ana", "valores": {"estado": "Cancelada"}})
    assert not r["ok"]
    assert r["resultado"] == (
        "ERROR: hay 2 registros en Miembros que coinciden con «Ana»: Ana López — Plan: Trimestral · Alta: 21 de enero de 2026 · Vence: 25 de noviembre de 2026 · "
        "Estado: Cancelada (id miembros-0) | Ana Martínez — Plan: Anual · Alta: — · Vence: — · Estado: Activa (id miembros-p1). "
        "No cambies nada: pregúntale cuál (por un dato que los distinga).")
    muchas = [{"id": f"x{i}", "valores": {"nombre": f"Ana {n}", "plan": "Mensual"}} for i, n in enumerate(["Uno", "Dos", "Tres", "Cuatro", "Cinco", "Seis"])]
    r6 = ejecutar("editar_registro", MIEMBROS, muchas, {"registro": "Ana", "valores": {"estado": "Cancelada"}})
    assert r6["resultado"].startswith("ERROR: hay 6 registros") and "(id x4) | …. No cambies nada" in r6["resultado"]


def test_no_existe_lo_dice_y_sugiere_parecidos():
    r = ejecutar("borrar_registro", MIEMBROS, M, {"seccion": "miembros", "registro": "Carlos Pereira"})
    assert not r["ok"]
    assert r["resultado"] == "ERROR: no encontré «Carlos Pereira» en Miembros (tiene 8 registros). Se parecen: Carlos Pérez. Pregúntale si es alguno."
    n = ejecutar("borrar_registro", MIEMBROS, M, {"registro": "Rosa Gómez"})
    assert n["resultado"] == "ERROR: no encontré «Rosa Gómez» en Miembros (tiene 8 registros). Pregúntale cómo se llama exactamente o si quiere agregarlo."


def test_borrar_un_ejemplo_y_uno_propio():
    con_maria = [*M, {"id": "miembros-p1", "valores": {"nombre": "María López", "plan": "Mensual", "estado": "Activa"}}]
    a = ejecutar("borrar_registro", MIEMBROS, con_maria, {"seccion": "miembros", "registro": "Carlos Pérez"})
    assert a["ok"], a["resultado"]
    assert a["operacion"] == {"tipo": "borrar", "id": "miembros-1"}
    assert a["resultado"] == ("Borrado de Miembros: Carlos Pérez — Plan: Mensual · Alta: 12 de octubre de 2026 · Vence: 21 de octubre de 2026 · "
                              "Estado: Pausada (id miembros-1). Se puede deshacer. Quedan 8.")
    assert a["etiqueta"] == "borró «Carlos Pérez» de Miembros"
    quedan = aplicar(con_maria, a)
    b = ejecutar("borrar_registro", MIEMBROS, quedan, {"seccion": "miembros", "registro": "María López"})
    assert b["ok"] and b["operacion"] == {"tipo": "borrar", "id": "miembros-p1"}
    assert len(aplicar(quedan, b)) == 7


def test_la_seccion_duena_da_el_titulo():
    # Una pestaña que muestra los datos de otra (Vencimientos → Miembros): quien llama pasa la sección dueña y sus campos.
    r = ejecutar_dato("agregar_registro", MIEMBROS, CM, M, {"seccion": "vencimientos", "valores": {"nombre": "Pedro Ruiz"}}, hoy=HOY, id_nuevo="n1")
    assert r["ok"] and r["operacion"]["valores"]["nombre"] == "Pedro Ruiz" and "Agregado a Miembros" in r["resultado"]


def test_herramienta_que_no_existe():
    assert ejecutar("otra", MIEMBROS, M, {})["resultado"] == "ERROR: la herramienta «otra» no existe."


def _consultar(sec, regs, args, pais="gt"):
    return consultar(sec, sec["campos"], regs, args, hoy=HOY, pais=pais)


def test_consultar_cuenta_filtra_y_suma():
    assert _consultar(MIEMBROS, M, {"seccion": "miembros", "filtros": {"estado": "activa"}}) == (
        "Hoy es 16 de octubre de 2026. En Miembros (Estado: Activa): 1 de 8 registros. Son: Sofía Ramírez — Plan: Mensual · Alta: 6 de diciembre de 2025 · "
        "Vence: 13 de octubre de 2026 · Estado: Activa (id miembros-4). Responde SOLO con estos números y datos (sin decir ids).")
    t = _consultar(PAGOS, P, {"seccion": "pagos", "periodo": {"cuando": "este mes"}, "sumar": "monto"})
    assert t.startswith(f"Hoy es 16 de octubre de 2026. En Pagos (Fecha del 1 de octubre de 2026 al 31 de octubre de 2026): 8 de 8 registros. "
                        f"Suma de Monto: Q{D}31,120. Son: Diego Morales — Monto: Q{D}3,370 · Fecha: 15 de octubre de 2026 (id pagos-0) | ")
    assert f"Suma de Monto: ${D}31.120." in _consultar(PAGOS, P, {"periodo": {"cuando": "este mes"}, "sumar": "monto"}, pais="co")
    assert _consultar(MIEMBROS, M, {"seccion": "miembros", "periodo": {"cuando": "este mes"}}) == (
        "ERROR: ¿por cuál fecha? Miembros tiene: alta (Alta), vence (Vence). Pon periodo.campo.")  # tiene Alta y Vence
    assert _consultar(MIEMBROS, M, {"seccion": "miembros", "buscar": "Ana López"}) == (
        "Hoy es 16 de octubre de 2026. En Miembros (que coinciden con «Ana López»): 1 de 8 registros. Son: Ana López — Plan: Trimestral · "
        "Alta: 21 de enero de 2026 · Vence: 25 de noviembre de 2026 · Estado: Cancelada (id miembros-0). Responde SOLO con estos números y datos (sin decir ids).")
    assert _consultar(MIEMBROS, M, {"seccion": "miembros", "buscar": "Rosa Gómez"}) == (
        "En Miembros no hay ningún registro que coincida con «Rosa Gómez» (tiene 8). Díselo; no inventes.")
    assert _consultar(PAGOS, P, {"seccion": "pagos", "sumar": "miembro"}) == "ERROR: «miembro» no se puede sumar en Pagos. Se pueden sumar: monto (Monto)."
    assert _consultar(MIEMBROS, M, {"sumar": "monto"}) == "ERROR: «monto» no se puede sumar en Miembros. Se pueden sumar: nada (no tiene números)."


def test_consultar_por_periodo_de_un_campo():
    t = _consultar(MIEMBROS, M, {"periodo": {"campo": "vence", "cuando": "vencidos"}})
    assert t.startswith("Hoy es 16 de octubre de 2026. En Miembros (Vence hasta el 15 de octubre de 2026): 3 de 8 registros. Son: María José Castillo")
    t7 = _consultar(MIEMBROS, M, {"periodo": {"campo": "vence", "cuando": "los próximos 7 días"}})
    assert "(Vence del 16 de octubre de 2026 al 23 de octubre de 2026): 2 de 8 registros." in t7
    assert _consultar(MIEMBROS, M, {"periodo": {"campo": "alta", "cuando": "cuando llueva"}}) == (
        "ERROR: no entendí el periodo «cuando llueva». Se entiende: hoy, esta semana, la semana pasada, este mes, el mes pasado, los próximos 7 días, "
        "los últimos 30 días, vencidos, octubre, del 1 al 15 de octubre, una fecha.")
    assert _consultar(MIEMBROS, [], {}) == ("Hoy es 16 de octubre de 2026. En Miembros: 0 de 0 registros. "
                                            "Responde SOLO con estos números y datos (sin decir ids).")
    assert ": 1 de 1 registro." in _consultar(MIEMBROS, M[:1], {})


def test_lista_de_carlos_es_un_estado():
    campos = [{"id": "f_n", "nombre": "Cliente", "tipo": "texto"}, {"id": "f_e", "nombre": "Estado", "tipo": "lista", "opciones": ["Pendiente", "Lista"]}]
    sec = {"id": "l_x", "titulo": "Citas", "campos": campos}
    r = ejecutar_dato("agregar_registro", sec, campos, [], {"valores": {"cliente": "Lía"}}, hoy=HOY, id_nuevo="n1")
    assert r["operacion"]["valores"] == {"f_n": "Lía", "f_e": "Pendiente"} and "Estado: Pendiente por defecto (dilo)." in r["resultado"]
    assert ejecutar_dato("agregar_registro", sec, campos, [], {"valores": {"cliente": "Lía", "estado": "x"}}, hoy=HOY)["resultado"].startswith(
        "ERROR: «x» no es una opción de Estado (opciones: Pendiente, Lista).")


def test_herramientas_literales():
    nombres = [h["function"]["name"] for h in HERRAMIENTAS_DATOS]
    assert nombres == ["agregar_registro", "editar_registro", "borrar_registro", "consultar_datos"]
    agregar = HERRAMIENTAS_DATOS[0]["function"]
    assert agregar["parameters"]["required"] == ["seccion", "valores"]
    assert agregar["description"].startswith("Agrega UN registro (un cliente, un pago, una cita…) a una sección")
    assert HERRAMIENTAS_DATOS[3]["function"]["parameters"]["properties"]["periodo"]["properties"]["cuando"]["description"] == (
        "como lo dijo: «este mes», «esta semana», «los próximos 7 días»")


@pytest.mark.parametrize("valores", [{"nombre": "  Rosa  ", "Fecha de alta": "ayer"}])
def test_campos_por_nombre_y_recorte(valores):
    campos = [*CM[:2], {"id": "f_alta", "nombre": "Fecha de alta", "tipo": "fecha"}]
    r = ejecutar_dato("agregar_registro", MIEMBROS, campos, [], {"valores": valores}, hoy=HOY, id_nuevo="n1")
    assert r["operacion"]["valores"] == {"nombre": "Rosa", "f_alta": "2026-10-15"}

# Contratos: el sistema de diseño del laboratorio dentro del CRM de Carlos (D61)

Plan completo: lo del laboratorio entra en la base de Carlos, que se amplía paso a paso. Este archivo fija las **interfaces** que comparten los frentes que trabajan en paralelo. Si un frente necesita cambiar un contrato, lo dice al coordinador; no lo cambia por su cuenta.

Reglas para todos:
- Las 359 pruebas de `test/crm` siguen en verde.
- El resto de `test/` no suma fallas: hoy fallan 4 de scheduler/workflow y 7 de `agente_v3`, y no son del CRM.
- Todo cambio de esquema es **aditivo**.
- Nombres, esquemas y textos de las herramientas del laboratorio se copian **literales** (el prompt es frágil, medido).
- Lo calculable lo calcula el código.

## 1. Documento `crm_workspaces` (esquema 2, perezoso)
Lo de Carlos queda igual. Se agrega:

```
esquema: 2
plantilla: { id: "membresias" | "gimnasio" | …, origen: "asignar" | "generador", porque: [str] }
inicio:  [ Bloque ]                       # piezas del inicio
paginas: { <sec_id>: [ Bloque ] }         # lienzo propio de una pestaña (si no hay, se usa su vista)
marca:   { primario?, secundario?, fondo?, superficie?, texto?, fuenteTitulos?, fuenteTexto?, nombre?, logo_id? }
toma:    { activa, fase, ficha{objetivo, secciones, bloques, marca, restricciones}, notas, preguntadas, rechazo }
puntos_n: int                              # contador de puntos de deshacer (los puntos viven en crm_puntos)
```

**Bloque** (igual que en el laboratorio):

```
{ uid: str, vista: str, seccion: <sec_id>, opciones: {}, ancho: 3|4|6|8|12, alto: 1..4, fijo?: bool }
```

**`listas[i]`** (cada lista = una sección general). Campos nuevos, todos opcionales:

```
vista: "tabla"|"tablero"|"agenda"|"vencimientos"|"calendario_mes"|"tablero_dinero"|"cifra"|"atencion"|"franjas"|"matriz"
opciones: {}            # opciones de su vista (ids de campos)
icono: str, grupo: 0|1|2, ficha: {grupos, relacionados, linea_tiempo}, tarjeta: {campos}
opciones_estado: { <campo_id>: [str] }, mapeo_estado: { <campo_id>: {viejo: nuevo} }, origen: <id de plantilla o pestaña>
campos[j].tipo: "texto"|"numero"|"dinero"|"fecha"|"hora"|"estado"|"lista"   # "lista" = alias de "estado"
campos[j].opciones: [str]                                                    # para estado
registros[k].ejemplo: true                                                   # sembrado; «quitar ejemplos» borra solo estos
```

**Ids:**
- Las secciones que vienen de una plantilla del laboratorio llevan el prefijo `l_` (`miembros` → `l_miembros`), porque `CrmPage` reconoce las listas por `l_`.
- Los bloques usan esos mismos ids.

## 2. Secciones virtuales: `backend/app/crm/secciones_v.py`
Una vista uniforme de **todo** lo que tiene registros, sin mover los datos de Carlos.

```python
secciones_de(doc) -> list[Seccion]
# Seccion = {id, titulo, campos:[{id,nombre,tipo,opciones?}], vista, opciones, icono, grupo,
#            ficha?, tarjeta?, virtual: None|"contactos"|"tareas"}
registros_de(doc, sec_id) -> list[{id, valores:{campo_id: v}, ejemplo?: bool}]
registro_agregar(doc, sec_id, valores) -> (doc_nuevo, registro)        # ErrorCrm si no se puede
registro_actualizar(doc, sec_id, rid, cambios) -> (doc_nuevo, registro)
registro_eliminar(doc, sec_id, rid) -> doc_nuevo
```

- **`contactos`** (id `contactos`, si no está oculta):
  - campos `nombre` (texto), `detalle` (texto), `canal` (texto), `etapa` (estado, opciones = `doc.etapas`), `responsable` (texto), más los `campos_contacto` (con su id `f_…`);
  - `valores` sale de `n`, `det`, `canal`, `etapa`, `dueno` y `extra`;
  - las escrituras van a `operaciones.contactos_*`.
- **`tareas`** (id `desarrollo`, el de su menú):
  - campos `tarea` (texto), `vence` (fecha), `hora` (hora), `estado` (estado: «Por hacer», «En curso», «Hecho» ↔ `porHacer`, `enCurso`, `hecho`);
  - las escrituras van a `operaciones.tareas_*`.
- **`listas`:** cada una como sección; las escrituras van a `estructura.registro_*`.

## 3. Puntos de deshacer: colección `crm_puntos`

```
{ user_id, n: int, hora: ISO, antes_de: str (≤80), cambio: ["bloques"|"marca"|"estructura"|"datos"],
  foto: { bloques?: {inicio, paginas}, marca?: {...},
          estructura?: {listas_meta (sin registros), etapas, campos_contacto, ocultas, secciones},
          datos?: { <sec_id>: [registros] } } }   # solo las secciones que cambiaron
```

- Se guardan los últimos 30 por usuario.
- Los crea `puntos.con_punto(antes, despues, texto)`: mide qué cambió, como `conPunto` del laboratorio.
- `deshacer` es selectivo por categoría. En `datos` usa 3 vías (como `revertirDatos`): solo lo de ese pedido; si un pedido posterior tocó lo mismo, se deshacen en cadena y se dice.
- Lo hecho **a mano** (rutas REST) también deja punto, con `antes_de` = «A mano: …».

## 4. Vista para la pantalla (`vista.py`, camelCase, aditivo)

```
crm.esquema, crm.plantilla, crm.inicio, crm.paginas, crm.marca, crm.toma
crm.listas[i]: + vista, opciones, icono, grupo, ficha, tarjeta, opcionesEstado, origen; campos con los tipos nuevos
crm.listas[i].registros[k].ejemplo
crm.puntos: [{n, antesDe, hora, cambio}]   # los últimos 30, sin foto
```

## 5. Catálogos compartidos: `backend/app/crm/catalogos/*.json`
Los genera `laboratorio/servidor/exportar-catalogos.mjs` a partir de los JS (la fuente mientras viva el laboratorio). Se commitean.

| Archivo | Contenido |
|---|---|
| `plantillas.json` | `{ semillas: [6 objetos], biblioteca: [21 objetos] }`, con la forma de `semillas.js` / `biblioteca/*.js` sin funciones |
| `pestanas.json` | Las 35 plantillas de pestaña (`biblioteca-pestanas`) |
| `graficos.json` | `{ <tipo>: { nombre, familia, requiere, opciones?, … } }`, sin `Componente` ni `calcular`. La regla de `compatibles()` se porta a Python y se verifica con fixtures |
| `vistas.json` | `VISTAS` de `validar.js`: qué opciones pide cada vista |
| `iconos.json`, `fuentes.json` | Los catálogos |

`test_catalogos.py` regenera y falla si difieren.

## 6. Fixtures dorados: `backend/test/crm/fixtures/lab/<funcion>.json`
Solo para **funciones puras con la misma forma de entrada y salida** en JS y en Python:

```
[ { caso: str, entrada: {...args}, salida: <resultado exacto> } ]
```

Cubren `parseFecha`, `parseNumero`, `parseHora`, `opcionDe`, `parsePeriodo`, `fechaLarga`, `buscarRegistro`, `acomodar`, `compatibles` (por cada sección de cada plantilla), `afirmaCambio` y `revertirDatos`.

Las **herramientas** (`edicion`/`registros`/`chat`) no se comparan con fixtures, porque la forma del estado cambia (plantilla + cambios → documento). Se comparan con los **bancos** a través de `adaptador_lab.py`.

## 7. Adaptador de bancos (solo para medir): `POST /api/v1/crm/lab/chat` con `CRM_LAB_ADAPTER=1`
- **Entra** lo mismo que `/api/lab/chat` del laboratorio: `{plantilla, estado, texto, historial, muestra, seleccion, imagen}`.
- El adaptador:
  1. siembra un documento desde la plantilla y `muestra` (los ejemplos), y le aplica `estado` (bloques, marca, estructura, datos delta) sobre un `_FakeDb`;
  2. corre el agente;
  3. devuelve la forma del laboratorio: `{respuesta, estado (con datos como delta frente a la siembra), cambios, fallos, intentos, consultas, avisos}`.
- Los bancos (`laboratorio/pruebas/*.py`) toman la URL de la variable `BASE`.

## 8. Mapeo de herramientas
| Laboratorio | Destino en Carlos |
|---|---|
| `agregar_registro`, `editar_registro`, `borrar_registro`, `consultar_datos` | Nombre del laboratorio. El handler pasa por `secciones_v`. Las `agregar_contacto`/… de Carlos quedan como alias por una versión |
| `crear_seccion`, `agregar_campo`, `quitar_campo`, `renombrar_campo`, `cambiar_opciones_estado` | Nombre del laboratorio, que llama a `estructura.*` de Carlos |
| `agregar_bloque`, `quitar_bloque`, `mover_bloque`, `cambiar_tamano`, `cambiar_visual`, `cambiar_rangos`, `cambiar_ficha`, `cambiar_tarjeta`, `cambiar_marca`, `restablecer_marca`, `usar_logo`, `abrir_seccion`, `leer_enlace`, toma (`abrir_toma`, `anotar_bloque`, `anotar_ficha`, `anotar_nota`, `quitar_de_ficha`, `cerrar_toma`), `deshacer` | Nuevas, en `edicion.py` / `toma.py` / `puntos.py` |

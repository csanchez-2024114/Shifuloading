# Contrato con el servidor de Shifu

La interfaz está lista para conectarse. Todo el acceso a datos pasa por `src/api/index.js`; las pantallas no usan `fetch` ni `localStorage` para esto.

## Cómo conectarlo

1. Copia `.env.example` a `.env` y escribe la dirección del servidor **con el prefijo de versión**: `VITE_API_URL=http://localhost:5000/api/v1`. Todas las rutas de abajo cuelgan de ahí.
2. Reinicia `npm run dev`. Con esa variable la interfaz usa el servidor real; sin ella usa el **servidor simulado** (`src/api/mock/`), que guarda todo en el navegador y puede borrarse al terminar.
3. Si el servidor está en otro dominio, debe permitir CORS para el origen de la interfaz y las cabeceras `Content-Type` y `Authorization`.

## Reglas generales

- JSON en ambos sentidos. Con sesión, cabecera `Authorization: Bearer <token>` (el token se guarda al iniciar sesión).
- Errores: estado HTTP adecuado y `{ "mensaje": "texto para mostrar" }` (en errores genéricos del servidor puede venir `{ "detail": "..." }`; la interfaz entiende ambos). `404` en `GET /crm` significa "esta persona aún no tiene CRM". `409` si el CRM cambió mientras se guardaba (se puede reintentar). `422` si algo no cumple las reglas (etapa inválida, nombre vacío, etc.).
- **Toda ruta que cambia el CRM devuelve el CRM completo y actualizado** (forma de abajo). La pantalla solo lo reemplaza.
- Los ids son cadenas, los asigna el servidor.

## Rutas

| Método y ruta | Cuerpo | Respuesta |
|---|---|---|
| `POST /auth/register` | `{ name, last_name, email, password }` (contraseña: 8+ con letra y número) | `201 { user, access_token, refresh_token }` · `400` si la cuenta ya existe |
| `POST /auth/login` | `{ email, password }` | `{ user, access_token, refresh_token }` · `401 { detail }` si no coincide |
| `POST /auth/refresh` | `{ refresh_token }` | `{ access_token, refresh_token }` (el anterior queda invalidado) |
| `POST /auth/logout` | `{ refresh_token }` + token de acceso | `{ success }` |
| `GET /crm` | — | CRM · `404` si no tiene |
| `POST /crm` | `{ brief }` (respuestas del cuestionario, ver abajo) | CRM nuevo, armado por Shifu a partir del brief. **409** si la persona ya tiene un CRM con datos (contactos, registros o tareas suyas): no se pisa; para rehacerlo, primero `DELETE /crm` |
| `DELETE /crm` | — | `204` (para repetir el cuestionario) |
| `POST /crm/contactos` | `{ filas: [{ n, det?, extra? }], canal, texto? }` | CRM (alta de uno o varios; `texto` es la frase que queda en Actividad) |
| `PATCH /crm/contactos/:id` | campos a cambiar (`etapa`, `n`, `dueno`…) | CRM |
| `DELETE /crm/contactos/:id` | — | CRM |
| `POST /crm/siguiente-pregunta` | `{ nombre, ubicacion?, que_vendes, qa: [{ pregunta, respuesta }] }` (las 3 preguntas fijas y las que la IA ya hizo; sin sesión, limitado por IP y por tope diario) | `{ modo: "ia"\|"base", pregunta: { id, tipo: "una"\|"varias"\|"parrafo", titulo, emoji, sub, opciones } \| null, rubro: string\|null }`. Es el cuestionario que escribe la IA, una pregunta a la vez: `pregunta` trae la siguiente; `pregunta: null` con `modo: "ia"` significa que ya sabe lo suficiente (mínimo 4, máximo 5 preguntas de la IA); `modo: "base"` significa que la IA no está disponible y la pantalla sigue con sus preguntas fijas de respaldo. `422` si faltan el nombre o qué vende |
| `POST /crm/seguimiento` (antiguo, ya no lo usa la pantalla) | `{ brief }` (sin sesión; limitado por IP) | `{ preguntas: [{ id, tipo: "una"\|"varias"\|"parrafo", titulo, emoji, sub, opciones: [{ v, e, t }] }], modo: "ia"\|"base" }`: preguntas propias del negocio que la IA hace tras las generales |
| `GET /crm/chat/historial` | — | `{ mensajes: [{ de: "yo"\|"shifu", t }], saludo: string\|null }`: la conversación guardada en el servidor y, si hace más de 6 horas que no hablan y hay algo pendiente, un saludo que retoma lo último |
| `GET /crm/memoria` | — | `{ estilo, hechos[], trabajo }`: lo que Shifu recuerda de la persona (nada escondido) |
| `DELETE /crm/chat` | — | 204. Borra el historial y todo lo que Shifu recuerda de la persona (el CRM no se toca) |
| `POST /crm/tareas` | `{ t, vence?, hora? }` (`vence` AAAA-MM-DD, hoy o futura; `hora` HH:MM) | CRM (entra en la columna `porHacer`) |
| `PATCH /crm/tareas/:id` | `{ columna?, t?, vence?, hora? }` (al menos uno; `vence: ""` le quita la fecha; solo se valida lo que se manda) | CRM |
| `DELETE /crm/tareas/:id` | — | CRM |
| `PUT /crm/automatizaciones/:id` | `{ on: boolean }` | CRM (422 si se intenta encender una que todavía no existe) |
| `PUT /crm/secciones/:id` | `{ nombre }` (renombra una sección) | CRM |
| `POST /crm/listas/:id/registros/lote` | `{ filas: [{ <idCampo>: valor }] (hasta 300), lote?: { id, nombre } }` (`id`: 6 a 40 letras, números, `_` o `-`; las tandas de una misma importación llevan el mismo `lote`) | `201` CRM + `importacion: { agregadas, omitidas }`. Se omiten filas vacías, repetidas o con un valor que no corresponde al tipo del campo; `422` con el motivo si no se pudo importar ninguna |
| `DELETE /crm/listas/:id/importaciones/:lote` | — | CRM sin los registros de esa importación (incluso los editados). No se puede deshacer. `404` si ya no existe |
| `POST /crm/listas/:id/registros` | `{ valores: { <idCampo>: valor } }` | `201` CRM (agrega un registro a una sección propia) |
| `PATCH /crm/listas/:id/registros/:rid` | `{ valores: { <idCampo>: valor } }` | CRM |
| `DELETE /crm/listas/:id/registros/:rid` | — | CRM |
| `POST /crm/chat` | `{ texto, contexto?: { pendiente?, imagen?, seccion? } }` | `{ respuesta, crm, vista?, pendiente? }` |

### Chat

El chat flotante manda lo que escribe la persona. El servidor (con la IA de Shifu) decide qué hacer: agregar, modificar o eliminar contactos y tareas, renombrar secciones, activar o apagar automatizaciones. Debe responder:

- `respuesta`: texto que Shifu dice.
- `crm`: el CRM ya con los cambios aplicados.
- `vista` (opcional): sección que conviene abrir (`contactos`, `desarrollo`, `importar`, `automatizaciones`…).
- `pendiente` (opcional): si antes de borrar pide confirmación, devuelve aquí lo que quedó por confirmar. La interfaz lo reenvía tal cual en `contexto.pendiente` con el siguiente mensaje ("sí" confirma, cualquier otra cosa cancela).

**Capturas de pantalla.** En el chat, la persona puede elegir una parte de la pantalla (botón de la cámara), pegar una imagen o ambas, y escribir qué quiere hacer ("quiero una columna aquí"). Llega en `contexto.imagen` como imagen JPEG en base64 (`data:image/jpeg;base64,...`, hasta 1400 px de ancho) y `contexto.seccion` con el nombre de la sección que tenía abierta. `texto` puede venir vacío si solo mandó la imagen: la IA debe preguntar qué quiere hacer. Hoy el servidor simulado solo acusa recibo (no lee imágenes); el servidor real debe pasarla al modelo de visión junto con el texto.

La lógica de ejemplo está en `src/api/mock/chat.js`.

## Forma del CRM

```json
{
  "brief": { "...respuestas del cuestionario..." },
  "totalContactos": 120,
  "contactos": [{ "id": "", "n": "Ana Morales", "det": "5555-1234", "canal": "WhatsApp", "etapa": "Nuevo", "dueno": "Tú", "dias": 0, "extra": { "<idCampo>": "valor" } }],
  "etapas": ["Nuevo", "En contacto", "Interesado", "Cliente"],
  "camposContacto": [{ "id": "f_ab12cd34", "nombre": "Cumpleaños", "tipo": "fecha" }],
  "ocultas": ["cobros"],
  "listas": [{ "id": "l_ab12cd34", "nombre": "Proveedores", "campos": [{ "id": "f_…", "nombre": "Nombre", "tipo": "texto" }],
               "registros": [{ "id": "", "valores": { "<idCampo>": "valor" } }] }],
  "vendedores": ["Tú", "Mariana Solís"],
  "tareas": { "porHacer": [{ "id": "", "t": "", "vence": "2026-11-02", "hora": "16:00", "contacto": "Nombre", "auto": true }], "enCurso": [], "hecho": [] },  // vence, hora y contacto son opcionales (las pone el chat al agendar)
  "eventos": [{ "id": "", "e": "➕", "t": "Agregaste a Ana Morales", "h": "ahora" }],
  "automatizaciones": [{ "id": "recordatorios", "pilar": "Estructura", "t": "", "d": "", "on": true, "disponible": true, "nota": null }],  // disponible:false = todavía no existe (no se puede encender; `nota` dice por qué)
  "secciones": { "contactos": "Pacientes" }
}
```

- `totalContactos` es el total real y `contactos` la lista. `etapa` es una de las `etapas` del CRM (por defecto Nuevo, En contacto, Interesado, Cliente; la persona puede cambiarlas por el chat). `dias` son los días desde el último contacto.
- `secciones` solo trae los nombres que la persona cambió; los demás salen del rubro (`src/crm/secciones.js`).
- `eventos`, del más nuevo al más viejo, es lo que muestra la sección de actividad.

## Estructura propia del CRM

Cada persona moldea su CRM hablando con Shifu (`POST /crm/chat`): la IA puede **cambiar las etapas**, **quitar secciones del menú** (`ocultas`; sus datos se conservan y se pueden volver a mostrar), **crear secciones propias** (`listas`, con campos de tipo `texto`, `numero` o `fecha` y sus registros), **agregar campos a los contactos** (`camposContacto`, valores en `contacto.extra`) y renombrar secciones. Los valores por tipo: `numero` acepta "1,250" o "3,5"; `fecha` acepta `2026-11-02`, `02/11/2026` o `02-11-2026` y se guarda como `YYYY-MM-DD`.

Lo que borra datos (un contacto, una tarea, un registro, un campo o una sección propia) nunca es inmediato: el servidor devuelve `pendiente` (`{tipo, id, …}`) y el cliente lo reenvía con el siguiente mensaje; "sí" lo confirma y lo resuelven reglas fijas, no la IA. Los tipos de `pendiente` son `contacto`, `tarea`, `lista`, `registro` (con `lista`) y `campo` (con `ambito`). Un id de sección propia es `l_…` y puede venir en `vista` para abrirla.

La respuesta de `/crm/chat` incluye `modo`: `"ia"` o `"reglas"` (si la IA no está disponible por falta de saldo, clave o tiempo, contesta con reglas básicas que no cambian la estructura). `contexto.historial` (hasta 8 `{de: "yo"|"shifu", t}`) permite entender "y también a Pedro".

## Brief (respuestas del cuestionario)

Además: `que_vendes` (texto libre: qué vende o qué servicio da) y `seguimiento: [{ pregunta, respuesta }]` (hasta 4, las preguntas que hizo la IA con lo que contestó). Con todo eso, `POST /crm` hace que la IA diseñe etapas, campos de contacto, secciones propias y nombres a la medida; el resumen de lo que armó llega en `resumenIA`. Si la IA no está disponible, el CRM nace con la plantilla base. Con `CRM_DISENO=1` el CRM se arma SIEMPRE nuevo con piezas de todas las plantillas según su % de compatibilidad con todas las respuestas (`app/crm/primer_diseno.py`; una llamada al modelo, dos como máximo; sin IA, respaldo con las piezas de mayor %), con 8 ejemplos por sección; `resumenIA` lo escribe el código con lo creado y `saludoEjemplos` trae 3 pedidos de ejemplo con las secciones reales. `que_vendes` y cada `respuesta` de `seguimiento` aceptan hasta 1500 caracteres.

Las preguntas y los valores posibles están en `src/brief/preguntas.js`. Forma: `nombre`, `ubicacion: { pais, ciudad? }`, `rubro`, `tiempo`, `canales[]`, `cartera`, `ciclo`, `problemas[]`, `equipo`, `herramientas[]`, `objetivos[]` (sin límite), `dolor`, `armado`, `autonomia`, `presupuesto`.
El avance del cuestionario se guarda en el navegador mientras se contesta; solo al terminar viaja al servidor con `POST /crm`.

## Estado del servidor

El módulo de CRM ya existe en `backend/app/crm` y `backend/app/routes/crm` (colección `crm_workspaces`, un documento por persona) y implementa todas las rutas de `/crm` de arriba. Sus pruebas están en `backend/test/crm` (`pytest test/crm`). Todas las rutas exigen el token del usuario (`Authorization: Bearer ...`) y solo ven su propio CRM. El chat de `/crm/chat` es por reglas (sin IA) hasta que se conecte el agente.

**Sesión.** La interfaz usa las rutas `/auth/*` que ya trae el backend (correo y contraseña). El token de acceso va en `Authorization: Bearer ...`; si una petición responde `401`, la interfaz pide otro con `/auth/refresh` (una sola vez, aunque fallen varias a la vez) y repite la petición; si tampoco se puede, borra la sesión y manda a `/login`. Flujo de una persona nueva: cuestionario → crear cuenta (`/registro`) → `POST /crm` con sus respuestas. Una persona que vuelve: `/login` (correo, luego contraseña) → su CRM. Sin `VITE_API_URL` no hay cuentas y todo esto se salta.

## Pendiente de definir en el servidor

- Cobros (la pantalla usa datos de ejemplo todavía).
- Lectura de la captura por un modelo de visión: hoy el servidor la recibe y acusa recibo, pero no la interpreta.
- Pantalla `/panel` (asistente de inicio): su chat sigue respondiendo con texto fijo; falta conectarlo a `POST /chat`.
- Lectura de archivos `.xlsx` (hoy se pega o se sube CSV/TXT y se interpreta en el navegador).
- Entrar con Google, Apple, Facebook, WhatsApp o clave de acceso (los botones del login todavía no hacen nada) y recuperar contraseña (el backend ya tiene `/auth/forgot-password` y `/auth/reset-password`, falta la pantalla).


## Automatizaciones

Funcionan de verdad tres, sin conectar nada de afuera: **recordatorios** (crea una tarea con `auto: true` cuando un contacto lleva 3 días sin cambiar de etapa), **reparto** (asigna los contactos nuevos por turnos entre el equipo) y **resumen** (una vez por semana deja un resumen en `eventos`). **bienvenida**, **contacto** y **vencidos** todavía no existen (`disponible: false`). Lo pendiente se calcula cuando alguien abre o toca el CRM y, con `SHIFU_SCHEDULER=1`, también cada `CRM_RELOJ_SEGUNDOS` (300) en el programador (`app/crm/reloj.py`), aunque nadie lo tenga abierto. El reloj deja avisos en `user_notifications` (`GET /me/notifications`, la campana del CRM) de tipo `crm_recordatorio` y `crm_resumen`, que además salen por correo si `SHIFU_NOTICE_EMAILS=1` y hay SMTP. Repetirlo no duplica nada: se guarda solo si nadie cambió el CRM en medio (versión) y los avisos se crean después de guardar.


## Memoria de Shifu

El historial del chat y lo que Shifu recuerda viven en el servidor (colección `crm_conversaciones`, un documento por persona), no en la pantalla: sobreviven a recargar y a cambiar de dispositivo, y lo que mande el navegador en `contexto.historial` solo se usa si todavía no hay nada guardado.

- **Historial:** los últimos 200 mensajes.
- **Memoria:** el estilo (`tratamiento` tú/usted, `tono`, `largo`, `emojis`), hasta 12 hechos duraderos del negocio o de cómo quiere su CRM, y una frase de en qué trabajaron la última vez. Se pone al día en segundo plano cada 4 mensajes de la persona y con la herramienta `recordar`. Lo que la persona pide explícitamente manda sobre lo que se observa.
- **Privacidad:** nunca se guardan contraseñas, claves, tarjetas, identificaciones, teléfonos, correos ni datos de salud, religión o política. Los hechos duraderos tampoco llevan nombres de clientes. La persona lo borra todo con `DELETE /crm/chat`; rehacer el CRM olvida la conversación pero conserva cómo le gusta que le hablen.
- Lo recordado entra al prompt como contexto, nunca como órdenes.

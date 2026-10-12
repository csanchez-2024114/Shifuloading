# UI actions: contrato entre el agente y el frontend

Vigente desde la versión 0.10.1 del agente. Este documento es para quien construye un frontend que conversa con Shifu. Un ejemplo que lo implementa completo está en [ui/flow.html](../../ui/flow.html).

## Qué es

Junto con cada respuesta, el agente puede mandar **acciones de interfaz**: cosas que el frontend debe mostrar o abrir. Llegan en el evento `done` del chat (SSE `/api/v1/chat/stream` y WebSocket `/ws/chat`), en el campo `ui_actions`, y se guardan con el mensaje, así que también vienen al recargar una conversación.

```json
{"type": "done", "text": "Puedes pulsar el botón de abajo.", "workflow_id": null,
 "ui_actions": [{"type": "ui_action", "id": "open_memory", "label": "Ver lo que Shifu recuerda", "params": {}, "confirm": false}]}
```

## Lo que el frontend manda

En cada mensaje del chat, el frontend declara qué acciones sabe ejecutar:

```json
{"text": "ábreme mis workflows", "conversation_id": "…", "ui_supported": ["open_workflows", "open_memory", "open_settings"]}
```

- El agente **solo ofrece** acciones que estén en esa lista. Así nunca dice "pulsa el botón" para algo que ese frontend no pinta.
- Un frontend que no manda `ui_supported` no recibe ninguna acción de tipo `ui_action`. Las de sistema (abajo) llegan siempre.
- La lista se manda en todos los mensajes; puede cambiar de un mensaje a otro.

## Los cuatro tipos de acción

| `type` | Quién la decide | Campos | Qué debe hacer el frontend |
|---|---|---|---|
| `ui_action` | El usuario la pidió ("ábreme…") | `id`, `label`, `params`, `confirm` | Mostrar un botón con `label` bajo la respuesta; al pulsarlo, ejecutar lo que corresponda a `id` |
| `connect_app` | El sistema: falta conectar una app | `app`, `reason`, `auth_url`, `auth_type` (`oauth2`, `apikey`, `oauth1`) | Mostrar el control para conectar esa app |
| `render_workflow` | El sistema: se acaba de activar un workflow | `workflow_id`, `steps` | Mostrar el workflow; cada paso trae `order`, `name`, `app`, `function_id`, `config` |
| `open_trigger` | El sistema: ese workflow tiene disparador | `workflow_id`, `trigger_type`, `summary`, `webhook_url` | Mostrar cuándo corre o la dirección del webhook |

## Reglas que el frontend debe cumplir

1. **`confirm: true` obliga a confirmar.** Esa acción cambia algo. El frontend pide confirmación en el propio botón antes de ejecutarla; el texto del agente no cuenta como confirmación.
2. **Ignorar lo desconocido.** Un `type`, un `id` o un campo que el frontend no conoce se ignora sin romper. El contrato solo crece: no se quitan ni se renombran campos.
3. **El `label` ya viene en el idioma del usuario** cuando el catálogo lo tiene; si no, en español. El frontend puede usar su propio texto a partir del `id`.
4. **`params` solo trae lo que el catálogo declara** para esa acción (por ejemplo `app` en `open_app`). Los valores son texto.
5. **Como máximo dos `ui_action` por respuesta.**

## El catálogo

Las acciones de tipo `ui_action` están en la colección `ui_actions_catalog` de Mongo, un documento por acción. Agregar una acción no toca el código del agente.

| Campo | Para qué |
|---|---|
| `id` | Lo que recibe el frontend |
| `label` | Texto del botón: un texto, o un objeto por idioma (`{"es": "…", "en": "…"}`) |
| `description` | En inglés. El agente la lee para decidir cuándo aplica: debe decir qué abre y cuándo usarla |
| `params` | Parámetros que el agente puede llenar, cada uno con su explicación en inglés |
| `source` | `user` (el usuario la pide) o `system` (la arma el código; el modelo no la ve) |
| `status` | Solo `active` se usa |
| `plans` | Opcional. Lista de planes que la pueden usar; sin el campo, todos |
| `confirm` | Opcional. `true` si la acción cambia algo |

**Para agregar una acción:**

1. Agregar el documento en Mongo, o una fila en [scripts/seed_ui_actions.py](../../scripts/seed_ui_actions.py) y correrlo.
2. Implementarla en el frontend y sumar su `id` a `ui_supported`.
3. Agregar a [scripts/eval_ui_actions.py](../../scripts/eval_ui_actions.py) una frase que la pida y otra parecida que no deba dispararla, y correrlo.

El agente toma el cambio en menos de 10 minutos (caché) o al reiniciar.

## Lista de prueba cargada hoy

`open_workflows`, `open_connections`, `open_memory`, `open_notifications`, `open_settings`, `open_billing`, `new_conversation`, `open_help`, `open_app` (con `params.app`). Todas abren una pantalla; ninguna lleva `confirm` ni `plans`.

## Límites conocidos

- El agente detecta la petición por lo que el usuario escribe; no sabe qué hay en cada pantalla.
- En un saludo a secas ("hola") no se evalúan acciones.
- Si el frontend no soporta lo pedido, el agente dice que no puede abrirlo; a veces agrega indicaciones genéricas ("busca el ícono de engranaje") que no conoce de verdad.
- No hay todavía botón de confirmar para las escrituras que el agente hace en las apps del usuario; ese "sí" va por texto.

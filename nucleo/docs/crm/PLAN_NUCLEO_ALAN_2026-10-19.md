# Plan: el CRM generativo encima del núcleo «Agente 0» de Alan — 19-oct-2026

Solo plan; no se cambió código. Lo pidió el usuario: el repo de Alan (`Alan4745/langgraph`, todas sus ramas) es la base nueva; encima va **todo** lo que hoy tiene el CRM, sin descartar nada; si Alan tiene algo mejor, se adopta lo suyo y se adapta al CRM.

Debate: Claude (agente de planificación, leyó el código de los dos lados), Composer 2.5 y Grok 4.7 por separado, con el mismo planteamiento (`documentos/debate_nucleo/`). Lo dudoso se verificó en el código (ver §9).

## 1. Decisiones (en lo que coinciden los tres, salvo donde se indica)

1. **Repositorio nuevo = clon de Alan, con su historia.** Se conserva `origin` de Alan como `upstream` para traer sus mejoras. El núcleo (`src/assistant/core/`) no se toca, salvo **un** gancho (punto 4), que se le propone a Alan para que también quede en su repo.
2. **El CRM es un perfil:** `AGENT_PROFILE=crm`.
   - `src/assistant/packs/crm/`: todo el dominio (lógica pura, sin bucle del modelo).
   - `src/assistant/profiles/crm/`: prompt, herramientas, políticas, middlewares y estado del turno.
3. **Se adopta de Alan:**
   - `create_agent` con sus middlewares: `LimiteLlamadas`, `LimiteRepeticiones`, `AterrizajeSuave`, `AvisoCorte`, `ToolErrorMiddleware`, `FiltroURLs`.
   - El checkpointer por hilo y `MongoDBStore` para los recuerdos.
   - `files/`: GridFS, extracción en subproceso y contenido no confiable.
   - Trazas, métricas, feedback, el marco de evals, `tool_spec` y `HumanInTheLoop` (este queda listo, pero apagado al principio).
4. **El único cambio al núcleo: `AgentProfile.extra_middleware(settings) -> list`**, que se agrega al final de la lista de `build_agent`.
   - Hoy la lista está fija en `core/agent.py:build_agent` y el perfil no puede sumar middlewares (verificado).
   - Sin este gancho, el contexto de pantalla, el filtro tras deshacer y la verdad de la respuesta quedan fuera del agente.
   - Se cubre con la prueba de caracterización de Alan.
5. **Se conserva lo nuestro, porque Alan no lo tiene:**
   - el documento del CRM por persona con `version`, y deshacer por puntos con foto;
   - los pendientes que anota el código, los cercos y ganchos de verdad, y la pantalla que ve el modelo;
   - el catálogo de conceptos, la toma, el brief, el primer diseño, el logo y lo regional;
   - el respaldo sin IA (`chat.py`), `consultar_datos` con cifras calculadas por el código y el adaptador del laboratorio.
6. **Interruptores del perfil `crm`:**

   | Interruptor | Valor | Por qué |
   |---|---|---|
   | `MODEL_CALL_LIMIT` | 7 | Igual que el `MAX_VUELTAS` de hoy; además apaga el clasificador, que es una llamada extra |
   | `ANSWER_VERIFY` | 0 | Nuestros ganchos ya cumplen ese papel |
   | `USE_BIGTOOL` | 0 | Unas 50 herramientas no lo necesitan, y `retrieve_tools` sería una llamada de más |
   | `MEMORY_SUMMARIZE` | 0 | Hasta igualar el banco de memoria |
   | `EFFECT_APPROVAL` | 0 | Los bancos esperan el «sí» por mensaje |

   **El modelo se fija en el de la línea base** (`gpt-4.1-mini`). Cambiar a `gpt-6-luna` es otra decisión, que se mide aparte.
7. **Agente síncrono.** Los middlewares de Alan solo tienen versión sync.
   - Las rutas FastAPI async entran al turno con `asyncio.to_thread`.
   - Las herramientas trabajan sobre una copia del documento en memoria, y el documento se escribe **una sola vez** al final del turno, con el reintento por `version` de hoy.
   - `web.buscar` y `leer_enlace` pasan a httpx síncrono.
   - Motor sigue en el resto del backend de Carlos.
8. **Estado del turno en una `ContextVar` (`TurnoCrm`)**, igual que hace Alan con `_turn_counter()`. Lleva la `SesionDiseno`: doc, cambios, fallos, consultas, avisos, deshecho y pendientes. No va al checkpointer.
9. **Hilo = `crm:{user_id}`** (un hilo por persona, como hoy).
   - El candado en memoria de Alan vale con **un worker**.
   - Antes de usar varios workers o réplicas: candado en Mongo con caducidad, por usuario.
10. **Pantalla:** se queda la app React. La UI de un HTML de Alan solo sirve para depurar.
11. **Auth: se queda el JWT de Carlos** (decisión de Grok y Composer; Claude proponía la de Alan).
    - La de Alan es de cookie, pensada para su demo. `AUTH_ENABLED` de Alan queda en 0.
    - El `user_id` sale siempre del JWT, nunca del cliente.
12. **El codificador** (rama `feat/agente-codificador`) entra al repo como **otro perfil** (`coder`) y no se mezcla con el CRM. Sus patrones (`tool_spec`, tokens de vista previa) quedan disponibles.

## 2. Dónde va cada archivo

| Hoy (Shifuloading, rama david) | Destino |
|---|---|
| Dominio: `edicion, registros, toma, pantalla, conceptos + catalogos/*, puntos, por_hacer, plantillas, sembrar, primer_diseno, diseno, generador, operaciones, estructura, secciones, secciones_v, valores, validar, lienzo, marca, regional, web, chat, vista, ejemplos, asignar, afirma, reloj, adaptador_lab, responder_lab, repositorio` | `packs/crm/` (cambian los imports; `repositorio` pasa a pymongo síncrono en `packs/crm/repos/`) |
| `SesionDiseno` y `Sesion` (cercos, contexto, herramientas, ganchos) | `packs/crm/sesion/` (se conservan las clases; deja de existir el bucle) |
| Bucle `agente_diseno._responder` y `agente.responder` | Pasan a middlewares (§3); el código viejo queda hasta la fase 6 |
| `prompt_sistema`, `INSTRUCCIONES_*` | `profiles/crm/prompts/system.md` (se arma en `ContextoCrm`) |
| Herramientas (`HERRAMIENTAS_EDICION`, `HERRAMIENTAS_DATOS`, toma, deshacer, agendar, enlace, las de Carlos) | `profiles/crm/tools.py` (`build_tools`, `@tool` que llaman a la sesión del turno) |
| `memoria.py` (mensajes completos, ventana, resumen, estilo y hechos) | Estilo, hechos y `por_hacer`: `packs/crm/conversacion.py`; la ventana y el resumen, al checkpointer y `ResumenPorTurno` **solo** tras la compuerta de memoria (fase 4) |
| `adjuntos.py` | Lectura de archivos: `files/` de Alan. `columnas_fuera`, la nota de columnas y el logo se quedan en el pack |
| `traza.py` | Tracing y `TurnRecorder` de Alan; se conservan `cambios/fallos/intentos/consultas/avisos` en la respuesta |
| `automatizaciones.py` | `packs/crm/` (sigue en pausa; fuera del prompt) |
| `routes/crm/crmRoutes.py`, `labRoutes.py` | `profiles/crm/routes.py` (mismos contratos HTTP), montado en la app de producto |
| Resto del backend de Carlos (~70k líneas: auth, billing, canales, workers, integraciones…) | Carpeta `producto/` del repo, completa desde el día 1; sus routers se encienden por fases (fase 5). Nada se borra |
| React (`src/`), `laboratorio/` y sus bancos | Igual, en la raíz del repo nuevo (o `web/`) |
| `backend/test/crm` (~18.000 pruebas) | `tests/crm/` |
| Documentos (`documentos/`, plan maestro, listas, mediciones) | `docs/crm/` |

## 3. El bucle del turno en middlewares (sin llamadas nuevas)

Verificado: en LangChain un middleware puede devolver `jump_to` a `"model"`, `"tools"` o `"end"`. Así se rehace la vuelta de corrección de hoy sin agregar llamadas.

| Hoy (`agente_diseno.py` / `agente.py`) | Middleware (`profiles/crm/middleware.py`) |
|---|---|
| `mensajes[0]` = prompt + contexto JSON + conceptos + pendientes + aviso de toma | `ContextoCrm.wrap_model_call` (en cada vuelta) |
| `planificar_cerco_masivo(llamadas)` | `after_model` (lee los `tool_calls` antes del nodo de herramientas) |
| `SesionDiseno._cerco` (antes de ejecutar) | `CercoCrm.wrap_tool_call`: si frena, devuelve el error como `ToolMessage` sin llamar al handler |
| Avisos tras herramientas (`senal_toma`, `aviso_campos_vacios`, aviso de deshacer) | `before_model`, si la vuelta anterior fue de herramientas |
| `tras_deshacer` / `solo_responder` (herramientas acotadas por una vuelta) | `wrap_model_call` con `request.override(tools=…)` |
| `revisar_respuesta` + `GANCHOS_PANTALLA`, hasta `MAX_CORRECCIONES=2` | `RevisionRespuesta.after_model` con `jump_to="model"` y el contador en el estado del turno (la misma vuelta extra de hoy) |
| `pregunta_pendiente` (corta sin otra vuelta) | `jump_to="end"` |
| Retoques finales: `verdad_lado_final`, `respuesta_del_codigo`, `_respuesta_solo_deshacer`, `respuesta_confirmando`, promesas → `por_hacer`, `frase_columnas`, `creado_sin_decir`, `revisar_sustituto_final` | `VerdadFinal.after_agent`, en el **mismo orden** que hoy; reemplaza el último mensaje (como `AnswerVerifier`). `revisar_sustituto_final` usa su vuelta dentro del tope, no aparte |
| `construir_desde_ficha` (sin modelo) | Se resuelve antes de entrar al grafo |

**Cuidado 1, los avisos internos en el historial.**
- El checkpointer guardaría los avisos de corrección y las respuestas descartadas. Hoy no quedan en la memoria.
- Hace falta un `wrap_model_call` que los quite de los turnos anteriores (como `PodaHerramientas` de Alan), y que `get_history` los oculte.
- Si no, cambia lo que el modelo recuerda y baja el banco de memoria.

**Cuidado 2, el orden de los hooks.**
- Los `after_*` corren en orden inverso a la lista.
- Por eso, **primero un middleware único `BucleCRM`** que replique el bucle de hoy casi literal.
- Solo con paridad medida se separa en los middlewares finos de la tabla.

## 4. Fases y compuertas

**Regla de compuerta**, en cada fase:
- 3 corridas de cada banco, comparando rangos (porque varían entre corridas).
- Llamadas al modelo por mensaje ≤ hoy, y p95 de tiempo igual o mejor.
- `tests/crm` en verde.

Si algo baja, no se pasa de fase.

| Fase | Qué se hace | Compuerta |
|---|---|---|
| **0. Línea base e inventario** | 3 corridas de los 8 bancos con el núcleo actual, guardando trazas y llamadas por mensaje. Checklist de paridad generado del código: cada función pública, herramienta, rama de `_cerco`, gancho, ruta de `crmRoutes`/`labRoutes`, colección, variable de entorno, catálogo y pantalla de React, cada una con su destino y la prueba que la cubre | Checklist sin filas vacías |
| **1. Repo y dominio** | Clon de Alan (+ rama codificador como perfil), el gancho `extra_middleware`, `packs/crm` completo, `producto/` de Carlos en el árbol (apagado), pruebas portadas | Las ~18.000 pruebas pasan igual; las de Alan, también |
| **2. Puente con `BucleCRM`** | `profiles/crm` con herramientas y un solo middleware que replica el bucle. La ruta `/api/v1/crm/lab/chat` compatible **desde el primer día**. Prueba de reproducción: modelo falso con respuestas grabadas de los bancos; los dos núcleos deben mandar al modelo y devolver exactamente lo mismo | Reproducción idéntica + bancos ≥ base |
| **3. Middlewares finos** | Separar `BucleCRM` en los de §3, uno por uno; limpiar los avisos del historial | Bancos ≥ base tras cada uno |
| **4. Datos, memoria y archivos** | Repo síncrono con `version`, puntos y logos. El historial pasa al checkpointer, primero con los mismos 16 mensajes de hoy; después `MEMORY_SUMMARIZE=1`. `files/` de Alan debajo de adjuntos. Prueba de concurrencia (2 usuarios a la vez; 2 pestañas del mismo usuario → 409) | Bancos de memoria y citas ≥ base |
| **5. Producto** | `crmRoutes` completas (CRUD, brief, siguiente-pregunta, importar, logo, puntos), React apuntando al repo nuevo, JWT de Carlos, routers de Carlos encendidos por grupos. QA privado por Tailscale con el repo nuevo | Pantalla revisada en video (escritorio y celular) + bancos |
| **6. Apagar el núcleo viejo** | El bucle viejo deja de usarse (se borra solo después de una semana estable). Opcionales medidos aparte: SSE en el chat, tarjetas de aprobación, `gpt-6-luna`, candado en Mongo para varios workers | Bancos ≥ base con todo encendido |

## 5. Riesgos y cómo se cubren

| Riesgo | Cobertura |
|---|---|
| El orden del bucle se rompe al repartirlo en hooks | Fase 2 con `BucleCRM` literal y prueba de reproducción con modelo falso |
| Lo que recuerda el modelo cambia con el checkpointer | Los mismos 16 mensajes primero; los avisos internos fuera; el resumen solo tras la compuerta |
| Llamadas extra escondidas (clasificador, verificador, bigtool) | `MODEL_CALL_LIMIT=7`, `ANSWER_VERIFY=0` y `USE_BIGTOOL=0`, más el contador de llamadas por mensaje en cada compuerta |
| Comparar con otro modelo | Se fija `gpt-4.1-mini` hasta la fase 6 |
| Varios workers y el candado en memoria | Un worker hasta tener el candado en Mongo |
| Perder algo en el traslado | Checklist de paridad generado del código; ninguna fase se cierra con filas vacías |
| Que el repo diverja del de Alan | Remoto `upstream`, núcleo intacto, el gancho propuesto a Alan |
| Big bang | El repo viejo sigue andando y el QA actual queda hasta la fase 5 |

## 6. Qué decide el usuario antes de empezar
1. Dónde vive el repo nuevo. Recomendado: un repo propio, por ejemplo `Astral910/crm-agente0`, con `upstream` = Alan. ¿O una rama en el de Alan?
2. Avisar a Alan del gancho `extra_middleware`, y a Carlos de que su backend entra completo, apagado al principio.
3. Arrancar la fase 0.

## 7. Reparto del trabajo
- **Composer 2.5:** lo mecánico (mover archivos y ajustar imports en la fase 1, portar pruebas), siempre en un worktree y con el diff revisado.
- **Grok 4.7:** segunda opinión en cada compuerta y casos nuevos de banco.
- **Claude:** el gancho del núcleo, `BucleCRM`, los middlewares, la prueba de reproducción, las mediciones y la revisión de todo antes de juntar.

## 8. Debate (fuentes)
`documentos/debate_nucleo/`: `PLANTEAMIENTO.md`, `composer.md`, `grok.md`.

El plan de Claude está resumido en este documento:
- `BucleCRM` primero.
- La `ContextVar`.
- Limpiar los avisos internos del historial.
- La prueba de reproducción.

Discrepancias resueltas:

| Tema | Claude | Composer | Grok | Decisión |
|---|---|---|---|---|
| Tope de llamadas | — | 3 | 7 | **7** (igual que hoy; lo normal siguen siendo 2–3) |
| Auth | Alan | Carlos | Carlos | **Carlos** |
| Tocar el núcleo | No hace falta | No | Un gancho | **Un gancho** (verificado: hoy no se puede sin él) |
| Historial | Esperar a la paridad | Checkpointer directo | Los mismos 16 mensajes primero | **Grok** |
| Backend de Carlos | Inventario por router | Mismo despliegue | Todo en el árbol, apagado | **Grok + inventario** (no se descarta nada) |

## 9. Verificado en código
- `JumpTo = Literal["tools", "model", "end"]` en `langchain/agents/middleware/types.py`. Lo vi en LangChain 1.3.4; Alan usa 1.4.6, así que hay que volver a verificarlo al instalar en la fase 1.
- `build_agent` arma la lista de middlewares fija; `AgentProfile` no tiene gancho para agregar.
- `MAX_VUELTAS = 7`, `MAX_CORRECCIONES = 2` y `MAX_ACCIONES = 12` en `backend/app/crm/agente.py`.
- En nuestro CRM, lo asíncrono vive en `repositorio`, `memoria`, `agente_diseno`, `diseno`, `reloj`, `web`, `agente`, `adaptador_lab`, `sembrar`, `responder_lab` y `primer_diseno`. La lógica de edición, registros, pantalla y cercos es síncrona.

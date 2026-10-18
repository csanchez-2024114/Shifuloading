# REFACTOR_PLAN: núcleo de agente + perfiles

Estado: **aprobado** (2026-10-17), con las decisiones de la sección 8.

- Fase 2: terminada (`cd42cc0`).
- Fase 3: terminada (`28bb3c8`…`0b68973`). Huella intacta; las constantes que cambiaron de módulo se leen con el mapa de reubicación (`MOVED_CONSTANTS` en `tests/test_caracterizacion.py`).
- Fase 4: terminada (`1c1b71e`…`b667f45`). JSON de la huella sin cambios; los valores que cambiaron de módulo se leen con el mapa de reubicación, y el test del multiconjunto lo comprueba contra `05773c4`.
- Fase 5: terminada (`6968647`…`3dfb595`). Perfiles `generic` y `tests/profiles/minimal`, y `docs/CREAR_PERFIL.md`. JSON de la huella sin cambios; solo el mapa de reubicación (reglas → `packs.lang.es_en`; `agent.EVIDENCE_TOOLS` → `core.agent:evidence_tools()`).
- Siguiente: Fase 6.
Rama `refactor/core-profiles`. Línea base: 269 tests en `main`; 346 con los de caracterización (commit `05773c4`).

Principio rector: **mover primero y cambiar después**. En la Fase 2, cada archivo se mueve 1:1 y su nombre viejo sigue apuntando al **mismo objeto de módulo**. Los cortes de los módulos mixtos (sacar textos, reglas y herramientas de dominio) llegan en las Fases 3 y 4, con la huella (`tests/snapshots/perfil_por_defecto.json`) como juez: con el perfil por defecto, el modelo, la UI y el cliente SSE deben recibir exactamente lo mismo.

---

## 1. Clasificación de módulos

**Núcleo** = cómo funciona un agente (bucle, topes, memoria, contexto, verificación, streaming, persistencia, cuentas), sin textos de un idioma ni herramientas de un caso de uso. **Pack** = pieza reutilizable que no es del núcleo (paquetes de herramientas o de idioma). **Perfil** = lo que define un caso de uso.

| Archivo actual | Clase | Qué es núcleo | Qué sale y adónde | Cómo se parte |
|---|---|---|---|---|
| `config.py` | mixto | `Settings`, `ConfigError`, `_num`/`_bool`, la ventana del modelo | `read_system_prompt()` (ruta fija `prompts/system.md`) → `profile.system_prompt_path`. Mensaje en español de `require_api_key` (`config.py:177-180`) → catálogo | F3: `read_system_prompt(profile)`; F4: el texto va al catálogo |
| `agent.py` | mixto (mayormente núcleo) | Toda la maquinaria: middleware, topes, aterrizaje, aborto, compactación, verificador, stream, historial. Prompts al modelo en inglés y genéricos (`SUMMARY_PROMPT`, `STRUCTURED_SUMMARY_PROMPT`, `VERIFY_ANSWER_PROMPT`, `CLASSIFIER_PROMPT`, `LAST_STEP_NOTE`, `SOFT_CAP_NOTE`…) | **Reglas:** `_CONTINUE_RE` (`agent.py:63`), `_SIGNAL_RE`/`_SIGNAL_WORDS`/`SHORT_MESSAGE_CHARS` (`agent.py:75-82`) → `profile.intents`. **Textos al usuario en español:** `LIMIT_MSG` (50), `CUT_NOTE` (56), `UNVERIFIED_NOTE` (634), `TURN_CAP_MSG` y el formato de miles (818-824), recursión (1072-1073), errores de `compact_thread` (543, 547) → catálogo. **Dominio:** `OLD_TOOL_NAMES` (252-255), los nombres de herramientas del perfil por defecto → `profile.legacy_tool_names`. El `interrupt_on` con `send_simulated_email`/`deep_research` (700-705) → `profile.tool_policies`. `EVIDENCE_TOOLS` (598) se deriva de las políticas (`evidence=True`) | F3 políticas y nombres antiguos; F4 textos y regex |
| `tools.py` | mixto | Biblioteca base de herramientas: `calculator`, `current_datetime`, `check_python_syntax`, `web_search` (+ presupuesto), `deep_research` (+ subagente), `save_memory`/`search_memories`/`update_memory` | `send_simulated_email` (234-239) → `profiles/default`. `build_tools` (631-646): la lista la decide el perfil. **Reglas:** `_RESEARCH_AGAIN` (415-416), `FOLLOW_UP_MAX_CHARS` (417), `_EXPLICIT_RESEARCH` (556-557) → `profile.intents`. **Texto:** `DEEP_RESEARCH_CONFIRM` (552) → catálogo | F3 email y lista; F4 regex y texto |
| `memory.py` | mixto | Store, checkpointer, arranque, procedencia, verificación, dedup, tope por turno, recall, `update`/`delete`, dos bases | `MEMORY_POLICIES` y `SEARCH_ECONOMY_RULE` (217-248) → `profile.memory_policies` (son reglas de qué guardar: caso de uso). **Léxico es/en** de la búsqueda por palabras: `_SUBJECT` (109), `_STOPWORDS` (403-412), `_TOPICS` (417-420), la heurística `_stem` → `packs/lang/es_en.py`, inyectado por el perfil. Mensajes de `ConfigError` en español (36-38, 49-63, 525-536) → catálogo | F3 políticas; F4 léxico y textos |
| `context.py` | núcleo | todo | — | se mueve tal cual |
| `citations.py` | mixto (casi núcleo) | Normalizar URLs, `keep_supported`, `enforce` | `_SOURCES_HEADING` (fuentes/sources/referencias…, 197-198) → `profile.intents`. Notas en español que llegan a la UI (238-239, 246, 258) y el `"Fuentes: "` reinsertado (257) → catálogo | F4 |
| `context.py`, `tool_spec.py` | núcleo | todo (`@tool_spec` es el framework de herramientas de apps) | — | tal cual |
| `auth.py` | mixto (casi núcleo) | argon2id, sesiones, CSRF, bloqueo | Mensajes en español (25-28) → catálogo | F4 |
| `ai_data.py`, `appdata/` | núcleo (plataforma) | repositorios y borrado | — | tal cual |
| `server.py` | mixto (casi núcleo) | Endpoints, SSE, keepalive, sesión, propiedad | Ruta fija `static/index.html` (208) → `profile.static_dir`. Detalles HTTP en español (159, 166, 173, 180, 255, 294, 331, 372, 386, 398) → catálogo. El `title="Agente 0"` de FastAPI (150) → `profile.display_name` | F3 ruta y nombre; F4 textos |
| `bigtool_agent.py` | mixto | El motor: índice, `retrieve_tools`, `PromptedModel`, `_seguro`, `RegistroTolerante`, `interrupt()` | El registro (217-221): `extra_tools()`, `crm_tools()`, `_herramientas_math/_texto` (demos) → los da el perfil. `BIGTOOL_PROMPT` menciona "math, text, web, memory, date, research" (55-61) → `profile.bigtool_prompt` (default idéntico) | F3 |
| `extra_tools.py` | pack | — | → `packs/tools/utilities.py`. Son genéricas (conversiones, fechas, finanzas, clima, Wikipedia), aunque algunas son de un contexto concreto (`validate_curp`, IVA 16%). Ver la pregunta Q3 | F3, 1:1 |
| `apps/crm_demo.py` | perfil | — | → `profiles/default/apps/crm_demo.py` | F3, 1:1 |
| `prompts/system.md` | perfil | — | → `profiles/default/prompts/system.md` | F3 (ver Q1) |
| `static/index.html` | mixto (caso especial) | La cáscara de chat es genérica y ya tiene respaldos para herramientas desconocidas ("usó X", "⚙️ Usando X…", `index.html:684`, `844-846`) | Textos de la UI en español, `TOOL_LABELS`/`TOOL_DONE`/`NOT_RUN` (707-740), `OLD_TOOL_NAMES` (701), y `toolOutputLabel`, que **traduce los mensajes en inglés del núcleo** | Esta tarea: se mueve **intacta** a `profiles/default/static/` (mismo sha256). Separar la cáscara de las etiquetas por perfil cambia el archivo: queda anotado como siguiente paso (ver Q2) |
| `scripts/*.py` | núcleo (plataforma) | migración y asignación de legado | — | se quedan en `scripts/`; importan `assistant.*`, que sigue funcionando |

Nota: `ESFUERZOS` usa las claves `bajo`/`medio`/`alto`, que son **identificadores del contrato** (campo `effort` del body de `/chat`, `level` del evento `effort`, `CONTRATO.md`), no textos. Se quedan como claves fijas del núcleo. El perfil puede cambiar los números y el razonamiento de cada nivel, no las claves.

---

## 2. Estructura propuesta y mapa viejo → nuevo

```
src/assistant/
├── __init__.py                 # instala los alias de compatibilidad (assistant.agent → assistant.core.agent, …)
├── _compat.py                  # buscador de alias (MetaPathFinder) + DeprecationWarning
├── core/                       # NO importa de packs/ ni de profiles/
│   ├── __init__.py
│   ├── config.py               ← config.py
│   ├── profile.py              # NUEVO: AgentProfile, ToolPolicy, IntentRules, TextCatalog, load_profile()
│   ├── agent.py                ← agent.py
│   ├── context.py              ← context.py
│   ├── citations.py            ← citations.py
│   ├── memory.py               ← memory.py
│   ├── tools.py                ← tools.py (biblioteca base de herramientas)
│   ├── tool_spec.py            ← tool_spec.py
│   ├── auth.py                 ← auth.py
│   ├── ai_data.py              ← ai_data.py
│   ├── appdata/                ← appdata/ (__init__, repos, mongo, memory)
│   ├── server.py               ← server.py
│   └── extensions/
│       ├── __init__.py
│       └── bigtool.py          ← bigtool_agent.py
├── packs/                      # reutilizable entre perfiles; importa solo de core/
│   ├── __init__.py
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── utilities.py        ← extra_tools.py (31 herramientas)
│   │   └── demo.py             ← _herramientas_math/_herramientas_texto de bigtool_agent.py (F3)
│   ├── lang/
│   │   ├── __init__.py
│   │   └── es_en.py            # F4: léxico de la búsqueda por palabras (_SUBJECT, _STOPWORDS, _TOPICS, _stem)
│   └── i18n/
│       ├── __init__.py
│       └── es.py               # F4: catálogo en español (los textos de hoy, literales)
└── profiles/                   # importa de core/ y packs/; nunca un perfil de otro
    ├── __init__.py
    ├── default/                # reproduce EXACTAMENTE el comportamiento actual
    │   ├── __init__.py         # PROFILE = AgentProfile(...)
    │   ├── prompts/system.md   ← prompts/system.md
    │   ├── static/index.html   ← static/index.html (sin cambios)
    │   ├── tools.py            # send_simulated_email (sale de tools.py) y la lista de herramientas
    │   ├── policies.py         # MEMORY_POLICIES, SEARCH_ECONOMY_RULE, tool_policies, legacy_tool_names
    │   ├── rules.py            # F4: los regex de intención actuales, idénticos
    │   └── apps/crm_demo.py    ← apps/crm_demo.py
    └── generic/                # F5: prompt neutro, solo herramientas base
        ├── __init__.py
        └── prompts/system.md
tests/
├── profiles/minimal/           # F5: tercer perfil de ejemplo (prompt y herramienta propios)
├── test_dependencias.py        # F3/F5: regla de imports
├── test_compat.py              # F2: los nombres viejos son el mismo módulo
└── test_perfiles.py            # F5: generic, minimal, error de perfil inexistente
```

Mapa viejo → nuevo (los nombres viejos siguen importando):

| Viejo | Nuevo | Fase |
|---|---|---|
| `assistant.config` | `assistant.core.config` | F2 |
| `assistant.context` | `assistant.core.context` | F2 |
| `assistant.citations` | `assistant.core.citations` | F2 |
| `assistant.tool_spec` | `assistant.core.tool_spec` | F2 |
| `assistant.memory` | `assistant.core.memory` | F2 |
| `assistant.ai_data` | `assistant.core.ai_data` | F2 |
| `assistant.appdata[.repos/.mongo/.memory]` | `assistant.core.appdata[...]` | F2 |
| `assistant.auth` | `assistant.core.auth` | F2 |
| `assistant.agent` | `assistant.core.agent` | F2 |
| `assistant.tools` | `assistant.core.tools` | F2 |
| `assistant.server` (y `uvicorn assistant.server:app`) | `assistant.core.server` | F2 |
| `assistant.bigtool_agent` | `assistant.core.extensions.bigtool` | F2 |
| `assistant.extra_tools` | `assistant.packs.tools.utilities` | F3 |
| `assistant.apps[.crm_demo]` | `assistant.profiles.default.apps[...]` | F3 |
| `prompts/system.md` | `src/assistant/profiles/default/prompts/system.md` | F3 (Q1) |
| `static/index.html` | `src/assistant/profiles/default/static/index.html` | F3 (Q1) |

---

## 3. Interfaz del perfil

```python
# core/profile.py
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal, Mapping
import re

Effect = Literal["read", "write", "send", "delete"]

@dataclass(frozen=True)
class ToolPolicy:
    effect: Effect = "read"
    # lo que hoy recibe HumanInTheLoopMiddleware(interrupt_on={name: ...}): False, True o un dict con
    # allowed_decisions/description/when. El perfil por defecto da lo mismo que agent.py:700-705.
    approval: bool | dict = False
    evidence: bool = False          # cuenta como evidencia para AnswerVerifier (hoy: web_search, deep_research)

@dataclass(frozen=True)
class IntentRules:
    """Reglas de intención que hoy son regex fijos en el código. Defaults = los patrones actuales (pack es_en)."""
    continue_request: re.Pattern            # agent._CONTINUE_RE
    explicit_research: re.Pattern           # tools._EXPLICIT_RESEARCH
    research_again: re.Pattern              # tools._RESEARCH_AGAIN
    follow_up_max_chars: int                # tools.FOLLOW_UP_MAX_CHARS (200)
    classifier_signal_re: re.Pattern        # agent._SIGNAL_RE
    classifier_signal_words: tuple[str, ...]  # agent._SIGNAL_WORDS
    short_message_chars: int                # agent.SHORT_MESSAGE_CHARS (60)
    sources_heading: re.Pattern             # citations._SOURCES_HEADING

@dataclass(frozen=True)
class MemoryLexicon:
    """Búsqueda por palabras y forma neutra de los recuerdos (memory.py:107-117, 391-451)."""
    subject_re: re.Pattern
    stopwords: frozenset[str]
    topics: Mapping[str, str]
    stem: Callable[[str], str]

class TextCatalog(Mapping[str, str]):
    """Textos al usuario y al modelo por clave ("user.limit", "user.cut_note", "http.login_required",
    "model.last_step_note"...). load_profile() valida que estén todas las claves que pide el núcleo (lista en
    core/profile.py: REQUIRED_TEXTS) y falla con la lista de las que faltan."""

@dataclass(frozen=True)
class EffortLevel:
    max_calls: int | None           # None = EFFORT_HIGH_MAX_CALLS (como hoy "alto")
    reasoning: str

@dataclass(frozen=True)
class AgentProfile:
    name: str
    display_name: str                                   # título de FastAPI ("Agente 0")
    system_prompt_path: Path                            # se relee en cada mensaje, como hoy
    build_tools: Callable[["BaseChatModel", "Settings", Callable], list["BaseTool"]]  # agente normal; recibe search_fn
    bigtool_tools: Callable[["Settings"], list["BaseTool"]] = lambda s: []  # extra del registro de bigtool
    bigtool_prompt: str | None = None                  # None = el del núcleo
    tool_policies: Mapping[str, ToolPolicy] = field(default_factory=dict)
    memory_policies: Mapping[str, str] = field(default_factory=dict)  # "strict"/"broad" -> texto del prompt
    search_economy_rule: str = ""
    texts: TextCatalog = ...
    intents: IntentRules = ...
    lexicon: MemoryLexicon = ...
    efforts: Mapping[str, EffortLevel] = ...            # claves fijas: bajo/medio/alto (contrato)
    legacy_tool_names: Mapping[str, str] = field(default_factory=dict)  # OLD_TOOL_NAMES
    static_dir: Path | None = None                      # carpeta de la UI; index.html dentro

def load_profile(name: str | None = None) -> AgentProfile:
    """AGENT_PROFILE (default "default"). Importa por nombre `assistant.profiles.<name>` (o una ruta con puntos
    para perfiles externos, p. ej. tests.profiles.minimal) y lee su PROFILE. Si no existe: ConfigError con los
    perfiles disponibles. Valida el catálogo y que cada política nombre una herramienta existente."""
```

Cómo llega el perfil al núcleo, sin cambiar las firmas que usan los tests:
- `create_app(agent=None, settings=None, ..., profile=None)`, `build_tools(model, settings, search_fn=..., checker=None, profile=None)` y `build_agent(..., profile=None)`: con `profile=None` se usa `load_profile()`, que con `AGENT_PROFILE` sin definir carga `default`. Así las llamadas de hoy (`build_agent(llm, tools, settings, ...)`) dan exactamente lo mismo.
- Las funciones con reglas (`necesita_clasificador`, `research_needs_confirmation`, `earlier_research`, `_continue_cut`, `drop_sources_section`, la búsqueda por palabras) reciben las reglas por parámetro con default = el perfil activo. Los tests de caracterización ya fijan su salida caso por caso.
- `AGENT_PROFILE` es la única variable de entorno nueva. Todas las demás se conservan con el mismo nombre y default (la huella guarda la lista de 57).

---

## 4. Regla de dependencias

- `assistant.core.*` no importa `assistant.packs` ni `assistant.profiles`.
- `assistant.packs.*` solo importa de `assistant.core`.
- `assistant.profiles.<x>` importa de `core` y `packs`, nunca de otro perfil.
- **Excepción documentada:** `core/profile.py:load_profile` importa el perfil **por nombre** con `importlib` (un string, no un import estático). Es la inversión de dependencias que permite el pivote.

**Test** `tests/test_dependencias.py`: recorre con `ast` todos los `.py` de `src/assistant/core/` y `src/assistant/packs/` y junta cada `Import`/`ImportFrom`, **también los imports dentro de funciones** (hoy hay varios perezosos, por ejemplo `agent.py:564`, `tools.py:324`). Falla si un módulo del núcleo nombra `assistant.packs`/`assistant.profiles`, si un pack nombra `assistant.profiles`, o si un perfil importa otro perfil. Detecta también `importlib.import_module("assistant.profiles...")` con un literal, salvo en `core/profile.py`. Al final de la Fase 3 entra en modo estricto; durante la Fase 2 el núcleo aún tiene dominio dentro (ver el orden de commits), así que el test entra con una lista blanca explícita que se vacía commit a commit.

---

## 5. Compatibilidad

- **Imports antiguos:** `assistant/__init__.py` instala un `MetaPathFinder` con el mapa viejo → nuevo. Al importar `assistant.agent`, el buscador devuelve **el mismo objeto de módulo** que `assistant.core.agent` (no una copia que reexporta). Esto importa por dos razones:
  1. Los tests hacen `monkeypatch.setattr(agent_mod, "ChatOpenAI", ...)`, `setattr(tools, "_ddg_search", ...)`, etc. Con una reexportación (`from assistant.core.tools import *`), el parche caería en la copia y el núcleo no lo vería.
  2. Las clases deben ser una sola: `DuplicateEmail`, `Context`, `TurnTokens`.

  Cubre también los submódulos (`assistant.appdata.mongo`). Emite `DeprecationWarning` una vez por nombre viejo.

  Lo probé en el scratchpad con un paquete de juguete: mismo objeto, parches visibles, submódulos con la misma clase y `importlib.reload` funcionando. Un detalle que salió en esa prueba: la maquinaria de import sobreescribe `__spec__` y `__package__` del módulo real con el nombre viejo, y eso rompería imports relativos perezosos. Por eso el loader guarda el `__spec__`, `__loader__` y `__package__` originales y los restaura en `exec_module`. `tests/test_compat.py` comprueba `assistant.agent is assistant.core.agent` para cada entrada del mapa.
- **`uvicorn assistant.server:app`** sigue igual: el alias resuelve al módulo del núcleo y el `__getattr__` perezoso de `app` sigue ahí.
- **Variables de entorno:** todas iguales; `AGENT_PROFILE` es nueva y opcional (default `default`).
- **Endpoints, eventos SSE y `CONTRATO.md`:** sin cambios de formato. Se verifica con la huella (`routes`, `sse`) y con un diff de `CONTRATO.md` al final.
- **Bigtool → `core/extensions/bigtool.py`.** Es un **motor de ejecución** alternativo (cómo se presentan las herramientas al modelo), no un caso de uso: cualquier perfil podría querer correr con él. Lo de dominio que tiene dentro (el registro con `extra_tools`, `crm_demo` y las demos de math y texto) sale al perfil por `bigtool_tools`. Dejarlo junto al núcleo mantiene visible la regla "un cambio en el agente normal suele necesitar su equivalente en bigtool". Moverlo a un perfil obligaría a cada perfil a duplicarlo.
- **Rutas de archivos:** `config.ROOT` hoy es `parents[2]` de `config.py` (`config.py:9`). Al bajar un nivel pasa a `parents[3]`. Es el **único** cambio de línea "no mecánico" de la Fase 2 y lo cubre la carga de `.env` (huella `config`). `read_system_prompt()` y `FileResponse` dejan de usar `ROOT` en la Fase 3 (las rutas vienen del perfil).
- **`OLD_TOOL_NAMES`** (nombres en español de hilos viejos) pasa al perfil por defecto, porque son los nombres de *sus* herramientas antiguas. Un perfil nuevo no hereda nada. La UI mantiene su propia copia (no cambia).

---

## 6. Riesgos, mitigación y orden de commits

| Riesgo | Mitigación |
|---|---|
| Alias que dejan dos copias de un módulo (parches que no llegan, clases distintas) | Alias por `MetaPathFinder` al mismo objeto + `test_compat.py` con `is` para cada nombre |
| Importaciones circulares (`tools` ↔ `agent`, imports perezosos) | Fase 2 es 1:1: el grafo de imports no cambia, solo los nombres; la suite completa en cada commit |
| `ROOT` y rutas (`.env`, `system.md`, `index.html`) | Un solo cambio (`parents[3]`) en el commit de `config`; la huella detecta un `.env` no cargado o un prompt distinto |
| Tests que leen archivos por ruta: 6 archivos leen `prompts/system.md` o `static/index.html` (`test_idioma`, `test_herramientas_caras`, `test_mejoras`, `test_nombres_antiguos`, `test_sintaxis`, `test_tiempos_ui`) | Ver Q1: actualizar solo la constante de ruta en esos tests (mismas aserciones), en el mismo commit del movimiento |
| Cambiar de lugar un texto cambia su clave en la huella (`constants`) | En la F4 la huella pasa a leer cada texto de su nuevo hogar con un mapa clave vieja → nueva. Un test compara que el **multiconjunto de valores** sea idéntico al de `05773c4`: cambian las direcciones, no los textos |
| La UI traduce los mensajes en inglés del núcleo (`toolOutputLabel`) | El catálogo de textos al modelo del perfil por defecto es literalmente el actual; `idioma::la_interfaz_muestra_los_mensajes_...` lo vigila. Queda anotado que un perfil que cambie esos mensajes rompe las etiquetas de la UI |
| Prompt releído en caliente | Se conserva: `system_prompt_path` se lee en cada mensaje |
| `langgraph._internal` y bigtool fijado a un commit | Sin cambios de versión; `tests/test_cierre_abortado.py` sigue de guardia |
| CRLF/OneDrive al mover con `git mv` | `git mv` (conserva el historial) y verificar el sha256 de `index.html`/`system.md` en la huella |

**Orden de commits** (suite en verde y mismo número de tests en cada uno; los nuevos se suman y se dicen en el mensaje):

- **Fase 0 (hecha)**
  1. ✅ `05773c4` Tests de caracterización y huella.
  2. Docs: `PARIDAD.md`, `REFACTOR_PLAN.md`, `REFACTOR_NOTAS.md`.
- **Fase 2: movimiento mecánico**
  3. Mecanismo de alias (`_compat.py`) + `test_compat.py`, con el mapa vacío.
  4. Mover `config`, `context`, `citations`, `tool_spec` → `core/` (incluye `ROOT` a `parents[3]`).
  5. Mover `memory`, `ai_data`, `appdata/`, `auth` → `core/`.
  6. Mover `agent`, `tools` → `core/`.
  7. Mover `server` → `core/`.
  8. Mover `bigtool_agent` → `core/extensions/bigtool.py`.
- **Fase 3: interfaz de perfil**
  9. `core/profile.py` (dataclasses + `load_profile`, error claro) y `profiles/default` armado con las piezas actuales en su sitio, sin moverlas todavía; los parámetros `profile=None` de `create_app`/`build_tools`/`build_agent`.
  10. `send_simulated_email`, la lista de herramientas, `tool_policies` (HITL y evidencia) y `legacy_tool_names` → perfil.
  11. `MEMORY_POLICIES`/`SEARCH_ECONOMY_RULE` → perfil.
  12. `extra_tools` → `packs/tools/utilities.py`; demos → `packs/tools/demo.py`; `crm_demo` → perfil; registro de bigtool desde el perfil.
  13. `system.md` e `index.html` → `profiles/default/` (según Q1) y rutas desde el perfil.
  14. `test_dependencias.py` en modo estricto, con la lista blanca vacía.
- **Fase 4: textos y reglas**
  15. Catálogo (`packs/i18n/es.py`) y claves en el núcleo; textos al usuario.
  16. Textos de HTTP, auth y arranque al catálogo.
  17. Reglas de intención → `IntentRules` (patrones idénticos).
  18. Léxico de memoria → `packs/lang/es_en.py`.
  19. Huella con el mapa de claves y el test de multiconjunto de valores.
- **Fase 5: prueba de pivote**
  20. `profiles/generic` + test de que arranca y responde con modelos falsos.
  21. `tests/profiles/minimal` (herramienta y prompt propios) + test.
  22. `docs/CREAR_PERFIL.md`.
- **Fase 6: verificación**
  23. `PARIDAD.md` marcado, diff de `CONTRATO.md`, README y CLAUDE.md actualizados.

Ninguna fase llama a la API real. Si en algún punto hiciera falta validar con el modelo real (no lo preveo: la huella garantiza que el modelo recibe lo mismo), me detengo y te paso el costo estimado antes.

---

## 7. A confirmar (necesito tu decisión)

- **Q1. Rutas de `prompts/system.md` y `static/index.html`.**
  - (a) *Recomendada:* moverlos a `profiles/default/` y, en el mismo commit, cambiar **solo la constante de ruta** en los 6 tests que los leen (mismas aserciones; ninguno se desactiva).
  - (b) Dejarlos en la raíz y que el perfil por defecto apunte ahí (cero cambios en tests, pero el perfil no queda autocontenido).

  Con cualquiera de las dos, README y CLAUDE.md dirán la ruta nueva.
- **Q2. La UI en esta tarea.**
  - *Recomendado:* `index.html` va **intacto** al perfil por defecto, y `generic` reutiliza esa misma UI (respaldos genéricos para herramientas desconocidas).
  - Separar la cáscara de las etiquetas por perfil (por ejemplo, un `labels.json` servido por el perfil) cambiaría el archivo y el sha256: lo propongo como tarea aparte. ¿De acuerdo?
- **Q3. `extra_tools.py`** (31 herramientas, algunas mexicanas como `validate_curp` o el IVA del 16%).
  - *Recomendado:* `packs/tools/utilities.py`, reutilizable por cualquier perfil.
  - Alternativa: `profiles/default/`, porque son una elección del caso de uso actual.
- **Q4. `check_python_syntax`.**
  - *Recomendado:* biblioteca base del núcleo (es una utilidad sin dominio), pero **no** incluida en `generic`, cuyo alcance definiste: calculator, current_datetime, web_search, memoria y deep_research.
  - ¿O prefieres que salga del núcleo a un pack?
- **Q5. Idioma de los textos del núcleo.**
  - *Recomendado:* el núcleo **no** trae textos por defecto en ningún idioma: declara las claves (`REQUIRED_TEXTS`) y el perfil debe darlas todas. `default` y `generic` usan `packs/i18n/es.py`. Los prompts al modelo en inglés (resumen, verificador, clasificador, notas de tope) sí quedan como defaults del núcleo, sobreescribibles, porque la regla del proyecto es que lo que lee el modelo va en inglés.
  - El único texto del núcleo fuera del catálogo sería el error "perfil inexistente", que sale antes de cargar cualquier perfil. ¿En español?
- **Q6. Defaults de configuración por perfil.** ¿Quieres que un perfil pueda fijar defaults propios de variables (por ejemplo `generic` con `TURN_TOKEN_CAP` más bajo)? *Recomendado:* **no en esta tarea**. Todas las variables y defaults siguen en `Settings`; anotado en `REFACTOR_NOTAS.md` como mejora.
- **Q7. Commits de documentación.** `AUDITORIA_AGENTE.md` (de la auditoría anterior) sigue sin trackear. ¿Lo commiteo en la rama junto con estos documentos o lo dejo fuera?
- **Q8. Reglas de CLAUDE.md.** Dicen "nunca ramas nuevas" y "sin commits hasta que se pidan". Entendí que esta tarea los pide expresamente (rama `refactor/core-profiles`, un commit por paso) y por eso ya creé la rama y un commit. Sigue sin haber push. Confírmame que es así.

---

## 8. Decisiones (2026-10-17)

| # | Decisión |
|---|---|
| Q1 | (a): `system.md` e `index.html` van a `profiles/default/`; en ese mismo commit, en los 6 tests que los leen, cambia solo la constante de ruta |
| Q2 | `index.html` va intacto al perfil por defecto y `generic` lo reutiliza; las etiquetas por perfil, en una tarea aparte |
| Q3 | `extra_tools.py` → `packs/tools/utilities.py` |
| Q4 | `check_python_syntax` se queda en `core/tools.py`, fuera de `generic`; anotado en `REFACTOR_NOTAS.md` como candidato a pack |
| Q5 | El núcleo no trae textos al usuario. `TextCatalog` = **base** (`packs/i18n/es.py`) + **sobreescrituras del perfil**; la validación de `REQUIRED_TEXTS` se hace sobre el catálogo **ya fusionado**. El error de perfil inexistente va en español |
| Q6 | No hay defaults de configuración por perfil |
| Q7 | La auditoría queda en `docs/AUDITORIA_AGENTE.md`, en un commit solo de docs (`52e661f`) |
| Q8 | Rama y commits sí; **ni push ni merge a `main`** |

Además:
- **`CONTRATO.md`** se corrige en un commit de docs aparte, **después de la Fase 6**, con los valores tomados del código.
- **Plan B del alias:** si el `MetaPathFinder` da problemas, shims de archivo (`sys.modules[__name__] = <módulo de core>`, y en paquetes también cada submódulo). `test_compat.py` no cambia, porque verifica el resultado y no el mecanismo.
- **`tests/test_compat.py`** entra en el primer commit de la Fase 2 con **3 tests de cantidad fija**: uno recorre el mapa completo. La suite pasa de 346 a **349** y no cambia en el resto de la Fase 2.
- **Imports internos:** en cada movimiento, los imports dentro de `src/` pasan al nombre nuevo (`assistant.core.*`). Los tests y los scripts siguen usando los nombres viejos, y así prueban la compatibilidad.

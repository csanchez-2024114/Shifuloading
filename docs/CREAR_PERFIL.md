# Crear un perfil

Un perfil define un caso de uso sobre el núcleo (`assistant.core`): el prompt, las herramientas, las aprobaciones, las políticas de memoria, los textos al usuario, las reglas de intención y la UI. El núcleo no se toca.

Se elige con la variable `AGENT_PROFILE`:

- un nombre sin puntos (`generic`) carga `assistant.profiles.<nombre>`;
- un nombre con puntos (`mi_paquete.mi_perfil`) se importa tal cual, también desde fuera del repositorio;
- vacía, se usa `default`.

Para empezar, hay dos perfiles que sirven de ejemplo:

- `src/assistant/profiles/generic/`: completo, un archivo y el prompt;
- `tests/profiles/minimal/`: el mínimo, con una herramienta propia.

## Pasos

1. **Crea el paquete** `src/assistant/profiles/<nombre>/__init__.py`. Para un perfil externo, cualquier paquete importable.
2. **Escribe el prompt** en `prompts/system.md`, **en inglés**: todo lo que lee el modelo va en inglés. Se relee en cada mensaje, así que no hace falta reiniciar. El núcleo le agrega la política de memoria y la fecha local.
3. **Elige las herramientas** con `build_tools(model, settings, base) -> list`:
   - `base` son las 8 del núcleo, en su orden: `web_search`, `calculator`, `current_datetime`, `check_python_syntax`, `save_memory`, `search_memories`, `update_memory` y `deep_research`;
   - puedes filtrarlas por `t.name` y agregar las tuyas (`@tool` de LangChain, con descripción en inglés).
4. **Define las políticas por herramienta** en `tool_policies: {nombre: ToolPolicy(...)}`:
   - `approval=True` muestra la tarjeta de aprobación;
   - para `deep_research`, usa `approval=research_approval()` (de `assistant.core.tools`) y `description_key="tools.deep_research_confirm"`;
   - `evidence=True` marca las herramientas cuyo resultado contrasta `ANSWER_VERIFY`;
   - `effect` es solo metadato por ahora.
5. **Escribe la política de memoria**, en inglés, en `memory_policies`. La clave `"strict"` es obligatoria, y `{max_per_turn}` se reemplaza por el tope. La regla opcional va en `search_economy_rule` (`MEMORY_SEARCH_ECONOMY`).
6. **Arma los textos al usuario** con `texts=TextCatalog(es.TEXTS, {clave: texto})`, que toma la base `assistant.packs.i18n.es` y le aplica tus sobreescrituras. El catálogo ya fusionado debe tener todas las claves de `REQUIRED_TEXTS` (`assistant.core.i18n`): si falta alguna, `load_profile` falla y la lista.
7. **Agrega el idioma, si lo quieres**:
   - `intents=es_en.INTENTS` y `lexicon=es_en.LEXICON`, de `assistant.packs.lang`;
   - sin ellos, el perfil usa reglas neutras: no reconoce "continúa" ni los pedidos de investigar, y la memoria por palabras no tiene raíz ni palabras vacías.
8. **Declara `PROFILE = AgentProfile(...)`** con:
   - `name` y `display_name` (el título de FastAPI);
   - `system_prompt_path`;
   - `static_dir=ui.STATIC_DIR` (`assistant.packs.ui`, la UI compartida);
   - lo de los pasos 3 a 7;
   - si renombras herramientas, `legacy_tool_names` y `bigtool_tools(settings)` (las extra del registro con `USE_BIGTOOL=1`).

   **Importa solo de `assistant.core` y `assistant.packs`, nunca de otro perfil.** Lo compartible va en `packs/`.
9. **Pruébalo con modelos falsos.** Copia `tests/test_perfil_generic.py` o `tests/test_perfil_minimo.py`: monkeypatch `AGENT_PROFILE`, `load_profile()`, `build_tools`/`build_agent` con `fake_llm`, y `/chat` y `/resume` con `TestClient`. `tests/test_dependencias.py` comprueba los imports de `profiles/` y de `tests/profiles/`. Para arrancarlo: `$env:AGENT_PROFILE="<nombre>"` y luego `uvicorn assistant.server:app`.

## Límites que hay que conocer

- **`load_profile` usa `importlib` por nombre.** Es la única excepción a la regla de dependencias: `core/profile.py` nombra el paquete `assistant.profiles` con un string, sin importarlo. El núcleo nunca importa un perfil.
- **Con `profile=None`, el núcleo carga el perfil activo**: el de `AGENT_PROFILE` y, si está vacía, `default`.
  - Pasar `profile=` a `build_agent`, `build_tools`, `create_app` o `system_prompt_text` no basta.
  - Algunas piezas no reciben el perfil y siempre leen el activo: las reglas de intención (continuar, investigar, el encabezado de fuentes), el léxico de la memoria y los textos de los avisos durante el turno.
  - Para probar un perfil, fija `AGENT_PROFILE`.
- **La confirmación de `deep_research` lee los nombres antiguos del perfil activo.** La tarjeta no sale si el hilo ya tiene una investigación anterior, y para buscarla el núcleo usa `legacy_tool_names` del perfil activo, no el que pasaste.
- **La UI traduce los mensajes en inglés del núcleo.** `packs/ui/index.html` reconoce por prefijo los resultados del tipo `Not run: …`, `Cancelled: …` y `User rejected the tool call`, y los convierte en las etiquetas en español de los chips. Un perfil que cambie esos textos (por ejemplo, desde una herramienta propia que los imite) rompe las etiquetas. Además, las herramientas nuevas se muestran con su nombre crudo, porque no están en `TOOL_LABELS`/`TOOL_DONE`. Para cambiar eso, el perfil tiene que traer su propia UI en `static_dir`.
- **El perfil debe completar `REQUIRED_TEXTS` o heredar la base.** Lo más simple es `TextCatalog(es.TEXTS, ...)`. Un catálogo propio sin base tiene que traer todas las claves.
- **Con `USE_BIGTOOL=1`, el registro siempre incluye las 8 herramientas base del núcleo** (también `check_python_syntax`), más `bigtool_tools(settings)`. `build_tools` no filtra ese registro.

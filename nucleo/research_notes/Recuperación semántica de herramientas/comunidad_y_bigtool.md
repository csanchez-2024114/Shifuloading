# Experiencia de la comunidad con langgraph-bigtool y agentes con "muchas herramientas" (tool RAG)

Fecha de la investigación: 2026-10-15. Notas en español; las citas textuales se mantienen en inglés.
Leyenda: **[medido]** = resultado con números y metodología declarada (a menudo de un proveedor interesado); **[anecdótico]** = informe individual sin medición; **[código]** = verificado leyendo el código fuente.

## 1. langgraph-bigtool: issues/discusiones en GitHub, problemas y workarounds

### Takeaway
Los issues abiertos de langgraph-bigtool reflejan sobre todo limitaciones de API (sin parámetro de prompt, sin herramientas "siempre disponibles", sin `state_schema`, roces con LangGraph Platform/MCP) y se resuelven con workarounds de la comunidad: mensaje de sistema en el input, `retrieve_tools_function` personalizado que añade IDs fijos, etc. Casi ninguno tiene respuesta del mantenedor después de mediados de 2025. La acumulación de `selected_tool_ids` es un comportamiento de diseño (reducer de solo-añadir) que se ve en el código, pero **no encontré ningún issue que lo reporte explícitamente**.

### Cited Findings
**Inventario de issues (API de GitHub, consultada el 2026-10-15)** — [lista de issues](https://api.github.com/repos/langchain-ai/langgraph-bigtool/issues?state=all&per_page=100)
- El repo tiene 33 issues/PR en total. Los issues de usuarios abiertos son #7, #11, #12, #13, #14, #15, #18, #19, #20, #21 y #30, y casi toda la actividad desde 2026 son PR de dependabot. — [Issues del repo](https://github.com/langchain-ai/langgraph-bigtool/issues)

**selected_tool_ids se acumula y nunca se limpia [código]**
- El estado se define como `class State(MessagesState): selected_tool_ids: Annotated[list[str], _add_new]` y el reducer hace `return left + [item for item in right if item not in set(left)]`. Es decir, solo añade IDs nuevos sin duplicar y no hay forma integrada de eliminarlos. Con un checkpointer, los IDs persisten durante todo el hilo y en cada turno se vinculan al modelo todas las herramientas recuperadas antes (`selected_tools = [tool_registry[id] for id in state["selected_tool_ids"]]`). — [graph.py](https://github.com/langchain-ai/langgraph-bigtool/blob/main/langgraph_bigtool/graph.py)
- DeepWiki lo resume así: "When new tools are identified, they are added to this list without duplicating existing entries." — [DeepWiki: Agent Creation with StateGraph](https://deepwiki.com/langchain-ai/langgraph-bigtool/2.1-agent-creation-with-stategraph)
- No encontré ningún issue, discusión ni post que reporte esto como problema ni que proponga un workaround concreto, como sobrescribir el reducer o resetear el estado. Ver Gaps.

**#7 "how to add system prompt?" (2025-03-07, abierto)**
- Respuesta de ccurme (colaborador de LangChain, 2025-03-10): "When invoking the agent, you can pass in a list of messages that includes a system message", con el ejemplo `{"role": "system", ...}` dentro de `messages`. `create_agent` no tiene parámetro `prompt`. — [Issue #7](https://github.com/langchain-ai/langgraph-bigtool/issues/7)
- La firma de `create_agent` solo acepta `llm, tool_registry, limit=2, filter, namespace_prefix=("tools",), retrieve_tools_function, retrieve_tools_coroutine` [código]. — [graph.py](https://github.com/langchain-ai/langgraph-bigtool/blob/main/langgraph_bigtool/graph.py)

**#11 "[Feature Request] Base (non-retrieval) tools" (2025-04-02, abierto)**
- La petición: "tools that are always accessible, without needing to use the retrieval tool." ccurme respondió "happy to review a design (or a PR if it's simple enough)!", pero no se llegó a implementar. — [Issue #11](https://github.com/langchain-ai/langgraph-bigtool/issues/11)
- Workaround de la comunidad (pongpeerakun, 2025-05-08): un `retrieve_tools_function` personalizado que siempre devuelve IDs fijos además de los recuperados: `return ["id_1", "id_2", *tool_ids]`. Ojo: las herramientas "base" solo quedan disponibles después de la primera llamada a `retrieve_tools`, no desde el primer turno. — [Issue #11](https://github.com/langchain-ai/langgraph-bigtool/issues/11)

**#18 "How can I inject custom state schema or config schema?" (2025-07-06, abierto, 0 respuestas)**
- Un usuario necesita herramientas con `InjectedState`/`InjectedToolArg` y señala: "I don't currently see a way to inject the state schema or config schema into the `create_agent` function, like is possible in `create_react_agent` and ... `create_supervisor`." No hubo respuesta. — [Issue #18](https://github.com/langchain-ai/langgraph-bigtool/issues/18)
- El `State` está fijado en el código (MessagesState + selected_tool_ids) [código]. Como `create_agent` devuelve un `StateGraph` sin compilar, en la práctica los usuarios añaden nodos propios. En #19 un usuario muestra `builder.add_node(...)` con subagentes y un `trim_messages_node`. — [graph.py](https://github.com/langchain-ai/langgraph-bigtool/blob/main/langgraph_bigtool/graph.py); [Issue #19](https://github.com/langchain-ai/langgraph-bigtool/issues/19)

**#19 Command/handoff a subagente ejecuta subagente y agente principal en paralelo (2025-08-27, abierto, 0 respuestas)**
- Al devolver `Command(goto=[Send(agent_name, ...)])` desde una herramienta, "it call the `subagent` and `main agent` parallely in the same step". Es coherente con que bigtool enruta las tool calls con `Send` y tiene un edge fijo `tools -> agent` [código]. — [Issue #19](https://github.com/langchain-ai/langgraph-bigtool/issues/19)

**#21 "Latest version of LangGraph not supported?" (2025-12-10, abierto)**
- Con langgraph 1.0.4 aparece el error `AttributeError: 'ToolNode' object has no attribute 'inject_tool_args'. Did you mean: '_inject_tool_args'?`. — [Issue #21](https://github.com/langchain-ai/langgraph-bigtool/issues/21)
- Comentario del 2026-03-13: "the maintainers haven't fixed it yet". El 2026-07-15: "They seemed to have fixed it 4 months ago ... But the last release was a little over a year ago". — [Issue #21](https://github.com/langchain-ai/langgraph-bigtool/issues/21)
- La corrección es el PR #25 (merge el 2026-03-31, de jkennedyvz): usa `getattr` para probar primero `_inject_tool_args` y caer en `inject_tool_args` si no existe. — [PR #25](https://github.com/langchain-ai/langgraph-bigtool/pull/25)
- PyPI solo tiene 0.0.1 (2025-03-04), 0.0.2 (2025-03-05) y 0.0.3 (2025-06-03). El arreglo para 1.x está en `main`, pero **no se ha publicado en PyPI**. El workaround práctico es instalar desde git o hacer un fork. — [PyPI JSON](https://pypi.org/pypi/langgraph-bigtool/json)

**#15 MCP: las herramientas no se recuperan bien (2025-05-18, abierto)**
- El usuario carga herramientas MCP con `load_mcp_tools`, las indexa en Supabase con embeddings `intfloat/e5-base-v2` y el LLM (gemini-2.0-flash) responde "The available tools do not allow me to interact with databases ... I can only retrieve tools based on a search query." Conclusión: "I have several tools in my mcp server but none of them is accessed by LLM". — [Issue #15](https://github.com/langchain-ai/langgraph-bigtool/issues/15)
- Respuesta de la comunidad (pongpeerakun): duda de que la búsqueda vectorial funcione ("I am not sure your vector search working properly") y propone usar `vecs` con `init_embeddings("openai:text-embedding-3-small")` y un `retrieve_tools_function` propio. **[anecdótico]**. El problema de fondo es la recuperación propia, no bigtool. — [Issue #15](https://github.com/langchain-ai/langgraph-bigtool/issues/15)

**#14 LangGraph Platform / InMemoryStore (2025-04-30, abierto)**
- Al desplegar el ejemplo del README en LangSmith self-hosted aparece el error: "Your graph ... includes a custom store (type InMemoryStore) ... persistence is handled automatically by the platform ... please remove the custom store". Otro usuario (2025-09-08): "I am facing the exact same error. Were you able to figure out a workaround?". No hubo respuesta oficial. — [Issue #14](https://github.com/langchain-ai/langgraph-bigtool/issues/14)
- Inferencia (no documentada en el issue): en Platform hay que quitar `store=` de `compile()`, configurar el índice semántico del store en `langgraph.json` e indexar las herramientas en el store de la plataforma, no en un InMemoryStore local.

**Otros**
- #12 (soporte JS/TS): la comunidad creó `bigtool-ts` (2026-01-19), compatible con LangGraph, Inngest AgentKit, Vercel AI SDK y Mastra. — [Issue #12](https://github.com/langchain-ai/langgraph-bigtool/issues/12)
- #20 (2025-11-29, austinmw): "with LangChain v1, would it make sense to create a new built-in tool which functions as a tool search tool? Not sure if this would require a built-in middleware". Sin respuesta. — [Issue #20](https://github.com/langchain-ai/langgraph-bigtool/issues/20)
- #6: el README añadió "related work" (Toolshed, Graph RAG-Tool Fusion, ToolRet) a propuesta de EliasLumer. — [Issue #6](https://github.com/langchain-ai/langgraph-bigtool/issues/6)
- En el foro de LangChain, un usuario probó un "fail-closed guard" antes de `langgraph_bigtool.create_agent()` porque "its API exposes a natural tool registry boundary" (2026-06). — [Foro LangChain](https://forum.langchain.com/t/feedback-wanted-automatic-fail-closed-guard-before-langgraph-bigtool-create-agent/4053)

### Inferences
- **Patrones de workaround** que aparecen o se deducen: (a) un `retrieve_tools_function` propio que inyecta IDs "base" y permite filtros o lógica propia; (b) `filter` y `namespace_prefix` del store para particionar por app o tenant; (c) mensaje de sistema en el input; (d) instalar desde `main`/fork para langgraph 1.x; (e) añadir nodos al `StateGraph` devuelto. Ninguno resuelve la acumulación de `selected_tool_ids`. Para eso harían falta un fork con otro reducer (por ejemplo, reemplazar en lugar de añadir, o un tope de N) o actualizar el estado con `graph.update_state` entre turnos. Esto último es inferencia mía, no lo encontré documentado.
- El patrón de respuestas (ccurme activo en marzo-abril de 2025; desde entonces casi solo mantenimiento de dependencias) sugiere que el paquete está en modo mantenimiento mínimo.

### Gaps
- No encontré ningún issue ni post que trate explícitamente la acumulación de `selected_tool_ids` ni workarounds publicados para ella.
- No pude leer los comentarios de la discusión langgraph #2057 (how-to "many tools"): la página devolvió 404 sin autenticación. Según un resumen de búsqueda, se habla de un bucle de reintento que vuelve a `select_tools` tras un error de herramienta, pero no lo he verificado. — [Discussion #2057](https://github.com/langchain-ai/langgraph/discussions/2057)

## 2. Foros de LangChain y discusiones: "too many tools", herramientas dinámicas, alternativas a bigtool

### Takeaway
En el foro oficial, los "LangChain Expert" y el equipo de LangChain recomiendan para v1 middleware (`wrap_model_call` filtrando `request.tools`, `LLMToolSelectorMiddleware`) o el patrón clásico de "handle large numbers of tools" (vector DB + `select_tools`). No recomiendan bigtool explícitamente. LangChain v1 ya incluye dos alternativas nativas: `LLMToolSelectorMiddleware` y `ProviderToolSearchMiddleware`.

### Cited Findings
- **Recuperación con dependencias** (foro, 2026-01-16). La pregunta: "There are lots of tools, so i retrieval tools for each query, but some query need two or more tools (dependency)". pawel-twardziak (LangChain Expert) respondió: indexar las descripciones en una vector DB ("How to handle large numbers of tools - it's a legacy doc, but in general the idea is still valid in Langchain v1"), añadir metadatos `requires=["tool_b","tool_c"]` y expandir dependencias de forma determinista, permitir un bucle "reselect_tools" cuando una herramienta dice que necesita X, y usar "composite tools" para cadenas estables. — [Foro LangChain #2736](https://forum.langchain.com/t/how-to-retrieval-tools-when-some-tools-have-dependency/2736)
- **Listas dinámicas con create_agent** (2025-10-24). La solución de la comunidad: registrar todas las herramientas por adelantado y filtrar `request.tools` en un `AgentMiddleware.wrap_model_call` según estado o contexto (patrón "Claude Skills"). — [Foro LangChain #1920](https://forum.langchain.com/t/are-dynamic-tool-lists-allowed-when-using-create-agent/1920)
- **Propuesta de carga dinámica para MCP** (2025-12-16): "Connecting 5 MCP servers can consume 50,000+ tokens (~40% of context window)" e "Increased tool count paradoxically degrades response quality and speed". Otro usuario propone las meta-herramientas `list_inactive_tools`/`activate_tool`. pawel-twardziak: "something many devs actually ask for as an idiomatic feature of Langchain". **[anecdótico]** — [Foro LangChain #2526](https://forum.langchain.com/t/proposal-for-dynamic-tool-loading-mechanism-in-langchain-mcp-integration/2526)
- **Bind dinámico en ToolNode** (2026-07-15). pawel-twardziak (LangChain Expert): "ToolNode is a name-indexed dispatcher, not a model binding ... every other registered tool is inert and costs nothing", y recomienda registrar todo el registro en el ToolNode y limitar solo lo que se vincula al modelo. dariel.datoon (LangChain Team) propone que el planner emita tool calls estructuradas. — [Foro LangChain #4163](https://forum.langchain.com/t/how-to-dynamically-bind-a-tool-to-the-toolnode/4163)
- **Heurística de un experto** (2026-10-12), keenborder786 (LangChain Expert): "In my experience, keeping the number of tools around 5–6 can be a good starting point." **[anecdótico]** — [Foro LangChain #4731](https://forum.langchain.com/t/agent-passes-wrong-data-for-the-tool/4731)
- **LLMToolSelectorMiddleware** (LangChain v1, "Since v1.0"): usa un LLM (puede ser uno más barato) para filtrar herramientas antes de la llamada principal, con `max_tools`, `always_include` (no cuenta contra `max_tools`) y `system_prompt`. Es la respuesta nativa al "base tools" de bigtool #11. — [Referencia LLMToolSelectorMiddleware](https://reference.langchain.com/python/langchain/agents/middleware/tool_selection/LLMToolSelectorMiddleware); [Prebuilt middleware docs](https://docs.langchain.com/oss/python/langchain/middleware/built-in)
- **ProviderToolSearchMiddleware**: marca herramientas con `extras["defer_loading"]` e inyecta la tool search del proveedor en el servidor. Solo funciona con Anthropic y OpenAI, y lanza `ValueError` si el proveedor no la soporta. — [Referencia ProviderToolSearchMiddleware](https://reference.langchain.com/python/langchain/agents/middleware/provider_tool_search/ProviderToolSearchMiddleware)
- Las docs de Tools de LangChain advierten que demasiadas herramientas saturan el contexto y aumentan los errores, y describen dos enfoques: filtrar herramientas pre-registradas según estado, permisos o contexto, o registrarlas en tiempo de ejecución. — [Docs LangChain Tools](https://docs.langchain.com/oss/python/langchain/tools)

### Inferences
- Para un proyecto nuevo en LangChain/LangGraph v1, la ruta que el ecosistema empuja es middleware: `wrap_model_call` con recuperación semántica propia, `LLMToolSelectorMiddleware` o `ProviderToolSearchMiddleware`, no `langgraph-bigtool`. bigtool sigue sirviendo como referencia de diseño (store + `retrieve_tools`).

### Gaps
- No encontré ningún comentario explícito de staff de LangChain que declare bigtool "deprecated" o "no recomendado". La conclusión se basa en la actividad del repo y en la existencia de middleware nativo.

## 3. Reddit / Hacker News: experiencias con 100+ / 1000+ herramientas, sobrecarga MCP y colisiones de nombres

### Takeaway
No pude acceder a Reddit: la API devolvió respuestas no-JSON (bloqueo) y las búsquedas web no devolvieron hilos. En HN, el hilo "Claude Advanced Tool Use" (673 puntos, 266 comentarios) muestra opiniones divididas: algunos ya hacían "tool search" a mano, otros temen la opacidad para depurar, y otros prefieren menos herramientas y más CLI o skills. Las colisiones entre herramientas de nombre parecido están bien documentadas en issues de GitHub de varios clientes MCP. El consenso es prefijar por servidor o app y fallar de forma explícita ante duplicados.

### Cited Findings
**Hacker News — "Claude Advanced Tool Use" (2025-11-24)** — [HN 46038047](https://news.ycombinator.com/item?id=46038047). Todo **[anecdótico]**.
- michaelanckaert: "I did something similar with a couple of agents I wrote. First LLM Call: only pass the 'search tool' tool ... Second LLM Call: pass the additional tools that were returned". — [comentario](https://news.ycombinator.com/item?id=46039171)
- dalemhurley: "Tool search is formalising what a lot of teams have been working towards. I had previously called it tool caller ... when the domain was mentioned, the tools for the domain would be loaded" (enrutamiento en dos pasos por dominio o app). — [comentario](https://news.ycombinator.com/item?id=46043715)
- RobertDeNiro: "Since this tool search feature is completely opaque, the wrong tool might not get selected. Then you'll have to figure out if it was the search". — [comentario](https://news.ycombinator.com/item?id=46039293)
- jameslk: "you run into the problem of having many tools that can accomplish the same task ... tool makers start to abuse Tool Engine Optimization". — [comentario](https://news.ycombinator.com/item?id=46038932)
- morelandjs: "with MCP we moved away from [RAG] and instead dumped all the tool descriptions into the context ... it turned out this was way better and more accurate. Now ... flooded with too many tool descriptions." — [comentario](https://news.ycombinator.com/item?id=46039648)
- noodletheworld: si el agente no conoce las herramientas al planificar, "might end up solving a problem naively step-by-step using primitive operations, when a single tool already exists". Es un riesgo propio del tool RAG. — [comentario](https://news.ycombinator.com/item?id=46042957)
- jmward01 y ra prefieren menos herramientas y mejores definiciones o skills ("you could get by with ShellTool"). — [jmward01](https://news.ycombinator.com/item?id=46039238); [ra](https://news.ycombinator.com/item?id=46040731)
- slimslenders apunta al Docker MCP Gateway con "dynamic MCPs" como implementación agnóstica del modelo. — [comentario](https://news.ycombinator.com/item?id=46050398)
- tasoeur (2026-09): "I've been bitten by the usual suspects: too many tools will cause context windows to grow quick". — [HN 49559951](https://news.ycombinator.com/item?id=49559951)

**Colisiones de nombres y namespacing** (issues de GitHub, 2025–2026)
- langchainjs mcp-adapters: los nombres duplicados entre servidores se devolvían tal cual y las llamadas iban a la primera herramienta registrada. El PR hace que falle con error y sugiere prefijo opcional. — [langchainjs PR #11759](https://github.com/langchain-ai/langchainjs/pull/11759)
- deepagents: "MCP-prefixed tool names can collide with MCP and built-in tools". — [deepagents #4666](https://github.com/langchain-ai/deepagents/issues/4666)
- LM Studio envía al modelo nombres sin prefijo de servidor, así que dos `search_code` son indistinguibles. — [lmstudio #2445](https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/2445)
- OpenAI Agents JS: `search-a` y `search_a` colisionaban tras normalizar. — [openai-agents-js PR #1935](https://github.com/openai/openai-agents-js/pull/1935)
- Tres herramientas `create_issue` (GitHub/GitLab) en la misma sesión se señalan como riesgo de selección errónea, con la recomendación de nombres con prefijo de servicio (`github_create_issue`). — [mcp-github-pr-issue-analyser #406](https://github.com/saidsef/mcp-github-pr-issue-analyser/issues/406)
- Hasta los esquemas de prefijo pueden colisionar si no son inyectivos. — [nodal-agents #661](https://github.com/Kwintspiracy/nodal-agents/issues/661)
- Seguridad: "MCP spec has no mandatory namespacing", lo que permite que un servidor malicioso suplante el nombre de una herramienta de confianza. — [vulnerablemcp.info](https://vulnerablemcp.info/vuln/tool-name-collisions.html)
- Anthropic: "The most common failures are wrong tool selection and incorrect parameters, especially when tools have similar names", con el ejemplo `notification-send-user` vs `notification-send-channel`. — [Anthropic Engineering](https://www.anthropic.com/engineering/advanced-tool-use)
- Arcade (4.027 herramientas): para "Youtube_SearchVideos" la búsqueda devolvió "Youtube_SearchForVideos" ("Close, but no cigar"). Arcade usa la convención `App_Action` (Gmail_SendEmail, Slack_SendMessage). — [Arcade blog](https://arcade.dev/blog/anthropic-tool-search-4000-tools-test)

**Límites de los clientes**: Cursor tiene un máximo aproximado de 40 herramientas y la API de OpenAI unas 128 funciones, según un post secundario sin verificar. — [DEV: MCP proxy pattern](https://dev.to/algis/mcp-proxy-pattern-secure-retrieval-first-tool-routing-for-agents-247c)

### Inferences
- Patrón recomendado para colisiones entre apps: nombre canónico `app__accion` o `App_Accion` en el índice y en el binding, filtro por app o namespace (enrutamiento en dos pasos: primero la app y después la herramienta dentro de su namespace), y error explícito ante duplicados. bigtool lo permite vía `namespace_prefix`/`filter` del store, aunque el `filter` es estático por agente salvo que se use un `retrieve_tools_function` propio.

### Gaps
- **Reddit: sin datos.** reddit.com bloqueó la API JSON sin autenticación y WebSearch no devolvió hilos de r/LangChain, r/LocalLLaMA, r/AI_Agents ni r/mcp. Habría que buscarlos a mano.
- No encontré hilos de HN que mencionen langgraph-bigtool explícitamente.

## 4. Blogs y casos con números: precisión vs. número de herramientas

### Takeaway
Hay bastantes números, pero casi todos vienen de proveedores con interés comercial (Anthropic, Redis, Stacklok, Arcade) o de un paper pequeño (RAG-MCP). Coinciden en que cargar todas las herramientas degrada precisión y coste, y en que la recuperación ayuda mucho. También muestran que **la calidad de la recuperación es el cuello de botella**: con miles de herramientas, BM25/regex encuentra la herramienta correcta en solo el 34–64 % de los casos según el test.

### Cited Findings
- **Anthropic** (2025-11-24) **[medido, proveedor; datasets no públicos]**: "58 tools consuming approximately 55K tokens before the conversation even starts" y "we've seen tool definitions consume 134K tokens before optimization". Con Tool Search Tool, unos 8,7K tokens ("85% reduction"). Sobre la precisión en MCP evals: "Opus 4 improved from 49% to 74%, and Opus 4.5 improved from 79.5% to 88.1%". Lo recomiendan con más de 10 herramientas o más de 10K tokens de definiciones, y no cuando todas las herramientas se usan en cada sesión. — [Anthropic Engineering: Advanced tool use](https://www.anthropic.com/engineering/advanced-tool-use)
- **Arcade** (Eric Gustin, 2025-12-03) **[medido, n=25 tareas, proveedor]**: con 4.027 herramientas en la Tool Search de Anthropic, la herramienta correcta aparece en el top-K en el 56 % de los casos con regex (14/25) y en el 64 % con BM25 (16/25). Se midió solo la recuperación, no la selección. Fallos: Gmail_SendEmail para "send an email" y Slack_SendMessage para "post a message to Slack". Conclusión: "not ready for prime time" para agentes con acciones reales, aunque "the token savings are real". — [Arcade blog](https://arcade.dev/blog/anthropic-tool-search-4000-tools-test)
- **Stacklok** (2025-12-10) **[medido, proveedor comparando su producto]**: con 2.792 herramientas (dataset MCP-tools), una consulta sintética por herramienta y Claude Sonnet 4.5, MCP Optimizer (búsqueda híbrida/semántica) obtuvo 98,03 % de recuperación y 93,95 % de selección. Tool Search de Anthropic obtuvo 47,85 % / 33,70 % con BM25 y 39,00 % / 30,01 % con regex. Cita clave: "if the correct tool doesn't appear in the search results, even the best model cannot select it." — [DEV/Stacklok](https://dev.to/stacklok/stackloks-mcp-optimizer-vs-anthropics-tool-search-tool-a-head-to-head-comparison-2f32)
- **Redis** (2025-12-09, actualizado 2026-06-01) **[medido, proveedor; sin metodología detallada]**: cuatro servidores MCP (Redis 44, GitHub 40, Jira 27, Grafana 56) suman 167 herramientas y unos 60K tokens. En un agente de soporte, el filtrado vectorial o híbrido con top-K de 3–5 bajó los tokens de ~23k a ~0,4k, la latencia de ~3,4 s a ~0,4 s y subió la precisión de selección de ~42 % a ~85 %. Sobre K: "Too few risks missing the right tool. Too many brings back the overload problem. Most deployments find 3-5 optimal". También critican la navegación jerárquica (zendesk → tickets → search_tickets) porque "users describe problems, not paths". — [Redis blog](https://redis.io/blog/from-reasoning-to-retrieval-solving-the-mcp-tool-overload-problem/)
- **RAG-MCP** (Gan y Sun, arXiv, 2025-05-06) **[medido, académico]**: precisión de selección del 43,13 % con RAG-MCP frente al 13,62 % del baseline con todas las herramientas, y más de un 50 % menos de tokens de prompt. — [arXiv 2505.03275](https://arxiv.org/abs/2505.03275)
- **LangChain** (2025-03): bigtool es "reliable enough to work w/ local models (via @ollama) w/ > 50 tools". **[afirmación de marketing, sin métricas]** — [LangChain en X](https://x.com/LangChainAI/status/1905302614218305891)
- **Composio Tool Router**: meta-herramientas de búsqueda, planificación, autenticación y ejecución sobre "1000+" herramientas. No encontré métricas publicadas de precisión. — [Composio docs](https://docs.composio.dev/tool-router/overview)
- Umbrales "40–50 herramientas" y similares aparecen en posts secundarios (DEV, getunblocked, jenova) sin fuente primaria verificable. — [DEV merlonix](https://dev.to/merlonix/how-many-mcp-tools-is-too-many-tool-count-selection-overload-7gc); [getunblocked](https://getunblocked.com/blog/mcp-tool-overload/)

### Inferences
- Lección práctica: el método de recuperación importa más que el patrón agéntico. Embeddings o búsqueda híbrida sobre nombre, descripción y parámetros, con top-K de 3–5 y enriquecimiento de descripciones con sinónimos ("send/post", "ticket/task"), superan claramente a BM25/regex en catálogos de miles de herramientas. Esto apoya el uso del store semántico de LangGraph (como bigtool) o de un vector DB propio frente al keyword search.
- Conviene evaluar por separado la **recuperación** (¿está la herramienta correcta en el top-K?) y la **selección** (¿la elige el LLM?), como hacen Arcade y Stacklok.

### Gaps
- No hay benchmarks independientes (no de proveedor) que repliquen estos números a escala de miles de herramientas. Las cifras de Anthropic no son reproducibles (datasets no públicos, según Stacklok).
- No encontré números específicos de Zapier ni Toolhouse.

## 5. ¿Está langgraph-bigtool mantenido o recomendado en 2025–2026?

### Takeaway
Está en **mantenimiento mínimo**. La última versión en PyPI es la 0.0.3 (2025-06-03), y desde entonces los commits son casi todos bumps de dependabot que mergea un empleado (John Kennedy), más el arreglo de compatibilidad con 1.x (#25), que no se ha publicado. Los issues de funcionalidad (#11, #18, #19, #20) no tienen respuesta del equipo. LangChain apunta hoy al middleware de v1 (`LLMToolSelectorMiddleware`, `ProviderToolSearchMiddleware`, `wrap_model_call`) como vía para gestionar muchas herramientas.

### Cited Findings
- Versiones en PyPI: 0.0.1 (2025-03-04), 0.0.2 (2025-03-05) y 0.0.3 (2025-06-03), sin versiones posteriores. — [PyPI](https://pypi.org/project/langgraph-bigtool/)
- Commits de 2026: arreglo de compatibilidad con langgraph 1.x (PR #25, 2026-03-31), "fix: update typing-extensions to 4.15.0 for py3.10 compat" (2026-06-28) y PR de dependabot (anyio, urllib3, langchain 1.3.9, etc.) hasta octubre de 2026. — [Commits](https://github.com/langchain-ai/langgraph-bigtool/commits/main); [PR #25](https://github.com/langchain-ai/langgraph-bigtool/pull/25)
- Un usuario en #21 (2026-07-15): "the last release was a little over a year ago". — [Issue #21](https://github.com/langchain-ai/langgraph-bigtool/issues/21)
- Petición de un "tool search tool" nativo en v1 (#20, 2025-11-29) sin respuesta en el repo. LangChain sí incluye ahora `ProviderToolSearchMiddleware` y `LLMToolSelectorMiddleware`. — [Issue #20](https://github.com/langchain-ai/langgraph-bigtool/issues/20); [ProviderToolSearchMiddleware](https://reference.langchain.com/python/langchain/agents/middleware/provider_tool_search/ProviderToolSearchMiddleware); [LLMToolSelectorMiddleware](https://reference.langchain.com/python/langchain/agents/middleware/tool_selection/LLMToolSelectorMiddleware)
- Un LangChain Expert en el foro (2026-01) remite al doc "How to handle large numbers of tools" ("legacy doc, but ... still valid in Langchain v1"), no a bigtool. — [Foro LangChain #2736](https://forum.langchain.com/t/how-to-retrieval-tools-when-some-tools-have-dependency/2736)

### Inferences
- Para producción en 2026: usar bigtool desde `main` o un fork, o, preferiblemente, reimplementar su patrón (store con índice semántico + herramienta `retrieve_tools` + tope o reset de herramientas activas) como middleware de `create_agent` v1. Así se resuelven de golpe #7 (prompt), #11 (`always_include`), #18 (`state_schema`/`context_schema` nativos de create_agent) y la acumulación de `selected_tool_ids`.

### Gaps
- No encontré ninguna declaración oficial de LangChain que marque bigtool como deprecated, ni una que lo recomiende explícitamente en 2025–2026.

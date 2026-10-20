# Qué indexar y cómo redactar y enriquecer las descripciones de herramientas para la recuperación semántica

Contexto: ~4.500 herramientas (30 apps × 150 funciones), muchas con nombres casi iguales entre apps (create_item, list_items...). Hoy langgraph-bigtool indexa "name: description" con text-embedding-3-small y top-k=3.

## 1. Qué campos indexar: ¿un documento concatenado o varios vectores por herramienta?

### Takeaway
La evidencia más fuerte apoya un documento enriquecido por herramienta, embebido como un solo vector o como varias copias aumentadas cuyas puntuaciones se promedian. Debe incluir: nombre legible (con espacios), descripción, esquema de argumentos con nombres y descripciones claros, preguntas sintéticas y temas o intenciones clave. Qué campo aporta más depende del dataset, así que hay que validarlo con un pequeño conjunto "golden" propio. Los ejemplos de uso con llamadas API (example_usage) no ayudan e incluso perjudican.

### Cited Findings
- Toolshed (Lumer et al., PwC, ICAART 2025) concatena 5 componentes en un único vector por herramienta: 1) nombre, 2) descripción, 3) esquema de argumentos (parámetros y su descripción), 4) preguntas hipotéticas sintéticas y 5) temas o intenciones clave sintéticos. Guarda además un diccionario de metadatos que mapea el documento al nombre real de la función en código. — [Toolshed, arXiv 2410.14594](https://arxiv.org/abs/2410.14594)
- Toolshed convierte el nombre a una "versión embebible" con espacios ("GetRecord" pasa a "Get Record"), porque los nombres de función de OpenAI no admiten espacios. Recomienda que cada nombre sea único y que las herramientas no se solapen. — [Toolshed](https://arxiv.org/abs/2410.14594)
- Buenas prácticas de indexación de Toolshed, textuales en lo esencial:
  - (2) La descripción debe ser "larga, de alta calidad y descriptiva (como cuándo usar la herramienta y cuándo no)".
  - (3) Añadir el esquema de argumentos "puede ayudar", siempre con nombres y descripciones de parámetros claros y sin abreviaturas.
  - (4) Las preguntas sintéticas deben ser diversas, imitar las preguntas futuras de los usuarios y usar los parámetros.
  - (5) Los temas clave se generan a partir del nombre, la descripción y las preguntas sintéticas.

  — [Toolshed](https://arxiv.org/abs/2410.14594)
- Ablación de Toolshed (Apéndice I, Seal-Tools con ~4.000 herramientas, embedders text-embedding-3-large, text-embedding-3-small y ada-002):
  - Se probaron 6 configuraciones: nombre+descripción; +esquema; +1 query; +esquema+1 query; +2 queries; +esquema+2 queries.
  - Tendencia general: "cuanto más enriquecido el documento, mayor la precisión de recuperación".
  - En Seal-Tools "el esquema de argumentos fue un elemento crítico, mientras que las preguntas hipotéticas no añadieron mucho valor". En ToolE, en cambio, "las preguntas hipotéticas fueron críticas".
  - Los autores recomiendan probar configuraciones sobre un golden dataset pequeño propio.

  — [Toolshed](https://arxiv.org/abs/2410.14594)
- Resultado global de Toolshed (pipeline completo con enriquecimiento, reescritura y descomposición de la query y reranking; GPT-4o + text-embedding-3-large):
  - Mejoras absolutas de Recall@5 de 46%, 56% y 47% en ToolE single-tool, ToolE multi-tool y Seal-Tools.
  - Frente a Re-Invoke: +5 puntos en ToolE single-tool y +9 en multi-tool. Frente al retriever de Seal-Tools: +41.

  Ojo: es el ensemble completo, no solo el enriquecimiento del documento. — [Toolshed](https://arxiv.org/abs/2410.14594)
- Re-Invoke (Google, Findings EMNLP 2024) usa varios vectores por herramienta:
  - Genera 10 queries sintéticas por herramienta (text-bison, temperatura 0.7).
  - Crea 10 copias del documento con el formato "Documentation: <tool document> Query: <predicted query>".
  - Promedia las similitudes de las copias (agregación mean).
  - Probaron anteponer, añadir al final y repetir: "rinden similar".

  — [Re-Invoke, arXiv 2408.01875](https://arxiv.org/abs/2408.01875)
- Agregación en Re-Invoke (nDCG@5, solo generador de queries, ToolE single/multi): mean 0.7813/0.6906 frente a max 0.7716/0.6333. El promedio supera al máximo en los 5 datasets. — [Re-Invoke](https://arxiv.org/abs/2408.01875)
- Tool-DE (oct 2025) define un tool_profile estructurado con estos campos:
  - function_description (menos de 20 palabras)
  - tags (3-5 palabras clave)
  - when_to_use (opcional)
  - limitations (opcional)
  - example_usage (hasta 2 pares query/llamada)

  Para recuperar solo se usan function_description, when_to_use, limitations y tags; example_usage se excluye. — [Tool-DE, arXiv 2510.22670](https://arxiv.org/html/2510.22670)
- Ablación por campos de Tool-DE (GritLM y BM25s; resultados direccionales, sin tabla numérica en texto):
  - Quitar example_usage sube nDCG@10, y es el campo con menor ganancia, a menudo negativa.
  - function_description y tags son neutros o positivos, y quitarlos causa "caídas notables".
  - Inconsistencia interna: una sección dice que quitar when_to_use mejora el rendimiento y otra lo mantiene.

  — [Tool-DE](https://arxiv.org/html/2510.22670)
- Tool2Vec propone embeber la herramienta como el promedio de embeddings de queries de usuario de ejemplo, no su descripción, para cerrar la "brecha semántica" entre query y descripción. Reporta mejoras de hasta +27.28 en Recall@K en ToolBench y +30.5 en su dataset ToolBank. Son cifras "hasta", sin desglose en el abstract. — [Tool2Vec, arXiv 2409.02141](https://arxiv.org/abs/2409.02141); resumen práctico en [Red Hat Emerging Tech blog (dic 2025)](https://next.redhat.com/2025/12/05/a-practical-approach-to-smart-tool-retrieval-for-enterprise-ai-agents/)
- RAG-MCP indexa los metadatos de cada servidor o herramienta MCP (descripción y parámetros), recupera el top-k e inyecta solo la mejor descripción. La precisión de selección sube de 13.62% a 43.13% y los tokens de prompt bajan más de 50%. Las fuentes secundarias señalan que la precisión se degrada al crecer el registro. — [RAG-MCP, arXiv 2505.03275](https://arxiv.org/html/2505.03275v1); [review](https://www.themoonlight.io/en/review/rag-mcp-mitigating-prompt-bloat-in-llm-tool-selection-via-retrieval-augmented-generation)
- ToolRet (Findings ACL 2025): corpus de 43k herramientas y 7.6k tareas. Las queries son cortas (menos de 60 tokens, unas 25 palabras) y la documentación media mide 174.56 tokens; la mayoría está por debajo de 200. — [ToolRet, arXiv 2503.01763](https://arxiv.org/abs/2503.01763)

### Inferences
- Para el caso de 4.500 herramientas, "name: description" a secas es la configuración mínima, la nº1 de Toolshed. Añadir el esquema de parámetros, el nombre de la app y queries sintéticas es lo que la evidencia respalda.
- Para multi-vector, la variante probada es la de Re-Invoke: N copias "doc + query_i" con agregación por promedio. Equivale aproximadamente a un vector centroide, parecido a Tool2Vec. En un vector store sin agregación nativa, se puede indexar cada copia con un tool_id en los metadatos y agregar puntuaciones por tool_id en la aplicación, o simplemente precomputar el embedding promedio por herramienta.
- No conviene meter example_usage con llamadas API en el texto embebido (Tool-DE). Las preguntas en lenguaje natural sí (Re-Invoke, Toolshed).

### Gaps
- No encontré una comparación directa y controlada entre un vector por campo (nombre, descripción, parámetros por separado con fusión) y un documento concatenado. Re-Invoke y Toolshed solo comparan variantes de concatenación.
- No hay ablaciones públicas con text-embedding-3-small sobre un corpus de herramientas casi duplicadas entre apps. Toolshed muestra gráficas para 3-small, pero los valores no se pueden extraer del texto.
- No verifiqué el formato exacto que usa langgraph-bigtool más allá de lo indicado en el contexto del usuario.

## 2. Descripciones detalladas o cortas, y queries sintéticas (doc2query / reverse HyDE)

### Takeaway
Las queries sintéticas añadidas al documento tienen la evidencia cuantitativa más sólida:
- Re-Invoke: nDCG@5 en ToolE single-tool pasa de 0.652 a 0.781 (+20% relativo); con 1 query ya se obtiene la mayor parte de la ganancia, y saturan hacia 5-10.
- Toolshed recomienda descripciones largas con "cuándo usar y cuándo no".
- La expansión de documentos de Tool-DE da ganancias pequeñas o nulas con embedders fuertes y puede diluir la semántica.

En resumen, la calidad y la orientación a intenciones del texto importan más que la longitud.

### Cited Findings
- Ablación de Re-Invoke (dense, Vertex AI textembedding-gecko@003; nDCG@5 en ToolBench I1/I2/I3 y ToolE single/multi):
  - Baseline (solo documento): 0.5962 / 0.3880 / 0.4633 / 0.6522 / 0.5296
  - + generador de queries (documento + queries sintéticas): 0.6286 / 0.4135 / 0.4906 / 0.7813 / 0.6906
  - Solo la query sintética, sin documento: 0.4924 / 0.3050 / 0.4121 / 0.7535 / 0.6814. Es peor que añadirla al documento, así que hay que conservar el documento original.
  - 1 query: 0.5962 / 0.3741 / 0.4543 / 0.7388 / 0.6503
  - 5 queries: 0.6242 / 0.4091 / 0.4882 / 0.7777 / 0.6724
  - 10 queries: 0.6286 / 0.4135 / 0.4906 / 0.7813 / 0.6906

  — [Re-Invoke](https://arxiv.org/abs/2408.01875)
- En Re-Invoke, el extractor de intenciones en la query (el LLM reescribe la petición del usuario en una o varias intenciones) aporta por separado:
  - nDCG@5 en ToolBench I2: de 0.3880 a 0.5157.
  - Combinado con el generador de queries: 0.6110 / 0.5379 / 0.5955 / 0.7821 / 0.7231.
  - No mejora en I1, donde todas las APIs pertenecen a la misma herramienta y cada intención recupera APIs solapadas.

  — [Re-Invoke](https://arxiv.org/abs/2408.01875)
- Re-Invoke con BM25 en lugar de dense también gana mucho: ToolE multi-tool pasa de 0.2635 a 0.5637, lo que muestra que el enriquecimiento ayuda también al índice léxico. HyDE clásico (generar un documento hipotético a partir de la query) empeora en casi todos los datasets: dense ToolBench I1 cae de 0.5962 a 0.4336. — [Re-Invoke](https://arxiv.org/abs/2408.01875)
- Toolshed: las preguntas hipotéticas fueron "críticas" en ToolE pero aportaron poco en Seal-Tools, donde lo crítico fue el esquema de argumentos. — [Toolshed](https://arxiv.org/abs/2410.14594)
- Tool-DE (nDCG@10 / R@10 promedio, documentos originales de ToolRet frente a expandidos):
  - BM25s: 36.41/46.40 frente a 39.35/48.17
  - GritLM-7B: 41.13/51.28 frente a 43.54/54.07
  - NV-Embed-v1: 42.71 frente a 43.21
  - Qwen3-Embedding-8B: 46.21 frente a 46.23 (R@10 baja de 57.52 a 56.83)
  - e5-mistral-7b: 40.02 frente a 38.85 (empeora)

  La expansión alarga los documentos de 131.72 a 177.61 tokens, y los autores atribuyen parte de la caída a "dilución semántica". — [Tool-DE](https://arxiv.org/html/2510.22670)
- Tool-DE: un retriever fine-tuneado sobre documentos expandidos (Tool-Embed-4B) llega a nDCG@10 52.23 y R@10 63.13 en Tool-DE. Un reranker LLM (Tool-Rank-4B) suma +4.21 nDCG@10 (56.44). — [Tool-DE](https://arxiv.org/html/2510.22670)
- EasyTool (NAACL 2024) convierte documentación larga y heterogénea en "instrucciones de herramienta concisas y unificadas": en ToolBench pasa de 2.530 a 748 tokens (−70.43%). Afirma mejorar la recuperación, pero no encontré la tabla de retrieval. — [EasyTool, arXiv 2401.06201](https://arxiv.org/abs/2401.06201)
- Anthropic recomienda describir la herramienta "como a un nuevo empleado", explicitando el contexto implícito: formatos de query, terminología y relaciones entre recursos. Según el artículo, "incluso pequeños refinamientos en las descripciones pueden producir mejoras dramáticas"; no da cifras numéricas. — [Anthropic Engineering, Writing tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- ToolRet: incluso el mejor embedder general de entonces (NV-Embed-v1) logra solo nDCG@10 33.83 en el escenario sin instrucción. Los autores lo atribuyen a (i) poco solapamiento léxico entre la query y la documentación de la herramienta y (ii) el desplazamiento de dominio respecto a los corpus de IR habituales. Añadir una instrucción a la query mejora a todos los modelos: NV-Embed-v1 llega a 42.71 de media, gte-Qwen2-1.5B-instruct a 45.96. Rerankers genéricos como MonoT5 pueden empeorar el resultado (33.83 a 28.92). — [ToolRet](https://arxiv.org/abs/2503.01763)

### Inferences
- El principal problema documentado es la brecha entre la query del usuario y la descripción de la API (ToolRet, Tool2Vec). Las queries sintéticas la reducen directamente porque llevan el documento al "espacio de queries". Esto encaja con la recomendación de Toolshed de que las preguntas "imiten las preguntas futuras del usuario y usen parámetros".
- Las ganancias dependen del embedder: son grandes con embedders débiles o antiguos (gecko, BM25) y marginales con los más fuertes (Qwen3-8B). text-embedding-3-small es un modelo modesto, así que cabe esperar ganancias apreciables, aunque no hay cifras directas para él.
- Para mantener el documento centrado: function_description corta, tags y queries sintéticas, mejor que prosa muy larga. "Cuándo usar / cuándo no" ayuda más al LLM que elige entre los top-k que al embedding: Toolshed lo recomienda y Tool-DE da señales mixtas.
- La reescritura de la query (intenciones) es un complemento barato y con ganancias medidas, sobre todo cuando una petición pide varias herramientas.

### Gaps
- No hay números de Recall@k para text-embedding-3-small con y sin queries sintéticas en un corpus de ~4.500 herramientas.
- La cifra de mejora en retrieval de EasyTool no se encontró.
- Los valores de nDCG del retriever de ToolLLM/ToolBench y de Gorilla (retriever-aware) no se verificaron en esta sesión (fuentes: [ToolLLM, arXiv 2307.16789](https://arxiv.org/abs/2307.16789), [Gorilla, arXiv 2305.15334](https://arxiv.org/abs/2305.15334)). Tampoco se verificaron "Tool documentation enables zero-shot tool use" ([arXiv 2308.00675](https://arxiv.org/abs/2308.00675)), que sostiene que la documentación sola permite un uso zero-shot comparable a demostraciones few-shot pero trata la selección o uso por el LLM, no la recuperación por embeddings, ni ToolGen ([arXiv 2410.03439](https://arxiv.org/abs/2410.03439)). No incluir cifras de estos sin verificarlas.

## 3. Cómo desambiguar herramientas casi duplicadas entre apps

### Takeaway
La evidencia es sobre todo práctica, no cuantitativa en retrieval:
- Prefijar o "namespacear" por servicio y recurso (asana_search, jira_search).
- Nombres únicos con versión legible.
- Descripciones con propósito distinto y explícito.
- Consolidar herramientas solapadas.
- Para hacerlo a escala: filtrado jerárquico o por metadatos de la app, y reranking que considere el conjunto de candidatos.

### Cited Findings
- Anthropic: "el namespacing (agrupar herramientas relacionadas bajo prefijos comunes) puede ayudar a delimitar fronteras entre muchas herramientas", por servicio (asana_search, jira_search) y por recurso (asana_projects_search). Elegir entre prefijo y sufijo tuvo "efectos no triviales" en sus evaluaciones y "varía según el LLM". — [Anthropic, Writing tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- Anthropic: "cuando las herramientas se solapan en función o tienen un propósito vago, los agentes se confunden"; "asegúrate de que cada herramienta tenga un propósito claro y distinto". También recomienda consolidar operaciones (por ejemplo, schedule_event en lugar de list_users + list_events + create_event) y usar nombres de parámetro inequívocos (user_id en lugar de user). — [Anthropic](https://www.anthropic.com/engineering/writing-tools-for-agents)
- Toolshed: "las herramientas no deben ser idénticas ni solaparse, y los nombres deben ser únicos". Propone metadatos y agrupaciones jerárquicas de herramientas para filtrar (Apéndice A, Fig. 6) como vía para mejorar la precisión. — [Toolshed](https://arxiv.org/abs/2410.14594)
- Re-Invoke: en ToolBench I1 (APIs de una misma herramienta, muy parecidas entre sí) el extractor de intenciones no ayudó (0.5962 frente a 0.5910), señal de que los casi duplicados son el caso difícil para la recuperación por embeddings. — [Re-Invoke](https://arxiv.org/abs/2408.01875)
- La búsqueda semántica simple "carece del matiz para distinguir herramientas descritas de forma similar". Por eso Tool2Vec añade ToolRefiner, un reranker que puntúa la query contra el conjunto completo de candidatos. — [Red Hat blog](https://next.redhat.com/2025/12/05/a-practical-approach-to-smart-tool-retrieval-for-enterprise-ai-agents/); [Tool2Vec](https://arxiv.org/abs/2409.02141)
- Los rerankers generales pueden no ayudar, o empeorar, en tool retrieval (MonoT5 sobre NV-Embed-v1 baja nDCG@10 de 33.83 a 28.92 en ToolRet). Los rerankers especializados sí ayudan (Tool-Rank-4B: +4.21 nDCG@10). — [ToolRet](https://arxiv.org/abs/2503.01763); [Tool-DE](https://arxiv.org/html/2510.22670)

### Inferences
- Para create_item o list_items repetidos en 30 apps:
  - Incluir en el texto embebido el nombre de la app y el recurso de forma explícita y legible ("Jira: create issue (crea una incidencia/issue en un proyecto de Jira)"), además del prefijo en el nombre (jira_create_issue).
  - Generar queries sintéticas que mencionen la app y el vocabulario propio del dominio ("abre un ticket en Jira").
  - Usar la app como metadato para un filtro previo, o una búsqueda en dos etapas (app y luego función) cuando la query nombra la app.
- Con top-k=3 sobre 4.500 herramientas casi duplicadas, el riesgo es que los 3 resultados sean la misma operación en apps distintas. Subir k (por ejemplo 10-20) y añadir un reranker o un paso de selección por LLM, o diversificar por app, es coherente con la evidencia de Toolshed y Tool2Vec sobre el reranking. Es una inferencia, no un resultado medido sobre este setup.
- Las descripciones contrastivas ("úsala para X en la app A; para Y en la app B usa b_...") se recomiendan en la práctica ("when not to use" en Toolshed), pero no encontré cifras de su efecto aislado en retrieval.

### Gaps
- No encontré estudios cuantitativos que midan el efecto en recall de prefijar el nombre de la app ni de las descripciones contrastivas en corpus con funciones homónimas entre apps.
- No se cuantificó el efecto de filtrar por metadatos de la app frente a un índice plano a esta escala (~4.500).

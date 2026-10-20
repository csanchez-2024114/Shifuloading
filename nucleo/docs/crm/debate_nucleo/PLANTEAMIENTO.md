# Debate: trasladar el CRM generativo encima del núcleo «Agente 0» de Alan

Solo análisis y plan. NO cambies código. Responde en español.

## Decisión ya tomada por el usuario (no la discutas, planéala)
- La BASE nueva es el repo de Alan, completo: ~/CURSOR/HyperShifu/langgraph-alan (ramas main y origin/feat/agente-codificador; lee README.md, CONTRATO.md, docs/CREAR_PERFIL.md, docs/ESTADO.md, docs/ACTIVACION.md, docs/CODER_PLAN.md en la rama codificador con `git show origin/feat/agente-codificador:docs/CODER_PLAN.md`, src/assistant/core/*, profiles/*, packs/*).
- Se clona ese repo y ENCIMA se monta todo lo que hoy tiene nuestro CRM, sin descartar ni omitir nada. Si Alan tiene algo mejor que lo nuestro, se adopta lo de Alan y se adapta a nuestro CRM. Se mejora hasta tener TODAS las funciones actuales, bien hechas.
- Se desconecta nuestro núcleo de agente y se coloca el de Alan con cuidado.

## Lo nuestro (hoy, rama david de ~/CURSOR/HyperShifu/Shifuloading)
- backend/app/crm/ (~14.000 líneas Python): agente_diseno.py (bucle del turno en modo diseño, cercos por herramienta, ganchos de respuesta, deshacer, pendientes), agente.py (agente de Carlos: herramientas de datos, tareas, contactos, Sesion base), edicion.py (herramientas de diseño del laboratorio), toma.py (preguntas iniciales), primer_diseno.py/diseno.py/sembrar.py (primer CRM), registros.py, pantalla.py (qué ve el modelo), conceptos.py + catalogos/*.json, memoria.py (mensajes completos, ventana por tokens, resumen rodante), por_hacer.py (pendientes que anota el código), puntos.py (deshacer), adjuntos.py, web.py, marca.py (logo), traza.py, regional.py, repositorio.py (Mongo async con motor), automatizaciones.py (en pausa).
- backend/app/routes/crm/crmRoutes.py (FastAPI async, /api/v1/crm/chat, brief, siguiente-pregunta, importar, logo…) y labRoutes.py (/api/v1/crm/lab/chat que usan los bancos).
- Frontend React/Vite: src/pages/CrmPage.jsx, src/crm/plantillas/*, src/pages/BriefPage.jsx. Laboratorio en laboratorio/ (referencia y bancos de medición con IA real: laboratorio/pruebas/banco*.py).
- Resto del backend (~70.000 líneas) viene del producto de Carlos/HyperShifu: auth, billing, canales, workers, etc.
- Pruebas: backend/test/crm (≈18.000 pruebas sin IA real).
- Reglas: 2–3 llamadas al modelo por mensaje, sin agregar llamadas; método de Alan (el código define el cerco, el modelo elige; nada de parches con palabras o regex; lo calculable lo calcula el código; nunca afirmar lo que no pasó); línea base y misma medición antes de juntar; automatizaciones en pausa; un CRM distinto por persona, todo desde un chat.
- Medición actual (bancos con IA real, gpt-4.1-mini): datos 63/63, citas 17/18 (2 corridas), deshacer 17-18/18, pestañas 22-24/27, banco2 14-15/16, conceptos 9-12/14, memoria 13-18/18 (varían entre corridas).

## Lo que ya sabemos del núcleo de Alan
- Perfiles (AGENT_PROFILE): prompt, build_tools, ToolPolicy (effect, approval, evidence), textos, UI propia (static_dir); el núcleo no se toca.
- create_agent de LangChain + middlewares: LimiteLlamadas, LimiteRepeticiones, AvisoCorte, ResumenPorTurno (compactación), FiltroURLs, AnswerVerifier, HumanInTheLoop (tarjetas de aprobación), AterrizajeSuave (tope de tokens), ToolErrorMiddleware. Checkpointer MongoDBSaver por hilo, MongoDBStore para memoria larga.
- TODO síncrono (pymongo). Clasificador de esfuerzo = 1 llamada extra salvo MODEL_CALL_LIMIT>0. ANSWER_VERIFY = llamada extra (interruptor). Modelo por defecto gpt-6-luna.
- tool_spec + bigtool (índice semántico para cientos de herramientas). appdata (repos Mongo/memoria). files (adjuntos con GridFS). auth (cuentas). metrics, tracing, feedback, evals. Candado por hilo (un worker).
- Rama feat/agente-codificador: perfil coder, proyectos, sandbox, vista previa, recursos.

## Qué te pido
Propón el plan COMPLETO del traslado, con estas secciones:
1. Arquitectura destino: dónde vive cada pieza nuestra dentro del repo de Alan (core / packs / profiles/crm / UI). Qué se adopta de Alan en lugar de lo nuestro (memoria, compactación, adjuntos, aprobaciones, topes, trazas, evals, auth…) y qué de lo nuestro se conserva porque Alan no lo tiene.
2. Cómo se trasladan nuestros cercos, ganchos de respuesta, deshacer, pendientes y la verdad de la respuesta al modelo de middlewares de Alan, sin agregar llamadas al modelo.
3. Datos: el documento del CRM y los registros (hoy Mongo async con motor) vs pymongo síncrono y checkpointer de Alan. ¿Async o sync? ¿Qué pasa con el candado por hilo y un solo worker?
4. Frontend: nuestra app React vs la UI de un HTML de Alan (SSE /chat, /resume, tarjetas). Cómo conectarlas.
5. El resto del backend de Carlos (auth, billing, canales…): qué entra, qué no, y cómo.
6. Orden por fases con compuertas de medición (los bancos deben seguir corriendo contra una ruta compatible desde el día 1), riesgos y cómo no perder nada (inventario/checklist de paridad).
7. Lo que más te preocupa del plan y lo que harías distinto.
Sé concreto: archivos, funciones, middlewares. Máximo ~1500 palabras.

# Grupo F — Chat de producción: tracking de tokens real

- [x] En `chat_stream::run_graph()` (bloque de éxito, tras `save_message`): contar tokens de la respuesta. Se encontró que `debug_ws.py` (`_ShifuDebugStreamer._extract_total_tokens`) ya extrae el conteo REAL vía `on_llm_end`/`LLMResult.llm_output.token_usage` (o `usage_metadata` del `AIMessage` en LangChain nuevo) — se portó esa misma lógica a `_ChatStreamer` en `chat.py` (antes `on_llm_end` era un no-op `pass`). `chat_stream` usa `streamer.total_tokens` (real) y solo cae a `len(accumulated)//4` si el proveedor/modelo no expone `token_usage` (fallback, no caso normal).
- [x] Llamar `track_daily_tokens(redis_client, user_id, tokens)`
- [x] Llamar `maybe_get_token_warning(redis_client, user_id, user_plan, daily_total)`
- [ ] Verificación: mandar mensajes por el chat real hasta cruzar 80% del cupo diario (o bajar el límite de plan temporalmente para probar) y confirmar que llega `usage_warning` por WS en producción, no solo debug — pendiente de prueba manual end-to-end (fuera del alcance de este agente: requiere servidor + Redis corriendo y un usuario real logueado)

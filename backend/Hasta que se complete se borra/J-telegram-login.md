# Grupo J — Telegram Login Widget (autenticación nueva)

- [x] Env var nueva `TELEGRAM_BOT_TOKEN` (`config.py`, misma variable de entorno que ya usa `app/integrations/providers/telegram.py` — un solo bot, dos features)
- [x] `POST /api/v1/auth/telegram` en `authRoutes.py`, mismo patrón que `google_login`
- [x] Verificar `hash` con HMAC-SHA256 (algoritmo estándar de Telegram Login Widget) contra el bot token — helpers `telegram_data_check_string`/`verify_telegram_login_hash`, más rechazo de `auth_date` > 24hs (anti-replay)
- [x] Buscar/crear `UserAuthMethod` tipo `TELEGRAM`
- [x] Devolver `_auth_response(...)` igual que login/register
- [x] No confundir con `/api/v1/integrations/telegram/login` (eso es conectar, no tocar) — verificado, no se tocó `app/integrations/providers/telegram.py`
- [x] Frontend: `postTelegramCallback` (`src/api/analysisApi.ts`) apunta a `/api/v1/auth/telegram` (antes `/auth/telegram/callback`), persiste `access_token`/`refresh_token`/`user_id` en localStorage igual que `googleLoginApi`; `useConnectorConnections.ts::handleTelegramResponse` ajustado a la respuesta real (`access_token` en vez de `response.status`)
- [x] Verificación: `python -c "import main"` limpio + `test_telegram_auth.py` (5 asserts: hash válido, bot token incorrecto, payload alterado, hash ausente, orden alfabético del data_check_string) — todos pasan. `npx tsc -b --noEmit` sin errores nuevos en los archivos tocados.
- [ ] Pendiente (fuera de alcance de esta sesión, requiere bot real + navegador): probar el login end-to-end con el widget de Telegram real en el browser

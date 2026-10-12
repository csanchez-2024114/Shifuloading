# Grupo G — Home/Insights: 9 endpoints de analytics

- [x] Router nuevo `app/routes/me/analytics.py`, `prefix="/api/v1/me/analytics"`
- [x] `GET /gauge` — tokens usados/límite (quota.py + billing/plans.py)
- [x] `GET /files` — cloudinary_service.get_user_inventory()
- [x] `GET /pie` — intent_outcomes agrupado por tool_used
- [x] `GET /line` — intent_outcomes/workflow_runs por día, últimos 30d
- [x] `GET /bar` — éxitos vs intentos (REPURPOSE: actualizar title/subtitle/sources en el hook)
- [x] `GET /area` — acciones chat vs workflow por día (REPURPOSE: actualizar copy)
- [x] `GET /composed` — intentos/éxitos/tiempo promedio (REPURPOSE: actualizar copy)
- [x] `GET /scatter` — duración vs complejidad de runs (REPURPOSE fuerte: actualizar copy, no es ROI)
- [x] `GET /radar` — noveno chart. Fuente elegida: distribución éxitos/fallos de intent_outcomes
      agrupada por `category` del catálogo (`catalog_apps`), resuelta vía los `app` de los steps
      del workflow de cada outcome (`workflow_id` → `workflows.steps.app` → categoría). Un run
      que toca apps de 2+ categorías cuenta en ambas (distribución aproximada, no partición exacta
      — documentado en el docstring del endpoint).
- [x] Frontend: migrar los 9 hooks `useFetchAnalytics*.ts` de `fetch()`+`getApiBackend()` a `http.ts`
- [x] Verificación: ver los 9 charts en Insights con datos reales y copy honesto

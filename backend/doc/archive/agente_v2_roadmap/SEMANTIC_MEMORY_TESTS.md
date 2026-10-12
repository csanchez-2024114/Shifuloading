# Semantic Memory — Test Protocol

Protocolo de pruebas para validar la capa `user_semantic_memory` end-to-end.
Ejecutar en orden. Marcar cada nivel antes de pasar al siguiente.

---

## Nivel 1 — Escritura básica (Smoke Test)

**Objetivo:** Verificar que un hecho nuevo se persiste en `user_semantic_memory`.

**Mensaje a enviar:**
```
Trabajo principalmente con Python y uso FastAPI para mis APIs.
```

**Logs esperados:**
```
[user_profile_updater] semantic fact user=<id> key='preferred_language' value='Python'
[user_profile_updater] semantic fact user=<id> key='preferred_framework' value='FastAPI'
[user_profile_updater] done user=<id> keys=['preferred_language', 'preferred_framework']
```

**MongoDB — `user_semantic_memory`:**
```json
{ "user_id": "...", "key": "preferred_language", "value": "Python", "mention_count": 1, "source": "implicit" }
{ "user_id": "...", "key": "preferred_framework", "value": "FastAPI", "mention_count": 1, "source": "implicit" }
```

**Criterio de éxito:** Ambos documentos existen en MongoDB con `mention_count: 1`.

- [ ] PASS
- [ ] FAIL — Notas:

---

## Nivel 2 — Lectura e inyección (Turno siguiente)

**Objetivo:** Verificar que en el turno siguiente los hechos se cargan y aparecen en el SystemMessage.

**Mensaje a enviar (turno nuevo, misma conversación o nueva):**
```
¿Con qué tecnologías me recomiendas construir un endpoint de webhooks?
```

**Logs esperados:**
```
[semantic_memory_loader] user=<id> facts=2 top_keys=['preferred_language', 'preferred_framework']
```

En `active_blocks` (log de chat.py):
```
active_blocks=[..., 'semantic_memory(facts=2)', ...]
```

**Comportamiento esperado del agente:** La respuesta menciona Python y/o FastAPI de forma natural — sin anunciar que "recuerda" eso, simplemente lo usa como contexto.

**Criterio de éxito:** Log de `semantic_memory_loader` muestra `facts=2` y la respuesta está personalizada con el stack del usuario.

- [ ] PASS
- [ ] FAIL — Notas:

---

## Nivel 3 — Acumulación de mention_count (Refuerzo)

**Objetivo:** Verificar que repetir un hecho incrementa `mention_count` correctamente.

**Mensajes a enviar en 3 turnos distintos:**

Turno A:
```
Sí, como te dije, Python es mi lenguaje principal.
```
Turno B:
```
Estoy armando un proyecto nuevo en Python, ¿qué me recomiendas?
```
Turno C:
```
Siempre vuelvo a Python para este tipo de tareas.
```

**MongoDB después de los 3 turnos — `user_semantic_memory`:**
```json
{ "key": "preferred_language", "value": "Python", "mention_count": 4 }
```
*(era 1 del Nivel 1, más 3 menciones nuevas = 4)*

**Qué verificar:**
- `mention_count` se incrementa con cada mención
- El valor se actualiza si cambia (ej: si el usuario dice "ahora uso Python 3.12", `value` se actualiza)
- `last_seen_at` se actualiza en cada mención

**Criterio de éxito:** `mention_count >= 4` en MongoDB para `preferred_language`.

- [ ] PASS
- [ ] FAIL — Notas:

---

## Nivel 4 — Separación correcta Profile vs Semantic (Aislamiento)

**Objetivo:** Verificar que los hechos que pertenecen al User Profile NO van a `user_semantic_memory`, y los que no pertenecen SÍ van.

**Mensaje a enviar:**
```
Soy Alan Cruz, trabajo en HyperReality Company en México. Mi stack favorito es LangGraph y uso bases de datos vectoriales como Qdrant para memoria a largo plazo.
```

**Qué debe pasar en `user_preferences` (profile):**
```json
{ "prefs.user_name.value": "Alan Cruz" }
{ "prefs.user_company.value": "HyperReality Company" }
{ "prefs.user_country.value": "México" }
```

**Qué debe pasar en `user_semantic_memory`:**
```json
{ "key": "preferred_framework", "value": "LangGraph" }
{ "key": "preferred_database", "value": "Qdrant" }
{ "key": "use_case", "value": "long-term memory" }
```

**Qué NO debe pasar:**
- `user_name` en `user_semantic_memory`
- `preferred_framework` en `user_preferences`

**Criterio de éxito:** Los 3 facts de identidad están en `user_preferences`, los hechos técnicos están en `user_semantic_memory`, sin cruces entre colecciones.

- [ ] PASS
- [ ] FAIL — Notas:

---

## Nivel 5 — Límite top-20 + ordenamiento por relevancia (Stress)

**Objetivo:** Verificar que con más de 20 hechos en DB, solo los top-20 se inyectan y están ordenados por `mention_count` descendente.

**Setup previo — enviar estos mensajes en turnos distintos para poblar la colección:**
```
Uso Notion para documentación.
```
```
Mi horario de trabajo es de 9 a 18 GMT-6.
```
```
Prefiero código asíncrono sobre síncrono.
```
```
Trabajo en modo async-first, sin reuniones antes de mediodía.
```
```
Mi industria es SaaS B2B.
```
```
El cliente principal son empresas de 50 a 500 empleados.
```
```
Prefiero MongoDB sobre SQL para este proyecto.
```
```
Uso GitHub Actions para CI/CD.
```
```
Mi deploy target es Railway.
```
```
Trabajo solo, soy el único developer del proyecto.
```

Más los hechos de niveles anteriores = ~15 hechos totales. Luego repetir `preferred_language: Python` en 10 turnos más para darle `mention_count` alto.

**MongoDB — resultado esperado:**
- Más de 20 documentos en `user_semantic_memory` para el usuario
- `preferred_language` tiene el `mention_count` más alto

**Log esperado en el siguiente turno:**
```
[semantic_memory_loader] user=<id> facts=20 top_keys=['preferred_language', 'preferred_framework', ...]
```

**Verificar:**
1. El log dice exactamente `facts=20`, no más
2. `preferred_language` aparece primero en `top_keys` (mayor `mention_count`)
3. El hecho con `mention_count` más bajo queda fuera del top-20 y NO aparece en el SystemMessage
4. La respuesta del agente usa los hechos de mayor relevancia

**Criterio de éxito:** El bloque `semantic_memory` en el SystemMessage tiene exactamente 20 entradas, ordenadas por frecuencia descendente, y el hecho menos frecuente no está incluido.

- [ ] PASS
- [ ] FAIL — Notas:

---

## Resumen

| Nivel | Qué prueba | Criterio mínimo | Resultado |
|-------|-----------|-----------------|-----------|
| 1 | Escritura | Docs en MongoDB con `mention_count=1` | |
| 2 | Lectura + inyección | Log `facts=N` + respuesta personalizada | |
| 3 | Acumulación | `mention_count` incrementa por turno | |
| 4 | Separación Profile/Semantic | Sin cruces entre colecciones | |
| 5 | Límite top-20 + ordenamiento | Exactamente 20 hechos, ordenados por frecuencia | |

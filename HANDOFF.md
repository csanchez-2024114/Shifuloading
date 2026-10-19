# Handoff — worktree `wt-conceptos` (rama `etapa1/conceptos`)

## Revisión del revisor (commit `452e8b3`) — ajustes hechos

Se **mantienen**: `conceptos.json`, `conceptos.py` (línea por concepto + detalle al detectar), brief en contexto, aviso de sección vacía, sugerencia 2–3 gráficas (`plantillas.compatibles` + `rubros_grok.json`), reglas del prompt (incl. «sí/dale/ok» = acepta la recomendada).

Se **quitaron** los tres parches de palabras (método de Alan):

| Parche quitado | Sustitución |
|----------------|-------------|
| `sin_jerga` / `_JERGA_SUBS` | `humanizar_estado_modelo()` en el JSON de contexto (`secciones_del_menu`, `tablas_del_negocio`, `graficas_disponibles`, `plantillas_de_pestana`, tipos de pieza legibles) y `humanizar_resultado_herramienta()` + `pantalla.asi_se_ve_legible()` en resultados de edición; mensajes de error de datos solo con títulos visibles; instrucciones del prompt sin «propia/integrada». |
| `texto_tras_afirmacion` | Eliminado; el turno usa el texto real del usuario; solo queda la regla en `INSTRUCCIONES_LAB` (línea «sí/dale/ok»). |
| `masivo_destruye_bloques` | Cerco de bloques otra vez con `MASIVO.search` como en `david` (`planificar_cerco_masivo` y `quitar_bloque`). Se conserva `masivo_destruye_registros` para secciones/campos/registros (punto 20). |

## Puntos cerrados (LISTA_PENDIENTES 19-oct)

| # | Qué | Cómo (tras ajuste revisor) |
|---|-----|----------------------------|
| **19** | La IA sabe qué es cada cosa | Catálogo + `bloque_para_prompt` / `_detectar` (sin cambio). |
| **20** | Confirmar según riesgo | `masivo_destruye_registros` + instrucciones de confirmación masiva; bloques con cerco `david`. |
| **7** | «Sí» suelto acepta la recomendada | Solo prompt (`INSTRUCCIONES_LAB`); historial del chat. |
| **8** | Sin jerga interna | Origen: contexto y resultados de herramientas humanizados (no regex en la respuesta). |
| **12** | El negocio pesa más que la plantilla | `resumen_del_brief` + aviso en `avisos_turno`. |
| **13** | Gráfica sobre sección vacía | `avisos_turno` si 0 registros. |
| **14** | Solo 2–3 gráficas | `sugerir_graficas` + aviso (nombres sin ids técnicos en el aviso). |

## Archivos tocados (commit nuevo)

- `backend/app/crm/conceptos.py`
- `backend/app/crm/agente_diseno.py`
- `backend/app/crm/pantalla.py` (`asi_se_ve_legible`)
- `backend/test/crm/test_conceptos.py`
- `backend/test/crm/test_agente_diseno.py`

Sin cambios en `conceptos.json` ni `banco_conceptos.py` en este commit.

## Pruebas (verificado en este worktree)

```bash
cd backend && MONGO_URI=mongodb://x:1 SECRET_KEY=prueba-local-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx OPENAI_API_KEY=sk-falso \
  /Users/josueboror/CURSOR/HyperShifu/HyperShifu-crm-agent/backend/.venv/bin/python -m pytest test/crm -q -p no:cacheprovider
```

- **Resultado:** `17878 passed`, `1 skipped`, **1 failed** (`test_reloj.py::test_el_programador_llama_al_reloj_del_crm_y_si_falla_sigue` — falta `ENCRYPTION_KEY` al importar workers; no relacionado con conceptos).
- Tests de conceptos: 8 en `test_conceptos.py` (humanización + catálogo/gráficas).

## Banco con IA real (revisor)

No corrido aquí (sin clave OpenAI).

1. Servidor lab (puerto libre, p. ej. 5190):

```bash
cd backend && CRM_DISENO=1 CRM_LAB_ADAPTER=1 \
  MONGO_URI=mongodb://x:1 SECRET_KEY=prueba-local-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx OPENAI_API_KEY=<real> \
  /Users/josueboror/CURSOR/HyperShifu/HyperShifu-crm-agent/backend/.venv/bin/python scripts/crm_dev_server.py --puerto 5190
```

2. Desde la raíz del worktree:

```bash
BASE=http://localhost:5190 RUTA_CHAT=/api/v1/crm/lab/chat \
  python3 laboratorio/pruebas/banco_conceptos.py
```

3. Bancos base (regresión): `banco2.py`, `banco_deshacer.py 3`, `banco_toma.py 1`, `banco_ficha.py`, `banco_datos.py 3`, `banco_pestanas.py 3` con la misma `BASE`/`RUTA_CHAT`. Guardar en `documentos/mediciones/2026-10-19_conceptos/`.

## Commits en la rama

- `1206c5f` — Banco de conceptos y brief en adaptador lab.
- `452e8b3` — Catálogo y reglas (revisado: quedan parches prohibidos fuera).
- *(pendiente de commit)* — Quitar parches de palabras; jerga en el origen; cerco bloques como `david`.

## Qué falta / riesgos

- **Medición IA real** (`banco_conceptos` + bancos base): revisor con clave.
- **Jerga residual:** el modelo aún ve nombres de herramientas en el esquema de tools y algo de ids en `bloques.id` (necesario para `quitar_bloque`); el prompt sigue pidiendo no repetirlos al usuario.
- **`test_reloj`:** fallo ambiental; otro frente.

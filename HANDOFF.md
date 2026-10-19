# HANDOFF — frente «diseño» (rama etapa1/diseno, sobre b4f578f)

## Hecho (commits 2cee0ec, 8af5f37, e8f516f; pruebas: 17886 en verde, `test/crm`)
Lista 21, 21b, 22 (solo piezas), 23, 24, 25, 27, 29.
- `backend/app/crm/primer_diseno.py` (nuevo): el CRM inicial SIEMPRE se arma nuevo.
  - `compatibilidad(brief)`: % por SECCIÓN de todas las plantillas y pestañas (raíces `raiz()` + TF-IDF por sección) contra TODAS
    las respuestas (`necesidades`: que_vendes, seguimiento, dolor, casillas). Puente: `catalogos/rubros_semilla.json` (borrador de
    Grok, semilla, no verdad) → `rubros_parecidos` y combinaciones de rubros. `piezas_para_el_modelo`: top 14, una por título.
  - `crear()`: 1 llamada (`modelo_creacion`, JSON) con piezas + %; reintento solo si el JSON es malo (máx 2); si falla →
    `plantilla_de_respaldo` (piezas ≥30 %, o la semilla «simple»). Cerco: `plantilla_de_propuesta`, `_campo`, `completar_opciones`,
    `_bloque` (gráficos con `plantillas.cumple`), `bloques_por_defecto`, mínimo 3 secciones, máx 7 campos. Siembra con
    `sembrar.sembrar(..., nivel="pocos")` (8 ejemplos, valores del negocio; campos «persona» con nombres; texto sin ejemplos en
    blanco; `ordenar_fechas_y_horas`).
  - `resumen()` y `ejemplos_saludo()` los escribe el código con lo creado → `resumen_ia`, `saludo_ejemplos` (vista: `saludoEjemplos`).
- `sembrar.crear_desde_cuestionario` llama a `primer_diseno.crear` (sin `asignar` ni `ajustar_sembrado` en este camino).
- Límite 300 → 1500: `src/pages/BriefPage.jsx` (`LARGO_ABIERTA`), `crmRoutes.py` (`que_vendes` x2, `Seguimiento.respuesta`).
- `src/pages/CrmPage.jsx`: saludo con `crm.saludoEjemplos`; el aviso de bienvenida se cierra al saludar (ya no se repite).
- Banco nuevo `laboratorio/pruebas/banco_creacion.py` (IA real, en proceso; `BACKEND=` elige la copia del código).

## Resultados (`~/CURSOR/HyperShifu/documentos/mediciones/2026-10-19_diseno/`)
- Creación: base david 0/6 (PepesCore=gimnasio 220 ej.; Astral 2 secciones 0 ej.), p50 4.7 s · ahora 12/12 (2 reps), p50 7.7 s,
  máx 14.6 s, 1 llamada siempre. (Las 2 últimas correcciones —e8f516f, 8af5f37 en parte— no se volvieron a medir con IA real.)
- Bancos de siempre (5201): banco2 14/16 y 15/16 (base 15/16) · deshacer 17/18 x2 (base 18/18; la MISMA base b4f578f re-corrida
  dio 18/18 y 15/18 → ruido del modelo; este frente no toca el chat) · toma 11/11 · ficha 7/7 · datos 61/63 · pestañas 19/27 y 20/27
  (base 20/27). Tiempos 1.9–2.4 s (base 1.9–2.0).

## Falta
- Re-correr `banco_creacion.py 2` con e8f516f para confirmar.
- 30 (empezar de cero / pestaña vacía): no se tocó; es del chat (herramientas), no de la creación.
- 22 catálogo que crece: solo queda guardado `doc.plantilla.piezas` (qué pieza usó cada sección) como señal futura.
- Marcar 21–25, 27, 29 en LISTA_PENDIENTES (no lo hice: documento compartido).
- Calibrar `PISO_SIM`/`MIN_PCT_*` con más descripciones reales (academia aún ve el rubro «Gimnasio» como parecido; el modelo lo descarta).

## Cómo probar
`cd backend && <venv>/bin/python -m pytest test/crm -q -p no:cacheprovider` (nuevos: `test_primer_diseno.py`).
`cd backend && <venv>/bin/python ../laboratorio/pruebas/banco_creacion.py 2` (IA real; `SALIDA=x.json` guarda el detalle).

# Bitácora de memoria del agente

Corridas de `scripts/eval_memory.py` (casos en `scripts/eval_memory_cases.json`). La línea se agrega sola; las notas de revisión a mano van en `BITACORA.md`. Precisión = preguntas acertadas / preguntas (abstención correcta = decir que no sabe).

## Notas de revisión (más reciente arriba; la tabla de corridas va al final porque se llena sola)

### 2026-10-10 · v0.3.2 → v0.4.0 · re-calificación con la medición corregida
Revisé a mano las 3 fallas de `v040` y 2 eran errores de medición:
- El juez citaba con "…" entre trozos y el código exigía la cita literal completa. Ahora acepta trozos, siempre que cada uno exista en la respuesta.
- La respuesta esperada "eventos corporativos (ya no bodas)" castigaba un "eventos corporativos" correcto.

Re-califiqué **las dos corridas** con el mismo criterio. Es la comparación justa:

| | base_v032 | v040 |
|---|---|---|
| total | 20/26 | **25/26** |
| entre conversaciones | 2/8 | **7/8** |
| multi_session / temporal | 0/4 · 0/2 | 3/4 · **2/2** |
| misma conversación (hasta 25 turnos) | 14/14 | 14/14 |
| abstención / update | 4/4 · 4/4 | 4/4 · 4/4 |
| intentos por pregunta | 2.15 | **1.23** |
| rechazos de no_fabrication en preguntas | 3 | 0 |
| tokens del responder en el turno 25 | 8150 | 7258 |

**Defecto real que queda** (cuatro_sesiones r1): "¿qué automatizaciones teníamos pendientes?" Recordó Gmail→Sheets, pero en lugar del recordatorio de los lunes mencionó "enviar contratos", que salió del relleno de una sesión posterior.
- **Revisado.** El diario y el contexto estaban bien: llegaron las 3 tareas, en orden y con sus nombres. Hubo 3 pendientes reales (la tercera, "enviar contratos", la propuso el usuario simulado en la sesión 3) y el agente nombró 2, omitiendo el recordatorio. Es una omisión del responder al enumerar, no una pérdida de memoria.
- **Mejora de la medición pendiente.** La respuesta esperada debería decir "las tareas de las sesiones 1 y 2, aunque mencione otras".

**`larga50_v041` (50 turnos, 2 repeticiones; el código ya era 0.4.2 aunque el backend reportaba 0.4.1).**
- Resultado: **8/8**. Los datos sembrados en los turnos 2–4 se recordaron en los turnos 26, 39 y 49, con 2/2 en abstención y 0 rechazos de `no_fabrication`.
- **Decisión: no se compacta todavía**, porque la precisión no cae a 50 turnos.
- El costo sí crece: el responder pasa de 2.7k a 18k tokens de entrada en el turno 49 (unos $0.003 por turno con 4o-mini). La compactación queda como optimización de costo, no de memoria, y se mide con el mismo caso si algún día hace falta.

| fecha | versión | etiqueta | precisión | por habilidad | por distancia (turnos) | misma conv. / entre sesiones | tokens responder t1 → último | rechazos no_fabrication en preguntas | USD | archivo |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-10 13:00 | 0.3.2+c12926c8 | smoke | 2/2 | extraction 2/2 | 6-15 2/2 | misma conversacion 2/2 | 2927 → t14: 5189 | 0 | 0.069 | mem_smoke_20261010_130038.json |
| 2026-10-10 13:17 | 0.3.2+c12926c8 | base_v032 | 19/26 | abstention 4/4, extraction 12/12, multi_session 0/4, temporal 0/2, update 3/4 | 1-5 1/2, 16+ 2/2, 6-15 12/18, ? 4/4 | ? 4/4, entre sesiones 1/8, misma conversacion 14/14 | 2835 → t25: 8150 | 3 | 1.075 | mem_base_v032_20261010_131711.json |
| 2026-10-10 13:41 | 0.4.0+ce826190 | v040 | 23/26 | abstention 4/4, extraction 12/12, multi_session 2/4, temporal 2/2, update 3/4 | 1-5 1/2, 16+ 2/2, 6-15 16/18, ? 4/4 | ? 4/4, entre sesiones 5/8, misma conversacion 14/14 | 2809 → t25: 7258 | 0 | 1.024 | mem_v040_20261010_134130.json |
| 2026-10-10 13:48 | 0.4.0+ce826190 | v040 | 23/26 | abstention 4/4, extraction 12/12, multi_session 2/4, temporal 2/2, update 3/4 | 1-5 1/2, 16+ 2/2, 6-15 16/18, ? 4/4 | ? 4/4, entre sesiones 5/8, misma conversacion 14/14 | 2817 → t25: 7003 | 2 | 1.026 | mem_v040_20261010_134837.json |
| 2026-10-10 14:36 | 0.4.1+7f2c3d75 | larga50_v041 | 8/8 | abstention 2/2, extraction 6/6 | 16+ 6/6, ? 2/2 | ? 2/2, misma conversacion 6/6 | 2763 → t49: 18132 | 0 | 0.744 | mem_larga50_v041_20261010_143611.json |
| 2026-10-10 15:53 | 0.5.1+7493fa50 | doce_v051 | 1/3 | abstention 1/1, multi_session 0/2 | 16+ 0/2, ? 1/1 | ? 1/1, entre sesiones 0/2 | 2810 → t25: 3097 | 0 | 0.116 | mem_doce_v051_20261010_155318.json |
| 2026-10-10 16:12 | 0.5.2+de3ab868 | doce_v053 | 1/3 | abstention 1/1, multi_session 0/2 | 16+ 0/2, ? 1/1 | ? 1/1, entre sesiones 0/2 | 2810 → t25: 3092 | 0 | 0.115 | mem_doce_v053_20261010_161204.json |
| 2026-10-10 16:34 | 0.5.2+d22187e9 | doce_v053b | 2/3 | abstention 1/1, multi_session 1/2 | 16+ 1/2, ? 1/1 | ? 1/1, entre sesiones 1/2 | 2810 → t25: 3070 | 0 | 0.117 | mem_doce_v053b_20261010_163406.json |
| 2026-10-10 17:20 | 0.5.3+bef3d07e | fecha_v054 | 0/2 | multi_session 0/1, temporal 0/1 | 1-5 0/2 | entre sesiones 0/2 | 2607 → t6: 2988 | 0 | 0.032 | mem_fecha_v054_20261010_172054.json |
| 2026-10-10 17:24 | 0.5.3+bef3d07e | fecha_v054b | 1/2 | multi_session 1/1, temporal 0/1 | 1-5 1/2 | entre sesiones 1/2 | 2607 → t6: 3004 | 0 | 0.032 | mem_fecha_v054b_20261010_172426.json |
| 2026-10-10 17:26 | 0.5.3+6d07083e | fecha_v054c | 0/2 | multi_session 0/1, temporal 0/1 | 1-5 0/2 | entre sesiones 0/2 | 2607 → t6: 2979 | 0 | 0.031 | mem_fecha_v054c_20261010_172639.json |
| 2026-10-10 17:29 | 0.5.3+6d07083e | fecha_v054d | 0/4 | multi_session 0/2, temporal 0/2 | 1-5 0/4 | entre sesiones 0/4 | 2607 → t6: 3034 | 0 | 0.07 | mem_fecha_v054d_20261010_172920.json |
| 2026-10-10 17:33 | 0.5.3+6d07083e | fecha_v054e | 0/4 | multi_session 0/2, temporal 0/2 | 1-5 0/4 | entre sesiones 0/4 | 2607 → t6: 3179 | 0 | 0.076 | mem_fecha_v054e_20261010_173311.json |
| 2026-10-10 17:36 | 0.5.3+6d07083e | fecha_v054f | 3/4 | multi_session 2/2, temporal 1/2 | 1-5 3/4 | entre sesiones 3/4 | 2607 → t6: 3054 | 0 | 0.063 | mem_fecha_v054f_20261010_173632.json |
| 2026-10-10 20:15 | 0.6.2+b93b09f8 | larga50_v062 | 4/4 | abstention 1/1, extraction 3/3 | 16+ 3/3, ? 1/1 | ? 1/1, misma conversacion 3/3 | 3077 → t49: 5699 | 0 | 0.256 | mem_larga50_v062_20261010_201531.json |
| 2026-10-11 16:29 | 0.9.8+84209035 | base_prefs_v098 | 4/8 | goal 2/4, observed 2/2, preference 0/2 | 1-5 4/8 | entre sesiones 4/8 | 2648 → t5: 2804 | 1 | 0.085 | mem_base_prefs_v098_20261011_162956.json |
| 2026-10-11 16:34 | 0.9.8+35fd1c69 | prefs_v099 | 9/12 | goal 5/6, observed 3/3, preference 1/3 | 1-5 9/12 | entre sesiones 9/12 | 2638 → t5: 2882 | 0 | 0.113 | mem_prefs_v099_20261011_163427.json |
| 2026-10-11 16:37 | 0.9.8+4d27b8a5 | prefs_v099b | 0/4 | preference 0/4 | 1-5 0/4 | entre sesiones 0/4 | 2682 → t4: 2785 | 0 | 0.073 | mem_prefs_v099b_20261011_163746.json |
| 2026-10-11 16:46 | 0.9.8+35fd1c69 | prefs_v099c | 12/16 | goal 7/8, observed 4/4, preference 1/4 | 1-5 12/16 | entre sesiones 12/16 | 2641 → t5: 2854 | 2 | 0.185 | mem_prefs_v099c_20261011_164633.json |

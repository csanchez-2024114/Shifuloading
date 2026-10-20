# Lista de paridad del CRM (fase 0 del plan del núcleo de Alan)

Generada del código el 19-oct-2026 (rama crm de crm-agente0, a partir de david 87c3902). Una fila por pieza: dónde vive hoy, a dónde va y qué la cubre. Ninguna fase se cierra con filas sin destino o sin cobertura.

Estado de las columnas: **Destino** según el plan (§2); **Cubierto** = pruebas sin IA que la ejercitan (por nombre en tests/crm) y, cuando aplica, el banco con IA real.

## Módulos y funciones públicas

| Módulo | Funciones/clases públicas | Destino | Pruebas que las nombran |
|---|---|---|---|
| `adaptador_lab` | 8 | packs/crm (igual) | 8/8 |
| `adjuntos` | 6 | files/ de Alan + pack (columnas, logo) | 2/6 |
| `afirma` | 3 | packs/crm (igual) | 1/3 |
| `agente` | 9 | packs/crm/sesion (Sesion); bucle → middlewares | 8/9 |
| `agente_diseno` | 12 | profiles/crm (BucleCRM) + packs/crm/sesion | 6/12 |
| `asignar` | 2 | packs/crm (igual) | 2/2 |
| `automatizaciones` | 6 | pack (en pausa) | 3/6 |
| `chat` | 3 | packs/crm (igual) | 3/3 |
| `colecciones` | 1 | packs/crm (igual) | 1/1 |
| `conceptos` | 9 | packs/crm (igual) | 7/9 |
| `diseno` | 11 | packs/crm (igual) | 8/11 |
| `edicion` | 5 | packs/crm (igual) | 3/5 |
| `ejemplos` | 9 | packs/crm (igual) | 6/9 |
| `estructura` | 27 | packs/crm (igual) | 20/27 |
| `generador` | 1 | packs/crm (igual) | 1/1 |
| `lienzo` | 7 | packs/crm (igual) | 7/7 |
| `marca` | 5 | packs/crm (igual) | 3/5 |
| `memoria` | 20 | packs/crm/conversacion + checkpointer (fase 4) | 19/20 |
| `operaciones` | 17 | packs/crm (igual) | 13/17 |
| `pantalla` | 19 | packs/crm (igual) | 7/19 |
| `plantillas` | 13 | packs/crm (igual) | 13/13 |
| `por_hacer` | 10 | packs/crm (igual) | 7/10 |
| `primer_diseno` | 19 | packs/crm (igual) | 12/19 |
| `puntos` | 7 | packs/crm (igual) | 5/7 |
| `regional` | 4 | packs/crm (igual) | 3/4 |
| `registros` | 8 | packs/crm (igual) | 4/8 |
| `reloj` | 1 | pack + workers del producto | 1/1 |
| `repositorio` | 13 | packs/crm/repos (pymongo sync, fase 4) | 5/13 |
| `responder_lab` | 1 | packs/crm (igual) | 0/1 |
| `secciones` | 1 | packs/crm (igual) | 1/1 |
| `secciones_v` | 5 | packs/crm (igual) | 5/5 |
| `seleccion` | 1 | packs/crm (igual) | 0/1 |
| `sembrar` | 9 | packs/crm (igual) | 7/9 |
| `toma` | 21 | packs/crm (igual) | 19/21 |
| `topes` | 0 | packs/crm (igual) | 0/0 |
| `traza` | 10 | tracing/TurnRecorder de Alan + pack | 5/10 |
| `validar` | 5 | packs/crm (igual) | 5/5 |
| `valores` | 16 | packs/crm (igual) | 8/16 |
| `vista` | 3 | packs/crm (igual) | 2/3 |
| `web` | 5 | pack (httpx sync) | 4/5 |

## Herramientas que ve el modelo

| Herramienta | Destino | Pruebas que la nombran |
|---|---|---|
| `abrir_seccion` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 4 |
| `agendar` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 12 |
| `agregar_bloque` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 33 |
| `agregar_campo` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 13 |
| `agregar_registro` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 56 |
| `agregar_tarea` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 23 |
| `agregar_vendedor` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 6 |
| `borrar_registro` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 15 |
| `buscar_en_internet` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 5 |
| `cambiar_ficha` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 2 |
| `cambiar_marca` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 5 |
| `cambiar_opciones_estado` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 5 |
| `cambiar_rangos` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 0 |
| `cambiar_tamano` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 2 |
| `cambiar_tarea` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 3 |
| `cambiar_tarjeta` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 2 |
| `cambiar_visual` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 7 |
| `consultar_datos` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 7 |
| `crear_seccion` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 29 |
| `definir_etapas` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 2 |
| `definir_opciones` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 2 |
| `deshacer` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 24 |
| `editar_registro` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 23 |
| `eliminar_tarea` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 1 |
| `leer_enlace` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 4 |
| `mostrar_seccion` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 1 |
| `mover_bloque` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 1 |
| `mover_campo` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 2 |
| `mover_tarea` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 1 |
| `quitar_bloque` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 8 |
| `quitar_campo` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 8 |
| `quitar_seccion` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 18 |
| `recordar` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 5 |
| `recordar_ciudad` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 2 |
| `renombrar_campo` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 4 |
| `renombrar_seccion` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 4 |
| `restablecer_marca` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 1 |
| `usar_logo` | BucleCRM (fase 2) → CercoCrm/wrap_tool_call (fase 3) | 6 |

## Rutas HTTP

| Archivo | Método y ruta | Destino |
|---|---|---|
| `crmRoutes.py` | POST `/seguimiento` | profiles/crm/routes.py, mismo contrato (fase 5) |
| `crmRoutes.py` | POST `/siguiente-pregunta` | profiles/crm/routes.py, mismo contrato (fase 5) |
| `crmRoutes.py` | POST `/contactos` | profiles/crm/routes.py, mismo contrato (fase 5) |
| `crmRoutes.py` | PATCH `/contactos/{contacto_id}` | profiles/crm/routes.py, mismo contrato (fase 5) |
| `crmRoutes.py` | DELETE `/contactos/{contacto_id}` | profiles/crm/routes.py, mismo contrato (fase 5) |
| `crmRoutes.py` | POST `/listas/{lista_id}/registros` | profiles/crm/routes.py, mismo contrato (fase 5) |
| `crmRoutes.py` | POST `/listas/{lista_id}/registros/lote` | profiles/crm/routes.py, mismo contrato (fase 5) |
| `crmRoutes.py` | DELETE `/listas/{lista_id}/registros` | profiles/crm/routes.py, mismo contrato (fase 5) |
| `crmRoutes.py` | DELETE `/listas/{lista_id}/importaciones` | profiles/crm/routes.py, mismo contrato (fase 5) |
| `crmRoutes.py` | DELETE `/listas/{lista_id}/importaciones/{lote_id}` | profiles/crm/routes.py, mismo contrato (fase 5) |
| `crmRoutes.py` | PATCH `/listas/{lista_id}/registros/{registro_id}` | profiles/crm/routes.py, mismo contrato (fase 5) |
| `crmRoutes.py` | DELETE `/listas/{lista_id}/registros/{registro_id}` | profiles/crm/routes.py, mismo contrato (fase 5) |
| `crmRoutes.py` | POST `/tareas` | profiles/crm/routes.py, mismo contrato (fase 5) |
| `crmRoutes.py` | PATCH `/tareas/{tarea_id}` | profiles/crm/routes.py, mismo contrato (fase 5) |
| `crmRoutes.py` | DELETE `/tareas/{tarea_id}` | profiles/crm/routes.py, mismo contrato (fase 5) |
| `crmRoutes.py` | PUT `/automatizaciones/{auto_id}` | profiles/crm/routes.py, mismo contrato (fase 5) |
| `crmRoutes.py` | PUT `/secciones/{seccion_id}` | profiles/crm/routes.py, mismo contrato (fase 5) |
| `crmRoutes.py` | POST `/registros/ejemplos/quitar` | profiles/crm/routes.py, mismo contrato (fase 5) |
| `crmRoutes.py` | GET `/puntos` | profiles/crm/routes.py, mismo contrato (fase 5) |
| `crmRoutes.py` | POST `/deshacer` | profiles/crm/routes.py, mismo contrato (fase 5) |
| `crmRoutes.py` | POST `/chat` | profiles/crm/routes.py, mismo contrato (fase 5) |
| `crmRoutes.py` | GET `/logo/{logo_id}` | profiles/crm/routes.py, mismo contrato (fase 5) |
| `crmRoutes.py` | GET `/chat/historial` | profiles/crm/routes.py, mismo contrato (fase 5) |
| `crmRoutes.py` | GET `/memoria` | profiles/crm/routes.py, mismo contrato (fase 5) |
| `crmRoutes.py` | DELETE `/chat` | profiles/crm/routes.py, mismo contrato (fase 5) |
| `labRoutes.py` | POST `/lab/chat` | profiles/crm/routes.py, mismo contrato (fase 5) |

## Colecciones de Mongo

- `users` (USERS)
- `user_notifications` (USER_NOTIFICATIONS)
- `crm_workspaces` (CRM)
- `crm_conversaciones` (CRM_CONVERSACIONES)
- `crm_puntos` (CRM_PUNTOS)
- `crm_logos` (CRM_LOGOS)

## Variables de entorno que lee el CRM

- `CRM_AGENT_MODEL`
- `CRM_DISENO`
- `CRM_IA`
- `CRM_LAB_ADAPTER`
- `CRM_RELOJ_SEGUNDOS`
- `CRM_SEGUIMIENTO_DIARIO`
- `CRM_TRAZA`
- `CRM_TRAZA_DIR`
- `CRM_UTC_OFFSET`
- `TAVILY_API_KEY`

## Catálogos

- `conceptos.json`
- `fuentes.json`
- `graficos.json`
- `iconos.json`
- `pestanas.json`
- `plantillas.json`
- `rubros_grok.json`
- `rubros_semilla.json`
- `vistas.json`

## Pantalla (React) y laboratorio

- `src/App.jsx`
- `src/components/BuscadorGlobal.jsx`
- `src/components/CapturaPantalla.jsx`
- `src/components/Iconos.jsx`
- `src/components/ImportarALista.jsx`
- `src/components/Logo.jsx`
- `src/components/Nav.jsx`
- `src/components/PanelAnalisis.jsx`
- `src/components/ProductShowcase.jsx`
- `src/components/ShifuAvatar.jsx`
- `src/components/TextoChat.jsx`
- `src/components/home/Hero.jsx`
- `src/components/home/Plataforma.jsx`
- `src/components/home/Secciones.jsx`
- `src/crm/plantillas/ChatDiseno.jsx`
- `src/crm/plantillas/DisenoCrm.jsx`
- `src/crm/plantillas/LogoNegocio.jsx`
- `src/main.jsx`
- `src/pages/BriefPage.jsx`
- `src/pages/CrmPage.jsx`
- `src/pages/HomePage.jsx`
- `src/pages/InfoDesarrolladores.jsx`
- `src/pages/InfoIntegraciones.jsx`
- `src/pages/LoginPage.jsx`
- `src/pages/PanelPage.jsx`
- `src/pages/RegistroPage.jsx`
- laboratorio: 155 archivos; bancos: banco2, banco_citas, banco_conceptos, banco_creacion, banco_datos, banco_deshacer, banco_ficha, banco_memoria, banco_pestanas, banco_toma

## Bancos con IA real (compuerta de cada fase)

Línea base (19-oct, gpt-4.1-mini, 1–2 corridas válidas; la 3.ª se cortó por falta de crédito): datos 63/63 · citas 8–9/9 · deshacer 17/18 · pestañas 23/27 · banco2 14/16 · conceptos 9–10/14 · memoria 18/18 · toma 11/11 · ficha 7/7 · creación 6/6. Resultados en documentos/mediciones/linea_base_agente0/ (Shifuloading).

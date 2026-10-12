# Contrato con el servidor de Shifu

La interfaz está lista para conectarse. Todo el acceso a datos pasa por `src/api/index.js`; las pantallas no usan `fetch` ni `localStorage` para esto.

## Cómo conectarlo

1. Copia `.env.example` a `.env` y escribe la dirección del servidor: `VITE_API_URL=https://api.shifu.example`.
2. Reinicia `npm run dev`. Con esa variable la interfaz usa el servidor real; sin ella usa el **servidor simulado** (`src/api/mock/`), que guarda todo en el navegador y puede borrarse al terminar.
3. Si el servidor está en otro dominio, debe permitir CORS para el origen de la interfaz y las cabeceras `Content-Type` y `Authorization`.

## Reglas generales

- JSON en ambos sentidos. Con sesión, cabecera `Authorization: Bearer <token>` (el token se guarda al iniciar sesión).
- Errores: estado HTTP adecuado y `{ "mensaje": "texto para mostrar" }`. `404` en `GET /crm` significa "esta persona aún no tiene CRM".
- **Toda ruta que cambia el CRM devuelve el CRM completo y actualizado** (forma de abajo). La pantalla solo lo reemplaza.
- Los ids son cadenas, los asigna el servidor.

## Rutas

| Método y ruta | Cuerpo | Respuesta |
|---|---|---|
| `POST /auth/correo` | `{ correo }` | `{ existe: boolean, token?: string }` (token solo si ya tiene cuenta) |
| `GET /crm` | — | CRM · `404` si no tiene |
| `POST /crm` | `{ brief }` (respuestas del cuestionario, ver abajo) | CRM nuevo, armado por Shifu a partir del brief |
| `DELETE /crm` | — | `204` (para repetir el cuestionario) |
| `POST /crm/contactos` | `{ filas: [{ n, det? }], canal, texto? }` | CRM (alta de uno o varios; `texto` es la frase que queda en Actividad) |
| `PATCH /crm/contactos/:id` | campos a cambiar (`etapa`, `n`, `dueno`…) | CRM |
| `DELETE /crm/contactos/:id` | — | CRM |
| `POST /crm/tareas` | `{ t }` | CRM (entra en la columna `porHacer`) |
| `PATCH /crm/tareas/:id` | `{ columna: "porHacer" \| "enCurso" \| "hecho" }` | CRM |
| `DELETE /crm/tareas/:id` | — | CRM |
| `PUT /crm/automatizaciones/:id` | `{ on: boolean }` | CRM |
| `PUT /crm/secciones/:id` | `{ nombre }` (renombra una sección) | CRM |
| `POST /chat` | `{ texto, contexto?: { pendiente? } }` | `{ respuesta, crm, vista?, pendiente? }` |

### Chat

El chat flotante manda lo que escribe la persona. El servidor (con la IA de Shifu) decide qué hacer: agregar, modificar o eliminar contactos y tareas, renombrar secciones, activar o apagar automatizaciones. Debe responder:

- `respuesta`: texto que Shifu dice.
- `crm`: el CRM ya con los cambios aplicados.
- `vista` (opcional): sección que conviene abrir (`contactos`, `desarrollo`, `importar`, `automatizaciones`…).
- `pendiente` (opcional): si antes de borrar pide confirmación, devuelve aquí lo que quedó por confirmar. La interfaz lo reenvía tal cual en `contexto.pendiente` con el siguiente mensaje ("sí" confirma, cualquier otra cosa cancela).

La lógica de ejemplo está en `src/api/mock/chat.js`.

## Forma del CRM

```json
{
  "brief": { "...respuestas del cuestionario..." },
  "totalContactos": 120,
  "contactos": [{ "id": "", "n": "Ana Morales", "det": "5555-1234", "canal": "WhatsApp", "etapa": "Nuevo", "dueno": "Tú", "dias": 0 }],
  "vendedores": ["Tú", "Mariana Solís"],
  "tareas": { "porHacer": [{ "id": "", "t": "" }], "enCurso": [], "hecho": [] },
  "eventos": [{ "id": "", "e": "➕", "t": "Agregaste a Ana Morales", "h": "ahora" }],
  "automatizaciones": [{ "id": "recordatorios", "pilar": "Estructura", "t": "", "d": "", "on": true }],
  "secciones": { "contactos": "Pacientes" }
}
```

- `contactos` es la parte visible (los primeros); `totalContactos` es el total real. `etapa` ∈ `Nuevo`, `En contacto`, `Interesado`, `Cliente`. `dias` son los días desde el último contacto.
- `secciones` solo trae los nombres que la persona cambió; los demás salen del rubro (`src/crm/secciones.js`).
- `eventos`, del más nuevo al más viejo, es lo que muestra la sección de actividad.

## Brief (respuestas del cuestionario)

Las preguntas y los valores posibles están en `src/brief/preguntas.js`. Forma: `nombre`, `ubicacion: { pais, ciudad? }`, `rubro`, `tiempo`, `canales[]`, `cartera`, `ciclo`, `problemas[]`, `equipo`, `herramientas[]`, `objetivos[]` (sin límite), `dolor`, `armado`, `autonomia`, `presupuesto`.
El avance del cuestionario se guarda en el navegador mientras se contesta; solo al terminar viaja al servidor con `POST /crm`.

## Pendiente de definir en el servidor

- Cobros (la pantalla usa datos de ejemplo todavía).
- Pantalla `/panel` (asistente de inicio): su chat sigue respondiendo con texto fijo; falta conectarlo a `POST /chat`.
- Lectura de archivos `.xlsx` (hoy se pega o se sube CSV/TXT y se interpreta en el navegador).
- Inicio de sesión completo (contraseña, Google, etc.): hoy solo existe el primer paso por correo.

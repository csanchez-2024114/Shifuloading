# Encargo para Cursor: vistas nuevas del laboratorio (herramientas que la persona puede pedir)

Trabajas en el repo Shifuloading, rama `david`. **NO hagas commit ni push.**

**Solo puedes CREAR estos tres archivos:**
- `laboratorio/src/plantillas/vistas-extra.jsx`
- `laboratorio/src/plantillas/vistas-extra.css`
- `laboratorio/src/lab/VistasExtraPage.jsx`

**No edites ningún archivo existente.** Otra persona está tocando `vistas.jsx`, `validar.js`, `edicion.js`, `PlantillaCRM.jsx` y `chat.js` al mismo tiempo; la integración la hacemos nosotros.

## Contexto
Shifu es un CRM/ERP que cada usuario arma por chat. Cada pestaña es un cuaderno en blanco y estas vistas son **herramientas que aparecen cuando la persona las pide** (por ejemplo, "quiero ver mis pagos en un calendario").

**Antes de escribir, lee completos estos archivos y copia su patrón:**
- `laboratorio/src/plantillas/vistas.jsx`: componentes Tabla, Kpis, Tablero, Agenda, Vencimientos, y los helpers `ver`, `region`, `useConSalida`, `AnimarContext`, `FichaContext`, `abrible`, COLORES, MESES, DIAS.
- `laboratorio/src/plantillas/validar.js`: `VISTAS` define qué opciones pide cada vista.
- `laboratorio/src/plantillas/plantillas.css`: clases `pl-*`, container queries `@container bloque` y tokens `var(--tx)`, `--tx3`, `--card`, `--panel`, `--linea`, `--acento`, `--fuente`.

## Contrato de cada vista
- Firma: `function X({ seccion, campos, registros, opciones, datos })`.
- **Solo dibuja.** Nunca llama a la API. Todo número sale de contar `registros` (`r.valores[campoId]`), nada escrito a mano.
- Un registro abre su ficha. Para eso, reimplementa `abrible` igual que en `vistas.jsx`: `useContext(FichaContext)` y `role="button"`, `tabIndex`, `data-abre`, `onClick(e)` con `abrir(seccion.id, r.id, e.currentTarget)`. Importa `FichaContext` desde `./vistas`.
- Sin registros: muestra un estado vacío corto. Copia el patrón de `Vacio` (clase `mc-vacio-grande pl-vacio`).
- **Nunca se rompe:**
  - usa solo container queries (`@container bloque (max-width: …)`);
  - nada debe salirse del bloque, encimarse ni partir palabras;
  - textos largos con «…» y `title` con el texto completo;
  - con muchos datos, tope y «+N más», o scroll interno.

  Se prueba en bloques de 220×170, 340×260, 520×360 y 900×380, con 0, 1, 8 y 220 registros y nombres de 80 letras.
- Usa los mismos tokens y estilos que el resto. Nada de colores nuevos fuera de COLORES y los tokens. Debe verse bien en tema claro y oscuro.
- Exporta `export const VISTAS_EXTRA = { nombre: { requiere: {...}, opcional: {...} } }` con el mismo formato que `VISTAS` de `validar.js`, y `export const COMPONENTES_EXTRA = { nombre: Componente }`.

## Las vistas
1. **`calendario`**: mes completo en rejilla de 7 columnas (lunes a domingo).
   - Opciones: `fecha` (requerida, campo fecha), `titulo`, `estado` (opcional: colorea el punto), `mes` (opcional, `YYYY-MM`; por defecto el actual).
   - Flechas para cambiar de mes y botón "Hoy". Cada día muestra hasta 3 registros y «+N».
   - Aviso abajo: "N registros sin fecha no aparecen".
   - En bloque angosto pasa a lista por día.
2. **`tablero_dinero`**: como `Tablero`, pero cada columna muestra conteo y **total** (`suma`, campo dinero o número), formateado con `ver('dinero', …)`.
   - Cada tarjeta muestra los días que lleva en la etapa (`dias_en`: campo fecha opcional; si no viene, no se muestra): gris normal, ámbar desde 20 días y rojo desde 30.
   - Opciones: `por` (estado, requerida), `suma` (requerida), `titulo`, `detalle`, `dias_en`.
3. **`cifra`**: una tarjeta grande con un solo número.
   - Opciones: `funcion` (conteo | suma | promedio), `valor` (campo número o dinero si no es conteo), `filtro` opcional `{campo, igual}`, `meta` (número opcional: barra de progreso con color verde ≥100 %, gris 50-99 %, rojo <50 %), `fecha` (campo fecha opcional para la tendencia), `periodo` (mes | semana; por defecto mes), `ayuda` (texto opcional: ícono "?" con `title`).
   - **Tendencia:** compara el periodo actual contra el anterior usando `fecha` y muestra ▲/▼ con el %.
4. **`atencion`**: panel de lo que necesita atención de la sección.
   - Opciones: `fecha` (requerida), `estado` y `excluir` (estados terminados).
   - Tres contadores grandes: "Vencidos", "Vencen en 7 días" y "Vencen en 30 días". Abajo, la lista de los 5 más urgentes.
5. **`franjas`**: bandeja priorizada por franjas plegables, con color y numeración continua.
   - Opciones: `fecha` (próxima fecha, requerida), `estado` (opcional), `titulo`, `detalle`, `urgentes` (lista de opciones de estado que van primero).
   - Franjas:
     - "Atender ahora": estado en `urgentes` y fecha ≤ hoy.
     - "Vencidos".
     - "Hoy y mañana".
     - "Próximos 7 días".
     - "Más adelante".
     - "Sin fecha".
6. **`matriz`**: filas = valores distintos de un campo texto (`filas`), columnas = opciones de un campo estado (`columnas`), celda = conteo.
   - Encabezado con total por columna y % de la fila con mayor conteo.
   - Opciones: `filas` (texto, requerida), `columnas` (estado, requerida).
   - Tope de 12 filas y «+N filas más».

## Página de prueba
`laboratorio/src/lab/VistasExtraPage.jsx` exporta por defecto `function VistasExtraPage({ plantilla, datos, tema })`.
- Para la primera sección con campos de la plantilla, elige opciones razonables según los tipos de sus campos.
- Dibuja cada vista nueva dentro de `<section className="pl-bloque">` en 4 tamaños (220×170, 340×260, 520×360, 900×380), envuelto en `<div className="mc pl" data-tema={tema} data-estilo="vivo" data-densidad="compacto">`.
- Importa `vistas-extra.css`, `@base/crm.css`, `@base/crm-extra.css`, `../plantillas/plantillas.css` y `../plantillas/estilos.css`.
- **No la conectes a ninguna ruta:** eso lo hacemos nosotros.

## Cómo comprobar antes de entregar
Desde `/Users/josueboror/CURSOR/HyperShifu/Shifuloading`, corre `npx vite build --config laboratorio/vite.config.js --outDir /tmp/vx --emptyOutDir`. Debe compilar sin errores.

Al final responde con: la lista de archivos, qué hace cada vista en una línea, y cualquier duda o límite que encontraste. No afirmes que probaste algo que no probaste.

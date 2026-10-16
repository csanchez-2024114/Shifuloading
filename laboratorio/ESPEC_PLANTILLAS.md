# Cómo crear una plantilla de la biblioteca (para agentes)

Contexto: CRM "Shifu" para pymes de LatAm. Las plantillas son **datos**: definen qué secciones tiene un CRM, sus campos y qué se ve en la
pantalla de inicio. NO llevan datos de clientes. El usuario después modifica todo por chat; la plantilla es su punto de partida.

## Reglas de trabajo
- Crea **un archivo por plantilla** en `laboratorio/src/plantillas/biblioteca/<id>.js`, con `export default { ... }`, y el `id` igual al nombre del archivo (kebab-case, sin acentos).
- **No edites ningún otro archivo.** No hagas commit ni push.
- Usa como referencia exacta `laboratorio/src/plantillas/biblioteca/taller-mecanico.js`. Lee también `semillas.js`, `validar.js` y `graficos.jsx` (la parte de `GRAFICOS`, `CLASES` y `compatibles`).
- **Filtro de calidad obligatorio:** desde `/Users/josueboror/CURSOR/HyperShifu/Shifuloading` corre `node laboratorio/servidor/calidad.mjs <id>` y corrige hasta que salga ✓. Una plantilla que no pasa no se entrega.
- Todo va en **español neutro** (de "tú"), con nombres cortos y claros para alguien que no sabe de CRM.

## Forma
```js
{
  id, nombre, para,                         // "para": una frase de para quién es
  asignacion: {                             // con esto el sistema la elige según el cuestionario
    rubros: [...],                          // servicios | agencia | comercio | salud | educacion | tecnologia | inmobiliaria | otro
    ciclos: [...],                          // cotizacion | rapida | recurrente | mezcla
    objetivos: [...],                       // seguimientos | contactos | ia | reportes | cotizaciones | equipo | integraciones
    negocios: ['...', '...', '...'],        // 3+ negocios reales para los que sirve
  },
  inicio: [ { vista, seccion, opciones, ancho, alto }, ... ],   // 3 a 6 bloques
  secciones: [ { id, titulo, grupo, icono, vista, opciones?, campos: [...] }, ..., ...fijas ],
}
```

- **Campos:** `{ id, nombre, tipo }`, con tipo `texto`, `numero`, `dinero`, `fecha`, `hora` o `estado` (este último con `opciones: [3-7 valores en orden de avance]`).
  - Los de tipo **texto** llevan `ejemplos: [5+ valores realistas del rubro]`. Las excepciones son `nombre`, `telefono`, `cliente` y `empresa`.
  - Los de tipo **numero**, **dinero** y **fecha** pueden llevar `rango: [min, max]`. En las fechas el rango son días relativos a hoy, por ejemplo `[-30, 15]`.
  - Máximo 8 campos por sección.
- **Secciones:** al menos 3 con campos.
  - `grupo` puede ser 0 (Estructura), 1 (Medición y equipo) o 2 (Automatizaciones).
  - `icono` puede ser: usuarios, calendario, caja, tarjeta, tablero, tabla, actividad, equipo, rayo, documento, camion o reloj.
  - `vista` de una sección: tabla, tablero (`opciones.por` = campo estado), agenda (`opciones.fecha`, `hora`, `titulo`, `detalle`) o vencimientos (`opciones.fecha`, `titulo`, `detalle`, `dias`, `estado`, `excluir`).
  - Termina siempre con las 3 secciones fijas (Historial, Equipo y Automatizaciones), como en el ejemplo.
- **Inicio:**
  - Vistas posibles: `kpis` (opciones: `por`, `suma`, `vencen` + `dias`, `hoy`), `tablero`, `agenda`, `vencimientos`, `tabla` y `grafico` (`opciones.tipo` = un id del catálogo que sea **compatible** con los campos de esa sección; hay 43 tipos).
  - **Al menos un `grafico`.**
  - La rejilla tiene 12 columnas: `ancho` puede ser 3, 4, 6, 8 o 12, y `alto` de 1 a 4. El `kpis` siempre ocupa una fila.
  - **Máximo 5 filas** y casi sin huecos: debe caber en una pantalla.
- **Diseño:** elige vistas y gráficos que respondan a lo que ese negocio necesita ver a diario (qué vence, qué está en curso, cuánto dinero, quién sigue). Evita gráficos decorativos.

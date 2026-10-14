/* Estilos visuales del laboratorio. Todos usan los MISMOS colores y los mismos contenedores redondeados del CRM base;
 * solo cambian distribución, tipografía, espacio, sombra y animación. El CSS de cada uno vive en estilos.css bajo [data-estilo]. */
/* Decidido 2026-10-14: Vivo + Compacto con animación lenta. Los demás quedan ocultos (oculto: true), no borrados. */
export const ESTILOS = [
  { id: 'vivo-compacto', base: 'vivo', densidad: 'compacto', nombre: '★ Vivo + Compacto', idea: 'Animado e interactivo, con mucha información por pantalla' },
  { id: 'vivo-nube', oculto: true, base: 'vivo', densidad: 'nube', nombre: '★ Vivo + Nube', idea: 'Animado e interactivo, aireado y con sombra suave' },
  { id: 'actual', oculto: true, base: 'actual', nombre: 'Actual', idea: 'El laboratorio tal como está hoy (referencia)' },
  { id: 'nube', oculto: true, base: 'nube', densidad: 'nube', nombre: '1 · Nube', idea: 'Aireado: más espacio, sombra suave, tarjetas que flotan y entran en cascada' },
  { id: 'compacto', oculto: true, base: 'compacto', densidad: 'compacto', nombre: '2 · Compacto', idea: 'Denso: KPIs en una sola franja, filas bajas, más datos por pantalla' },
  { id: 'riel', oculto: true, base: 'riel', nombre: '3 · Riel', idea: 'Menú arriba como píldoras, inicio a 3 columnas, todo el ancho para los datos' },
  { id: 'vivo', oculto: true, base: 'vivo', nombre: '4 · Vivo (solo)', idea: 'Animado, densidad normal: barras que crecen, dona que se dibuja, hoy que late, tarjetas que reaccionan' },
  { id: 'enfoque', oculto: true, base: 'enfoque', nombre: '5 · Enfoque', idea: 'Editorial tipo bento: menú de solo iconos, números grandes, bloques de distinto tamaño' },
]

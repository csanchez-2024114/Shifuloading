/* Piezas de dibujo del CRM que comparten el laboratorio (PlantillaCRM) y el CRM de Carlos (src/crm/plantillas):
 * el lienzo de bloques (inicio o pestaña con lienzo propio), la vista de una sección y cómo se dibuja cada vista.
 * Solo dibujan: no guardan estado ni llaman a la API. Los estilos los carga quien las usa (plantillas.css y compañía). */
import { COMPONENTES } from './vistas'
import { COMPONENTES_EXTRA } from './vistas-extra'
import { camposDe } from './validar'
import { registrosDe } from './datosEjemplo'
import { Grafico, GRAFICOS } from './graficos'

export const TITULO_VISTA = { kpis: 'Resumen', tablero: 'Por etapa', agenda: 'Próximos días', vencimientos: 'Por vencer', grafica: 'Gráfica', tabla: 'Lista', calendario_mes: 'Calendario', tablero_dinero: 'Por etapa y monto', cifra: 'Cifra', atencion: 'Atención', franjas: 'Por atender', matriz: 'Cruce' }
/** Título de un bloque: su vista (o el nombre del gráfico) y la sección de la que sale. */
export const nombreBloque = (w, porId) => `${w.vista === 'grafico' ? GRAFICOS[w.opciones?.tipo]?.nombre || 'Gráfico' : TITULO_VISTA[w.vista] || w.vista} · ${porId[w.seccion]?.titulo ?? ''}`

const ANCHO_COMPLETO = ['kpis', 'tablero', 'agenda']
/** Tamaño inicial: resumen, tablero y agenda a lo ancho; lo demás a media columna; si queda uno solo en su fila, a lo ancho. */
export function conTamano(bloques) {
  const medios = bloques.filter((b) => !ANCHO_COMPLETO.includes(b.vista))
  const solo = medios.length % 2 === 1 ? medios[medios.length - 1].uid : null
  return bloques.map((b) => ({ ...b,
    ancho: b.ancho || (ANCHO_COMPLETO.includes(b.vista) || b.uid === solo ? 12 : 6),
    alto: b.alto || (b.vista === 'kpis' ? 1 : b.vista === 'tablero' || b.vista === 'agenda' ? 2 : 2) }))
}

/** Arma `dibujar(seccion, vista, opciones)`: la vista con los datos reales o, si la sección no tiene registros, su forma
 * «sombría» (D25) con datos fantasma apagados y un mensaje encima (los datos fantasma no se leen ni se pueden tocar). */
export function hacerDibujar({ porId, datos, fantasma }) {
  const dibujarCon = (s, nombreVista, opciones, d) => {
    if (nombreVista === 'grafico') return <Grafico key={opciones?.tipo} tipo={opciones?.tipo} seccion={s} campos={camposDe(s, porId)} registros={registrosDe(s, d)} opciones={opciones || {}} />
    const V = COMPONENTES[nombreVista] || COMPONENTES_EXTRA[nombreVista]
    return V ? <V seccion={s} campos={camposDe(s, porId)} registros={registrosDe(s, d)} opciones={opciones || {}} datos={d} /> : null
  }
  return (s, nombreVista, opciones) => {
    // Un bloque cuya sección se acaba de quitar sigue unos instantes en pantalla (animación de salida): se dibuja vacío.
    if (!s) return null
    const sinDatos = (s.campos || s.fuente) && !registrosDe(s, datos).length
    if (!sinDatos || !fantasma) return dibujarCon(s, nombreVista, opciones, datos)
    return (
      <div className="pl-sombra">
        <div className="pl-sombra-forma" aria-hidden="true" inert="">{dibujarCon(s, nombreVista, opciones, fantasma)}</div>
        <p className="pl-sombra-msg"><b>Todavía no hay datos</b><span>Usa «Agregar» en {s.titulo} o díselo a Shifu, y aparece aquí.</span></p>
      </div>
    )
  }
}

/** Lienzo de bloques en la rejilla de 12 columnas: el inicio (con animación de salida y de lo nuevo) o el de una pestaña. */
export function Lienzo({ bloques, porId, dibujar, saliendo = [], animado = false, pagina = false }) {
  return (
    <div className={pagina ? 'pl-inicio pl-pagina' : 'pl-inicio'}>
      {bloques.map((w, i) => (pagina
        ? (
          <section key={w.uid} className={`pl-bloque pl-bloque-${w.vista}`} data-bloque={w.uid} style={{ '--i': i, '--ancho': w.ancho, '--alto': w.alto, viewTransitionName: `pl-${w.uid}` }} data-ancho={w.ancho}>
            <h2>{nombreBloque(w, porId)}</h2>
            {dibujar(porId[w.seccion], w.vista, w.opciones)}
          </section>
        )
        : (
          <section key={w.uid} className={`pl-bloque pl-bloque-${w.vista}${saliendo.includes(w.uid) ? ' saliendo' : ''}${w.nuevo ? ' nuevo' : ''}`} data-bloque={w.uid} data-animar={w.nuevo && animado ? '' : undefined} style={{ '--i': w.nuevo ? 0 : i, '--ancho': w.ancho, '--alto': w.alto, viewTransitionName: `pl-${w.uid}` }} data-ancho={w.ancho}>
            <h2>{nombreBloque(w, porId)}</h2>
            {dibujar(porId[w.seccion], w.vista, w.opciones)}
          </section>
        )))}
    </div>
  )
}

/** Lo que muestra una sección: su lienzo propio (D49) si lo tiene; si no, su vista de siempre. */
export function VistaSeccion({ seccion, porId, dibujar }) {
  if (!seccion.pagina) return <div className="pl-seccion">{dibujar(seccion, seccion.vista, seccion.opciones)}</div>
  if (!seccion.pagina.length) return <div className="mc-vacio-grande pl-vacio pl-pagina-vacia"><b>Esta pestaña está en blanco</b><p>Pídele a Shifu qué quieres ver aquí: una lista, un tablero, un calendario, una gráfica…</p></div>
  return <Lienzo bloques={seccion.pagina} porId={porId} dibujar={dibujar} pagina />
}

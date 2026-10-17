/* Recorrido de primera entrada (D24): la persona ve SU CRM (la estructura que salió de sus respuestas) con datos de ejemplo,
 * y Shifu le muestra cada parte. Al final se borran los datos de ejemplo y quedan las vistas "sombrías" hasta su primer dato.
 * Los textos los arma el código a partir de la plantilla (sin IA): rápido y siempre fiel a lo que hay en pantalla. */
import { useEffect, useLayoutEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import ShifuAvatar from '@base/components/ShifuAvatar'
import { GRAFICOS } from './graficos'

const QUE_ES = {
  kpis: (s) => `Arriba, el resumen de ${s}: los números se cuentan solos con lo que registras.`,
  tablero: (s) => `${s} por etapa. Cuando algo avanza, dímelo («pasa a Ana a Pagado») y muevo su tarjeta.`,
  vencimientos: (s) => `Lo que vence pronto en ${s}, ordenado por urgencia: así nada se te pasa.`,
  agenda: (s) => `Tu agenda de ${s} para los próximos días.`,
  tabla: (s) => `La lista de ${s}, con buscador y páginas.`,
  grafica: (s) => `Una gráfica de ${s} que se actualiza sola.`,
}

export function pasosDe(plantilla, bloques, porId) {
  const pasos = [{ sel: '.mc-cab', texto: `Este es tu CRM. Lo armé con tus respuestas. Por ahora tiene datos de ejemplo para que veas cómo se usa.` }]
  for (const b of bloques) {
    const s = porId[b.seccion]?.titulo || ''
    const texto = b.vista === 'grafico' ? `${GRAFICOS[b.opciones?.tipo]?.nombre || 'Gráfico'} de ${s}: se calcula solo con tus datos.` : (QUE_ES[b.vista] || ((x) => x))(s)
    pasos.push({ sel: `[data-bloque="${b.uid}"]`, texto })
  }
  const secciones = plantilla.secciones.filter((x) => x.campos).map((x) => x.titulo)
  pasos.push({ sel: '.mc-menu', texto: `En el menú están tus secciones: ${secciones.join(', ')}. Cada una se puede cambiar.` })
  pasos.push({ sel: '.mc-chat-panel, .mc-chat-btn', texto: 'Y aquí estoy yo. Todo se hace hablándome: tus datos («agrega a María López») y cualquier cambio de diseño (colores, logo, otra gráfica, secciones).' })
  pasos.push({ sel: null, final: true, texto: 'Eso es todo. ¿Borro los datos de ejemplo para que empieces con los tuyos? Las vistas quedarán en gris hasta tu primer registro.' })
  return pasos
}

export default function Recorrido({ pasos, onTerminar, onSaltar }) {
  const [i, setI] = useState(0)
  const [rect, setRect] = useState(null)
  const paso = pasos[i]
  useLayoutEffect(() => {
    const medir = () => { const el = paso.sel && document.querySelector(paso.sel); setRect(el ? el.getBoundingClientRect() : null) }
    // Lo que se señala tiene que verse: si está fuera de la pantalla (en el celular, casi todo), se lleva al centro primero.
    // Medido en la prueba de cliente: en 390 px los pasos de la dona, la agenda y la línea quedaban en negro, sin globo.
    const el = paso.sel && document.querySelector(paso.sel), r = el?.getBoundingClientRect()
    if (r && (r.top < 0 || r.bottom > window.innerHeight)) el.scrollIntoView({ block: r.height > window.innerHeight * 0.6 ? 'start' : 'center' })
    medir(); const t = setTimeout(medir, 450) // después de que la pantalla se acomode
    window.addEventListener('resize', medir); window.addEventListener('scroll', medir, true)
    return () => { clearTimeout(t); window.removeEventListener('resize', medir); window.removeEventListener('scroll', medir, true) }
  }, [paso])
  useEffect(() => {
    const tecla = (e) => { if (e.key === 'ArrowRight' && !paso.final) setI((x) => Math.min(pasos.length - 1, x + 1)); if (e.key === 'ArrowLeft') setI((x) => Math.max(0, x - 1)); if (e.key === 'Escape') onSaltar() }
    window.addEventListener('keydown', tecla); return () => window.removeEventListener('keydown', tecla)
  }, [paso, pasos.length, onSaltar])
  const m = 8
  const foco = rect && { top: rect.top - m, left: rect.left - m, width: rect.width + 2 * m, height: rect.height + 2 * m }
  // La burbuja va debajo del foco si cabe; si no, arriba; si tampoco (el menú ocupa todo el alto), al lado; sin foco, al centro.
  // Medido en la prueba de cliente: con el menú, «arriba» la dejaba fuera de la pantalla.
  const ALTO_B = 190, W = window.innerWidth, H = window.innerHeight
  const abajo = foco && foco.top + foco.height + ALTO_B < H
  const arriba = foco && !abajo && foco.top - ALTO_B > 0
  const lado = foco && !abajo && !arriba && (foco.left + foco.width + 372 < W ? foco.left + foco.width + 12 : Math.max(12, foco.left - 372))
  const burbuja = !foco ? { top: '50%', left: '50%', transform: 'translate(-50%, -50%)' }
    : lado !== false && lado !== undefined && !abajo && !arriba ? { top: Math.min(Math.max(12, foco.top + 12), H - ALTO_B), left: Math.min(lado, W - 372), transform: 'none' }
    : { top: abajo ? foco.top + foco.height + 12 : foco.top - 12, left: Math.min(Math.max(12, foco.left), W - 372), transform: abajo ? 'none' : 'translateY(-100%)' }
  const negritas = (t) => t.split('**').map((x, k) => (k % 2 ? <b key={k}>{x}</b> : x))
  return createPortal(
    <div className="rc" role="dialog" aria-modal="true" aria-label="Recorrido por tu CRM">
      <div className={`rc-foco${foco ? '' : ' sin'}`} style={foco || undefined} />
      <div className="rc-burbuja" style={burbuja} key={i}>
        <div className="rc-cab"><ShifuAvatar size={28} /><small>{i + 1} de {pasos.length}</small></div>
        <p>{negritas(paso.texto)}</p>
        <div className="rc-botones">
          {paso.final
            ? <><button type="button" onClick={onSaltar}>Mantener ejemplos</button><button type="button" className="si" onClick={onTerminar}>Borrar ejemplos y empezar</button></>
            : <><button type="button" onClick={onSaltar}>Saltar</button>{i > 0 && <button type="button" onClick={() => setI(i - 1)}>Atrás</button>}<button type="button" className="si" onClick={() => setI(i + 1)}>Siguiente</button></>}
        </div>
      </div>
    </div>,
    document.body,
  )
}

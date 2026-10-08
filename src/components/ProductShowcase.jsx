import { useEffect, useRef, useState } from 'react'
import Logo from './Logo'
import PanelAnalisis from './PanelAnalisis'
import ShifuAvatar from './ShifuAvatar'

/* Maqueta animada del CRM de Shifu con datos inventados: el dueño del negocio le pregunta a la IA (burbuja gris) por sus clientes y esta responde y agenda (el dueño es la burbuja azul).
 * Se repite sola. Con "reducir movimiento" activado en el sistema, se muestra el resultado final sin animar. */

const MENU = ['Panel', 'Contactos', 'Negocios', 'Seguimientos', 'Reportes']

const GUION = [
  { de: 'dueno', texto: '¿A qué clientes llevo más de una semana sin contactar?' },
  { de: 'shifu', texto: 'A 12. Los más importantes son Ana, Carlos y Luis. ¿Les programo un seguimiento por WhatsApp?' },
  { de: 'dueno', texto: 'Sí, y que el mensaje sea amable.' },
  { de: 'shifu', texto: 'Listo ✓ Programé 12 seguimientos y redacté cada mensaje. Te aviso cuando respondan.' },
]

const BARRAS = [38, 52, 44, 63, 58, 76, 88]
const DIAS = ['L', 'M', 'X', 'J', 'V', 'S', 'D']

/* Guion maestro: la conversación con la IA (≈13 s) y luego las tres escenas del panel (5 s cada una), en bucle. */
const SECUENCIA = [
  { vista: 'ia', ms: 13500 },
  { vista: 'panel', escena: 0, ms: 5200 },
  { vista: 'panel', escena: 1, ms: 5200 },
  { vista: 'panel', escena: 2, ms: 5200 },
]

function usarReducirMovimiento() {
  const [r, setR] = useState(false)
  useEffect(() => {
    const m = window.matchMedia('(prefers-reduced-motion: reduce)')
    setR(m.matches)
    const f = (e) => setR(e.matches)
    m.addEventListener('change', f)
    return () => m.removeEventListener('change', f)
  }, [])
  return r
}

/** Número que sube suavemente hasta `valor` cada vez que `valor` cambia. */
function Contador({ valor, formato = (n) => String(Math.round(n)) }) {
  const [v, setV] = useState(valor)
  const previo = useRef(valor)
  useEffect(() => {
    const desde = previo.current
    if (valor < desde) { setV(valor); previo.current = valor; return undefined }     // al reiniciar el ciclo, vuelve de golpe
    const t0 = Date.now()
    // Temporizador y no requestAnimationFrame: este se pausa cuando la pestaña no se ve y la cifra se quedaría sin subir.
    const id = setInterval(() => {
      const k = Math.min((Date.now() - t0) / 900, 1)
      setV(desde + (valor - desde) * (1 - Math.pow(1 - k, 3)))
      if (k >= 1) { previo.current = valor; clearInterval(id) }
    }, 30)
    return () => clearInterval(id)
  }, [valor])
  return <>{formato(v)}</>
}

export default function ProductShowcase() {
  const reducir = usarReducirMovimiento()
  // paso: cuántos mensajes se ven; escribiendo: la IA está "escribiendo"; cerrada: aparece la venta cerrada
  const [paso, setPaso] = useState(GUION.length)
  const [escribiendo, setEscribiendo] = useState(false)
  const [cerrada, setCerrada] = useState(true)
  const [ciclo, setCiclo] = useState(0)
  const [idx, setIdx] = useState(0)            // posición en SECUENCIA
  const [pausa, setPausa] = useState(false)    // el mouse está encima: no avanza solo
  const { vista, escena = 0 } = SECUENCIA[idx]
  const anterior = useRef(0)

  // Avanza solo al siguiente paso cuando se cumple su tiempo (no con "reducir movimiento" ni con el mouse encima).
  useEffect(() => {
    if (reducir || pausa) return undefined
    const t = setTimeout(() => setIdx((i) => (i + 1) % SECUENCIA.length), SECUENCIA[idx].ms)
    return () => clearTimeout(t)
  }, [idx, pausa, reducir])

  // Cada vez que se vuelve a la conversación con la IA, esta arranca desde el principio.
  useEffect(() => {
    if (idx === 0 && anterior.current !== 0) setCiclo((c) => c + 1)
    anterior.current = idx
  }, [idx])

  useEffect(() => {
    if (reducir) { setPaso(GUION.length); setEscribiendo(false); setCerrada(true); return undefined }
    const timers = []
    const en = (ms, fn) => timers.push(setTimeout(fn, ms))
    setPaso(0); setCerrada(false); setEscribiendo(false)
    let t = 900
    GUION.forEach((m, i) => {
      if (m.de === 'shifu') { en(t, () => setEscribiendo(true)); t += 1200 }
      en(t, () => { setEscribiendo(false); setPaso(i + 1) })
      t += 1500
    })
    en(t, () => setCerrada(true))
    return () => timers.forEach(clearTimeout)
  }, [ciclo, reducir])

  const alDia = 38 + (cerrada ? 12 : 0)      // seguimientos al día: suben cuando Shifu programa los 12

  return (
    <section className="show" id="ia">
      <div className="show-cabecera">
        <p className="show-etiqueta">Así trabaja Shifu</p>
        <h2>Una IA que conoce a tus clientes y te dice qué hacer hoy.</h2>
        <p className="show-sub">Pregúntale lo que necesites de tu negocio: Shifu responde al instante, agenda los seguimientos y tu equipo los ve en el CRM.</p>
      </div>

      <div className="show-escenario" onMouseEnter={() => setPausa(true)} onMouseLeave={() => setPausa(false)}>
      <div className="show-tabs" role="tablist">
        {[['ia', 'Asistente con IA', 0], ['panel', 'Panel de análisis', 1]].map(([k, etiqueta, destino]) => (
          <button key={k} type="button" role="tab" aria-selected={vista === k}
            className={`show-tab ${vista === k ? 'show-tab-activa' : ''}`} onClick={() => setIdx(destino)}>{etiqueta}</button>
        ))}
      </div>

      <div className="ventana" role="img" aria-label="Demostración animada del CRM de Shifu: la IA encuentra a los clientes sin seguimiento y programa los mensajes.">
        <div className="ventana-barra">
          <span className="punto" /><span className="punto" /><span className="punto" />
          <span className="ventana-url">{vista === 'ia' ? 'app.shifu.com / panel' : 'app.shifu.com / analisis'}</span>
        </div>
        <div className="ventana-pistas" style={{ transform: vista === 'ia' ? 'translateX(0)' : 'translateX(-50%)' }}>
        <div className="ventana-pista" aria-hidden={vista !== 'ia'}>
        <div className="ventana-cuerpo">
          <aside className="ventana-menu">
            <Logo height={22} />
            <ul>
              {MENU.map((m, i) => <li key={m} className={i === 0 ? 'activo' : ''}>{m}</li>)}
            </ul>
          </aside>

          <div className="ventana-main">
            <div className="kpis">
              <div className="kpi">
                <span>Seguimientos al día</span>
                <strong><Contador valor={alDia} /></strong>
                <em>Meta de hoy: 60</em>
              </div>
              <div className="kpi">
                <span>Negocios abiertos</span>
                <strong>24</strong>
                <em>+3 esta semana</em>
              </div>
              <div className="kpi">
                <span>Tasa de cierre</span>
                <strong>18%</strong>
                <em>+2 pts</em>
              </div>
            </div>

            <div className="paneles">
              <div className="panel-grafica">
                <span className="panel-titulo">Contactos nuevos esta semana</span>
                <div className="barras">
                  {BARRAS.map((h, i) => (
                    <div key={i} className="barra-col">
                      <div className={`barra ${i === BARRAS.length - 1 ? 'barra-hoy' : ''}`}
                        style={{ height: `${h}%`, animationDelay: `${i * 90}ms` }} />
                      <span>{DIAS[i]}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="panel-chat">
                <span className="panel-titulo">Shifu IA · Conversación en vivo</span>
                <div className="chat">
                  {GUION.slice(0, paso).map((m, i) => (m.de === 'shifu'
                    ? <div key={`${ciclo}-${i}`} className="fila-shifu"><ShifuAvatar /><div className="burbuja burbuja-shifu">{m.texto}</div></div>
                    : <div key={`${ciclo}-${i}`} className={`burbuja burbuja-${m.de}`}>{m.texto}</div>))}
                  {escribiendo && <div className="fila-shifu"><ShifuAvatar /><div className="burbuja burbuja-shifu escribiendo"><i /><i /><i /></div></div>}
                </div>
                <div className={`toast ${cerrada ? 'toast-visible' : ''}`}>
                  <span className="toast-ok">✓</span>
                  <span>Listo · <strong>12 seguimientos programados</strong></span>
                </div>
              </div>
            </div>
          </div>
        </div>
        </div>
        <div className="ventana-pista" aria-hidden={vista !== 'panel'}>
          <PanelAnalisis escena={escena} onElegir={(k) => setIdx(1 + k)} />
        </div>
        </div>
      </div>
      </div>
    </section>
  )
}

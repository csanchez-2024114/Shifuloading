import { useEffect, useRef, useState } from 'react'
import Logo from './Logo'
import PanelAnalisis from './PanelAnalisis'

/* Maqueta animada de Shifu con datos inventados: el dueño del negocio le pregunta a la IA (burbuja gris) y esta responde y actúa (el dueño es la burbuja azul).
 * Se repite sola. Con "reducir movimiento" activado en el sistema, se muestra el resultado final sin animar. */

const MENU = ['Panel', 'Conversaciones', 'Pedidos', 'Clientes', 'Análisis']

const GUION = [
  { de: 'dueno', texto: 'Una clienta pidió el modelo azul en talla M. ¿Tenemos stock?' },
  { de: 'shifu', texto: 'Sí, quedan 4 unidades. ¿Quieres que le cree el pedido a Ana por Q1,250?' },
  { de: 'dueno', texto: 'Sí, y envíale el enlace de pago.' },
  { de: 'shifu', texto: 'Listo ✓ Pedido #1042 creado y enlace de pago enviado a Ana.' },
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

const quetzales = (n) => `Q${Math.round(n).toLocaleString('es-GT')}`

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

  const ventas = 18420 + (cerrada ? 1250 : 0)
  const pedidos = 37 + (cerrada ? 1 : 0)

  return (
    <section className="show" id="ia">
      <div className="show-cabecera">
        <p className="show-etiqueta">Así trabaja Shifu</p>
        <h2>Una IA que atiende, vende y te cuenta cómo va el negocio.</h2>
        <p className="show-sub">Pregúntale lo que necesites de tu negocio: Shifu responde al instante, crea el pedido y tu equipo lo ve en el panel.</p>
      </div>

      <div className="show-escenario" onMouseEnter={() => setPausa(true)} onMouseLeave={() => setPausa(false)}>
      <div className="show-tabs" role="tablist">
        {[['ia', 'Atención con IA', 0], ['panel', 'Panel de análisis', 1]].map(([k, etiqueta, destino]) => (
          <button key={k} type="button" role="tab" aria-selected={vista === k}
            className={`show-tab ${vista === k ? 'show-tab-activa' : ''}`} onClick={() => setIdx(destino)}>{etiqueta}</button>
        ))}
      </div>

      <div className="ventana" role="img" aria-label="Demostración animada del panel de Shifu: la IA atiende a una clienta y cierra un pedido.">
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
                <span>Ventas de hoy</span>
                <strong><Contador valor={ventas} formato={quetzales} /></strong>
                <em>+12% vs. ayer</em>
              </div>
              <div className="kpi">
                <span>Pedidos</span>
                <strong><Contador valor={pedidos} /></strong>
                <em>+5 esta hora</em>
              </div>
              <div className="kpi">
                <span>Conversión</span>
                <strong>4.8%</strong>
                <em>+0.6 pts</em>
              </div>
            </div>

            <div className="paneles">
              <div className="panel-grafica">
                <span className="panel-titulo">Ventas de la semana</span>
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
                  {GUION.slice(0, paso).map((m, i) => (
                    <div key={`${ciclo}-${i}`} className={`burbuja burbuja-${m.de}`}>{m.texto}</div>
                  ))}
                  {escribiendo && <div className="burbuja burbuja-shifu escribiendo"><i /><i /><i /></div>}
                </div>
                <div className={`toast ${cerrada ? 'toast-visible' : ''}`}>
                  <span className="toast-ok">✓</span>
                  <span>Venta cerrada · <strong>Q1,250</strong></span>
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

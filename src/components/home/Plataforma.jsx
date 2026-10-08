import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Aparece } from './Secciones'

const APPS = ['◈', '♪', '✦', '◉', '▣', '☰', '◐', '⬡', '✚', '◍', '▲', '❖', '☷', '◆', '✉', '⚑', '◎', '▤', '♣', '✿', '⌘', '☼', '◇', '▦']

/** "Personalízalo todo con las apps": una rejilla de íconos que se ilumina al azar. */
export function Apps() {
  const [on, setOn] = useState(() => new Set())
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return undefined
    const t = setInterval(() => setOn(new Set(Array.from({ length: 6 }, () => Math.floor(Math.random() * APPS.length * 2)))), 1400)
    return () => clearInterval(t)
  }, [])
  return (
    <section className="sec sec-apps">
      <Aparece className="apps-texto">
        <h2 className="titulo-sec">Personalízalo todo con las apps</h2>
        <p>La tienda de aplicaciones de Shifu cuenta con <a href="#apps">más de 21,000 apps de comercio</a> para cualquier función especializada que pueda necesitar tu negocio.</p>
      </Aparece>
      <div className="apps-rejilla" aria-hidden="true">
        {[...APPS, ...APPS].map((a, k) => <span key={k} className={`app-ico t${k % 7} ${on.has(k) ? 'app-on' : ''}`}>{a}</span>)}
      </div>
    </section>
  )
}

export function Desarrolladores() {
  return (
    <section className="sec sec-dev">
      <Aparece className="dev-texto">
        <h2 className="titulo-sec">Impulsado por la IA.<br />Comercio en estado puro</h2>
        <p>El <a href="#dev">Protocolo Universal de Comercio</a> de Shifu y las <a href="#dev">API, herramientas y primitivas</a> dan a los desarrolladores el poder para crear las experiencias de comercio asistido por IA que buscan los negocios.</p>
      </Aparece>
      <Aparece className="dev-panel" retraso={100}>
        <div className="dev-chips"><span>Desarrollar para IA</span><span>Crear tiendas personalizables</span><span>Crea aplicaciones</span></div>
        <div className="dev-term" aria-hidden="true">
          <div className="dev-barra"><i /><i /><i /><span>shifu — zsh — 100×30</span></div>
          <pre>{`? Nombre de tu nueva tienda: mi-tienda
✔ shifu-app está lista para construir

Próximos pasos:
  • cd mi-tienda
  • npm run dev   # inicia el servidor
  • Abre http://localhost:3000

Referencia
  • Documentación de Shifu`}</pre>
        </div>
      </Aparece>
    </section>
  )
}

export function Estadisticas() {
  return (
    <section className="sec sec-mejor">
      <Aparece className="titulo-centro" como="h2">La mejor opción para hacerlo bien</Aparece>
      <Aparece className="mejor-pago" retraso={80}>
        <h3>La solución de pago con el mejor índice de conversión del mundo</h3>
        <div className="mejor-cifras">
          <div><small>MÁS CONVERSIÓN</small><strong>15 %</strong></div>
          <div><small>COMPRADORES CON ALTA INTENCIÓN</small><strong>250 M+</strong></div>
        </div>
        <p><a href="#pagos">Shifu Checkout</a> junto con Shifu Pay convierte hasta un 50 % más que el pago de otros comercios, y da visibilidad a tu marca ante millones de compradores.</p>
        <small className="mejor-nota">Según un estudio externo de ejemplo. Cifras ilustrativas.</small>
      </Aparece>
      <Aparece className="mejor-globo" retraso={160}>
        <div className="globo" aria-hidden="true"><i /><i /><i /></div>
        <div className="mejor-globo-texto">
          <h3>Estabilidad absoluta.<br />Velocidad inigualable</h3>
          <p>Tu tienda Shifu rinde al máximo, incluso durante tus ventas más fuertes de temporada.</p>
          <small className="globo-etq">175 PAÍSES · CON EMPRENDEDORES QUE VENDEN EN SHIFU</small>
        </div>
      </Aparece>
    </section>
  )
}

export function Capital() {
  return (
    <section className="sec sec-capital" id="empresas">
      <Aparece className="cap-texto">
        <h2 className="titulo-sec">Shifu está aquí para ayudar</h2>
        <p>Si tu negocio necesita un impulso, <a href="#capital">Shifu Capital</a> está aquí para echarte una mano.</p>
      </Aparece>
      <Aparece className="cap-cuerpo" retraso={100}>
        <figure className="cap-cita">
          <span className="cap-foto" aria-hidden="true" />
          <blockquote>“Shifu Capital nos brinda la financiación que necesitamos para comprar inventario y crecer con rapidez.”</blockquote>
          <figcaption><b>Jessica Rivas</b><br />CEO, Marca Ejemplo</figcaption>
        </figure>
        <ul className="cap-datos">
          <li><b>5000 millones USD prestados hasta ahora</b><small>Invertido en emprendedores de Shifu</small></li>
          <li><b>Préstamos de hasta 5 millones USD</b><small>Cantidades adaptadas a tus necesidades</small></li>
          <li><b>0 % de tus acciones</b><small>Sin ceder participaciones, nunca</small></li>
        </ul>
      </Aparece>
    </section>
  )
}

export function Pasos() {
  return (
    <section className="sec sec-pasos">
      <Aparece className="titulo-centro" como="h2">Crea rápido en Shifu</Aparece>
      <Aparece className="pasos-cuerpo" retraso={100}>
        <div className="pasos-fotos" aria-hidden="true"><span className="pf1" /><span className="pf2" /></div>
        <ol className="pasos-lista">
          <li><i>01</i><b>Añade tu primer producto</b></li>
          <li><i>02</i><b>Personaliza tu tienda</b></li>
          <li><i>03</i><b>Configura los pagos</b></li>
        </ol>
      </Aparece>
      <div className="centro"><Link to="/login" className="btn-pildora btn-grande">Comenzar ya</Link></div>
    </section>
  )
}

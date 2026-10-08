import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'

/* Secciones del cuerpo de la página de inicio. Todo el contenido (textos, marcas, imágenes) es propio de Shifu. */

/** Hace aparecer un bloque con un fundido suave cuando entra en pantalla. */
export function Aparece({ children, className = '', retraso = 0, como: Tag = 'div' }) {
  const ref = useRef(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return undefined
    if (!('IntersectionObserver' in window) || window.matchMedia('(prefers-reduced-motion: reduce)').matches) { el.classList.add('ap-on'); return undefined }
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { el.classList.add('ap-on'); io.disconnect() } }, { threshold: 0.12 })
    io.observe(el)
    return () => io.disconnect()
  }, [])
  return <Tag ref={ref} className={`ap ${className}`} style={{ transitionDelay: `${retraso}ms` }}>{children}</Tag>
}

/** Una tienda en miniatura dibujada con código. */
function Tienda({ nombre, tono, ancho = false, foto }) {
  return (
    <div className={`tienda tono-${tono} ${ancho ? 'tienda-ancha' : ''} ${foto ? 'tienda-conFoto' : ''}`} aria-hidden="true">
      <div className="tienda-barra"><b>{nombre}</b><span /><span /><span /></div>
      <div className="tienda-hero"><i style={foto ? { backgroundImage: `url(${foto})` } : undefined} /><em>{nombre}</em></div>
      <div className="tienda-grid"><i /><i /><i /><i /></div>
    </div>
  )
}

export function VendeDondeCompra() {
  return (
    <section className="sec sec-vende" id="vende">
      <Aparece className="enunciado">
        <b>Vende donde la gente compra.</b> <b>Online</b> y en persona. <span>A través de la IA y en redes sociales. A nivel local y global.</span>
      </Aparece>
      <Aparece className="tiendas" retraso={120}>
        <Tienda nombre="Casa Verde" tono="a" ancho foto="/img/tienda-1.webp" />
        <Tienda nombre="KOTA" tono="b" foto="/img/tienda-2.webp" />
        <Tienda nombre="Aurea" tono="c" ancho foto="/img/tienda-3.webp" />
      </Aparece>

      <Aparece className="panel-chat-ia" retraso={80}>
        <div className="pci-texto">
          <div className="pci-logos" aria-hidden="true"><span>◐</span><span>✦</span><span>◍</span></div>
          <h3>Tu marca ha entrado en el chat</h3>
          <p>Haz que te descubran en los canales de IA. Los compradores pagan directamente desde el chat: no tendrás que mover ni un dedo. Todo con la tecnología de <a href="#ia">Shifu IA</a>.</p>
        </div>
        <div className="pci-mock" aria-hidden="true">
          <div className="pci-pregunta">Busco un suéter cálido en verde, menos de $200</div>
          <div className="pci-prod"><span className="pci-foto" /><b>Suéter verde bosque</b><small>$148 · Envío gratis</small><u>Comprar</u></div>
        </div>
      </Aparece>
    </section>
  )
}

export function LlegaATodasPartes() {
  return (
    <section className="sec sec-llega">
      <Aparece className="titulo-sec" como="h2">Llega a todas partes.<br />Sin moverte de donde estás.</Aparece>
      <div className="tres">
        <Aparece className="caja" retraso={0}>
          <div className="caja-arte arte-tienda"><Tienda nombre="Jersey estrella" tono="d" foto="/img/moda-editorial.webp" /></div>
          <b>Consigue una tienda diseñada para convertir</b>
          <small>Plantillas listas y personalizables, sin escribir código.</small>
        </Aparece>
        <Aparece className="caja" retraso={120}>
          <div className="caja-arte arte-hub" aria-hidden="true">
            <span className="hub-centro">S</span>
            {['Pagos', 'Envíos', 'Catálogo', 'Inventario', 'Clientes', 'Tienda física'].map((t, k) => <span key={t} className={`hub-etq h${k}`}>{t}</span>)}
          </div>
          <b>Controla todo desde un solo lugar</b>
          <small>Pedidos, pagos, envíos e inventario en un único panel.</small>
        </Aparece>
        <Aparece className="caja" retraso={240}>
          <div className="caja-arte arte-canales" aria-hidden="true">
            {['Instagram', 'TikTok', 'Marketplace', 'Tienda', 'Chat IA', 'Web'].map((t, k) => <span key={t} className={`canal c${k}`}>{t}</span>)}
          </div>
          <b>Vende en todos los canales</b>
          <small>Conecta tus redes y mercados y vende desde todos a la vez.</small>
        </Aparece>
      </div>
    </section>
  )
}

export function Internacional() {
  return (
    <section className="sec sec-intl">
      <Aparece className="titulo-sec" como="h2">Crece más allá de tus fronteras</Aparece>
      <Aparece className="intl-panel" retraso={100}>
        <div className="intl-mock" aria-hidden="true">
          <div className="intl-banderas"><span>MX</span><span>ES</span><span>US</span><span>UK</span></div>
          <div className="intl-prod"><span className="intl-foto" /><button type="button" tabIndex={-1}>Comprar</button><em>Pedir por 125,00 US$</em></div>
          <div className="intl-envio">
            <b>Comprar 5 etiquetas de envío</b>
            <p><i /> Paquete estándar · Entrega a domicilio <u>4,91 €</u></p>
            <p><i /> Paquete premium · Entrega a domicilio <u>8,51 €</u></p>
            <p><i /> Paquete premium · Entrega en oficina <u>7,81 €</u></p>
            <div className="intl-total"><span>Total</span><strong>21,03 €</strong></div>
          </div>
        </div>
        <div className="intl-texto">
          <b>Vende a nivel internacional</b>
          <p>Simplifica las ventas en otros países con <a href="#intl">Shifu Mercados</a>. Entrega tus productos más rápido y a menor costo gracias a las herramientas de envío integradas.</p>
        </div>
      </Aparece>
    </section>
  )
}

const CASOS = [
  ['Comienza con rapidez', 'Ana lanzó su tienda desde casa. Hoy es un negocio con más de 4 millones en ventas.', 'a'],
  ['Crece todo lo que quieras', 'Una zapatería clásica unificó su tienda online, sus 25 tiendas físicas y a sus distribuidores en un solo sistema.', 'b'],
  ['Alcanza tus metas', 'Una marca favorita de los influencers empezó online y creció hasta tener tiendas físicas en todo el país.', 'c'],
]
const MARCAS = ['NÓRDICA', 'Taller 9', 'UNTO', 'Café Brava', 'MONTE', 'Ríos & Co.', 'ALBA', 'Fénix']

export function ParaTodos() {
  return (
    <section className="sec sec-todos" id="planes">
      <Aparece className="titulo-sec" como="h2">Para todos, desde emprendedores hasta grandes empresas</Aparece>
      <div className="tres">
        {CASOS.map(([t, d, g], k) => (
          <Aparece key={t} className="caso" retraso={k * 120}>
            <div className={`caso-foto caso-${g}`} aria-hidden="true"><i /><em /></div>
            <b>{t}</b><small>{d}</small>
          </Aparece>
        ))}
      </div>
      <div className="centro"><Link to="/login" className="btn-borde btn-grande">Elige el plan que más te convenga</Link></div>
      <div className="marcas" aria-label="Marcas que usan Shifu">
        <div className="marcas-pista">
          {[...MARCAS, ...MARCAS].map((m, k) => <span key={k}>{m}</span>)}
        </div>
      </div>
    </section>
  )
}

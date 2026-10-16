import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Aparece } from './Secciones'

const APPS = ['◈', '♪', '✦', '◉', '▣', '☰', '◐', '⬡', '✚', '◍', '▲', '❖', '☷', '◆', '✉', '⚑', '◎', '▤', '♣', '✿', '⌘', '☼', '◇', '▦']

/** "Conéctalo con todo lo que ya usas": una rejilla de íconos que se ilumina al azar. */
export function Integraciones() {
  const [on, setOn] = useState(() => new Set())
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return undefined
    const t = setInterval(() => setOn(new Set(Array.from({ length: 6 }, () => Math.floor(Math.random() * APPS.length * 2)))), 1400)
    return () => clearInterval(t)
  }, [])
  return (
    <section className="sec sec-apps" id="integraciones">
      <Aparece className="apps-texto">
        <h2 className="titulo-sec">Conéctalo con todo lo que ya usas</h2>
        <p>Shifu se conecta con tu WhatsApp, tu correo, tu calendario, tus hojas de cálculo y más, para que los datos de tus clientes fluyan solos. <Link to="/integraciones">Ver el directorio de integraciones</Link>.</p>
      </Aparece>
      <div className="apps-rejilla" aria-hidden="true">
        {[...APPS, ...APPS].map((a, k) => <span key={k} className={`app-ico t${k % 7} ${on.has(k) ? 'app-on' : ''}`}>{a}</span>)}
      </div>
    </section>
  )
}

const TABS_DEV = [
  ['api', 'API y webhooks'],
  ['auto', 'Automatizaciones'],
  ['campos', 'Campos personalizados'],
]

function PanelDev({ k }) {
  if (k === 'api') {
    return (
      <div className="dev-mini" key={k}>
        <div className="dev-barra"><i /><i /><i /><span>Pídele tu CRM a la API</span></div>
        <pre>{`GET  /crm
Authorization: Bearer ••••••••

200 OK
{ "contactos": 24, "tareas": 5, "secciones": 4 }    # ejemplo`}</pre>
        <div className="dev-aviso"><span aria-hidden="true">🔔</span><div><b>Webhook: contacto nuevo → tu sistema</b><small>Que Shifu avise solo cuando algo pasa.</small></div><em>Próximamente</em></div>
        <Link to="/desarrolladores" className="dev-mas">Ver la API completa →</Link>
      </div>
    )
  }
  if (k === 'auto') {
    return (
      <div className="dev-mini" key={k}>
        <div className="dev-barra"><i /><i /><i /><span>Automatizaciones de tu CRM</span></div>
        <ul className="dev-auto">
          {[['Recordatorios de seguimiento', 'Te avisa cuando un cliente lleva 3 días sin avanzar.'], ['Repartir clientes', 'Cada cliente nuevo se asigna a alguien de tu equipo.'], ['Resumen de la semana', 'Cada semana, lo que pasó en tu CRM en pocas líneas.']].map(([t, d]) => (
            <li key={t}><span className="dev-sw" aria-hidden="true"><i /></span><div><b>{t}</b><small>{d}</small></div><em className="ok">Activa</em></li>
          ))}
        </ul>
        <p className="dev-pie">Los avisos llegan a la campana de tu CRM y a tu correo. WhatsApp y cobros vencidos: próximamente.</p>
      </div>
    )
  }
  return (
    <div className="dev-mini" key={k}>
      <div className="dev-barra"><i /><i /><i /><span>Pedidos · agregar</span></div>
      <div className="dev-form">
        <label>Cliente<span className="dev-in">Carla Méndez</span></label>
        <label>Zona de servicio<span className="dev-in">Zona 7</span></label>
        <label>Estado<span className="dev-ops"><b className="on">pendiente</b><b>realizado</b><b>cancelado</b></span></label>
        <label>Monto<span className="dev-in">Q 4,500</span></label>
      </div>
      <p className="dev-pie">Dile a Shifu “quiero un campo Estado con tres opciones” y lo crea, sin código.</p>
    </div>
  )
}

export function Desarrolladores() {
  const [tab, setTab] = useState('api')
  return (
    <section className="sec sec-dev">
      <Aparece className="dev-texto">
        <h2 className="titulo-sec">Impulsado por la IA.<br />Un CRM sin límites</h2>
        <p>La <Link to="/desarrolladores">API y los webhooks</Link> de Shifu le dan a tu equipo técnico el poder para conectar el CRM con cualquier sistema y automatizar lo que haga falta, con la ayuda de la IA.</p>
      </Aparece>
      <Aparece className="dev-panel" retraso={100}>
        <div className="show-tabs dev-tabs" role="tablist" aria-label="Qué puedes hacer">
          {TABS_DEV.map(([k, t]) => (
            <button key={k} type="button" role="tab" aria-selected={tab === k} className={`show-tab ${tab === k ? 'show-tab-activa' : ''}`} onClick={() => setTab(k)}>{t}</button>
          ))}
        </div>
        <PanelDev k={tab} />
      </Aparece>
    </section>
  )
}

export function Estadisticas() {
  return (
    <section className="sec sec-mejor">
      <Aparece className="titulo-centro" como="h2">Pensado para que ningún cliente se pierda</Aparece>
      <Aparece className="mejor-pago" retraso={80}>
        <h3>Cuéntanos cómo vendes.<br />Shifu hace el resto.</h3>
        <div className="mejor-cifras">
          <div><small>MÁS SEGUIMIENTOS AL DÍA</small><strong>3×</strong></div>
          <div><small>PARA TENER TU CRM LISTO</small><strong>10 min</strong></div>
        </div>
        <p>Con Shifu IA, cada cliente tiene su siguiente paso y tu equipo sabe qué hacer hoy. Menos hojas sueltas, menos mensajes perdidos y más ventas cerradas.</p>
        <small className="mejor-nota">Cifras ilustrativas de ejemplo.</small>
      </Aparece>
      <Aparece className="mejor-globo" retraso={160}>
        <div className="globo" aria-hidden="true"><i /><i /><i /></div>
        <div className="mejor-globo-texto">
          <h3>Tus datos, seguros<br />y siempre disponibles</h3>
          <p>Cifrado, respaldos automáticos y permisos por persona: la información de tus clientes está protegida y a mano cuando la necesitas.</p>
          <small className="globo-etq">DATOS CIFRADOS · RESPALDOS AUTOMÁTICOS</small>
        </div>
      </Aparece>
    </section>
  )
}

const PASOS = [
  ['Cuéntale a Shifu sobre tu negocio',
   'Respondes unas preguntas cortas: cómo se llama tu negocio, qué vendes y qué te cuesta más trabajo con tus clientes. Según lo que contestes, Shifu te hace una o dos preguntas más de tu tipo de negocio. Son unos minutos.'],
  ['Revisa y ajusta tu CRM',
   'Shifu arma tu CRM con las etapas, secciones y campos que tu negocio necesita: una herrería y una tienda quedan distintas. Si algo no te cuadra, se lo pides en el chat: “agrega a Pedro” o “quita la sección de proveedores”.'],
  ['Conecta tus canales y empieza',
   'Trae tus contactos desde un Excel, tus notas o una captura de pantalla y empieza a trabajar. Shifu te avisa de los seguimientos en la campana y por correo. WhatsApp y calendario están por llegar.'],
]

export function Pasos() {
  const [abierto, setAbierto] = useState(null)
  return (
    <section className="sec sec-pasos">
      <Aparece className="titulo-centro" como="h2">Crea tu CRM en 3 pasos</Aparece>
      <Aparece className="pasos-cuerpo" retraso={100}>
        <div className="pasos-fotos" aria-hidden="true"><span className="pf1" /><span className="pf2" /></div>
        <ol className="pasos-lista">
          {PASOS.map(([t, d], k) => (
            <li key={t} className={abierto === k ? 'paso-abierto' : ''}>
              <button type="button" className="paso-btn" aria-expanded={abierto === k} aria-controls={`paso-${k}`} onClick={() => setAbierto(abierto === k ? null : k)}>
                <i>{`0${k + 1}`}</i><b>{t}</b><span className="paso-mas" aria-hidden="true">+</span>
              </button>
              <div id={`paso-${k}`} className="paso-detalle" role="region" hidden={abierto !== k}><p>{d}</p></div>
            </li>
          ))}
        </ol>
      </Aparece>
    </section>
  )
}

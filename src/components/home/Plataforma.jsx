import { useEffect, useState } from 'react'
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
        <p>Shifu se conecta con tu WhatsApp, tu correo, tu calendario, tus hojas de cálculo y más, para que los datos de tus clientes fluyan solos. <a href="#integraciones">Ver el directorio de integraciones</a>.</p>
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
        <h2 className="titulo-sec">Impulsado por la IA.<br />Un CRM sin límites</h2>
        <p>La <a href="#dev">API y los webhooks</a> de Shifu le dan a tu equipo técnico el poder para conectar el CRM con cualquier sistema y automatizar lo que haga falta, con la ayuda de la IA.</p>
      </Aparece>
      <Aparece className="dev-panel" retraso={100}>
        <div className="dev-chips"><span>API y webhooks</span><span>Automatizaciones</span><span>Campos personalizados</span></div>
        <div className="dev-term" aria-hidden="true">
          <div className="dev-barra"><i /><i /><i /><span>shifu — zsh — 100×30</span></div>
          <pre>{`? Nombre de tu CRM: estudio-aurora
✔ CRM creado con 5 etapas y 6 campos

Próximos pasos:
  • shifu importar contactos.xlsx
  • shifu conectar whatsapp
  • shifu abrir        # abre tu CRM

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
      <Aparece className="titulo-centro" como="h2">Pensado para que ningún cliente se pierda</Aparece>
      <Aparece className="mejor-pago" retraso={80}>
        <h3>Un CRM que se arma contigo y no al revés</h3>
        <div className="mejor-cifras">
          <div><small>MÁS SEGUIMIENTOS AL DÍA</small><strong>3×</strong></div>
          <div><small>PARA TENER TU CRM LISTO</small><strong>10 min</strong></div>
        </div>
        <p>Con <a href="#ia">Shifu IA</a>, cada cliente tiene su siguiente paso y tu equipo sabe qué hacer hoy. Menos hojas sueltas, menos mensajes perdidos y más ventas cerradas.</p>
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

export function Pasos() {
  return (
    <section className="sec sec-pasos">
      <Aparece className="titulo-centro" como="h2">Crea tu CRM en 3 pasos</Aparece>
      <Aparece className="pasos-cuerpo" retraso={100}>
        <div className="pasos-fotos" aria-hidden="true"><span className="pf1" /><span className="pf2" /></div>
        <ol className="pasos-lista">
          <li><i>01</i><b>Cuéntale a Shifu sobre tu negocio</b></li>
          <li><i>02</i><b>Revisa y ajusta tu CRM</b></li>
          <li><i>03</i><b>Conecta tus canales y empieza</b></li>
        </ol>
      </Aparece>
    </section>
  )
}

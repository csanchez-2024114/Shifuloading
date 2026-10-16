import { useEffect, useRef } from 'react'

/* Secciones del cuerpo de la página de inicio. Shifu sirve para crear CRMs con IA: todo el contenido (textos, nombres, cifras
 * y maquetas) es propio e inventado, dibujado con código para que se vea nítido en cualquier pantalla. */

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

/* ───────── Maquetas de CRM ───────── */

const COLUMNAS = [
  { t: 'Nuevo', n: 3, tarjetas: [['Estudio Aurora', 'Q12,000'], ['Café Brava', 'Q4,500']] },
  { t: 'En seguimiento', n: 5, tarjetas: [['Ríos & Co.', 'Q28,000'], ['Taller 9', 'Q9,800']] },
  { t: 'Propuesta', n: 2, tarjetas: [['Monte Verde', 'Q45,000']] },
  { t: 'Ganado', n: 4, tarjetas: [['Alba Digital', 'Q18,500']] },
]

function Pipeline({ compacto = false }) {
  return (
    <div className={`mk mk-pipeline ${compacto ? 'mk-compacto' : ''}`} aria-hidden="true">
      <div className="mk-cab"><b>Pipeline</b><span>14 negocios abiertos</span></div>
      <div className="mk-cols">
        {COLUMNAS.map((c) => (
          <div key={c.t} className="mk-col">
            <div className="mk-col-t">{c.t}<i>{c.n}</i></div>
            {c.tarjetas.map(([nombre, monto]) => (
              <div key={nombre} className="mk-neg"><b>{nombre}</b><small>{monto}</small><span className="mk-barra" /></div>
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

function Ficha() {
  return (
    <div className="mk mk-ficha" aria-hidden="true">
      <div className="mk-persona"><span className="mk-av">AM</span><div><b>Ana Morales</b><small>Estudio Aurora · Cliente</small></div></div>
      <div className="mk-tags"><span>Prioridad alta</span><span>WhatsApp</span></div>
      <ul className="mk-linea">
        <li><i>📞</i><div><b>Llamada</b><small>Ayer · 12 min</small></div></li>
        <li><i>💬</i><div><b>Mensaje por WhatsApp</b><small>Hoy · 9:40</small></div></li>
        <li><i>🧾</i><div><b>Cotización enviada</b><small>Hoy · Q12,000</small></div></li>
      </ul>
      <div className="mk-siguiente"><span>Siguiente paso</span><b>Enviar propuesta · mañana</b></div>
    </div>
  )
}

function Reporte() {
  const barras = [42, 66, 54, 78, 61, 90]
  return (
    <div className="mk mk-reporte" aria-hidden="true">
      <div className="mk-cab"><b>Resumen del mes</b><span>Junio</span></div>
      <div className="mk-kpis"><div><small>En juego</small><strong>Q184,500</strong></div><div><small>Tasa de éxito</small><strong>54%</strong></div></div>
      <div className="mk-grafica">{barras.map((h, k) => <i key={k} style={{ height: `${h}%` }} className={k === barras.length - 1 ? 'mk-hoy' : ''} />)}</div>
      <p className="mk-pie">Seguimientos al día: <b>38</b> de 60</p>
    </div>
  )
}

/* ───────── Secciones ───────── */

export function ReuneClientes() {
  return (
    <section className="sec sec-vende" id="clientes">
      <Aparece className="enunciado">
        <b>Reúne a tus clientes donde estén.</b> <b>WhatsApp</b>, correo y redes. <span>Con una IA que da seguimiento por ti. A tu manera y a tu medida.</span>
      </Aparece>
      <Aparece className="tiendas" retraso={120}>
        <Pipeline />
        <Ficha />
        <Reporte />
      </Aparece>

      <Aparece className="panel-chat-ia" retraso={80}>
        <div className="pci-texto">
          <div className="pci-logos" aria-hidden="true"><span>💬</span><span>✉️</span><span>📸</span></div>
          <h3>Tu CRM entiende tus chats</h3>
          <p>Conecta WhatsApp y tu correo: Shifu detecta quién te escribe, crea el contacto, anota lo que pidió y te propone el siguiente paso.</p>
        </div>
        <div className="pci-mock" aria-hidden="true">
          <div className="pci-pregunta">Hola, quisiera una cotización para un evento en agosto 🙌</div>
          <div className="pci-contacto">
            <span className="pci-nuevo">✨ Contacto creado por Shifu</span>
            <div className="pci-fila"><span className="mk-av">ML</span><div><b>María López</b><small>Prospecto · WhatsApp</small></div></div>
            <ul><li>🎯 Interés: evento en agosto</li><li>⏰ Siguiente paso: enviar cotización · hoy</li></ul>
            <u>Ver ficha</u>
          </div>
        </div>
      </Aparece>
    </section>
  )
}

export function TodoEnUnLugar() {
  return (
    <section className="sec sec-llega">
      <Aparece className="titulo-sec" como="h2">Todo tu negocio<br />en un solo lugar.</Aparece>
      <div className="tres">
        <Aparece className="caja" retraso={0}>
          <div className="caja-arte arte-tienda"><Pipeline compacto /></div>
          <b>Un CRM hecho para tu rubro</b>
          <small>Etapas y campos propios, listos desde el primer día y sin escribir código.</small>
        </Aparece>
        <Aparece className="caja" retraso={120}>
          <div className="caja-arte arte-hub" aria-hidden="true">
            <span className="hub-centro">S</span>
            {['Contactos', 'Negocios', 'Seguimientos', 'Cotizaciones', 'Equipo', 'Reportes'].map((t, k) => <span key={t} className={`hub-etq h${k}`}>{t}</span>)}
          </div>
          <b>Controla todo desde un solo lugar</b>
          <small>Clientes, oportunidades y tareas en un único panel, sin hojas sueltas.</small>
        </Aparece>
        <Aparece className="caja" retraso={240}>
          <div className="caja-arte arte-canales" aria-hidden="true">
            {['WhatsApp', 'Correo', 'Instagram', 'Calendario', 'Excel', 'Formulario'].map((t, k) => <span key={t} className={`canal c${k}`}>{t}</span>)}
          </div>
          <b>Conecta todos tus canales</b>
          <small>Las conversaciones y los datos entran solos al CRM.</small>
        </Aparece>
      </div>
    </section>
  )
}

const ETAPAS = ['Prospecto', 'Cotización', 'Negociación', 'Cliente', 'Renovación']
const CAMPOS = ['Empresa', 'Contacto', 'Póliza', 'Monto', 'Fecha de renovación', 'Asesor']

export function CrmAMedida() {
  return (
    <section className="sec sec-intl" id="medida">
      <Aparece className="titulo-sec" como="h2">Un CRM hecho a tu medida</Aparece>
      <Aparece className="intl-panel" retraso={100}>
        <div className="crm-mock" aria-hidden="true">
          <div className="crm-pide">
            <small>Tú le cuentas</small>
            <p>“Vendo seguros a empresas. Necesito seguir cotizaciones y avisar cuando toque renovar.”</p>
          </div>
          <div className="crm-flecha">✨</div>
          <div className="crm-arma">
            <small>Shifu arma tu CRM</small>
            <ol className="crm-etapas">{ETAPAS.map((e, k) => <li key={e} style={{ animationDelay: `${0.2 + k * 0.15}s` }}><i>{k + 1}</i>{e}</li>)}</ol>
            <div className="crm-campos">{CAMPOS.map((c) => <span key={c}>{c}</span>)}</div>
          </div>
        </div>
        <div className="intl-texto">
          <b>Describe tu negocio y Shifu arma tu CRM</b>
          <p>Cuéntale cómo vendes y te propone etapas, campos y recordatorios. Lo ajustas con un clic. Sin código ni semanas de configuración.</p>
        </div>
      </Aparece>
    </section>
  )
}

const CASOS = [
  ['Para freelancers y emprendedores', 'Ana ordenó todos sus clientes en una tarde y dejó de perder seguimientos entre chats y notas.', 'a'],
  ['Para negocios con local', 'Un espacio de arte unificó sus visitas, ventas y contactos en un solo CRM, sin hojas de cálculo.', 'b'],
  ['Para equipos de ventas', 'Cada persona ve sus clientes, y el equipo trabaja sobre los mismos datos con metas claras.', 'c'],
]

export function ParaTodos() {
  return (
    <section className="sec sec-todos" id="planes">
      <Aparece className="titulo-sec" como="h2">Para todos, desde emprendedores hasta grandes equipos</Aparece>
      <div className="tres">
        {CASOS.map(([t, d, g], k) => (
          <Aparece key={t} className="caso" retraso={k * 120}>
            <div className={`caso-foto caso-${g}`} aria-hidden="true"><i /><em /></div>
            <b>{t}</b><small>{d}</small>
          </Aparece>
        ))}
      </div>
    </section>
  )
}

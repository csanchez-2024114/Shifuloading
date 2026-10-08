/* Panel de análisis de Shifu dibujado con código (datos inventados): se ve nítido en cualquier pantalla,
 * a diferencia de una captura o un GIF. Lo controla el guion maestro de ProductShowcase: él decide qué escena se ve. */

const ESCENAS = ['Resumen', 'Equipo', 'Recomendaciones']

const VENDEDORES = [
  { nombre: 'Ana Morales', ventas: 6, monto: 'Q241,824', cotiza: 'Cada 6.1 días', vende: 'Cada 8.2 días', pierde: 'Cada 16 días', cierre: 67, resueltos: '6 de 9', clientes: 1005, act: '≈ 1.4 actividades c/u' },
  { nombre: 'Carla Méndez', ventas: 3, monto: 'Q160,300', cotiza: 'Cada 12 días', vende: 'Cada 16 días', pierde: 'Cada 49 días', cierre: 75, resueltos: '3 de 4', clientes: 1005, act: '≈ 1.4 actividades c/u' },
  { nombre: 'Diego Castillo', ventas: 1, monto: 'Q34,000', cotiza: 'Cada 5.4 días', vende: 'Cada 49 días', pierde: 'Cada 7 días', cierre: 13, resueltos: '1 de 8', clientes: 10, act: '≈ 1.9 actividades c/u' },
]

const RECOMENDACIONES = [
  { tipo: 'corrige', etiqueta: 'Corrige', titulo: '12 clientes llevan más de 7 días sin contacto', texto: 'Programa un seguimiento hoy para no perderlos. Shifu puede redactar los mensajes.' },
  { tipo: 'corrige', etiqueta: 'Corrige', titulo: 'Dependes de un solo cliente grande', texto: 'Es el 42% de tus negocios abiertos. Si se enfría, tu pipeline baja con él.' },
  { tipo: 'aprovecha', etiqueta: 'Aprovecha', titulo: 'Responder rápido te hace cerrar más', texto: 'Cierras 2 de cada 5 cuando contestas en menos de una hora.' },
  { tipo: 'oportunidad', etiqueta: 'Oportunidad', titulo: 'Reactiva a tus clientes de hace 6 meses', texto: 'Hay 18 que ya te compraron y no han vuelto: un mensaje a tiempo los puede traer de regreso.' },
]

function Resumen() {
  return (
    <div className="pa-escena">
      <div className="pa-exito">
        <div>
          <span className="pa-peq">Tasa de éxito de ventas</span>
          <strong className="pa-grande">54.3%</strong>
        </div>
        <p><b>25</b> ganados de <b>46</b> negocios resueltos en los últimos 180 días. Con esa tasa, lo que hay en juego (Q861,645) vale unos <b>Q468,285</b>.</p>
      </div>
      <div className="pa-frec">
        <div className="pa-tarjeta pa-azul"><strong>Cada 1.2 días</strong><span>cotización · 42 en total</span></div>
        <div className="pa-tarjeta pa-verde"><strong>Cada 2.5 días</strong><span>venta · 20 en total</span></div>
        <div className="pa-tarjeta pa-rojo"><strong>Cada 2.5 días</strong><span>negocio perdido · 20 en total</span></div>
      </div>
      <span className="pa-peq pa-sep">Actividad del equipo</span>
      <div className="pa-act">
        {[['Llamadas', 151], ['Correos', '1,375'], ['WhatsApp', '2,527'], ['Reuniones', 431]].map(([k, v]) => (
          <div key={k} className="pa-tarjeta"><span>{k}</span><strong>{v}</strong></div>
        ))}
      </div>
    </div>
  )
}

function Equipo() {
  return (
    <div className="pa-escena">
      <span className="pa-peq">Cada vendedor · el trabajo de cada uno por separado</span>
      <div className="pa-vend">
        {VENDEDORES.map((v) => (
          <div key={v.nombre} className="pa-tarjeta pa-vcard">
            <div className="pa-vcab">
              <span className="pa-av">{v.nombre[0]}</span>
              <div><b>{v.nombre}</b><small>{v.ventas} {v.ventas === 1 ? 'venta' : 'ventas'} · {v.monto}</small></div>
            </div>
            <ul>
              <li><span>Cotiza</span><b>{v.cotiza}</b></li>
              <li><span>Vende</span><b>{v.vende}</b></li>
              <li><span>Pierde</span><b>{v.pierde}</b></li>
            </ul>
            <ul className="pa-nuevo">
              <li><span>Porcentaje de cierre</span><b>{v.cierre}% <small>· {v.resueltos} resueltos</small></b></li>
              <li><span>Clientes añadidos</span><b>{v.clientes.toLocaleString('es-GT')} <small>· {v.act}</small></b></li>
            </ul>
          </div>
        ))}
      </div>
    </div>
  )
}

function Recomendaciones() {
  return (
    <div className="pa-escena">
      <span className="pa-peq">Qué hacer hoy · según cómo van tus clientes</span>
      <div className="pa-recs">
        {RECOMENDACIONES.map((r) => (
          <div key={r.titulo} className={`pa-rec pa-rec-${r.tipo}`}>
            <small>{r.etiqueta}</small>
            <b>{r.titulo}</b>
            <p>{r.texto}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

const VISTAS = [Resumen, Equipo, Recomendaciones]

export default function PanelAnalisis({ escena = 0, onElegir = () => {} }) {
  return (
    <div className="pa">
      <div className="pa-escenario">
        {VISTAS.map((V, k) => (
          <div key={ESCENAS[k]} className={`pa-capa ${k === escena ? 'pa-capa-activa' : ''}`} aria-hidden={k !== escena}><V /></div>
        ))}
      </div>
      <div className="pa-puntos" role="tablist" aria-label="Escenas del panel">
        {ESCENAS.map((e, k) => (
          <button key={e} type="button" role="tab" aria-selected={k === escena} aria-label={e}
            className={k === escena ? 'pa-punto pa-punto-activo' : 'pa-punto'} onClick={() => onElegir(k)} />
        ))}
      </div>
    </div>
  )
}

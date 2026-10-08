import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import Logo from '../components/Logo'
import ShifuAvatar from '../components/ShifuAvatar'
import { CLAVE, etiqueta } from '../brief/preguntas'
import { LuUsers, LuWallet, LuCode, LuActivity, LuIdCard, LuSearch, LuBell, LuRotateCcw, LuUpload, LuZap, LuSend, LuX } from 'react-icons/lu'
import '../crm.css'
import '../crm-extra.css'

/* El CRM básico que Shifu arma al terminar el cuestionario, con el tema oscuro de Shifu. Todo gira en torno a tres ideas:
 *   · Estructura: cómo está ordenado el negocio (contactos, trabajo del día a día e importación de Excel y notas).
 *   · Medición y equipo: cuánto se cobra, qué pasa y quién hace qué.
 *   · Automatizaciones: lo que Shifu hace solo.
 * Los datos son de ejemplo y se ajustan a lo respondido en el cuestionario. Lo que la persona agrega, cambia o elimina (con el chat
 * de Shifu o a mano) vive en el estado de esta página; cuando Shifu tenga servidor se guardará allí. */

const leer = () => {
  try { return JSON.parse(localStorage.getItem(CLAVE)) || null } catch { return null }
}
const norm = (s) => s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').trim()
const capitaliza = (s) => s.trim().replace(/\s+/g, ' ').replace(/(^|\s)(\p{L})/gu, (_, a, b) => a + b.toUpperCase())

const NOMBRES = ['Ana Morales', 'Luis Pérez', 'Sofía Ríos', 'Marcos Díaz', 'Valeria Soto', 'Diego Castillo', 'Camila Vega', 'Jorge Luna',
  'Paola Méndez', 'Andrés Cruz', 'Lucía Torres', 'Mateo Rojas', 'Elena Salas', 'Hugo Ibarra', 'Renata Paz', 'Iván Aguirre']
const EQUIPO = ['Mariana Solís', 'Carlos Aguilar', 'Diana Hidalgo']
const MONEDA = { gt: 'Q', mx: '$', co: '$', es: '€', us: '$', otro: '$' }
const CARTERA = { k1: 40, k2: 120, k3: 600, k4: 1200 }
const PERSONAS = { solo: 1, chico: 2, medio: 3, grande: 4 }
const ETAPAS = ['Nuevo', 'En contacto', 'Interesado', 'Cliente']

/* Cada CRM nombra sus secciones con el lenguaje del rubro. Orden: contactos, cobros, trabajo, actividad y equipo. */
const SECCIONES = {
  servicios: ['Clientes', 'Facturación', 'Proyectos', 'Bitácora', 'Equipo'],
  agencia: ['Clientes', 'Presupuestos y pagos', 'Campañas', 'Línea de tiempo', 'Talento'],
  comercio: ['Compradores', 'Caja', 'Pedidos', 'Movimiento', 'Vendedores'],
  salud: ['Pacientes', 'Pagos y consultas', 'Tratamientos', 'Historial', 'Especialistas'],
  educacion: ['Alumnos', 'Mensualidades', 'Clases', 'Novedades', 'Docentes'],
  tecnologia: ['Cuentas', 'Suscripciones', 'Desarrollo', 'Registro', 'Equipo técnico'],
  inmobiliaria: ['Interesados', 'Comisiones y pagos', 'Propiedades', 'Visitas', 'Asesores'],
  otro: ['Contactos', 'Cobros', 'Proyectos', 'Actividad', 'Equipo'],
}
const BASE = [
  { id: 'contactos', I: LuUsers, grupo: 0 }, { id: 'desarrollo', I: LuCode, grupo: 0 },
  { id: 'cobros', I: LuWallet, grupo: 1 }, { id: 'actividad', I: LuActivity, grupo: 1 }, { id: 'rrhh', I: LuIdCard, grupo: 1 },
]
const ORDEN = { contactos: 0, cobros: 1, desarrollo: 2, actividad: 3, rrhh: 4 }
const GRUPOS = ['Estructura', 'Medición y equipo', 'Automatizaciones']
const menuDe = (rubro, nombres) => [
  ...BASE.map((m) => ({ ...m, t: nombres[m.id] || (SECCIONES[rubro] || SECCIONES.otro)[ORDEN[m.id]] })),
  { id: 'importar', t: 'Importar datos', I: LuUpload, grupo: 0 },
  { id: 'automatizaciones', t: 'Automatizaciones', I: LuZap, grupo: 2 },
]

let uid = 0
const nuevoId = () => { uid += 1; return uid }

/* ───────── Pantalla de carga ───────── */

function Cargando({ pasos, onListo }) {
  const [hechos, setHechos] = useState(0)
  useEffect(() => {
    const quieto = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const t = setTimeout(() => (hechos >= pasos.length ? onListo() : setHechos(hechos + 1)), hechos >= pasos.length ? 700 : quieto ? 250 : 1050)
    return () => clearTimeout(t)
  }, [hechos, pasos.length, onListo])
  const pct = Math.round((hechos / pasos.length) * 100)
  return (
    <div className="carga" role="status" aria-live="polite">
      <div className="carga-fondo" aria-hidden="true"><i /><i /></div>
      <img className="carga-shifu" src="/img/shifu-cuerpo.webp" alt="" width="150" height="152" />
      <h1>Cargando tu entorno…</h1>
      <p className="carga-sub">Shifu está armando tu CRM según tu negocio y lo que necesitas.</p>
      <div className="carga-barra" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}><i style={{ width: `${pct}%` }} /></div>
      <ul className="carga-pasos">
        {pasos.map((p, k) => (
          <li key={p} className={k < hechos ? 'ok' : k === hechos ? 'ahora' : ''}>
            <span aria-hidden="true">{k < hechos ? '✓' : ''}</span>{p}
          </li>
        ))}
      </ul>
    </div>
  )
}

/* ───────── Vistas ───────── */

function Contactos({ d, lista, total, buscar, t, onBorrar }) {
  const q = norm(buscar)
  const vis = q ? lista.filter((f) => norm(f.n).includes(q)) : lista
  const por = (e) => lista.filter((c) => c.etapa === e).length
  return (
    <>
      <div className="mc-cab"><div><h1>{t}</h1><p>{total.toLocaleString('es')} en total. Aquí ves un adelanto de los primeros; los que agregues o importes aparecen arriba.</p></div></div>
      <div className="mc-kpis c4k">
        <div><small>En total</small><strong>{total.toLocaleString('es')}</strong></div>
        {ETAPAS.slice(1).map((e) => <div key={e}><small>{e}</small><strong>{por(e)}</strong></div>)}
      </div>
      <div className="mc-tabla" role="table">
        <div className="mc-fila cab" role="row"><span>Nombre</span><span>Canal</span><span>Etapa</span><span>Responsable</span><span>Último contacto</span></div>
        {vis.map((f) => (
          <div key={f.id} className="mc-fila" role="row">
            <span><i className="mc-av peq">{f.n[0]}</i><span className="mc-nom">{f.n}{f.det && <small>{f.det}</small>}</span></span>
            <span>{f.canal}</span><span><em className="mc-estado">{f.etapa}</em></span><span>{f.dueno}</span>
            <span className="mc-ultimo">{f.dias === 0 ? 'hoy' : `hace ${f.dias} ${f.dias === 1 ? 'día' : 'días'}`}
              <button type="button" className="mc-x" aria-label={`Eliminar a ${f.n}`} onClick={() => onBorrar(f)}><LuX /></button></span>
          </div>
        ))}
        {!vis.length && <p className="mc-vacio">Nada coincide con “{buscar}”.</p>}
      </div>
    </>
  )
}

function Cobros({ d, t }) {
  const m = d.moneda
  const filas = [['Ana Morales', 'Cotización #1042', 12000, 'Pagado'], ['Café Brava', 'Anticipo 50%', 4500, 'Pendiente'], ['Ríos & Co.', 'Cuota 2 de 3', 9800, 'Vencido'], ['Monte Verde', 'Cotización #1047', 28000, 'Pendiente'], ['Taller 9', 'Mensualidad', 3200, 'Pagado']]
  const suma = (e) => filas.filter((f) => f[3] === e).reduce((a, f) => a + f[2], 0)
  return (
    <>
      <div className="mc-cab"><div><h1>{t}</h1><p>Lo que has cobrado y lo que falta por cobrar. Datos de ejemplo.</p></div></div>
      <div className="mc-kpis">
        <div><small>Cobrado</small><strong>{m}{suma('Pagado').toLocaleString('es')}</strong></div>
        <div><small>Por cobrar</small><strong>{m}{suma('Pendiente').toLocaleString('es')}</strong></div>
        <div className="alerta"><small>Vencido</small><strong>{m}{suma('Vencido').toLocaleString('es')}</strong></div>
      </div>
      <div className="mc-tabla" role="table">
        <div className="mc-fila cab c4" role="row"><span>Cliente</span><span>Concepto</span><span>Monto</span><span>Estado</span></div>
        {filas.map(([c, tt, v, e]) => (
          <div key={c} className="mc-fila c4" role="row"><span><i className="mc-av peq">{c[0]}</i>{c}</span><span>{tt}</span><span>{m}{v.toLocaleString('es')}</span><span><em className={`mc-estado ${e.toLowerCase()}`}>{e}</em></span></div>
        ))}
      </div>
    </>
  )
}

const COLS = [['porHacer', 'Por hacer'], ['enCurso', 'En curso'], ['hecho', 'Hecho']]

function Desarrollo({ t, tareas, onAvanzar }) {
  return (
    <>
      <div className="mc-cab"><div><h1>{t}</h1><p>Lo que está por hacer, en curso y terminado. Toca una tarea para pasarla a la siguiente columna.</p></div></div>
      <div className="mc-tablero">
        {COLS.map(([k, titulo], c) => (
          <div key={k} className="mc-col"><h2>{titulo}<i>{tareas[k].length}</i></h2>
            {tareas[k].map((x) => (
              <button key={x.id} type="button" className="mc-tarea" onClick={() => onAvanzar(k, x)} title={c < 2 ? 'Pasar a la siguiente columna' : 'Volver a “Por hacer”'}>{x.t}</button>
            ))}
            {!tareas[k].length && <p className="mc-vacio chico">Sin tareas</p>}
          </div>
        ))}
      </div>
    </>
  )
}

function Actividad({ eventos, t }) {
  return (
    <>
      <div className="mc-cab"><div><h1>{t}</h1><p>Todo lo que pasa en tu CRM, en orden.</p></div></div>
      <ol className="mc-feed">{eventos.map((e) => <li key={e.id}><span aria-hidden="true">{e.e}</span><b>{e.t}</b><small>{e.h}</small></li>)}</ol>
    </>
  )
}

function Rrhh({ d, lista, total, t }) {
  const n = (v) => lista.filter((c) => c.dueno === v).length + Math.round(d.base / d.vendedores.length)
  return (
    <>
      <div className="mc-cab"><div><h1>{t}</h1><p>Tu gente y lo que le toca a cada quien. {total.toLocaleString('es')} contactos repartidos.</p></div></div>
      <div className="mc-equipo">
        {d.vendedores.map((v, k) => (
          <div key={v} className="mc-persona"><span className="mc-av grande" style={{ background: d.colores[k % d.colores.length] }}>{v[0]}</span><b>{v}</b><small>{k === 0 ? 'Administración' : 'Ventas'}</small><em>{n(v)} contactos</em></div>
        ))}
        {d.vendedores.length === 1 && <div className="mc-persona invita"><span aria-hidden="true">＋</span><b>Invita a tu equipo</b><small>Cuando crezcas, reparte clientes</small></div>}
      </div>
    </>
  )
}

function Automatizaciones({ autos, onAlternar }) {
  return (
    <>
      <div className="mc-cab"><div><h1>Automatizaciones</h1><p>Lo que Shifu hace solo por ti. Actívalas o apágalas cuando quieras, o pídeselo en el chat.</p></div></div>
      <ul className="mc-autos">
        {autos.map((a) => (
          <li key={a.id} className={a.on ? 'on' : ''}>
            <div><span className="mc-pilar">{a.pilar}</span><b>{a.t}</b><small>{a.d}</small></div>
            <button type="button" role="switch" aria-checked={a.on} aria-label={a.t} className="mc-switch" onClick={() => onAlternar(a.id)}><i /></button>
          </li>
        ))}
      </ul>
    </>
  )
}

/* Importar: lo que la persona ya tiene en Excel o en notas. Se pega el texto (copiar celdas de Excel funciona), o se sube un CSV o TXT. */
function leerTexto(texto) {
  const filas = []
  texto.split(/\r?\n/).forEach((linea, i) => {
    const crudo = linea.replace(/^\s*(?:[-•*·]|\d+[.)])\s*/, '').trim()
    if (crudo.length < 2) return
    const celdas = crudo.split(/\t|;|,(?=(?:[^"]*"[^"]*")*[^"]*$)/).map((c) => c.replace(/^"|"$/g, '').trim()).filter(Boolean)
    if (!celdas.length) return
    if (i === 0 && /^(nombre|name|cliente|contacto)\b/i.test(celdas[0])) return
    const nombre = capitaliza(celdas[0])
    if (!/\p{L}/u.test(nombre)) return
    filas.push({ n: nombre, det: celdas.slice(1).join(' · ') })
  })
  return filas.slice(0, 300)
}

function Importar({ existentes, onImportar, onVer }) {
  const [texto, setTexto] = useState('')
  const [nota, setNota] = useState('')
  const [hecho, setHecho] = useState(0)
  const archivo = useRef(null)
  const filas = useMemo(() => {
    const ya = new Set(existentes.map((n) => norm(n)))
    const vistos = new Set()
    return leerTexto(texto).filter((f) => { const k = norm(f.n); if (ya.has(k) || vistos.has(k)) return false; vistos.add(k); return true })
  }, [texto, existentes])
  const total = leerTexto(texto).length

  const subir = (e) => {
    const f = e.target.files?.[0]
    e.target.value = ''
    if (!f) return
    if (/\.xlsx?$/i.test(f.name)) { setNota('Para los archivos de Excel (.xlsx) abre la hoja, copia las celdas y pégalas aquí, o guárdala como CSV y súbela.'); return }
    if (f.size > 1_000_000) { setNota('Ese archivo pesa demasiado para esta versión. Prueba con uno de menos de 1 MB.'); return }
    const lector = new FileReader()
    lector.onload = () => { setTexto(String(lector.result || '')); setNota(`Leí “${f.name}”. Revisa la vista previa y confirma.`) }
    lector.onerror = () => setNota('No pude leer ese archivo.')
    lector.readAsText(f)
  }
  const importar = () => { onImportar(filas); setHecho(filas.length); setTexto(''); setNota('') }

  return (
    <>
      <div className="mc-cab"><div><h1>Importar datos</h1><p>¿Tienes tus clientes en un Excel o en notas? Pásalos aquí y Shifu los ordena como contactos.</p></div></div>
      <div className="mc-imp">
        <div className="mc-imp-izq">
          <label htmlFor="imp-texto"><b>1.</b> Pega tus notas o las celdas de tu Excel</label>
          <textarea id="imp-texto" rows={9} value={texto} onChange={(e) => { setTexto(e.target.value); setHecho(0); setNota('') }}
            placeholder={'Una persona por línea. Por ejemplo:\nLaura Gómez, 5555-1234, laura@correo.com\nRestaurante El Sol\tllamar el lunes\n- Pedro Castillo'} />
          <div className="mc-imp-o"><span>o</span></div>
          <input ref={archivo} type="file" accept=".csv,.tsv,.txt,.xls,.xlsx" hidden onChange={subir} />
          <button type="button" className="mc-subir" onClick={() => archivo.current?.click()}><LuUpload aria-hidden="true" /> Subir un archivo (CSV o TXT)</button>
          {nota && <p className="mc-imp-nota" role="status">{nota}</p>}
        </div>
        <div className="mc-imp-der">
          <b><span>2.</span> Revisa y confirma</b>
          {hecho > 0 && !filas.length && <div className="mc-imp-ok" role="status">✅ Listo: se importaron {hecho} {hecho === 1 ? 'contacto' : 'contactos'}. <button type="button" onClick={onVer}>Ver contactos</button></div>}
          {!texto.trim() && !hecho && <p className="mc-vacio">Cuando pegues algo, aquí verás cómo lo entendió Shifu.</p>}
          {texto.trim() && (
            <>
              <p className="mc-imp-res">Shifu encontró <b>{filas.length}</b> {filas.length === 1 ? 'contacto nuevo' : 'contactos nuevos'}{total > filas.length ? ` (${total - filas.length} ${total - filas.length === 1 ? 'ya existía o se repetía' : 'ya existían o se repetían'})` : ''}.</p>
              <ul className="mc-imp-lista">
                {filas.slice(0, 6).map((f) => <li key={f.n}><i className="mc-av peq">{f.n[0]}</i><b>{f.n}</b><small>{f.det || 'sin más datos'}</small></li>)}
                {filas.length > 6 && <li className="mas">y {filas.length - 6} más…</li>}
              </ul>
              <button type="button" className="btn-pildora" disabled={!filas.length} onClick={importar}>Importar {filas.length || ''} {filas.length === 1 ? 'contacto' : 'contactos'}</button>
            </>
          )}
        </div>
      </div>
    </>
  )
}

/* ───────── Chat con Shifu ───────── */

const SUGERENCIAS = [
  ['Estructura', 'Agrega a Laura Gómez'],
  ['Estructura', 'Agrega la tarea llamar a proveedores'],
  ['Medición', 'Mueve a Ana Morales a Cliente'],
  ['Automatización', 'Activa los recordatorios'],
  ['Estructura', 'Elimina a Luis Pérez'],
]

function ChatShifu({ abierto, setAbierto, mensajes, escribiendo, onEnviar }) {
  const [txt, setTxt] = useState('')
  const fin = useRef(null)
  useEffect(() => { fin.current?.scrollIntoView?.({ block: 'end' }) }, [mensajes, escribiendo, abierto])
  const enviar = (e) => { e?.preventDefault(); if (!txt.trim()) return; onEnviar(txt); setTxt('') }
  const [pista, setPista] = useState(true)
  useEffect(() => { const t = setTimeout(() => setPista(false), 7000); return () => clearTimeout(t) }, [])
  // El chat va fuera de la página (en el body) para que siempre quede fijo en la esquina y no dependa de ningún contenedor.
  return createPortal(
    <div className="mc-chat">
      {abierto && (
        <section className="mc-chat-panel" aria-label="Chat con Shifu">
          <header><ShifuAvatar size={34} /><div><b>Shifu</b><small>Tu asistente del CRM</small></div>
            <button type="button" onClick={() => setAbierto(false)} aria-label="Cerrar el chat"><LuX /></button></header>
          <div className="mc-chat-msgs" role="log" aria-live="polite">
            {mensajes.map((m) => (
              <div key={m.id} className={`cb ${m.de}`}>{m.de === 'shifu' && <ShifuAvatar size={26} />}<p>{m.t}</p></div>
            ))}
            {escribiendo && <div className="cb shifu"><ShifuAvatar size={26} /><p className="puntos" aria-label="Shifu está escribiendo"><i /><i /><i /></p></div>}
            <div ref={fin} />
          </div>
          <div className="mc-chat-sug" aria-label="Ideas para empezar">
            {SUGERENCIAS.map(([p, s]) => <button key={s} type="button" onClick={() => onEnviar(s)}><em>{p}</em>{s}</button>)}
          </div>
          <form onSubmit={enviar}>
            <input value={txt} onChange={(e) => setTxt(e.target.value)} placeholder="Pídele a Shifu agregar, cambiar o quitar algo…" aria-label="Mensaje para Shifu" maxLength={300} />
            <button type="submit" disabled={!txt.trim()} aria-label="Enviar"><LuSend /></button>
          </form>
        </section>
      )}
      <button type="button" className={`mc-chat-btn ${abierto ? 'abierto' : ''}`} onClick={() => setAbierto(!abierto)} aria-expanded={abierto} aria-label={abierto ? 'Cerrar el chat con Shifu' : 'Abrir el chat con Shifu'}>
        {abierto ? <LuX /> : <><ShifuAvatar size={46} /><i className="punto" /></>}
      </button>
      {!abierto && pista && <span className="mc-chat-hint">¿Qué cambiamos hoy?</span>}
    </div>,
    document.body,
  )
}

/* ───────── Página ───────── */

export default function CrmPage() {
  const nav = useNavigate()
  const { state } = useLocation()
  const guardado = useMemo(leer, [])
  const r = guardado?.resp
  const [cargando, setCargando] = useState(!!state?.cargar)
  const [vista, setVista] = useState('contactos')
  const [buscar, setBuscar] = useState('')
  const [bienvenida, setBienvenida] = useState(true)
  const [nombres, setNombres] = useState({})

  const d = useMemo(() => {
    if (!r) return null
    const total = CARTERA[r.cartera] || 60
    const personas = PERSONAS[r.equipo] || 1
    return {
      nombre: r.nombre || 'Mi negocio', total, base: Math.max(0, total - Math.min(total, 16)),
      vendedores: ['Tú', ...EQUIPO, 'Ana Ruiz'].slice(0, personas),
      colores: ['#7c5cff', '#22d3a6', '#f0587a', '#f5a623'],
      canales: (r.canales?.length ? r.canales : ['whatsapp']).map((c) => etiqueta('canales', c)),
      moneda: MONEDA[r.ubicacion?.pais] || '$',
      rubro: r.rubro ? etiqueta('rubro', r.rubro) : 'tu negocio',
    }
  }, [r])

  const [contactos, setContactos] = useState(() => (d ? Array.from({ length: Math.min(d.total, 16) }, (_, k) => ({
    id: nuevoId(), n: NOMBRES[k % NOMBRES.length], canal: d.canales[k % d.canales.length], etapa: ETAPAS[k % 4], dueno: d.vendedores[k % d.vendedores.length], dias: (k % 6) + 1,
  })) : []))
  const [tareas, setTareas] = useState(() => ({
    porHacer: ['Importar contactos', 'Definir etapas de venta', 'Plantilla de cotización'].map((t) => ({ id: nuevoId(), t })),
    enCurso: ['Conectar WhatsApp', 'Invitar al equipo'].map((t) => ({ id: nuevoId(), t })),
    hecho: ['Crear cuenta', 'Responder el cuestionario'].map((t) => ({ id: nuevoId(), t })),
  }))
  const [eventos, setEventos] = useState(() => (d ? [
    ['🤖', 'Shifu creó tu CRM', 'hace un momento'], ['📥', `Se cargaron ${d.total.toLocaleString('es')} contactos de ejemplo`, 'hace un momento'],
    ['🔔', 'Se activaron los recordatorios de seguimiento', 'hace 1 min'], ['💬', `Canales listos para conectar: ${d.canales.join(', ')}`, 'hace 1 min'], ['👋', 'Cuenta creada', 'hoy'],
  ].map(([e, t, h]) => ({ id: nuevoId(), e, t, h })) : []))
  const [autos, setAutos] = useState(() => {
    if (!r) return []
    const quiere = (v) => r.objetivos?.includes(v)
    const canal = (v) => r.canales?.includes(v)
    return [
      { id: 'recordatorios', pilar: 'Estructura', t: 'Recordatorios de seguimiento', d: 'Te avisa cuando un contacto lleva 3 días sin respuesta.', on: quiere('seguimientos') || r.problemas?.includes('olvido') || false },
      { id: 'bienvenida', pilar: 'Estructura', t: 'Bienvenida automática por WhatsApp', d: 'Responde al instante cuando alguien te escribe por primera vez.', on: canal('whatsapp') },
      { id: 'contacto', pilar: 'Estructura', t: 'Crear el contacto desde cada mensaje', d: 'Shifu detecta quién te escribe y lo agrega con lo que pidió.', on: quiere('ia') },
      { id: 'reparto', pilar: 'Medición y equipo', t: 'Repartir contactos nuevos entre el equipo', d: 'Cada contacto nuevo se asigna por turnos a tu equipo.', on: !!r.equipo && r.equipo !== 'solo' },
      { id: 'vencidos', pilar: 'Medición y equipo', t: 'Aviso de cobros vencidos', d: 'Te avisa y le recuerda al cliente cuando un pago se atrasa.', on: false },
      { id: 'resumen', pilar: 'Medición y equipo', t: 'Resumen semanal por correo', d: 'Cada lunes recibes cuánto vendiste, cuánto falta y quién avanzó más.', on: quiere('reportes') },
    ]
  })

  const menu = useMemo(() => menuDe(r?.rubro, nombres), [r, nombres])
  const tit = (id) => menu.find((m) => m.id === id)?.t
  const total = d ? d.base + contactos.length : 0

  const registrar = (e, t) => setEventos((ev) => [{ id: nuevoId(), e, t, h: 'ahora' }, ...ev].slice(0, 30))
  const agregarContactos = (filas, canal = 'Chat con Shifu') => {
    setContactos((c) => [...filas.map((f) => ({ id: nuevoId(), n: f.n, det: f.det, canal, etapa: 'Nuevo', dueno: 'Tú', dias: 0 })), ...c])
  }
  const borrarContacto = (c) => { setContactos((l) => l.filter((x) => x.id !== c.id)); registrar('🗑️', `Eliminaste a ${c.n}`) }
  const avanzarTarea = (col, x) => {
    const sig = { porHacer: 'enCurso', enCurso: 'hecho', hecho: 'porHacer' }[col]
    setTareas((t) => ({ ...t, [col]: t[col].filter((y) => y.id !== x.id), [sig]: [...t[sig], x] }))
  }
  const alternarAuto = (id) => {
    const a = autos.find((x) => x.id === id)
    setAutos((l) => l.map((x) => (x.id === id ? { ...x, on: !x.on } : x)))
    registrar(a.on ? '⏸️' : '⚡', `${a.on ? 'Apagaste' : 'Activaste'}: ${a.t}`)
  }

  /* Chat: Shifu entiende frases sencillas para agregar, modificar y eliminar. Pide confirmación antes de borrar. */
  const [chatAbierto, setChatAbierto] = useState(false)
  const [mensajes, setMensajes] = useState(() => [{ id: nuevoId(), de: 'shifu', t: 'Hola 👋 Soy Shifu. Dime qué quieres agregar, cambiar o quitar de tu CRM. Si tienes datos en Excel o en notas, pásalos por “Importar datos”.' }])
  const [escribiendo, setEscribiendo] = useState(false)
  const pendiente = useRef(null)
  const temporizador = useRef(null)
  useEffect(() => () => clearTimeout(temporizador.current), [])

  const buscarContacto = (q) => { const k = norm(q); return k ? contactos.find((c) => norm(c.n).includes(k)) : undefined }
  const buscarSeccion = (q) => { const k = norm(q); return k ? menu.find((m) => norm(m.t).includes(k) || k.includes(norm(m.t))) : undefined }
  const buscarEtapa = (q) => { const k = norm(q); return ETAPAS.find((e) => norm(e) === k || k.includes(norm(e).split(' ').pop())) }
  const buscarTarea = (q) => { const k = norm(q); for (const [col] of COLS) { const x = tareas[col].find((y) => norm(y.t).includes(k)); if (x) return [col, x] } return null }

  const entender = (crudo) => {
    const texto = crudo.trim()
    const t = norm(texto)

    if (pendiente.current) {
      const p = pendiente.current
      pendiente.current = null
      if (/^(si|claro|dale|confirmo|ok|adelante|borralo|eliminalo)/.test(t)) {
        if (p.tipo === 'contacto') { borrarContacto(p.c); return `Listo, eliminé a ${p.c.n} de tu CRM.` }
        setTareas((tt) => ({ ...tt, [p.col]: tt[p.col].filter((y) => y.id !== p.x.id) })); registrar('🗑️', `Eliminaste la tarea “${p.x.t}”`)
        return `Listo, eliminé la tarea “${p.x.t}”.`
      }
      return 'Perfecto, no borré nada. 👍'
    }

    if (/(import|excel|notas|csv|hoja de calculo|sheets|archivo)/.test(t)) { setVista('importar'); return 'Claro. Te llevé a “Importar datos”: pega ahí tus notas o las celdas de tu Excel y yo las ordeno como contactos.' }

    let m = t.match(/^(activa|enciende|prende|desactiva|apaga)r?\s+(?:la\s+|el\s+|las\s+|los\s+)?(.+)$/)
    if (m) {
      const k = norm(m[2]).split(' ').filter((w) => w.length > 3)
      const a = autos.find((x) => k.some((w) => norm(x.t).includes(w.slice(0, 6))))
      if (!a) return `No encontré esa automatización. Tienes: ${autos.map((x) => x.t.toLowerCase()).join(', ')}.`
      const quiere = /^(activa|enciende|prende)/.test(m[1])
      setAutos((l) => l.map((x) => (x.id === a.id ? { ...x, on: quiere } : x))); registrar(quiere ? '⚡' : '⏸️', `${quiere ? 'Activaste' : 'Apagaste'}: ${a.t}`); setVista('automatizaciones')
      return `${quiere ? 'Activé' : 'Apagué'} “${a.t}”.`
    }

    m = texto.match(/^(?:renombra|renombrar|cambia(?:r)?(?:\s+el\s+nombre\s+de)?|mueve|pasa|modifica|actualiza|pon)\s+(?:la\s+secci[oó]n\s+|secci[oó]n\s+|la\s+etapa\s+de\s+|a\s+)?(.+?)\s+(?:a|por|como)\s+(.+)$/i)
    if (m) {
      const [, x, y] = m
      const sec = buscarSeccion(x)
      if (sec && !buscarContacto(x)) {
        const nuevo = capitaliza(y).slice(0, 28)
        setNombres((n) => ({ ...n, [sec.id]: nuevo })); registrar('✏️', `Renombraste “${sec.t}” a “${nuevo}”`)
        return `Hecho: ahora la sección se llama “${nuevo}”.`
      }
      const c = buscarContacto(x)
      if (c) {
        const et = buscarEtapa(y)
        if (et) { setContactos((l) => l.map((z) => (z.id === c.id ? { ...z, etapa: et, dias: 0 } : z))); registrar('🔁', `${c.n} pasó a “${et}”`); setVista('contactos'); return `Listo: ${c.n} ahora está en “${et}”.` }
        const nuevo = capitaliza(y).slice(0, 40)
        setContactos((l) => l.map((z) => (z.id === c.id ? { ...z, n: nuevo } : z))); registrar('✏️', `${c.n} ahora se llama ${nuevo}`); setVista('contactos')
        return `Listo, cambié el nombre de ${c.n} a ${nuevo}.`
      }
      return `No encontré “${x}” ni como sección ni como contacto. ¿Me das el nombre tal como aparece?`
    }

    m = texto.match(/^(?:elimina(?:r)?|borra(?:r)?|quita(?:r)?|saca(?:r)?|remueve)\s+(?:a\s+|al\s+|el\s+|la\s+)?(.+)$/i)
    if (m) {
      const tarea = m[1].match(/^tarea\s*:?\s*(.+)$/i)
      if (tarea) {
        const hit = buscarTarea(tarea[1])
        if (!hit) return `No encontré la tarea “${tarea[1]}”.`
        pendiente.current = { tipo: 'tarea', col: hit[0], x: hit[1] }
        return `¿Seguro que quieres eliminar la tarea “${hit[1].t}”? Responde “sí” para confirmar.`
      }
      const c = buscarContacto(m[1].replace(/^(contacto|cliente|paciente|alumno|comprador|interesado|cuenta)\s+/i, ''))
      if (!c) return `No encuentro a “${m[1]}”. Escríbelo como aparece en tu lista.`
      pendiente.current = { tipo: 'contacto', c }
      return `¿Seguro que quieres eliminar a ${c.n}? Responde “sí” para confirmar.`
    }

    m = texto.match(/^(?:agrega(?:r)?|a[ñn]ade|a[ñn]adir|crea(?:r)?|registra(?:r)?|anota(?:r)?|suma(?:r)?|nuevo|nueva)\s+(.+)$/i)
    if (m) {
      const tarea = m[1].match(/^(?:la\s+|una\s+)?tarea\s*:?\s*(.+)$/i)
      if (tarea) {
        const nombre = tarea[1].trim().replace(/^./, (c) => c.toUpperCase()).slice(0, 60)
        setTareas((tt) => ({ ...tt, porHacer: [...tt.porHacer, { id: nuevoId(), t: nombre }] })); registrar('✅', `Agregaste la tarea “${nombre}”`); setVista('desarrollo')
        return `Anoté la tarea “${nombre}” en “Por hacer”.`
      }
      const nombre = capitaliza(m[1].replace(/^(?:a\s+|al\s+|un\s+|una\s+|el\s+|la\s+)?(?:contacto|cliente|paciente|alumno|comprador|interesado|cuenta|prospecto)?\s*(?:llamad[oa]\s+)?/i, '')).slice(0, 40)
      if (nombre.length < 2) return '¿Cómo se llama? Por ejemplo: “Agrega a Laura Gómez”.'
      if (buscarContacto(nombre)?.n.toLowerCase() === nombre.toLowerCase()) return `${nombre} ya está en tu lista.`
      agregarContactos([{ n: nombre }]); registrar('➕', `Agregaste a ${nombre}`); setVista('contactos')
      return `Listo, agregué a ${nombre} en “${tit('contactos')}”, en la etapa “Nuevo”.`
    }

    if (/^(hola|buenas|hey|ayuda|que puedes|qué puedes)/.test(t)) return 'Puedo agregar contactos y tareas, cambiarlos de etapa o de nombre, renombrar secciones, activar automatizaciones y eliminar lo que ya no uses (siempre te pido confirmación).'
    return 'Aún no entendí eso. Prueba con: “Agrega a Laura Gómez”, “Renombra Cobros a Facturación”, “Mueve a Ana Morales a Cliente”, “Activa los recordatorios” o “Elimina a Luis Pérez”.'
  }

  const enviar = (texto) => {
    setMensajes((l) => [...l, { id: nuevoId(), de: 'yo', t: texto.trim() }])
    const respuesta = entender(texto)
    setEscribiendo(true)
    clearTimeout(temporizador.current)
    temporizador.current = setTimeout(() => { setEscribiendo(false); setMensajes((l) => [...l, { id: nuevoId(), de: 'shifu', t: respuesta }]) }, 550)
  }

  const pasos = useMemo(() => {
    if (!d) return []
    const obj = r.objetivos?.[0] ? etiqueta('objetivos', r.objetivos[0]) : null
    return [
      `Leyendo lo que nos contaste de ${d.nombre}`,
      `Preparando un CRM para ${d.rubro.toLowerCase()}`,
      `Dejando listos tus canales: ${d.canales.slice(0, 2).join(' y ')}`,
      obj ? `Poniendo primero: ${obj.toLowerCase()}` : 'Ordenando tus secciones',
      'Cargando datos de ejemplo para que lo pruebes',
      'Dando los últimos toques',
    ]
  }, [d, r])

  // Sin respuestas guardadas no hay nada que armar: se manda al cuestionario.
  if (!d) return <Navigate to="/bienvenida" replace />
  if (cargando) return <Cargando pasos={pasos} onListo={() => { setCargando(false); nav('/mi-crm', { replace: true, state: null }) }} />

  const rehacer = () => { try { localStorage.removeItem(CLAVE) } catch { /* sin almacenamiento */ } nav('/bienvenida') }
  const ir = (id) => { setVista(id); setBuscar('') }

  return (
    <div className="mc">
      <header className="mc-top">
        <Link to="/" aria-label="Shifu"><Logo height={24} /></Link>
        <span className="mc-negocio">{d.nombre}</span>
        <label className="mc-buscar"><LuSearch aria-hidden="true" />
          <input type="search" placeholder="Buscar en todo el espacio…" value={buscar} onChange={(e) => { setBuscar(e.target.value); if (e.target.value) setVista('contactos') }} aria-label="Buscar" />
        </label>
        <button type="button" className="mc-camp" aria-label="Avisos"><LuBell /><i>3</i></button>
        <span className="mc-yo" aria-hidden="true">{d.nombre[0].toUpperCase()}</span>
      </header>

      <div className="mc-cuerpo">
        <nav className="mc-menu" aria-label="Secciones">
          {GRUPOS.map((g, gi) => (
            <div key={g} className="mc-grupo">
              <h2>{g}</h2>
              <ul>
                {menu.filter((m) => m.grupo === gi).map(({ id, t, I }) => (
                  <li key={id}><button type="button" className={vista === id ? 'on' : ''} aria-current={vista === id ? 'page' : undefined} onClick={() => ir(id)}><I aria-hidden="true" />{t}</button></li>
                ))}
              </ul>
            </div>
          ))}
          <button type="button" className="mc-rehacer" onClick={rehacer}><LuRotateCcw aria-hidden="true" /> Repetir cuestionario</button>
        </nav>

        <main className="mc-main">
          {bienvenida && (
            <aside className="mc-shifu" role="status">
              <ShifuAvatar size={40} />
              <p><b>Listo, {d.nombre}.</b> Armé tu CRM con {menu.length} secciones, {d.total.toLocaleString('es')} contactos de ejemplo y tus canales ({d.canales.join(', ')}). Pídeme cambios desde el chat de abajo a la derecha.</p>
              <button type="button" onClick={() => setBienvenida(false)} aria-label="Cerrar">✕</button>
            </aside>
          )}
          {vista === 'contactos' && <Contactos d={d} lista={contactos} total={total} buscar={buscar} t={tit('contactos')} onBorrar={borrarContacto} />}
          {vista === 'desarrollo' && <Desarrollo t={tit('desarrollo')} tareas={tareas} onAvanzar={avanzarTarea} />}
          {vista === 'importar' && (
            <Importar existentes={contactos.map((c) => c.n)} onVer={() => ir('contactos')}
              onImportar={(filas) => { agregarContactos(filas, 'Importado'); registrar('📥', `Importaste ${filas.length} ${filas.length === 1 ? 'contacto' : 'contactos'} desde tus notas o Excel`) }} />
          )}
          {vista === 'cobros' && <Cobros d={d} t={tit('cobros')} />}
          {vista === 'actividad' && <Actividad eventos={eventos} t={tit('actividad')} />}
          {vista === 'rrhh' && <Rrhh d={d} lista={contactos} total={total} t={tit('rrhh')} />}
          {vista === 'automatizaciones' && <Automatizaciones autos={autos} onAlternar={alternarAuto} />}
        </main>
      </div>

      <ChatShifu abierto={chatAbierto} setAbierto={setChatAbierto} mensajes={mensajes} escribiendo={escribiendo} onEnviar={enviar} />
    </div>
  )
}

import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import Logo from '../components/Logo'
import ShifuAvatar from '../components/ShifuAvatar'
import { SelectorCaptura, capturarRegion, imagenDeArchivo } from '../components/CapturaPantalla'
import { HAY_SERVIDOR, auth, chat as apiChat, crm as apiCrm } from '../api'
import { etiqueta } from '../brief/preguntas'
import { borrarBorrador, guardarBorrador, leerBorrador } from '../brief/borrador'
import { COLUMNAS, ETAPAS, tituloSeccion } from '../crm/secciones'
import { LuUsers, LuWallet, LuCode, LuActivity, LuIdCard, LuSearch, LuBell, LuLogOut, LuPlus, LuRotateCcw, LuTable, LuUpload, LuZap, LuCamera, LuSend, LuSun, LuMoon, LuX } from 'react-icons/lu'
import '../crm.css'
import '../crm-extra.css'
import '../crm-captura.css'

/* El CRM básico que Shifu arma al terminar el cuestionario, con el tema oscuro de Shifu. Todo gira en torno a tres ideas:
 *   · Estructura: cómo está ordenado el negocio (contactos, trabajo del día a día e importación de Excel y notas).
 *   · Medición y equipo: cuánto se cobra, qué pasa y quién hace qué.
 *   · Automatizaciones: lo que Shifu hace solo.
 * Esta pantalla no guarda nada por su cuenta: todo se pide y se cambia a través de `../api` (ver API.md). Cada cambio devuelve el
 * CRM completo y actualizado, y la pantalla solo lo reemplaza. Los cobros todavía son de ejemplo (no hay contrato para ellos). */

const norm = (s) => s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').trim()
const capitaliza = (s) => s.trim().replace(/\s+/g, ' ').replace(/(^|\s)(\p{L})/gu, (_, a, b) => a + b.toUpperCase())

const MONEDA = { gt: 'Q', mx: '$', co: '$', es: '€', us: '$', otro: '$' }
const COLORES = ['#7c5cff', '#22d3a6', '#f0587a', '#f5a623']

const BASE = [
  { id: 'contactos', I: LuUsers, grupo: 0 }, { id: 'desarrollo', I: LuCode, grupo: 0 },
  { id: 'cobros', I: LuWallet, grupo: 1 }, { id: 'actividad', I: LuActivity, grupo: 1 }, { id: 'rrhh', I: LuIdCard, grupo: 1 },
]
const GRUPOS = ['Estructura', 'Medición y equipo', 'Automatizaciones']
const menuDe = (rubro, secciones, ocultas = [], listas = []) => [
  ...BASE.map((m) => ({ ...m, t: tituloSeccion(rubro, m.id, secciones) })),
  { id: 'importar', t: tituloSeccion(rubro, 'importar'), I: LuUpload, grupo: 0 },
  { id: 'automatizaciones', t: tituloSeccion(rubro, 'automatizaciones'), I: LuZap, grupo: 2 },
].filter((m) => !ocultas.includes(m.id)).concat(listas.map((l) => ({ id: l.id, t: l.nombre, I: LuTable, grupo: 0, propia: true })))

/** Cómo se ve el valor de un campo según su tipo. */
const verValor = (tipo, v) => (v === undefined || v === null || v === '' ? '—' : tipo === 'fecha' ? String(v).split('-').reverse().join('/') : tipo === 'numero' ? Number(v).toLocaleString('es') : String(v))

/* ───────── Pantalla de carga ───────── */

function Cargando({ pasos, listo, onListo }) {
  const [hechos, setHechos] = useState(0)
  useEffect(() => {
    const fin = hechos >= pasos.length
    if (fin && !listo) return undefined // la animación terminó pero el CRM aún no llega: se espera
    const quieto = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const t = setTimeout(() => (fin ? onListo() : setHechos(hechos + 1)), fin ? 700 : quieto ? 250 : 1050)
    return () => clearTimeout(t)
  }, [hechos, pasos.length, listo, onListo])
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

function Fallo({ onReintentar }) {
  return (
    <div className="carga" role="alert">
      <img className="carga-shifu" src="/img/shifu-cabeza.webp" alt="" width="110" height="110" />
      <h1>No pudimos abrir tu CRM</h1>
      <p className="carga-sub">Revisa tu conexión e inténtalo de nuevo. Tus respuestas del cuestionario siguen guardadas.</p>
      <button type="button" className="btn-pildora btn-grande" onClick={onReintentar}>Reintentar</button>
    </div>
  )
}

/* ───────── Vistas ───────── */

function Contactos({ lista, total, buscar, t, onBorrar, onImportar, etapas, campos }) {
  const q = norm(buscar)
  const vis = q ? lista.filter((f) => norm(f.n).includes(q)) : lista
  const por = (e) => lista.filter((c) => c.etapa === e).length
  const cols = { '--cols': `1.6fr 1fr 1fr 1.2fr ${campos.map(() => '1fr').join(' ')} 1fr`.replace(/\s+/g, ' ') }
  return (
    <>
      <div className="mc-cab"><div><h1>{t}</h1><p>{total === 0 ? 'Todavía no tienes ninguno.' : `${total.toLocaleString('es')} en total.`}</p></div></div>
      <div className="mc-kpis c4k" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))' }}>
        <div><small>En total</small><strong>{total.toLocaleString('es')}</strong></div>
        {etapas.map((e) => <div key={e}><small>{e}</small><strong>{por(e)}</strong></div>)}
      </div>
      {total === 0 && (
        <div className="mc-vacio-grande">
          <b>Aquí aparecerán tus {t.toLowerCase()}</b>
          <p>Pídele a Shifu en el chat que agregue el primero (por ejemplo, “Agrega a Laura Gómez”) o trae de una vez los que ya tienes en un Excel o en tus notas.</p>
          <button type="button" className="btn-pildora" onClick={onImportar}>Importar desde Excel o notas</button>
        </div>
      )}
      {total > 0 && <div className="mc-tabla" role="table">
        <div className="mc-fila cab" role="row" style={cols}><span>Nombre</span><span>Canal</span><span>Etapa</span><span>Responsable</span>{campos.map((c) => <span key={c.id}>{c.nombre}</span>)}<span>Último contacto</span></div>
        {vis.map((f) => (
          <div key={f.id} className="mc-fila" role="row" style={cols}>
            <span><i className="mc-av peq">{f.n[0]}</i><span className="mc-nom">{f.n}{f.det && <small>{f.det}</small>}</span></span>
            <span>{f.canal}</span><span><em className="mc-estado">{f.etapa}</em></span><span>{f.dueno}</span>
            {campos.map((c) => <span key={c.id}>{verValor(c.tipo, f.extra?.[c.id])}</span>)}
            <span className="mc-ultimo">{f.dias === 0 ? 'hoy' : `hace ${f.dias} ${f.dias === 1 ? 'día' : 'días'}`}
              <button type="button" className="mc-x" aria-label={`Eliminar a ${f.n}`} onClick={() => onBorrar(f)}><LuX /></button></span>
          </div>
        ))}
        {!vis.length && <p className="mc-vacio">Nada coincide con “{buscar}”.</p>}
      </div>}
    </>
  )
}

/** Una sección propia: una tabla con los campos que la persona (o Shifu) definió. La estructura se cambia por el chat. */
function Lista({ lista, onAgregar, onBorrar }) {
  const [abierto, setAbierto] = useState(false)
  const [vals, setVals] = useState({})
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)
  const cols = { '--cols': `${lista.campos.map(() => 'minmax(0, 1fr)').join(' ')} 36px` }
  const enviar = async (e) => {
    e.preventDefault()
    const llenos = Object.fromEntries(Object.entries(vals).filter(([, v]) => String(v ?? '').trim() !== ''))
    if (!Object.keys(llenos).length) { setError('Escribe al menos un valor.'); return }
    setEnviando(true)
    const ok = await onAgregar(lista.id, llenos)
    setEnviando(false)
    if (ok) { setVals({}); setError(''); setAbierto(false) } else setError('No se pudo guardar. Revisa los valores.')
  }
  const nuevo = () => { setError(''); setVals({}); setAbierto(true) }
  return (
    <>
      <div className="mc-cab">
        <div><h1>{lista.nombre}</h1><p>{lista.registros.length === 0 ? 'Todavía no tiene registros.' : `${lista.registros.length.toLocaleString('es')} ${lista.registros.length === 1 ? 'registro' : 'registros'}.`} Para cambiar los campos o quitar la sección, pídeselo a Shifu en el chat.</p></div>
        {!abierto && <button type="button" className="btn-pildora" onClick={nuevo}><LuPlus aria-hidden="true" /> Agregar</button>}
      </div>
      {abierto && (
        <form className="mc-form-registro" onSubmit={enviar} noValidate>
          {lista.campos.map((c) => (
            <label key={c.id}>{c.nombre}
              <input type={c.tipo === 'numero' ? 'text' : c.tipo === 'fecha' ? 'date' : 'text'} inputMode={c.tipo === 'numero' ? 'decimal' : undefined} maxLength={200}
                value={vals[c.id] ?? ''} onChange={(e) => setVals((v) => ({ ...v, [c.id]: e.target.value }))} />
            </label>
          ))}
          {error && <p className="mc-form-error" role="alert">{error}</p>}
          <div className="mc-form-acciones">
            <button type="submit" className="btn-pildora" disabled={enviando}>{enviando ? 'Guardando…' : 'Guardar'}</button>
            <button type="button" className="mc-link" onClick={() => setAbierto(false)}>Cancelar</button>
          </div>
        </form>
      )}
      {lista.registros.length === 0 && !abierto && (
        <div className="mc-vacio-grande">
          <b>Esta sección está vacía</b>
          <p>Pídele a Shifu que agregue el primero (por ejemplo, “agrega a {lista.nombre.toLowerCase()} …”) o usa el botón Agregar.</p>
        </div>
      )}
      {lista.registros.length > 0 && (
        <div className="mc-tabla" role="table">
          <div className="mc-fila cab" role="row" style={cols}>{lista.campos.map((c) => <span key={c.id}>{c.nombre}</span>)}<span /></div>
          {lista.registros.map((r) => (
            <div key={r.id} className="mc-fila" role="row" style={cols}>
              {lista.campos.map((c) => <span key={c.id}>{verValor(c.tipo, r.valores[c.id])}</span>)}
              <span><button type="button" className="mc-x" aria-label="Eliminar este registro" onClick={() => onBorrar(lista.id, r.id)}><LuX /></button></span>
            </div>
          ))}
        </div>
      )}
    </>
  )
}

function Cobros({ moneda, t }) {
  // Todavía no hay módulo de cobros en el servidor: se muestra vacío, sin cifras de ejemplo.
  const m = moneda
  return (
    <>
      <div className="mc-cab"><div><h1>{t}</h1><p>Lo que has cobrado y lo que falta por cobrar.</p></div></div>
      <div className="mc-kpis">
        <div><small>Cobrado</small><strong>{m}0</strong></div>
        <div><small>Por cobrar</small><strong>{m}0</strong></div>
        <div className="alerta"><small>Vencido</small><strong>{m}0</strong></div>
      </div>
      <div className="mc-vacio-grande">
        <b>Aún no hay cobros registrados</b>
        <p>Cuando conectemos tus cobros, aquí verás lo que te pagaron y lo que está pendiente.</p>
      </div>
    </>
  )
}

function Desarrollo({ t, tareas, onMover }) {
  return (
    <>
      <div className="mc-cab"><div><h1>{t}</h1><p>Lo que está por hacer, en curso y terminado. Toca una tarea para pasarla a la siguiente columna.</p></div></div>
      <div className="mc-tablero">
        {COLUMNAS.map(([k, titulo], c) => (
          <div key={k} className="mc-col"><h2>{titulo}<i>{tareas[k].length}</i></h2>
            {tareas[k].map((x) => (
              <button key={x.id} type="button" className="mc-tarea" onClick={() => onMover(x, COLUMNAS[(c + 1) % COLUMNAS.length][0])} title={c < 2 ? 'Pasar a la siguiente columna' : 'Volver a “Por hacer”'}>{x.t}</button>
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

function Rrhh({ vendedores, lista, total, t }) {
  const resto = Math.max(0, total - lista.length)
  const n = (v) => lista.filter((c) => c.dueno === v).length + Math.round(resto / vendedores.length)
  return (
    <>
      <div className="mc-cab"><div><h1>{t}</h1><p>Tu gente y lo que le toca a cada quien. {total.toLocaleString('es')} contactos repartidos.</p></div></div>
      <div className="mc-equipo">
        {vendedores.map((v, k) => (
          <div key={v} className="mc-persona"><span className="mc-av grande" style={{ background: COLORES[k % COLORES.length] }}>{v[0]}</span><b>{v}</b><small>{k === 0 ? 'Administración' : 'Ventas'}</small><em>{n(v)} contactos</em></div>
        ))}
        {vendedores.length === 1 && <div className="mc-persona invita"><span aria-hidden="true">＋</span><b>Invita a tu equipo</b><small>Cuando crezcas, reparte clientes</small></div>}
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
            <button type="button" role="switch" aria-checked={a.on} aria-label={a.t} className="mc-switch" onClick={() => onAlternar(a)}><i /></button>
          </li>
        ))}
      </ul>
    </>
  )
}

/* Importar: lo que la persona ya tiene en Excel o en notas. Se pega el texto (copiar celdas de Excel funciona), o se sube un CSV o TXT.
 * La lectura del texto se hace aquí, en el navegador; al confirmar se manda la lista de contactos ya limpia. */
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
  const [enviando, setEnviando] = useState(false)
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
  const importar = async () => {
    setEnviando(true)
    const ok = await onImportar(filas)
    setEnviando(false)
    if (ok) { setHecho(filas.length); setTexto(''); setNota('') } else setNota('No se pudo importar. Inténtalo de nuevo.')
  }

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
              <button type="button" className="btn-pildora" disabled={!filas.length || enviando} onClick={importar}>Importar {filas.length || ''} {filas.length === 1 ? 'contacto' : 'contactos'}</button>
            </>
          )}
        </div>
      </div>
    </>
  )
}

/* ───────── Chat con Shifu ───────── */

/** Ideas para el chat. Las que nombran a un contacto usan uno que de verdad existe; si no hay ninguno, solo salen las generales. */
function sugerenciasDe(contactos) {
  const base = [
    ['Estructura', 'Agrega a Laura Gómez'],
    ['Estructura', 'Crea una sección para mis proveedores'],
    ['Estructura', 'Cambia las etapas a Prospecto, Cotización y Cliente'],
    ['Automatización', 'Activa los recordatorios'],
  ]
  const primero = contactos[0]?.n
  return primero ? [...base, ['Medición', `Mueve a ${primero} a Cliente`], ['Estructura', `Elimina a ${primero}`]] : base
}

function ChatShifu({ tema, abierto, setAbierto, mensajes, escribiendo, onEnviar, sugerencias, modo }) {
  const [txt, setTxt] = useState('')
  const [imagen, setImagen] = useState(null) // captura o imagen pegada, lista para mandar con el mensaje
  const [eligiendo, setEligiendo] = useState(false)
  const [capturando, setCapturando] = useState(false)
  const [errorImg, setErrorImg] = useState('')
  // Consejo de la cámara: sale cada vez que se abre el chat y se va al tocar la cámara, al cerrarlo o a los 12 segundos.
  const [consejo, setConsejo] = useState(false)
  const cerrarConsejo = () => setConsejo(false)
  useEffect(() => {
    if (!abierto) { setConsejo(false); return undefined }
    setConsejo(true)
    const t = setTimeout(() => setConsejo(false), 12000)
    return () => clearTimeout(t)
  }, [abierto])
  const fin = useRef(null)
  const campo = useRef(null)
  useEffect(() => { fin.current?.scrollIntoView?.({ block: 'end' }) }, [mensajes, escribiendo, abierto])
  const enviar = (e) => {
    e?.preventDefault()
    if ((!txt.trim() && !imagen) || escribiendo) return
    onEnviar(txt, imagen); setTxt(''); setImagen(null); setErrorImg('')
  }
  const [pista, setPista] = useState(true)
  useEffect(() => { const t = setTimeout(() => setPista(false), 7000); return () => clearTimeout(t) }, [])

  const elegida = async (region) => {
    setEligiendo(false); setCapturando(true); setErrorImg('')
    await new Promise((r) => setTimeout(r, 60)) // deja que la capa del selector desaparezca antes de dibujar
    try { setImagen(await capturarRegion(region)) } catch { setErrorImg('No pude tomar la captura. Inténtalo de nuevo o pega una imagen.') }
    setCapturando(false)
    setTimeout(() => campo.current?.focus(), 0)
  }
  const pegar = async (e) => {
    const archivo = [...(e.clipboardData?.files || [])].find((f) => f.type.startsWith('image/'))
    if (!archivo) return
    e.preventDefault()
    try { setImagen(await imagenDeArchivo(archivo)); setErrorImg('') } catch { setErrorImg('No pude usar esa imagen.') }
  }

  // El chat va fuera de la página (en el body) para que siempre quede fijo en la esquina y no dependa de ningún contenedor.
  return createPortal(
    <div className="mc-chat" data-tema={tema}>
      {abierto && (
        <section className="mc-chat-panel" aria-label="Chat con Shifu" hidden={eligiendo || capturando}>
          <header><ShifuAvatar size={34} /><div><b>Shifu</b><small>{modo === 'reglas' ? 'Modo básico · la IA no está disponible' : 'Tu asistente del CRM'}</small></div>
            <button type="button" onClick={() => setAbierto(false)} aria-label="Cerrar el chat"><LuX /></button></header>
          <div className="mc-chat-msgs" role="log" aria-live="polite">
            {mensajes.map((m) => (
              <div key={m.id} className={`cb ${m.de}`}>{m.de === 'shifu' && <ShifuAvatar size={26} />}
                <p>{m.imagen && <img className="cb-img" src={m.imagen} alt="Captura enviada a Shifu" />}{m.t}</p></div>
            ))}
            {escribiendo && <div className="cb shifu"><ShifuAvatar size={26} /><p className="puntos" aria-label="Shifu está escribiendo"><i /><i /><i /></p></div>}
            <div ref={fin} />
          </div>
          <div className="mc-chat-sug" aria-label="Ideas para empezar">
            {sugerencias.map(([p, s]) => <button key={s} type="button" disabled={escribiendo} onClick={() => onEnviar(s)}><em>{p}</em>{s}</button>)}
          </div>
          {(imagen || errorImg) && (
            <div className="mc-adjunto" role="status">
              {imagen && <img src={imagen.url} alt="Captura lista para enviar" />}
              <span>{imagen ? 'Captura lista. Cuéntale a Shifu qué quieres hacer con esto.' : errorImg}</span>
              <button type="button" onClick={() => { setImagen(null); setErrorImg('') }} aria-label="Quitar la captura"><LuX /></button>
            </div>
          )}
          {consejo && !imagen && !errorImg && (
            <div className="mc-consejo" role="note">
              <button type="button" className="mc-consejo-x" onClick={cerrarConsejo} aria-label="Cerrar el consejo"><LuX /></button>
              <p><b>📸 ¿Quieres mostrarme algo?</b> Toca la cámara, elige una parte de la pantalla y dime qué quieres cambiar ahí.</p>
            </div>
          )}
          <form onSubmit={enviar}>
            <button type="button" className="mc-chat-cam" onClick={() => { cerrarConsejo(); setEligiendo(true) }} disabled={escribiendo} aria-label="Capturar una parte de la pantalla" title="Capturar una parte de la pantalla"><LuCamera /></button>
            <input ref={campo} value={txt} onChange={(e) => setTxt(e.target.value)} onPaste={pegar} placeholder={imagen ? 'Qué quieres hacer con esta captura…' : 'Escribe, captura o pega una imagen…'} aria-label="Mensaje para Shifu" maxLength={300} />
            <button type="submit" disabled={(!txt.trim() && !imagen) || escribiendo} aria-label="Enviar"><LuSend /></button>
          </form>
        </section>
      )}
      <button type="button" className={`mc-chat-btn ${abierto ? 'abierto' : ''}`} onClick={() => setAbierto(!abierto)} aria-expanded={abierto} aria-label={abierto ? 'Cerrar el chat con Shifu' : 'Abrir el chat con Shifu'} hidden={eligiendo || capturando}>
        {abierto ? <LuX /> : <><ShifuAvatar size={46} /><i className="punto" /></>}
      </button>
      {!abierto && pista && <span className="mc-chat-hint">¿Qué cambiamos hoy?</span>}
      {eligiendo && <SelectorCaptura onElegir={elegida} onCancelar={() => setEligiendo(false)} />}
      {capturando && <div className="mc-captura mc-captura-espera" role="status">Tomando la captura…</div>}
    </div>,
    document.body,
  )
}

/* ───────── Página ───────── */

let idMensaje = 0
const mensaje = (de, t, imagen) => { idMensaje += 1; return { id: idMensaje, de, t, imagen } }

export default function CrmPage() {
  const nav = useNavigate()
  const { state } = useLocation()
  const recienTerminado = !!state?.cargar
  const borrador = useMemo(() => leerBorrador(), [])

  const [crm, setCrm] = useState(null)
  const [fallo, setFallo] = useState(false)
  const [animando, setAnimando] = useState(recienTerminado)
  const [vista, setVista] = useState('contactos')
  const [buscar, setBuscar] = useState('')
  const [bienvenida, setBienvenida] = useState(true)
  // Tema claro u oscuro: preferencia de cada persona, se recuerda en el navegador.
  const [tema, setTema] = useState(() => { try { return localStorage.getItem('shifu_tema') === 'claro' ? 'claro' : 'oscuro' } catch { return 'oscuro' } })
  useEffect(() => {
    try { localStorage.setItem('shifu_tema', tema) } catch { /* sin almacenamiento */ }
    document.documentElement.style.colorScheme = tema === 'claro' ? 'light' : 'dark'
    return () => { document.documentElement.style.colorScheme = '' }
  }, [tema])
  const [aviso, setAviso] = useState('')
  const pedido = useRef(null)
  const avisoT = useRef(null)

  // Al entrar: si venimos del cuestionario se crea el CRM; si no, se pide el que ya existe. Se pide una sola vez (también con StrictMode).
  const cargar = () => {
    setFallo(false)
    pedido.current = (recienTerminado && borrador?.resp ? apiCrm.crearDesdeBrief(borrador.resp) : apiCrm.obtener())
    pedido.current.then((s) => {
      if (s) { setCrm(s); return }
      // Sin CRM no hay nada que mostrar: se vuelve al cuestionario (con las respuestas guardadas, pero sin marcarlo como terminado).
      if (borrador) guardarBorrador({ ...borrador, fin: false })
      nav('/bienvenida', { replace: true })
    }).catch(() => setFallo(true))
  }
  useEffect(() => { if (!pedido.current) cargar() }, []) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => clearTimeout(avisoT.current), [])

  const brief = crm?.brief || borrador?.resp
  const d = useMemo(() => {
    if (!brief) return null
    return {
      nombre: brief.nombre || 'Mi negocio',
      canales: (brief.canales?.length ? brief.canales : ['whatsapp']).map((c) => etiqueta('canales', c)),
      moneda: MONEDA[brief.ubicacion?.pais] || '$',
      rubro: brief.rubro ? etiqueta('rubro', brief.rubro) : 'tu negocio',
    }
  }, [brief])
  const menu = useMemo(() => menuDe(brief?.rubro, crm?.secciones, crm?.ocultas, crm?.listas), [brief, crm?.secciones, crm?.ocultas, crm?.listas])
  const tit = (id) => menu.find((m) => m.id === id)?.t
  useEffect(() => { if (crm && menu.length && !menu.some((m) => m.id === vista)) setVista(menu[0].id) }, [crm, menu, vista])
  const pasos = useMemo(() => {
    if (!d) return []
    const obj = brief.objetivos?.[0] ? etiqueta('objetivos', brief.objetivos[0]) : null
    return [
      `Leyendo lo que nos contaste de ${d.nombre}`,
      `Preparando un CRM para ${d.rubro.toLowerCase()}`,
      `Dejando listos tus canales: ${d.canales.slice(0, 2).join(' y ')}`,
      obj ? `Poniendo primero: ${obj.toLowerCase()}` : 'Ordenando tus secciones',
      'Preparando tus secciones y automatizaciones',
      'Dando los últimos toques',
    ]
  }, [d, brief])

  /* Cada cambio se manda al servidor y la pantalla se queda con el CRM que devuelve. Si falla, se avisa y no se cambia nada. */
  const avisar = (m) => { setAviso(m); clearTimeout(avisoT.current); avisoT.current = setTimeout(() => setAviso(''), 3500) }
  const aplicar = async (peticion) => {
    try { setCrm(await peticion()); return true } catch (e) { avisar([404, 422, 501].includes(e?.estado) && e.message ? e.message : 'No se pudo guardar el cambio. Inténtalo de nuevo.'); return false }
  }

  /* Chat */
  const [chatAbierto, setChatAbierto] = useState(false)
  const [mensajes, setMensajes] = useState(() => [mensaje('shifu', 'Hola 👋 Soy Shifu. Dime qué quieres agregar, cambiar o quitar de tu CRM. Si tienes datos en Excel o en notas, pásalos por “Importar datos”.')])
  const [escribiendo, setEscribiendo] = useState(false)
  const [modo, setModo] = useState('ia') // "ia" o "reglas" (si la IA no pudo contestar)
  const pendiente = useRef(null)
  const enviar = async (texto, imagen) => {
    const t = texto.trim()
    if (!t && !imagen) return
    setMensajes((l) => [...l, mensaje('yo', t, imagen?.url)])
    setEscribiendo(true)
    try {
      const historial = mensajes.slice(-6).filter((m) => m.t).map((m) => ({ de: m.de, t: m.t.slice(0, 300) }))
      const r = await apiChat.enviar(t, { pendiente: pendiente.current, imagen: imagen?.url, seccion: tit(vista), historial })
      pendiente.current = r.pendiente || null
      if (r.modo) setModo(r.modo)
      if (r.crm) setCrm(r.crm)
      if (r.vista) setVista(r.vista)
      setMensajes((l) => [...l, mensaje('shifu', r.respuesta)])
    } catch {
      setMensajes((l) => [...l, mensaje('shifu', 'No pude conectarme con el servidor. Inténtalo de nuevo en un momento.')])
    } finally { setEscribiendo(false) }
  }

  if (fallo) return <Fallo onReintentar={() => { pedido.current = null; cargar() }} />
  if (animando && d) return <Cargando pasos={pasos} listo={!!crm} onListo={() => { setAnimando(false); nav('/mi-crm', { replace: true, state: null }) }} />
  if (!crm || !d) return <div className="carga" role="status"><p className="carga-sub">Abriendo tu CRM…</p></div>

  const salir = async () => { await auth.cerrarSesion(); nav('/login', { replace: true }) }
  const yo = auth.usuario()
  const inicial = (yo?.nombre || d.nombre)[0].toUpperCase()
  const rehacer = async () => {
    if (await aplicar(async () => { await apiCrm.reiniciar(); return crm })) { borrarBorrador(); nav('/bienvenida') }
  }
  const ir = (id) => { setVista(id); setBuscar('') }
  const vendedores = crm.vendedores

  return (
    <div className="mc" data-tema={tema}>
      <header className="mc-top">
        <Link to="/" aria-label="Shifu"><Logo height={24} /></Link>
        <span className="mc-negocio">{d.nombre}</span>
        <label className="mc-buscar"><LuSearch aria-hidden="true" />
          <input type="search" placeholder="Buscar en todo el espacio…" value={buscar} onChange={(e) => { setBuscar(e.target.value); if (e.target.value) setVista('contactos') }} aria-label="Buscar" />
        </label>
        <button type="button" className="mc-tema" role="switch" aria-checked={tema === 'claro'} aria-label="Modo claro" title={tema === 'claro' ? 'Cambiar a modo oscuro' : 'Cambiar a modo claro'}
          onClick={() => setTema(tema === 'claro' ? 'oscuro' : 'claro')}>
          <span className={tema === 'claro' ? 'on' : ''}><LuSun aria-hidden="true" /></span><span className={tema === 'oscuro' ? 'on' : ''}><LuMoon aria-hidden="true" /></span>
        </button>
        <button type="button" className="mc-camp" aria-label="Avisos"><LuBell /></button>
        <span className="mc-yo" title={yo?.correo || d.nombre} aria-hidden="true">{inicial}</span>
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
          {HAY_SERVIDOR && <button type="button" className="mc-rehacer mc-salir" onClick={salir}><LuLogOut aria-hidden="true" /> Cerrar sesión{yo?.correo ? <small>{yo.correo}</small> : null}</button>}
        </nav>

        <main className="mc-main">
          {bienvenida && (
            <aside className="mc-shifu" role="status">
              <ShifuAvatar size={40} />
              <p><b>Listo, {d.nombre}.</b> Armé tu CRM con {menu.length} secciones, listo para tus canales ({d.canales.join(', ')}). Empieza por tus contactos: pídemelo en el chat de abajo a la derecha o impórtalos desde tu Excel o tus notas. También puedo crear secciones nuevas, quitar las que no uses o cambiar tus etapas.</p>
              <button type="button" onClick={() => setBienvenida(false)} aria-label="Cerrar">✕</button>
            </aside>
          )}
          {vista === 'contactos' && <Contactos lista={crm.contactos} total={crm.totalContactos} buscar={buscar} etapas={crm.etapas ?? ETAPAS} campos={crm.camposContacto ?? []} t={tit('contactos')} onBorrar={(c) => aplicar(() => apiCrm.contactosEliminar(c.id))} onImportar={() => ir('importar')} />}
          {vista === 'desarrollo' && <Desarrollo t={tit('desarrollo')} tareas={crm.tareas} onMover={(x, destino) => aplicar(() => apiCrm.tareasMover(x.id, destino))} />}
          {vista === 'importar' && (
            <Importar existentes={crm.contactos.map((c) => c.n)} onVer={() => ir('contactos')}
              onImportar={(filas) => aplicar(() => apiCrm.contactosCrear(filas, 'Importado', `Importaste ${filas.length} ${filas.length === 1 ? 'contacto' : 'contactos'} desde tus notas o Excel`))} />
          )}
          {vista.startsWith('l_') && crm.listas?.find((l) => l.id === vista) && (
            <Lista lista={crm.listas.find((l) => l.id === vista)} onAgregar={(id, valores) => aplicar(() => apiCrm.registrosCrear(id, valores))}
              onBorrar={(id, rid) => aplicar(() => apiCrm.registrosEliminar(id, rid))} />
          )}
          {vista === 'cobros' && <Cobros moneda={d.moneda} t={tit('cobros')} />}
          {vista === 'actividad' && <Actividad eventos={crm.eventos} t={tit('actividad')} />}
          {vista === 'rrhh' && <Rrhh vendedores={vendedores} lista={crm.contactos} total={crm.totalContactos} t={tit('rrhh')} />}
          {vista === 'automatizaciones' && <Automatizaciones autos={crm.automatizaciones} onAlternar={(a) => aplicar(() => apiCrm.automatizacionFijar(a.id, !a.on))} />}
        </main>
      </div>

      {aviso && <p className="mc-toast" role="alert">{aviso}</p>}
      <ChatShifu modo={modo} sugerencias={sugerenciasDe(crm.contactos)} tema={tema} abierto={chatAbierto} setAbierto={setChatAbierto} mensajes={mensajes} escribiendo={escribiendo} onEnviar={enviar} />
    </div>
  )
}

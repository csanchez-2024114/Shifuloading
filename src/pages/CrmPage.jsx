import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import Logo from '../components/Logo'
import ShifuAvatar from '../components/ShifuAvatar'
import TextoChat from '../components/TextoChat'
import { SelectorCaptura, capturarRegion, imagenDeArchivo } from '../components/CapturaPantalla'
import ImportarALista from '../components/ImportarALista'
import { descargarExcel } from '../crm/exportarExcel'
import { logoDeArchivo } from '../crm/logo'
import Tour from '../components/Tour'
import { armarRecorrido } from '../crm/recorrido'
import { HAY_SERVIDOR, auth, avisos as apiAvisos, chat as apiChat, crm as apiCrm } from '../api'
import { etiqueta } from '../brief/preguntas'
import { borrarBorrador, guardarBorrador, leerBorrador } from '../brief/borrador'
import { COLUMNAS, ETAPAS, tituloSeccion } from '../crm/secciones'
import { LuUsers, LuWallet, LuCode, LuActivity, LuIdCard, LuSearch, LuBell, LuLogOut, LuPlus, LuRotateCcw, LuTable, LuUpload, LuZap, LuCamera, LuSend, LuSun, LuMoon, LuX, LuLightbulb, LuTrash2, LuImagePlus, LuSparkles, LuSettings, LuPencil, LuDownload } from 'react-icons/lu'
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
  { id: 'cobros', I: LuWallet, grupo: 2 }, { id: 'actividad', I: LuActivity, grupo: 2 }, { id: 'rrhh', I: LuIdCard, grupo: 2 },
]
/* Lo principal arriba, lo que armó la IA para ese negocio en su propio grupo, y las herramientas al final. Un grupo sin nada no se muestra. */
const GRUPOS = ['Mi negocio', 'Mis secciones', 'Medición y equipo', 'Herramientas']
const menuDe = (rubro, secciones, ocultas = [], listas = []) => [
  ...BASE.map((m) => ({ ...m, t: tituloSeccion(rubro, m.id, secciones) })),
  { id: 'importar', t: tituloSeccion(rubro, 'importar'), I: LuUpload, grupo: 3 },
  { id: 'automatizaciones', t: tituloSeccion(rubro, 'automatizaciones'), I: LuZap, grupo: 3 },
].filter((m) => !ocultas.includes(m.id)).concat(listas.map((l) => (
  // Las recomendaciones de Shifu son ideas, no una tabla del negocio: van con las herramientas y no llenan "Mis secciones".
  l.tipo === 'recomendaciones' ? { id: l.id, t: l.nombre, I: LuLightbulb, grupo: 3, propia: true } : { id: l.id, t: l.nombre, I: LuTable, grupo: 1, propia: true }
)))

/** Cómo lleva hoy la persona sus apuntes, según lo que contestó en el cuestionario: con eso la pantalla le ofrece lo que más le sirve (importar su Excel o subir una foto). */
const comoLlevaHoy = (brief) => {
  const dicho = norm([...(brief?.seguimiento || []).map((s) => s.respuesta), ...(brief?.herramientas || [])].join(' | '))
  return { excel: /excel|hoja de c|sheets|planilla|computadora|\bcompu\b/.test(dicho), papel: /cuaderno|papel|libreta|apunte|anoto|agenda/.test(dicho) }
}

/** Cómo se ve el valor de un campo según su tipo. */
/* Los números se ven como en Guatemala: coma para los miles y punto para los decimales (1,190.50). Los precios y montos siempre con dos decimales. */
const ESDINERO = /precio|monto|total|costo|valor|pago|deuda|saldo|ganancia|sueldo|salario|importe|\bq\b|\$/i
const verNumero = (v, nombre) => { const n = Number(v); return Number.isFinite(n) ? n.toLocaleString('es-GT', { minimumFractionDigits: ESDINERO.test(nombre || '') ? 2 : 0, maximumFractionDigits: 2 }) : String(v) }
const verValor = (tipo, v, nombre) => (v === undefined || v === null || v === '' ? '—' : tipo === 'fecha' ? String(v).split('-').reverse().join('/') : tipo === 'numero' ? verNumero(v, nombre) : String(v))

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

/* ───────── Formulario de una fila (agregar y editar) ───────── */

/** Lo que cambió entre lo que había y lo que quedó escrito: solo eso se manda al servidor, para no tocar lo demás. */
const cambiosDe = (antes, ahora) => Object.fromEntries(Object.entries(ahora).filter(([k, v]) => String(v ?? '').trim() !== String(antes[k] ?? '').trim()))
const resumenDe = (valores, campos) => campos.map((c) => valores[c.id]).find((v) => v !== undefined && v !== null && String(v).trim() !== '')

/** Se usa igual para una fila de una sección, un cliente o una tarea. `campos` = [{ id, nombre, tipo: 'texto' | 'numero' | 'fecha' | 'lista', opciones? }]. */
function FormFila({ titulo, campos, inicial = {}, enviando, error, onGuardar, onCancelar, guardar = 'Guardar' }) {
  const [vals, setVals] = useState(() => Object.fromEntries(campos.map((c) => [c.id, inicial[c.id] ?? ''])))
  const poner = (id, v) => setVals((x) => ({ ...x, [id]: v }))
  return (
    <form className="mc-form-registro" onSubmit={(e) => { e.preventDefault(); onGuardar(vals) }} noValidate>
      {titulo && <h3 className="mc-form-titulo">{titulo}</h3>}
      {campos.map((c, k) => (
        <label key={c.id}>{c.nombre}
          {c.tipo === 'lista'
            ? (
              <select value={vals[c.id] ?? ''} onChange={(e) => poner(c.id, e.target.value)}>
                <option value="">Elegir…</option>
                {(c.opciones || []).map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            )
            : (
              <input type={c.tipo === 'fecha' ? 'date' : 'text'} inputMode={c.tipo === 'numero' ? 'decimal' : undefined} maxLength={200} autoFocus={k === 0}
                value={vals[c.id] ?? ''} onChange={(e) => poner(c.id, e.target.value)} />
            )}
        </label>
      ))}
      {error && <p className="mc-form-error" role="alert">{error}</p>}
      <div className="mc-form-acciones">
        <button type="submit" className="btn-pildora" disabled={enviando}>{enviando ? 'Guardando…' : guardar}</button>
        <button type="button" className="mc-link" onClick={onCancelar}>Cancelar</button>
      </div>
    </form>
  )
}

/** La pregunta "¿Eliminar?" que reemplaza a una fila hasta que la persona confirma o se arrepiente. */
function ConfirmaBorrar({ que, onSi, onNo }) {
  const [haciendo, setHaciendo] = useState(false)
  return (
    <div className="mc-fila mc-fila-confirma" role="alertdialog" aria-label={`Confirmar que se elimina ${que}`}>
      <span>¿Eliminar {que}? No se puede deshacer.</span>
      <span className="mc-confirma-acc">
        <button type="button" className="mc-peligro mc-chico" disabled={haciendo} onClick={async () => { setHaciendo(true); await onSi(); setHaciendo(false) }}>{haciendo ? 'Eliminando…' : 'Sí, eliminar'}</button>
        <button type="button" className="mc-link" disabled={haciendo} onClick={onNo}>No</button>
      </span>
    </div>
  )
}

/* ───────── Vistas ───────── */

function Contactos({ lista, total, buscar, t, onAgregar, onActualizar, onBorrar, onImportar, etapas, campos, vendedores }) {
  const [modo, setModo] = useState(null) // null | 'nuevo' | id del cliente que se edita
  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState('')
  const [borrando, setBorrando] = useState(null)
  const q = norm(buscar)
  const vis = q ? lista.filter((f) => norm(f.n).includes(q)) : lista
  const por = (e) => lista.filter((c) => c.etapa === e).length
  const cols = { '--cols': `1.6fr 1fr 1fr 1.2fr ${campos.map(() => '1fr').join(' ')} 1fr`.replace(/\s+/g, ' ') }
  const editando = modo && modo !== 'nuevo' ? lista.find((c) => c.id === modo) : null
  const formulario = [
    { id: 'n', nombre: 'Nombre', tipo: 'texto' }, { id: 'det', nombre: 'Teléfono o correo', tipo: 'texto' }, { id: 'canal', nombre: 'Por dónde llegó (WhatsApp, local…)', tipo: 'texto' },
    ...(editando ? [{ id: 'etapa', nombre: 'Etapa', tipo: 'lista', opciones: etapas }, { id: 'dueno', nombre: 'Responsable', tipo: 'lista', opciones: vendedores }] : []),
    ...campos.map((c) => ({ ...c, id: `x:${c.id}` })),
  ]
  const inicial = editando
    ? { n: editando.n, det: editando.det || '', canal: editando.canal, etapa: editando.etapa, dueno: editando.dueno, ...Object.fromEntries(campos.map((c) => [`x:${c.id}`, editando.extra?.[c.id] ?? ''])) }
    : {}
  const abrir = (m) => { setError(''); setModo(m) }
  const guardar = async (vals) => {
    setError('')
    const separar = (obj) => ({ base: Object.fromEntries(Object.entries(obj).filter(([k]) => !k.startsWith('x:'))), extra: Object.fromEntries(Object.entries(obj).filter(([k]) => k.startsWith('x:')).map(([k, v]) => [k.slice(2), v])) })
    if (editando) {
      const { base, extra } = separar(cambiosDe(inicial, vals))
      if (!Object.keys(base).length && !Object.keys(extra).length) { setModo(null); return }
      setEnviando(true)
      const ok = await onActualizar(editando.id, { ...base, ...(Object.keys(extra).length ? { extra } : {}) })
      setEnviando(false)
      if (ok) setModo(null); else setError('No se pudo guardar. Revisa que el nombre no esté vacío y que los datos sean válidos.')
    } else {
      if (!String(vals.n || '').trim()) { setError('Escribe el nombre.'); return }
      const { base, extra } = separar(Object.fromEntries(Object.entries(vals).filter(([, v]) => String(v ?? '').trim() !== '')))
      setEnviando(true)
      const ok = await onAgregar({ n: base.n, ...(base.det ? { det: base.det } : {}), ...(base.canal ? { canal: base.canal } : {}), ...(Object.keys(extra).length ? { extra } : {}) })
      setEnviando(false)
      if (ok) setModo(null); else setError('No se pudo guardar. Revisa los datos.')
    }
  }
  return (
    <>
      <div className="mc-cab">
        <div><h1>{t}</h1><p>{total === 0 ? 'Todavía no tienes ninguno.' : `${total.toLocaleString('es')} en total. Toca uno para editarlo.`}</p></div>
        {!modo && <div className="mc-cab-acc"><button type="button" className="mc-sec" data-tour="importar" onClick={onImportar}><LuUpload aria-hidden="true" /> Importar</button><button type="button" className="btn-pildora" onClick={() => abrir('nuevo')}><LuPlus aria-hidden="true" /> Agregar</button></div>}
      </div>
      {modo && <FormFila key={modo} titulo={editando ? `Editar a ${editando.n}` : 'Agregar'} campos={formulario} inicial={inicial} enviando={enviando} error={error} onGuardar={guardar} onCancelar={() => setModo(null)} />}
      <div className="mc-kpis c4k" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))' }}>
        <div><small>En total</small><strong>{total.toLocaleString('es')}</strong></div>
        {etapas.map((e) => <div key={e}><small>{e}</small><strong>{por(e)}</strong></div>)}
      </div>
      {total === 0 && !modo && (
        <div className="mc-vacio-grande">
          <b>Aquí aparecerán tus {t.toLowerCase()}</b>
          <p>Agrega el primero tú mismo, pídeselo a Shifu en el chat (por ejemplo, “Agrega a Laura Gómez”) o trae de una vez los que ya tienes en un Excel o en tus notas.</p>
          <button type="button" className="btn-pildora" onClick={() => abrir('nuevo')}>Agregar el primero</button>
          <button type="button" className="mc-link" onClick={onImportar}>o importar desde Excel o notas</button>
        </div>
      )}
      {total > 0 && <div className="mc-tabla" role="table">
        <div className="mc-fila cab" role="row" style={cols}><span>Nombre</span><span>Canal</span><span>Etapa</span><span>Responsable</span>{campos.map((c) => <span key={c.id}>{c.nombre}</span>)}<span>Último contacto</span></div>
        {vis.map((f) => (borrando === f.id
          ? <ConfirmaBorrar key={f.id} que={`a ${f.n}`} onSi={async () => { await onBorrar(f); setBorrando(null) }} onNo={() => setBorrando(null)} />
          : (
            <div key={f.id} className="mc-fila mc-fila-editable" role="row" style={cols} onClick={() => abrir(f.id)}>
              <span><i className="mc-av peq">{f.n[0]}</i><span className="mc-nom">{f.n}{f.det && <small>{f.det}</small>}</span></span>
              <span>{f.canal}</span><span><em className="mc-estado">{f.etapa}</em></span><span>{f.dueno}</span>
              {campos.map((c) => <span key={c.id}>{verValor(c.tipo, f.extra?.[c.id], c.nombre)}</span>)}
              <span className="mc-ultimo">{f.dias === 0 ? 'hoy' : `hace ${f.dias} ${f.dias === 1 ? 'día' : 'días'}`}
                <span className="mc-acc">
                  <button type="button" className="mc-x" aria-label={`Editar a ${f.n}`} onClick={(e) => { e.stopPropagation(); abrir(f.id) }}><LuPencil /></button>
                  <button type="button" className="mc-x" aria-label={`Eliminar a ${f.n}`} onClick={(e) => { e.stopPropagation(); setBorrando(f.id) }}><LuX /></button>
                </span></span>
            </div>
          )))}
        {!vis.length && <p className="mc-vacio">Nada coincide con “{buscar}”.</p>}
      </div>}
    </>
  )
}

/** Una sección propia: una tabla con los campos que la persona (o Shifu) definió. Se puede agregar, editar y eliminar; la estructura se cambia por el chat. */
function Lista({ lista, onAgregar, onActualizar, onBorrar, onVaciar, onSubirFoto, onImportar, metodos }) {
  const [modo, setModo] = useState(null) // null | 'nuevo' | id del registro que se edita
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [borrando, setBorrando] = useState(null)
  const [buscar, setBuscar] = useState('')
  const [vaciando, setVaciando] = useState(null) // null | 'pregunta' | 'haciendo'
  const cols = { '--cols': `${lista.campos.map(() => 'minmax(0, 1fr)').join(' ')} 76px` }
  const editando = modo && modo !== 'nuevo' ? lista.registros.find((r) => r.id === modo) : null
  const valoresDe = (r) => Object.fromEntries(lista.campos.map((c) => [c.id, r.valores[c.id] ?? '']))
  const q = norm(buscar)
  const vis = q ? lista.registros.filter((r) => lista.campos.some((c) => norm(String(r.valores[c.id] ?? '')).includes(q))) : lista.registros
  const abrir = (m) => { setError(''); setModo(m) }
  const guardar = async (vals) => {
    setError('')
    if (editando) {
      const cambios = cambiosDe(valoresDe(editando), vals)
      if (!Object.keys(cambios).length) { setModo(null); return }
      setEnviando(true)
      const ok = await onActualizar(lista.id, editando.id, cambios)
      setEnviando(false)
      if (ok) setModo(null); else setError('No se pudo guardar. Revisa los valores (números en precios y cantidades, fechas como 25/12/2026).')
    } else {
      const llenos = Object.fromEntries(Object.entries(vals).filter(([, v]) => String(v ?? '').trim() !== ''))
      if (!Object.keys(llenos).length) { setError('Escribe al menos un valor.'); return }
      setEnviando(true)
      const ok = await onAgregar(lista.id, llenos)
      setEnviando(false)
      if (ok) setModo(null); else setError('No se pudo guardar. Revisa los valores.')
    }
  }
  return (
    <>
      <div className="mc-cab">
        <div><h1>{lista.nombre}</h1><p>{lista.registros.length === 0 ? 'Todavía no tiene registros.' : `${lista.registros.length.toLocaleString('es')} ${lista.registros.length === 1 ? 'registro' : 'registros'}. Toca uno para editarlo.`} Para cambiar los campos o quitar la sección, pídeselo a Shifu en el chat.</p></div>
        {!modo && (
          <div className="mc-cab-acc">
            <button type="button" className="mc-sec" data-tour="importar" onClick={onImportar}><LuUpload aria-hidden="true" /> Importar</button>
            <button type="button" className="btn-pildora" onClick={() => abrir('nuevo')}><LuPlus aria-hidden="true" /> Agregar</button>
          </div>
        )}
      </div>
      {modo && <FormFila key={modo} titulo={editando ? 'Editar registro' : 'Agregar registro'} campos={lista.campos} inicial={editando ? valoresDe(editando) : {}} enviando={enviando} error={error} onGuardar={guardar} onCancelar={() => setModo(null)} />}

      {lista.registros.length === 0 && !modo && (
        <div className="mc-vacio-grande mc-vacio-foto">
          {metodos.excel ? (
            <>
              <b>Trae tu Excel a “{lista.nombre}”</b>
              <p>Elige tu archivo y Shifu pasa aquí cada columna. Después, todo lo demás lo haces hablando con Shifu.</p>
              <div className="mc-vacio-acciones">
                <button type="button" className="btn-pildora mc-grande" onClick={onImportar}><LuUpload aria-hidden="true" /> Importar mi Excel</button>
                <button type="button" className="mc-link" onClick={() => abrir('nuevo')}>o agregar el primero a mano</button>
                {metodos.papel && <button type="button" className="mc-link" onClick={onSubirFoto}>o subir una foto de mi cuaderno</button>}
              </div>
            </>
          ) : metodos.papel ? (
            <>
              <b>Empieza a llenar “{lista.nombre}”</b>
              <p>Lo más fácil: toma una foto de tu cuaderno o de tu lista y Shifu la pasa aquí por ti. También puedes escribirle lo que quieras agregar.</p>
              <div className="mc-vacio-acciones">
                <button type="button" className="btn-pildora mc-grande" onClick={onSubirFoto}><LuImagePlus aria-hidden="true" /> Subir una foto</button>
                <button type="button" className="mc-link" onClick={() => abrir('nuevo')}>o agregar el primero a mano</button>
              </div>
            </>
          ) : (
            <>
              <b>Empieza a llenar “{lista.nombre}”</b>
              <p>Agrega el primero tú mismo, o cuéntaselo a Shifu en el chat con tus palabras. Más adelante puedes subir una foto o traer un Excel.</p>
              <div className="mc-vacio-acciones">
                <button type="button" className="btn-pildora mc-grande" onClick={() => abrir('nuevo')}><LuPlus aria-hidden="true" /> Agregar el primero</button>
                <button type="button" className="mc-link" onClick={onSubirFoto}>o subir una foto</button>
                <button type="button" className="mc-link" onClick={onImportar}>o importar un Excel</button>
              </div>
            </>
          )}
        </div>
      )}
      {lista.registros.length > 0 && (
        <>
          {lista.registros.length > 8 && (
            <label className="mc-buscar-lista"><LuSearch aria-hidden="true" />
              <input type="search" placeholder={`Buscar en ${lista.nombre}…`} value={buscar} onChange={(e) => setBuscar(e.target.value)} aria-label={`Buscar en ${lista.nombre}`} />
            </label>
          )}
          <div className="mc-tabla" role="table">
            <div className="mc-fila cab" role="row" style={cols}>{lista.campos.map((c) => <span key={c.id}>{c.nombre}</span>)}<span /></div>
            {vis.map((r) => (borrando === r.id
              ? <ConfirmaBorrar key={r.id} que={`“${String(resumenDe(r.valores, lista.campos) ?? 'este registro')}”`} onSi={async () => { await onBorrar(lista.id, r.id); setBorrando(null) }} onNo={() => setBorrando(null)} />
              : (
                <div key={r.id} className="mc-fila mc-fila-editable" role="row" style={cols} onClick={() => abrir(r.id)}>
                  {lista.campos.map((c) => <span key={c.id}>{verValor(c.tipo, r.valores[c.id], c.nombre)}</span>)}
                  <span className="mc-acc">
                    <button type="button" className="mc-x" aria-label="Editar este registro" onClick={(e) => { e.stopPropagation(); abrir(r.id) }}><LuPencil /></button>
                    <button type="button" className="mc-x" aria-label="Eliminar este registro" onClick={(e) => { e.stopPropagation(); setBorrando(r.id) }}><LuX /></button>
                  </span>
                </div>
              )))}
            {!vis.length && <p className="mc-vacio">Nada coincide con “{buscar}”.</p>}
          </div>
          <div className="mc-pie-lista">
            {vaciando === null
              ? <button type="button" className="mc-link mc-link-peligro" onClick={() => setVaciando('pregunta')}>Vaciar esta sección…</button>
              : (
                <div className="mc-aj-confirma" role="alertdialog" aria-label="Confirmar que se vacía la sección">
                  <p>⚠ Se borrarán los {lista.registros.length.toLocaleString('es')} registros de “{lista.nombre}”: todo, lo importado y lo que escribiste a mano. La sección y sus columnas se quedan. Una vez que lo hagas, no se podrá deshacer.</p>
                  <button type="button" className="mc-peligro" disabled={vaciando === 'haciendo'} onClick={async () => { setVaciando('haciendo'); await onVaciar(lista.id); setVaciando(null) }}>{vaciando === 'haciendo' ? 'Vaciando…' : 'Sí, vaciar la sección'}</button>
                  <button type="button" className="mc-link" disabled={vaciando === 'haciendo'} onClick={() => setVaciando(null)}>Cancelar</button>
                </div>
              )}
          </div>
        </>
      )}
    </>
  )
}

/* ───────── Ajustes ───────── */

/** Todo lo de la cuenta y la apariencia en un solo lugar: tema claro u oscuro, cerrar sesión y repetir el cuestionario (con confirmación, porque borra el CRM). */
function Ajustes({ tema, setTema, yo, negocio, hayServidor, onSalir, onRehacer, onDescargar, logo, onLogo, onQuitarLogo, onTour }) {
  const archivoLogo = useRef(null)
  const [subiendo, setSubiendo] = useState(false)
  const [notaLogo, setNotaLogo] = useState('')
  const elegirLogo = async (e) => {
    const f = e.target.files?.[0]
    e.target.value = ''
    if (!f) return
    setSubiendo(true); setNotaLogo('')
    const error = await onLogo(f)
    setNotaLogo(error || '¡Listo! Tu logotipo ya aparece arriba.')
    setSubiendo(false)
  }
  const [confirmando, setConfirmando] = useState(false)
  const [bajando, setBajando] = useState(false)
  const [notaExcel, setNotaExcel] = useState('')
  const descargar = async () => {
    setBajando(true); setNotaExcel('')
    try { setNotaExcel((await onDescargar()) ? '¡Listo! Revisa tu carpeta de Descargas.' : 'Todavía no hay nada que descargar: agrega algo a tu CRM primero.') } catch { setNotaExcel('No se pudo preparar el archivo. Inténtalo de nuevo.') }
    setBajando(false)
  }
  const [haciendo, setHaciendo] = useState(false)
  const rehacer = async () => { setHaciendo(true); await onRehacer(); setHaciendo(false); setConfirmando(false) }
  return (
    <>
      <div className="mc-cab"><div><h1>Ajustes</h1><p>Cómo se ve tu CRM y todo lo de tu cuenta, en un solo lugar.</p></div></div>
      <div className="mc-aj">
        <section aria-labelledby="aj-apariencia">
          <h2 id="aj-apariencia">Apariencia</h2>
          <div className="mc-aj-temas" role="radiogroup" aria-label="Tema de la pantalla">
            <button type="button" role="radio" aria-checked={tema === 'oscuro'} className={tema === 'oscuro' ? 'on' : ''} onClick={() => setTema('oscuro')}><LuMoon aria-hidden="true" /><b>Oscuro</b><small>Descansa la vista</small></button>
            <button type="button" role="radio" aria-checked={tema === 'claro'} className={tema === 'claro' ? 'on' : ''} onClick={() => setTema('claro')}><LuSun aria-hidden="true" /><b>Claro</b><small>Tono suave, como papel</small></button>
          </div>
        </section>

        {hayServidor && (
          <section aria-labelledby="aj-cuenta">
            <h2 id="aj-cuenta">Mi cuenta</h2>
            <div className="mc-aj-fila">
              <div><b>{[yo?.nombre, yo?.apellido].filter(Boolean).join(' ') || negocio}</b><small>{yo?.correo}</small></div>
              <button type="button" className="mc-sec" onClick={onSalir}><LuLogOut aria-hidden="true" /> Cerrar sesión</button>
            </div>
          </section>
        )}

        <section aria-labelledby="aj-negocio">
          <h2 id="aj-negocio">Mi negocio</h2>
          <div className="mc-aj-fila">
            <div className="mc-aj-logo">
              <span className="mc-aj-logo-vista">{logo ? <img src={logo} alt={`Logotipo de ${negocio}`} /> : <i aria-hidden="true">{negocio[0]?.toUpperCase()}</i>}</span>
              <div>
                <b>Logotipo de {negocio}</b>
                <small>Aparece en la barra de arriba. Sube una imagen PNG, JPG o WebP: se ajusta sola. Se ve mejor con fondo transparente.</small>
                {notaLogo && <small className="mc-aj-nota" role="status">{notaLogo}</small>}
              </div>
            </div>
            <div className="mc-aj-botones">
              <input ref={archivoLogo} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={elegirLogo} />
              <button type="button" className="mc-sec" disabled={subiendo} onClick={() => archivoLogo.current?.click()}><LuImagePlus aria-hidden="true" /> {subiendo ? 'Subiendo…' : logo ? 'Cambiar logotipo' : 'Subir logotipo'}</button>
              {logo && <button type="button" className="mc-link" disabled={subiendo} onClick={() => { setNotaLogo(''); onQuitarLogo() }}>Quitar</button>}
            </div>
          </div>
        </section>

        <section aria-labelledby="aj-ayuda">
          <h2 id="aj-ayuda">Ayuda</h2>
          <div className="mc-aj-fila">
            <div><b>Recorrido de bienvenida</b><small>Shifu te muestra otra vez qué hay en cada parte de tu CRM y todo lo que puede hacer por ti.</small></div>
            <button type="button" className="mc-sec" onClick={onTour}><LuSparkles aria-hidden="true" /> Ver el recorrido</button>
          </div>
        </section>

        <section aria-labelledby="aj-datos">
          <h2 id="aj-datos">Mis datos</h2>
          <div className="mc-aj-fila">
            <div><b>Descargar mi CRM en Excel</b><small>Un libro con una hoja por cada sección, con todo lo que llevas hasta hoy. Puedes descargarlo cuantas veces quieras.</small>{notaExcel && <small className="mc-aj-nota" role="status">{notaExcel}</small>}</div>
            <button type="button" className="mc-sec" disabled={bajando} onClick={descargar}><LuDownload aria-hidden="true" /> {bajando ? 'Preparando…' : 'Descargar Excel'}</button>
          </div>
        </section>

        <section aria-labelledby="aj-crm">
          <h2 id="aj-crm">Mi CRM</h2>
          <div className="mc-aj-fila">
            <div><b>Repetir el cuestionario</b><small>Empiezas de cero: se borra tu CRM actual con todo lo que tiene y Shifu arma uno nuevo con tus nuevas respuestas.</small></div>
            {!confirmando
              ? <button type="button" className="mc-sec" onClick={() => setConfirmando(true)}><LuRotateCcw aria-hidden="true" /> Repetir cuestionario</button>
              : <div className="mc-aj-confirma" role="alertdialog" aria-label="Confirmar que se borra el CRM">
                <p>¿Seguro? Se borra todo lo que tienes en “{negocio}”.</p>
                <button type="button" className="mc-peligro" disabled={haciendo} onClick={rehacer}>{haciendo ? 'Borrando…' : 'Sí, borrar y empezar de nuevo'}</button>
                <button type="button" className="mc-link" disabled={haciendo} onClick={() => setConfirmando(false)}>Cancelar</button>
              </div>}
          </div>
        </section>
      </div>
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

const MESES_CORTOS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
const fechaCorta = (iso) => { const [a, m, d] = iso.split('-').map(Number); return `${d} ${MESES_CORTOS[m - 1]} ${a}` }

function Desarrollo({ t, tareas, onMover, onAgregar, onActualizar, onBorrar }) {
  const [modo, setModo] = useState(null) // null | 'nueva' | id de la tarea que se edita
  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState('')
  const [borrando, setBorrando] = useState(null)
  const todas = COLUMNAS.flatMap(([k]) => tareas[k])
  const editando = modo && modo !== 'nueva' ? todas.find((x) => x.id === modo) : null
  const campos = [{ id: 't', nombre: 'Tarea', tipo: 'texto' }, { id: 'vence', nombre: 'Fecha (opcional)', tipo: 'fecha' }, { id: 'hora', nombre: 'Hora (opcional, como 16:30)', tipo: 'texto' }]
  const inicial = editando ? { t: editando.t, vence: editando.vence || '', hora: editando.hora || '' } : {}
  const abrir = (m) => { setError(''); setModo(m) }
  const guardar = async (vals) => {
    setError('')
    if (!String(vals.t || '').trim()) { setError('Escribe qué hay que hacer.'); return }
    setEnviando(true)
    let ok
    if (editando) {
      const cambios = cambiosDe(inicial, vals) // solo lo que cambió: si no tocó la fecha, no se vuelve a validar
      if (!Object.keys(cambios).length) { setEnviando(false); setModo(null); return }
      ok = await onActualizar(editando.id, cambios)
    } else ok = await onAgregar(vals.t.trim(), vals.vence, vals.hora)
    setEnviando(false)
    if (ok) setModo(null); else setError('No se pudo guardar. La fecha no puede ser anterior a hoy y la hora debe ser como 16:30.')
  }
  return (
    <>
      <div className="mc-cab">
        <div><h1>{t}</h1><p>Lo que está por hacer, en curso y terminado. Toca una tarea para pasarla a la siguiente columna, o el lápiz para editarla.</p></div>
        {!modo && <div className="mc-cab-acc"><button type="button" className="btn-pildora" onClick={() => abrir('nueva')}><LuPlus aria-hidden="true" /> Nueva tarea</button></div>}
      </div>
      {modo && <FormFila key={modo} titulo={editando ? 'Editar tarea' : 'Nueva tarea'} campos={campos} inicial={inicial} enviando={enviando} error={error} onGuardar={guardar} onCancelar={() => setModo(null)} />}
      <div className="mc-tablero">
        {COLUMNAS.map(([k, titulo], c) => (
          <div key={k} className="mc-col"><h2>{titulo}<i>{tareas[k].length}</i></h2>
            {tareas[k].map((x) => (
              <div key={x.id} className="mc-tarea">
                <button type="button" className="mc-tarea-mover" onClick={() => onMover(x, COLUMNAS[(c + 1) % COLUMNAS.length][0])} title={c < 2 ? 'Pasar a la siguiente columna' : 'Volver a “Por hacer”'}>
                  {x.t}
                  {(x.vence || x.contacto || x.auto) && <small className="mc-tarea-meta">{x.auto && '🤖 Automática · '}{x.vence && `📅 ${fechaCorta(x.vence)}${x.hora ? ` · ${x.hora}` : ''}`}{x.contacto && `${x.vence ? ' · ' : ''}👤 ${x.contacto}`}</small>}
                </button>
                {borrando === x.id
                  ? (
                    <span className="mc-tarea-acc mc-tarea-confirma" role="alertdialog" aria-label="Confirmar que se elimina la tarea">
                      <span>¿Eliminar? No se puede deshacer.</span>
                      <button type="button" className="mc-peligro mc-chico" onClick={async () => { await onBorrar(x); setBorrando(null) }}>Sí</button>
                      <button type="button" className="mc-link" onClick={() => setBorrando(null)}>No</button>
                    </span>
                  )
                  : (
                    <span className="mc-tarea-acc">
                      <button type="button" className="mc-x" aria-label="Editar la tarea" onClick={() => abrir(x.id)}><LuPencil /></button>
                      <button type="button" className="mc-x" aria-label="Eliminar la tarea" onClick={() => setBorrando(x.id)}><LuX /></button>
                    </span>
                  )}
              </div>
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
          <li key={a.id} className={`${a.on ? 'on' : ''} ${a.disponible === false ? 'pronto' : ''}`}>
            <div><span className="mc-pilar">{a.pilar}</span>{a.disponible === false && <span className="mc-pronto">Próximamente</span>}<b>{a.t}</b><small>{a.disponible === false && a.nota ? a.nota : a.d}</small></div>
            <button type="button" role="switch" aria-checked={a.on} aria-label={a.t} className="mc-switch" disabled={a.disponible === false} onClick={() => onAlternar(a)}><i /></button>
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

/* ───────── Campana de avisos ───────── */

const haceTiempo = (iso) => {
  const seg = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (Number.isNaN(seg)) return ''
  if (seg < 60) return 'ahora'
  if (seg < 3600) return `hace ${Math.floor(seg / 60)} min`
  if (seg < 86400) return `hace ${Math.floor(seg / 3600)} h`
  const d = Math.floor(seg / 86400)
  return `hace ${d} ${d === 1 ? 'día' : 'días'}`
}
// A dónde lleva cada tipo de aviso al tocarlo.
const DESTINO_DE_AVISO = { crm_recordatorio: 'desarrollo', crm_resumen: 'actividad' }

function Avisos({ onIr }) {
  const [lista, setLista] = useState([])
  const [sinLeer, setSinLeer] = useState(0)
  const [abierta, setAbierta] = useState(false)
  const caja = useRef(null)

  const cargar = () => apiAvisos.listar().then((r) => { setLista(r?.notifications || []); setSinLeer(r?.unread_count || 0) }).catch(() => { /* sin avisos por ahora */ })
  useEffect(() => {
    if (!HAY_SERVIDOR) return undefined
    cargar()
    const t = setInterval(() => { if (!document.hidden) cargar() }, 60000) // se revisa cada minuto mientras la pestaña está a la vista
    return () => clearInterval(t)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!abierta) return undefined
    const fuera = (e) => { if (caja.current && !caja.current.contains(e.target)) setAbierta(false) }
    const esc = (e) => { if (e.key === 'Escape') setAbierta(false) }
    document.addEventListener('mousedown', fuera); document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('mousedown', fuera); document.removeEventListener('keydown', esc) }
  }, [abierta])

  const tocar = async (a) => {
    setAbierta(false)
    if (DESTINO_DE_AVISO[a.type]) onIr(DESTINO_DE_AVISO[a.type])
    if (!a.read) {
      setLista((l) => l.map((x) => (x.id === a.id ? { ...x, read: true } : x))); setSinLeer((n) => Math.max(0, n - 1))
      try { await apiAvisos.leer(a.id) } catch { /* se verá como sin leer en la próxima revisión */ }
    }
  }
  const leerTodos = async () => {
    setLista((l) => l.map((x) => ({ ...x, read: true }))); setSinLeer(0)
    try { await apiAvisos.leerTodos() } catch { cargar() }
  }

  return (
    <div className="mc-avisos" ref={caja} data-tour="campana">
      <button type="button" className="mc-camp" aria-label={sinLeer ? `Avisos: ${sinLeer} sin leer` : 'Avisos'} aria-expanded={abierta} onClick={() => { setAbierta(!abierta); if (!abierta) cargar() }}>
        <LuBell />{sinLeer > 0 && <i aria-hidden="true">{sinLeer > 9 ? '9+' : sinLeer}</i>}
      </button>
      {abierta && (
        <section className="mc-avisos-panel" aria-label="Tus avisos">
          <header><b>Avisos</b>{sinLeer > 0 && <button type="button" onClick={leerTodos}>Marcar todo como leído</button>}</header>
          {lista.length === 0
            ? <p className="mc-avisos-vacio">Sin avisos por ahora. Cuando Shifu note algo que merece tu atención, te lo dirá aquí.</p>
            : <ul>{lista.map((a) => (
              <li key={a.id}><button type="button" className={a.read ? '' : 'nuevo'} onClick={() => tocar(a)}>
                <b>{a.title}</b><span>{a.message}</span><small>{haceTiempo(a.created_at)}</small>
              </button></li>
            ))}</ul>}
        </section>
      )}
    </div>
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

function ChatShifu({ tema, abierto, setAbierto, mensajes, escribiendo, onEnviar, sugerencias, modo, onOlvidar }) {
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
  const fotoRef = useRef(null)
  // Desde una sección vacía se pide “subir una foto de mi cuaderno”: se abre el chat y se abre el selector de fotos.
  useEffect(() => {
    const f = () => { setAbierto(true); setTimeout(() => fotoRef.current?.click(), 250) }
    window.addEventListener('shifu:subir-foto', f)
    return () => window.removeEventListener('shifu:subir-foto', f)
  }, [setAbierto])
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
  const fotoElegida = async (e) => {
    const archivo = e.target.files?.[0]
    e.target.value = ''
    if (!archivo) return
    try { setImagen(await imagenDeArchivo(archivo)); setErrorImg('') } catch { setErrorImg('No pude usar esa foto. Prueba con otra.') }
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
            {onOlvidar && <button type="button" onClick={onOlvidar} aria-label="Olvidar mi historial" title="Borrar el historial y lo que Shifu recuerda de mí"><LuTrash2 /></button>}
            <button type="button" onClick={() => setAbierto(false)} aria-label="Cerrar el chat"><LuX /></button></header>
          <div className="mc-chat-msgs" role="log" aria-live="polite">
            {mensajes.map((m) => (
              <div key={m.id} className={`cb ${m.de}`}>{m.de === 'shifu' && <ShifuAvatar size={26} />}
                <div className="cb-t">{m.imagen && <img className="cb-img" src={m.imagen} alt="Captura enviada a Shifu" />}{m.de === 'shifu' ? <TextoChat texto={m.t} /> : m.t}</div></div>
            ))}
            {escribiendo && <div className="cb shifu"><ShifuAvatar size={26} /><p className="puntos" aria-label="Shifu está escribiendo"><i /><i /><i /></p></div>}
            <div ref={fin} />
          </div>
          <div className="mc-chat-sug" aria-label="Ideas para empezar">
            {sugerencias.map(([p, s]) => <button key={s} type="button" disabled={escribiendo} onClick={() => onEnviar(s)}><em>{p}</em>{s}</button>)}
          </div>
          {(imagen || errorImg) && (
            <div className="mc-adjunto" role="status">
              {imagen && <img src={imagen.url} alt="Imagen lista para enviar" />}
              <span>{imagen ? 'Foto lista. Dime qué hago con ella, por ejemplo: “pasa esto a mi lista”.' : errorImg}</span>
              <button type="button" onClick={() => { setImagen(null); setErrorImg('') }} aria-label="Quitar la captura"><LuX /></button>
            </div>
          )}
          {consejo && !imagen && !errorImg && (
            <div className="mc-consejo" role="note">
              <button type="button" className="mc-consejo-x" onClick={cerrarConsejo} aria-label="Cerrar el consejo"><LuX /></button>
              <p><b>📷 ¿Tienes tus datos en un cuaderno?</b> Toca el botón de foto, súbela y yo los paso aquí.</p>
            </div>
          )}
          <form onSubmit={enviar}>
            <button type="button" className="mc-chat-cam mc-chat-foto" onClick={() => { cerrarConsejo(); fotoRef.current?.click() }} disabled={escribiendo} aria-label="Subir una foto" title="Subir una foto"><LuImagePlus /></button>
            <button type="button" className="mc-chat-cam" onClick={() => { cerrarConsejo(); setEligiendo(true) }} disabled={escribiendo} aria-label="Capturar una parte de la pantalla" title="Capturar una parte de la pantalla"><LuCamera /></button>
            <input ref={campo} value={txt} onChange={(e) => setTxt(e.target.value)} onPaste={pegar} placeholder={imagen ? 'Qué quieres hacer con esta foto…' : 'Escribe o sube una foto…'} aria-label="Mensaje para Shifu" maxLength={2000} />
            <button type="submit" disabled={(!txt.trim() && !imagen) || escribiendo} aria-label="Enviar"><LuSend /></button>
          </form>
        </section>
      )}
      <button type="button" data-tour="chat" className={`mc-chat-btn ${abierto ? 'abierto' : ''}`} onClick={() => setAbierto(!abierto)} aria-expanded={abierto} aria-label={abierto ? 'Cerrar el chat con Shifu' : 'Abrir el chat con Shifu'} hidden={eligiendo || capturando}>
        {abierto ? <LuX /> : <><ShifuAvatar size={46} /><i className="punto" /></>}
      </button>
      {!abierto && pista && <span className="mc-chat-hint">¿Qué cambiamos hoy?</span>}
      <input ref={fotoRef} type="file" accept="image/*" hidden onChange={fotoElegida} />
      {eligiendo && <SelectorCaptura onElegir={elegida} onCancelar={() => setEligiendo(false)} />}
      {capturando && <div className="mc-captura mc-captura-espera" role="status">Tomando la captura…</div>}
    </div>,
    document.body,
  )
}

/* ───────── Página ───────── */

let idMensaje = 0
const mensaje = (de, t, imagen) => { idMensaje += 1; return { id: idMensaje, de, t, imagen } }

/** Cómo es el logotipo: qué tan ancho es y si tiene fondo transparente. Con eso la barra lo muestra bien (un logo cuadrado va con el nombre al lado; uno ancho, solo). */
function useInfoLogo(logo) {
  const [info, setInfo] = useState(null)
  useEffect(() => {
    if (!logo) { setInfo(null); return undefined }
    let vivo = true
    const img = new Image()
    img.onload = () => {
      if (!vivo) return
      let transparente = false
      try {
        const c = document.createElement('canvas')
        c.width = 24; c.height = 24
        const g = c.getContext('2d')
        g.drawImage(img, 0, 0, 24, 24)
        const d = g.getImageData(0, 0, 24, 24).data
        for (let i = 3; i < d.length; i += 4) if (d[i] < 235) { transparente = true; break }
      } catch { /* si no se puede leer, se trata como un logo con fondo */ }
      setInfo({ ancho: img.naturalWidth / Math.max(1, img.naturalHeight) >= 2, transparente })
    }
    img.src = logo
    return () => { vivo = false }
  }, [logo])
  return info
}

export default function CrmPage() {
  const nav = useNavigate()
  const { state } = useLocation()
  const recienTerminado = !!state?.cargar
  const borrador = useMemo(() => leerBorrador(), [])

  const [crm, setCrm] = useState(null)
  const [fallo, setFallo] = useState(false)
  const [animando, setAnimando] = useState(recienTerminado)
  const [vistaPedida, setVista] = useState(null) // la sección que la persona abrió; la que se ve (`vista`) se calcula más abajo, con el menú
  const [buscar, setBuscar] = useState('')
  const [bienvenida, setBienvenida] = useState(true)
  const [importando, setImportando] = useState(null) // id de la sección a la que se está importando un Excel
  const infoLogo = useInfoLogo(crm?.logo)
  // Tema claro u oscuro: preferencia de cada persona, se recuerda en el navegador.
  const [tema, setTema] = useState(() => { try { return localStorage.getItem('shifu_tema') === 'claro' ? 'claro' : 'oscuro' } catch { return 'oscuro' } })
  const primerTema = useRef(true)
  useEffect(() => () => document.documentElement.classList.remove('cambiando-tema'), []) // si se sale de la página a mitad del cambio, no queda la clase puesta
  useEffect(() => {
    try { localStorage.setItem('shifu_tema', tema) } catch { /* sin almacenamiento */ }
    document.documentElement.style.colorScheme = tema === 'claro' ? 'light' : 'dark'
    // Al cambiar (no al abrir la página) los colores se mezclan con suavidad: la clase solo dura lo que dura la transición.
    let t
    if (primerTema.current) primerTema.current = false
    else { document.documentElement.classList.add('cambiando-tema'); t = setTimeout(() => document.documentElement.classList.remove('cambiando-tema'), 700) }
    return () => { clearTimeout(t); document.documentElement.style.colorScheme = '' }
  }, [tema])
  const [aviso, setAviso] = useState('')
  const pedido = useRef(null)
  const avisoT = useRef(null)

  // Al entrar: si venimos del cuestionario se crea el CRM; si no, se pide el que ya existe. Se pide una sola vez (también con StrictMode).
  const cargar = () => {
    setFallo(false)
    // Con el cuestionario recién terminado se crea el CRM; si el servidor dice que ya hay uno con datos (409), se abre ese y no se toca.
    pedido.current = (recienTerminado && borrador?.fin && borrador?.resp
      ? apiCrm.crearDesdeBrief(borrador.resp).catch((e) => (e?.estado === 409 ? apiCrm.obtener() : Promise.reject(e)))
      : apiCrm.obtener())
    pedido.current.then((s) => {
      if (s) { if (recienTerminado) borrarBorrador(); setCrm(s); return } // el CRM ya guarda sus respuestas: el borrador sobra
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
  // El título sale del menú; si la sección está oculta (el CRM nace limpio) se usa su nombre de siempre, para que nunca quede vacío.
  const tit = (id) => (id === 'ajustes' ? 'Ajustes' : menu.find((m) => m.id === id)?.t ?? tituloSeccion(brief?.rubro, id, crm?.secciones))
  // Solo se dibuja una sección que está en el menú: si la pedida está oculta (o todavía no se eligió ninguna), se abre la primera. Así nunca se pinta una sección oculta ni un instante.
  const vista = vistaPedida === 'ajustes' || menu.some((m) => m.id === vistaPedida) ? vistaPedida : (menu[0]?.id ?? 'contactos')
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

  // Importa un lote de filas a una sección. Devuelve { agregadas, omitidas } o null si falló.
  const importarLote = async (listaId, filas, lote) => {
    try { const r = await apiCrm.registrosImportar(listaId, filas, lote); setCrm(r); return r.importacion || { agregadas: filas.length, omitidas: 0 } } catch (e) { avisar([404, 422].includes(e?.estado) && e.message ? e.message : 'No se pudo importar. Inténtalo de nuevo.'); return null }
  }

  const actualizarRegistro = (listaId, id, valores) => aplicar(() => apiCrm.registrosActualizar(listaId, id, valores))
  // Devuelve '' si se guardó, o el motivo si no se pudo (para mostrarlo en Ajustes).
  const ponerLogo = async (archivo) => {
    try { return (await aplicar(async () => apiCrm.logoGuardar(await logoDeArchivo(archivo)))) ? '' : 'No se pudo guardar el logotipo. Inténtalo de nuevo.' } catch (e) { return e?.message || 'No pude usar esa imagen.' }
  }
  const quitarLogo = () => aplicar(() => apiCrm.logoQuitar())
  const quitarImportacion = (listaId, loteId) => aplicar(() => apiCrm.importacionQuitar(listaId, loteId))
  const vaciarLista = (listaId) => aplicar(() => apiCrm.registrosVaciar(listaId))
  const agregarContacto = (fila) => aplicar(() => apiCrm.contactosCrear([fila], 'Manual', `Agregaste a ${fila.n}`))
  const actualizarContacto = (id, cambios) => aplicar(() => apiCrm.contactosActualizar(id, cambios))
  const agregarTarea = (t, vence, hora) => aplicar(() => apiCrm.tareasCrear(t, vence, hora))
  const actualizarTarea = (id, cambios) => aplicar(() => apiCrm.tareasActualizar(id, cambios))

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
      const historial = mensajes.slice(-16).filter((m) => m.t).map((m) => ({ de: m.de, t: m.t.slice(0, 500) }))
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

  // Shifu se acuerda: al abrir el CRM se recupera la conversación guardada y, si hace rato que no hablan, él retoma lo último.
  const restaurado = useRef(false)
  useEffect(() => {
    if (!crm || restaurado.current || recienTerminado) return
    restaurado.current = true
    apiChat.historial().then((h) => {
      if (!h?.mensajes?.length) return
      setMensajes([...h.mensajes.map((m) => mensaje(m.de, m.t)), ...(h.saludo ? [mensaje('shifu', h.saludo)] : [])])
      if (h.saludo) setChatAbierto(true)
    }).catch(() => { /* sin historial: se queda el saludo de siempre */ })
  }, [crm, recienTerminado])
  const olvidar = async () => {
    if (!window.confirm('¿Borrar tu historial con Shifu y todo lo que recuerda de ti? Tu CRM no se toca.')) return
    try {
      await apiChat.olvidar()
      setMensajes([mensaje('shifu', 'Listo, empezamos de cero: ya no recuerdo nuestras conversaciones. 🙂 ¿En qué te ayudo?')])
      avisar('Shifu olvidó tu historial.')
    } catch { avisar('No se pudo borrar el historial. Inténtalo de nuevo.') }
  }

  // Recién creado con IA: el chat se abre solo y cuenta cómo armó el CRM, para que la persona lo ajuste hablando.
  const saludado = useRef(false)
  useEffect(() => {
    if (!crm?.resumenIA || saludado.current || !recienTerminado) return
    saludado.current = true
    setMensajes([mensaje('shifu', `Hola 👋 Soy Shifu. ${crm.resumenIA}

Si algo no te cuadra, dímelo y lo cambio. Por ejemplo:
- «agrega a Pedro»
- «quita la sección de proveedores»
- «agrega un campo de cumpleaños a los contactos»`)])
    setChatAbierto(true)
  }, [crm, recienTerminado])

  // Recorrido de bienvenida: se ofrece solo al terminar de generarse el CRM (una vez por persona) y se puede repetir desde Ajustes.
  const [tour, setTour] = useState(false)
  const tourPendiente = useRef(recienTerminado)
  const claveTour = () => `shifu_tour_${auth.usuario()?.correo || 'local'}`
  const empezarTour = () => {
    const primera = menu.find((m) => m.propia && m.grupo === 1) ?? menu[0] // se abre una pestaña propia para poder señalar sus botones
    if (primera) setVista(primera.id)
    setChatAbierto(false); setTour(true)
  }
  useEffect(() => {
    if (!tourPendiente.current || animando || !crm) return
    tourPendiente.current = false
    let visto = false
    try { visto = !!localStorage.getItem(claveTour()) } catch { /* sin almacenamiento: se muestra */ }
    if (!visto) empezarTour()
  }, [crm, animando]) // eslint-disable-line react-hooks/exhaustive-deps
  const terminarTour = () => {
    try { localStorage.setItem(claveTour(), '1') } catch { /* sin almacenamiento */ }
    setTour(false); setChatAbierto(true) // al cerrar, Shifu ya está abierto para saludar
  }

  if (fallo) return <Fallo onReintentar={() => { pedido.current = null; cargar() }} />
  if (animando && d) return <Cargando pasos={pasos} listo={!!crm} onListo={() => { setAnimando(false); nav('/mi-crm', { replace: true, state: null }) }} />
  if (!crm || !d) return <div className="carga" role="status"><p className="carga-sub">Abriendo tu CRM…</p></div>

  const salir = async () => { borrarBorrador(); await auth.cerrarSesion(); nav('/login', { replace: true }) }
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
        <Link to="/" aria-label="Shifu"><Logo height={30} color="var(--tx)" /></Link>
        <button type="button" className={`mc-marca ${crm.logo ? `con-logo ${infoLogo?.ancho ? 'ancho' : 'cuadrado'} ${infoLogo?.transparente ? 'transp' : 'opaco'}` : ''}`} onClick={() => ir('ajustes')} title={crm.logo ? `${d.nombre}: cambiar el logotipo en Ajustes` : 'Poner el logotipo de tu negocio (en Ajustes)'}>
          {crm.logo
            ? <><img src={crm.logo} alt={`Logotipo de ${d.nombre}`} />{!infoLogo?.ancho && <span>{d.nombre}</span>}</>
            : <><i aria-hidden="true">{d.nombre[0]?.toUpperCase()}</i><span>{d.nombre}</span></>}
        </button>
        <label className="mc-buscar"><LuSearch aria-hidden="true" />
          <input type="search" placeholder="Buscar en todo el espacio…" value={buscar} onChange={(e) => { setBuscar(e.target.value); if (e.target.value && menu.some((m) => m.id === 'contactos')) setVista('contactos') }} aria-label="Buscar" />
        </label>
        <Avisos onIr={ir} />
        <span className="mc-yo" title={yo?.correo || d.nombre} aria-hidden="true">{inicial}</span>
      </header>

      <div className="mc-cuerpo">
        <nav className={`mc-menu ${menu.length > 9 ? 'mc-menu-denso' : ''}`} aria-label="Secciones" data-tour="menu">
          {GRUPOS.map((g, gi) => (menu.some((m) => m.grupo === gi) && (
            <div key={g} className="mc-grupo">
              <h2>{g}</h2>
              <ul>
                {menu.filter((m) => m.grupo === gi).map(({ id, t, I }) => (
                  <li key={id}><button type="button" data-tour={`seccion-${id}`} title={t} className={vista === id ? 'on' : ''} aria-current={vista === id ? 'page' : undefined} onClick={() => ir(id)}><I aria-hidden="true" /><span>{t}</span></button></li>
                ))}
              </ul>
            </div>
          )))}
          <button type="button" data-tour="pedir" className="mc-pedir" onClick={() => setChatAbierto(true)}><LuSparkles aria-hidden="true" /><span>¿Qué más quieres tener?<small>Pídeselo a Shifu y lo agrega</small></span></button>
          <button type="button" data-tour="ajustes" className={`mc-ajustes ${vista === 'ajustes' ? 'on' : ''}`} aria-current={vista === 'ajustes' ? 'page' : undefined} onClick={() => ir('ajustes')}><LuSettings aria-hidden="true" /><span>Ajustes</span></button>
        </nav>

        <main className="mc-main">
          {bienvenida && (
            <aside className="mc-shifu" role="status">
              <ShifuAvatar size={40} />
              {crm.resumenIA
                ? <p><b>Listo, {d.nombre}.</b> {crm.resumenIA} Si algo no te cuadra, pídemelo en el chat de abajo a la derecha: puedo agregar, quitar o cambiar secciones, campos y etapas.</p>
                : <p><b>Listo, {d.nombre}.</b> Armé tu CRM con {menu.length} secciones, listo para tus canales ({d.canales.join(', ')}). Empieza por tus contactos: pídemelo en el chat de abajo a la derecha o impórtalos desde tu Excel o tus notas. También puedo crear secciones nuevas, quitar las que no uses o cambiar tus etapas.</p>}
              <button type="button" onClick={() => setBienvenida(false)} aria-label="Cerrar">✕</button>
            </aside>
          )}
          {vista === 'contactos' && <Contactos lista={crm.contactos} total={crm.totalContactos} buscar={buscar} etapas={crm.etapas ?? ETAPAS} campos={crm.camposContacto ?? []} vendedores={vendedores} t={tit('contactos')} onAgregar={agregarContacto} onActualizar={actualizarContacto} onBorrar={(c) => aplicar(() => apiCrm.contactosEliminar(c.id))} onImportar={() => ir('importar')} />}
          {vista === 'desarrollo' && <Desarrollo t={tit('desarrollo')} tareas={crm.tareas} onMover={(x, destino) => aplicar(() => apiCrm.tareasMover(x.id, destino))} onAgregar={agregarTarea} onActualizar={actualizarTarea} onBorrar={(x) => aplicar(() => apiCrm.tareasEliminar(x.id))} />}
          {vista === 'importar' && (
            <Importar existentes={crm.contactos.map((c) => c.n)} onVer={() => ir('contactos')}
              onImportar={(filas) => aplicar(() => apiCrm.contactosCrear(filas, 'Importado', `Importaste ${filas.length} ${filas.length === 1 ? 'contacto' : 'contactos'} desde tus notas o Excel`))} />
          )}
          {vista.startsWith('l_') && crm.listas?.find((l) => l.id === vista) && (
            <Lista lista={crm.listas.find((l) => l.id === vista)} metodos={comoLlevaHoy(brief)} onImportar={() => setImportando(vista)} onSubirFoto={() => window.dispatchEvent(new Event('shifu:subir-foto'))} onAgregar={(id, valores) => aplicar(() => apiCrm.registrosCrear(id, valores))}
              onActualizar={actualizarRegistro} onVaciar={vaciarLista}
              onBorrar={(id, rid) => aplicar(() => apiCrm.registrosEliminar(id, rid))} />
          )}
          {vista === 'cobros' && <Cobros moneda={d.moneda} t={tit('cobros')} />}
          {vista === 'actividad' && <Actividad eventos={crm.eventos} t={tit('actividad')} />}
          {vista === 'rrhh' && <Rrhh vendedores={vendedores} lista={crm.contactos} total={crm.totalContactos} t={tit('rrhh')} />}
          {vista === 'ajustes' && <Ajustes tema={tema} setTema={setTema} yo={yo} negocio={d.nombre} hayServidor={HAY_SERVIDOR} onSalir={salir} onRehacer={rehacer} onDescargar={() => descargarExcel(crm, d.nombre, { contactos: tit('contactos'), desarrollo: tit('desarrollo') })} logo={crm.logo} onLogo={ponerLogo} onQuitarLogo={quitarLogo} onTour={empezarTour} />}
          {vista === 'automatizaciones' && <Automatizaciones autos={crm.automatizaciones} onAlternar={(a) => aplicar(() => apiCrm.automatizacionFijar(a.id, !a.on))} />}
        </main>
      </div>

      {importando && crm.listas?.find((l) => l.id === importando) && (
        <ImportarALista lista={crm.listas.find((l) => l.id === importando)} onImportar={(filas, lote) => importarLote(importando, filas, lote)} onQuitar={(loteId) => quitarImportacion(importando, loteId)} onCerrar={() => setImportando(null)} />
      )}
      {tour && <Tour tema={tema} pasos={armarRecorrido({ negocio: d.nombre, menu, crm })} onFin={terminarTour} />}
      {aviso && <p className="mc-toast" role="alert">{aviso}</p>}
      <ChatShifu modo={modo} sugerencias={sugerenciasDe(crm.contactos)} tema={tema} abierto={chatAbierto} setAbierto={setChatAbierto} mensajes={mensajes} escribiendo={escribiendo} onEnviar={enviar} onOlvidar={HAY_SERVIDOR ? olvidar : undefined} />
    </div>
  )
}

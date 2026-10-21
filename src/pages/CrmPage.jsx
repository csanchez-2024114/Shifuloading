import { Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import Logo from '../components/Logo'
import ShifuAvatar from '../components/ShifuAvatar'
import TextoChat from '../components/TextoChat'
import { SelectorCaptura, capturarRegion, imagenDeArchivo } from '../components/CapturaPantalla'
import { documentoDeArchivo } from '../components/adjuntos'
import ImportarALista from '../components/ImportarALista'
import BuscadorGlobal from '../components/BuscadorGlobal'
import { ANCHO_VENTANA, alSoltar, guardarPos, leerPos } from '../components/posicionChat'
import { descargarExcel } from '../crm/exportarExcel'
import { bajarDescarga, exportar } from '../crm/descargas'
import { HAY_SERVIDOR, auth, avisos as apiAvisos, chat as apiChat, crm as apiCrm } from '../api'
import { etiqueta } from '../brief/preguntas'
import { borrarBorrador, guardarBorrador, leerBorrador } from '../brief/borrador'
import { COLUMNAS, ETAPAS, tituloSeccion } from '../crm/secciones'
import { avisoDeshacer } from '../crm/avisoDeshacer'
import { DISENO, ChatDiseno, DisenoCrm, LogoNegocio, cargarCaptura, cargarSugerencias, conInicio, esVistaDiseno, marcoDiseno, tomarSeleccion } from '../crm/plantillas' // sistema de diseño (D61), solo con VITE_CRM_DISENO=1
import { LuUsers, LuWallet, LuCode, LuActivity, LuIdCard, LuSearch, LuBell, LuLogOut, LuPlus, LuRotateCcw, LuTable, LuUpload, LuZap, LuCamera, LuSend, LuSun, LuMoon, LuX, LuLightbulb, LuTrash2, LuImagePlus, LuPaperclip, LuSparkles, LuSettings, LuPencil, LuDownload } from 'react-icons/lu'
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
      <span>¿Eliminar {que}? {avisoDeshacer()}</span>
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
        {!modo && <div className="mc-cab-acc"><button type="button" className="mc-sec" onClick={onImportar}><LuUpload aria-hidden="true" /> Importar</button><button type="button" className="btn-pildora" onClick={() => abrir('nuevo')}><LuPlus aria-hidden="true" /> Agregar</button></div>}
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
function Lista({ lista, onAgregar, onActualizar, onBorrar, onQuitarImportacion, onQuitarTodas, onVaciar, onSubirFoto, onImportar, metodos }) {
  const [modo, setModo] = useState(null) // null | 'nuevo' | id del registro que se edita
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [borrando, setBorrando] = useState(null)
  const [quitando, setQuitando] = useState(null) // id de la importación con la advertencia abierta
  const [haciendo, setHaciendo] = useState(false)
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
  const quitar = async (i) => { setHaciendo(true); await onQuitarImportacion(lista.id, i.id); setHaciendo(false); setQuitando(null) }
  const quitarTodas = async () => { setHaciendo(true); await onQuitarTodas(lista.id); setHaciendo(false); setQuitando(null) }
  const totalImportado = (lista.importaciones || []).reduce((n, i) => n + i.cantidad, 0)
  return (
    <>
      <div className="mc-cab">
        <div><h1>{lista.nombre}</h1><p>{lista.registros.length === 0 ? 'Todavía no tiene registros.' : `${lista.registros.length.toLocaleString('es')} ${lista.registros.length === 1 ? 'registro' : 'registros'}. Toca uno para editarlo.`} Para cambiar los campos o quitar la sección, pídeselo a Shifu en el chat.</p></div>
        {!modo && (
          <div className="mc-cab-acc">
            <button type="button" className="mc-sec" onClick={onImportar}><LuUpload aria-hidden="true" /> Importar</button>
            <button type="button" className="btn-pildora" onClick={() => abrir('nuevo')}><LuPlus aria-hidden="true" /> Agregar</button>
          </div>
        )}
      </div>
      {modo && <FormFila key={modo} titulo={editando ? 'Editar registro' : 'Agregar registro'} campos={lista.campos} inicial={editando ? valoresDe(editando) : {}} enviando={enviando} error={error} onGuardar={guardar} onCancelar={() => setModo(null)} />}

      {lista.importaciones?.length > 0 && (
        <details className="mc-importaciones">
          <summary><LuUpload aria-hidden="true" /> <b>Importaciones de esta sección ({lista.importaciones.length})</b> <small>Toca aquí para quitar lo que importaste</small></summary>
          {lista.importaciones.length > 1 && (
            <div className="mc-imp-item mc-imp-todas">
              <div><b>Todo lo importado</b><small>{totalImportado.toLocaleString('es')} registros de {lista.importaciones.length} importaciones</small></div>
              {quitando === 'todas'
                ? (
                  <div className="mc-aj-confirma" role="alertdialog" aria-label="Confirmar que se quita todo lo importado">
                    <p>⚠ Se borrarán los {totalImportado.toLocaleString('es')} registros de todas las importaciones de esta sección, incluso los que hayas editado. Lo que agregaste a mano se queda. {avisoDeshacer()}</p>
                    <button type="button" className="mc-peligro" disabled={haciendo} onClick={quitarTodas}>{haciendo ? 'Quitando…' : 'Sí, quitar todo lo importado'}</button>
                    <button type="button" className="mc-link" disabled={haciendo} onClick={() => setQuitando(null)}>Cancelar</button>
                  </div>
                )
                : <button type="button" className="mc-peligro mc-chico" onClick={() => setQuitando('todas')}>Quitar todo lo importado</button>}
            </div>
          )}
          {lista.importaciones.map((i) => (
            <div key={i.id} className="mc-imp-item">
              <div><b>{i.nombre}</b><small>{i.cantidad.toLocaleString('es')} {i.cantidad === 1 ? 'registro' : 'registros'} · {new Date(i.creado).toLocaleDateString('es')}</small></div>
              {quitando === i.id
                ? (
                  <div className="mc-aj-confirma" role="alertdialog" aria-label="Confirmar que se quita la importación">
                    <p>⚠ Se borrarán los {i.cantidad.toLocaleString('es')} registros de esta importación, incluso los que hayas editado. {avisoDeshacer()}</p>
                    <button type="button" className="mc-peligro" disabled={haciendo} onClick={() => quitar(i)}>{haciendo ? 'Quitando…' : 'Sí, quitar la importación'}</button>
                    <button type="button" className="mc-link" disabled={haciendo} onClick={() => setQuitando(null)}>Cancelar</button>
                  </div>
                )
                : <button type="button" className="mc-sec" onClick={() => setQuitando(i.id)}>Quitar importación</button>}
            </div>
          ))}
        </details>
      )}

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
                  <p>⚠ Se borrarán los {lista.registros.length.toLocaleString('es')} registros de “{lista.nombre}”: todo, lo importado y lo que escribiste a mano. La sección y sus columnas se quedan. {avisoDeshacer()}</p>
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
function Ajustes({ tema, setTema, yo, negocio, hayServidor, onSalir, onRehacer, onDescargar, onRespaldo }) {
  const [confirmando, setConfirmando] = useState(false)
  const [bajando, setBajando] = useState(false)
  const [notaExcel, setNotaExcel] = useState('')
  const descargar = async () => {
    setBajando(true); setNotaExcel('')
    try { setNotaExcel((await onDescargar()) ? '¡Listo! Revisa tu carpeta de Descargas.' : 'Todavía no hay nada que descargar: agrega algo a tu CRM primero.') } catch { setNotaExcel('No se pudo preparar el archivo. Inténtalo de nuevo.') }
    setBajando(false)
  }
  const [respaldando, setRespaldando] = useState(false)
  const [notaRespaldo, setNotaRespaldo] = useState('')
  const respaldar = async () => {
    setRespaldando(true); setNotaRespaldo('')
    try { await onRespaldo(); setNotaRespaldo('¡Listo! Guárdalo en un lugar seguro: ahí está todo tu CRM.') } catch (e) { setNotaRespaldo(e?.message || 'No se pudo preparar el respaldo. Inténtalo de nuevo.') }
    setRespaldando(false)
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

        <section aria-labelledby="aj-datos">
          <h2 id="aj-datos">Mis datos</h2>
          <div className="mc-aj-fila">
            <div><b>Descargar mi CRM en Excel</b><small>Un libro con una hoja por cada sección, con todo lo que llevas hasta hoy. Puedes descargarlo cuantas veces quieras.</small>{notaExcel && <small className="mc-aj-nota" role="status">{notaExcel}</small>}</div>
            <button type="button" className="mc-sec" disabled={bajando} onClick={descargar}><LuDownload aria-hidden="true" /> {bajando ? 'Preparando…' : 'Descargar Excel'}</button>
          </div>
          {onRespaldo && (
            <div className="mc-aj-fila">
              <div><b>Respaldo completo</b><small>Un solo archivo con todo tu CRM: secciones, registros, diseño y colores. También puedes pedírselo a Shifu: «hazme un respaldo».</small>{notaRespaldo && <small className="mc-aj-nota" role="status">{notaRespaldo}</small>}</div>
              <button type="button" className="mc-sec" disabled={respaldando} onClick={respaldar}><LuDownload aria-hidden="true" /> {respaldando ? 'Preparando…' : 'Descargar respaldo'}</button>
            </div>
          )}
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
                      <span>¿Eliminar? {avisoDeshacer()}</span>
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

function Importar({ existentes, onImportar, onVer, onCerrar }) {
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
      <div className="mc-cab"><div><h1>Importar datos</h1><p>¿Tienes tus clientes en un Excel o en notas? Pásalos aquí y Shifu los ordena como contactos.</p></div>
        {onCerrar && <button type="button" className="mc-link" onClick={onCerrar} aria-label="Cerrar"><LuX /></button>}</div>
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
    <div className="mc-avisos" ref={caja}>
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

const CLAVE_SUG_OCULTAS = 'shifu_sug_ocultas'
const ANCHO_CHAT = 360
const ALTO_CHAT = 560

function ChatShifu({ tema, abierto, setAbierto, mensajes, escribiendo, onEnviar, sugerencias, modo, onOlvidar, crm, aplicar, capturaLab, pos, setPos, onPosicion }) {
  const [txt, setTxt] = useState('')
  const [ancho, setAncho] = useState(() => (typeof window !== 'undefined' ? window.innerWidth : 1200))
  const ventana = DISENO && ancho >= ANCHO_VENTANA
  const [sugOcultas, setSugOcultas] = useState(() => { try { return localStorage.getItem(CLAVE_SUG_OCULTAS) === '1' } catch { return false } })
  const [cabEl, setCabEl] = useState(null)
  const [popEl, setPopEl] = useState(null)
  const arrastrando = useRef(null)
  useEffect(() => {
    const medir = () => setAncho(window.innerWidth)
    window.addEventListener('resize', medir)
    return () => window.removeEventListener('resize', medir)
  }, [])
  useEffect(() => { onPosicion?.(pos, ventana && abierto) }, [pos, ventana, abierto, onPosicion])
  const toggleSug = () => {
    setSugOcultas((v) => {
      const n = !v
      try { localStorage.setItem(CLAVE_SUG_OCULTAS, n ? '1' : '0') } catch { /* sin almacenamiento */ }
      return n
    })
  }
  const soltarVentana = (clientX, clientY) => {
    if (!ventana) return
    const nueva = alSoltar({ x: clientX, y: clientY }, { ancho: ANCHO_CHAT, alto: ALTO_CHAT }, { ancho: window.innerWidth, alto: window.innerHeight })
    setPos(nueva); guardarPos(nueva)
  }
  const enCabecera = (e) => {
    if (!ventana || e.button !== 0) return
    const panel = e.currentTarget.closest('.mc-chat-panel')
    const rect = panel?.getBoundingClientRect()
    if (!rect) return
    let x = pos?.modo === 'libre' ? pos.x : rect.left
    let y = pos?.modo === 'libre' ? pos.y : rect.top
    if (pos?.modo !== 'libre') setPos({ modo: 'libre', x, y })
    arrastrando.current = { ox: e.clientX - x, oy: e.clientY - y }
    e.currentTarget.setPointerCapture?.(e.pointerId)
  }
  useEffect(() => {
    if (!ventana) return undefined
    const mover = (e) => {
      const a = arrastrando.current
      if (!a) return
      setPos({ modo: 'libre', x: e.clientX - a.ox, y: e.clientY - a.oy })
    }
    const fin = (e) => {
      if (!arrastrando.current) return
      arrastrando.current = null
      soltarVentana(e.clientX, e.clientY)
    }
    window.addEventListener('pointermove', mover)
    window.addEventListener('pointerup', fin)
    return () => { window.removeEventListener('pointermove', mover); window.removeEventListener('pointerup', fin) }
  }, [ventana, setPos])
  const [imagen, setImagen] = useState(null) // captura o imagen pegada, lista para mandar con el mensaje
  const [documento, setDocumento] = useState(null) // PDF, Excel, etc. (no imagen)
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
  const docRef = useRef(null)
  // Desde una sección vacía se pide “subir una foto de mi cuaderno”: se abre el chat y se abre el selector de fotos.
  useEffect(() => {
    const f = () => { setAbierto(true); setTimeout(() => fotoRef.current?.click(), 250) }
    window.addEventListener('shifu:subir-foto', f)
    return () => window.removeEventListener('shifu:subir-foto', f)
  }, [setAbierto])
  useEffect(() => { fin.current?.scrollIntoView?.({ block: 'end' }) }, [mensajes, escribiendo, abierto])
  const puedeMandar = () => {
    if (escribiendo) return false
    if (documento || imagen?.url) return true
    if (capturaLab && imagen?.piezas?.length) return !!txt.trim()
    return !!txt.trim()
  }
  const enviar = (e) => {
    e?.preventDefault()
    if (!puedeMandar()) return
    onEnviar(txt, imagen, documento); setTxt(''); setImagen(null); setDocumento(null); setErrorImg('')
  }
  const usarArchivo = async (archivo) => {
    if (!archivo) return
    if (archivo.type?.startsWith('image/')) {
      setDocumento(null)
      try { setImagen(await imagenDeArchivo(archivo)); setErrorImg('') } catch { setErrorImg('No pude usar esa imagen.') }
      return
    }
    setImagen(null)
    try { setDocumento(await documentoDeArchivo(archivo)); setErrorImg('') } catch (err) { setErrorImg(err?.message || 'No pude usar ese archivo.') }
  }
  const [pista, setPista] = useState(true)
  useEffect(() => { const t = setTimeout(() => setPista(false), 7000); return () => clearTimeout(t) }, [])

  const elegida = async (region) => {
    setEligiendo(false); setCapturando(true); setErrorImg('')
    await new Promise((r) => setTimeout(r, 60)) // deja que la capa del selector desaparezca antes de dibujar
    if (capturaLab) {
      const piezas = capturaLab.piezasEnRegion(region)
      try {
        setImagen({ ...(await capturaLab.capturarRegionLab(region)), piezas })
      } catch (e) {
        console.error('[captura]', e)
        setImagen({ url: null, piezas })
        setErrorImg(piezas.length ? 'No pude dibujar la imagen, pero sé qué elegiste.' : 'No pude tomar la captura. Inténtalo de nuevo o pega una imagen.')
      }
    } else {
      try { setImagen(await capturarRegion(region)) } catch { setErrorImg('No pude tomar la captura. Inténtalo de nuevo o pega una imagen.') }
    }
    setCapturando(false)
    setTimeout(() => campo.current?.focus(), 0)
  }
  const fotoElegida = async (e) => {
    const archivo = e.target.files?.[0]
    e.target.value = ''
    await usarArchivo(archivo)
    setTimeout(() => campo.current?.focus(), 0)
  }
  const docElegido = async (e) => {
    const archivo = e.target.files?.[0]
    e.target.value = ''
    await usarArchivo(archivo)
    setTimeout(() => campo.current?.focus(), 0)
  }
  const pegar = async (e) => {
    const archivos = [...(e.clipboardData?.files || [])]
    const archivo = archivos.find((f) => f.type.startsWith('image/')) || archivos[0]
    if (!archivo) return
    e.preventDefault()
    await usarArchivo(archivo)
  }
  const soltar = async (e) => {
    e.preventDefault()
    const archivo = e.dataTransfer?.files?.[0]
    if (!archivo) return
    await usarArchivo(archivo)
  }

  const estiloLibre = ventana && pos?.modo === 'libre' ? { left: pos.x, top: pos.y } : undefined
  const bloqueDiseno = ChatDiseno && crm ? <ChatDiseno crm={crm} aplicar={aplicar} cabecera={cabEl} pop={popEl} /> : null
  const filaSug = sugerencias.length > 0 && (
    <div className={ventana ? 'mc-chat-sug-fila' : undefined}>
      {!sugOcultas && (
        <div className="mc-chat-sug" aria-label="Ideas para empezar">
          {sugerencias.map(([p, s]) => <button key={s} type="button" disabled={escribiendo} onClick={() => onEnviar(s)}><em>{p}</em>{s}</button>)}
        </div>
      )}
      {ventana && <button type="button" className="mc-chat-sug-toggle" onClick={toggleSug}>{sugOcultas ? 'Mostrar ideas' : 'Ocultar ideas'}</button>}
    </div>
  )

  // El chat va fuera de la página (en el body) para que siempre quede fijo en la esquina y no dependa de ningún contenedor.
  return createPortal(
    <div className={`mc-chat${ventana ? ' ventana' : ''}`} data-tema={tema} data-modo={ventana ? (pos?.modo || 'lado') : undefined} style={estiloLibre}>
      {ventana && !abierto && (
        <button type="button" className="mc-chat-riel" onClick={() => setAbierto(true)} aria-label="Abrir el chat con Shifu" title="Chat con Shifu">
          <ShifuAvatar size={32} /><small>Shifu</small>
        </button>
      )}
      {abierto && (
        <section className={`mc-chat-panel${ventana ? ' compacto' : ''}`} aria-label="Chat con Shifu" hidden={eligiendo || capturando}>
          <header onPointerDown={enCabecera}><ShifuAvatar size={ventana ? 28 : 34} /><div><b>Shifu</b><small>{modo === 'reglas' ? 'Modo básico' : 'Tu asistente'}</small></div>
            <span className="mc-chat-cab-acc" ref={setCabEl} />
            {onOlvidar && <button type="button" onClick={onOlvidar} aria-label="Olvidar mi historial" title="Borrar el historial y lo que Shifu recuerda de mí"><LuTrash2 /></button>}
            <button type="button" onClick={() => setAbierto(false)} aria-label="Cerrar el chat"><LuX /></button></header>
          <div className="mc-chat-msgs" role="log" aria-live="polite">
            {mensajes.map((m) => (
              <div key={m.id} className={`cb ${m.de}`}>{m.de === 'shifu' && <ShifuAvatar size={26} />}
                <div className="cb-t">{m.imagen && <img className="cb-img" src={m.imagen} alt="Captura enviada a Shifu" />}{m.de === 'shifu' ? <TextoChat texto={m.t} /> : m.t}
                  {m.archivos?.map((a) => <BotonArchivo key={a.id} archivo={a} />)}</div></div>
            ))}
            {escribiendo && <div className="cb shifu"><ShifuAvatar size={26} /><p className="puntos" aria-label="Shifu está escribiendo"><i /><i /><i /></p></div>}
            <div ref={fin} />
          </div>
          {ventana ? filaSug : (
            <div className="mc-chat-sug" aria-label="Ideas para empezar">
              {sugerencias.map(([p, s]) => <button key={s} type="button" disabled={escribiendo} onClick={() => onEnviar(s)}><em>{p}</em>{s}</button>)}
            </div>
          )}
          <div className="mcd-pop" ref={setPopEl} />
          {bloqueDiseno}
          {(imagen?.url || imagen?.piezas?.length || documento || errorImg) && (
            <div className="mc-adjunto" role="status">
              {imagen?.url && <img src={imagen.url} alt="Imagen lista para enviar" />}
              <span>{imagen?.url ? 'Foto lista. Dime qué hago con ella, por ejemplo: “pasa esto a mi lista”.'
                : imagen?.piezas?.length ? `Piezas en el recorte: ${imagen.piezas.map((p) => p.nombre || p.id).join(', ')}. Dime qué quieres hacer con ellas.`
                  : documento ? `Archivo listo (${documento.nombre}). Dime qué hago con él, por ejemplo: “pasa estas filas a mi lista”.`
                    : errorImg}</span>
              <button type="button" onClick={() => { setImagen(null); setDocumento(null); setErrorImg('') }} aria-label="Quitar el adjunto"><LuX /></button>
            </div>
          )}
          {consejo && !imagen?.url && !imagen?.piezas?.length && !documento && !errorImg && (
            <div className="mc-consejo" role="note">
              <button type="button" className="mc-consejo-x" onClick={cerrarConsejo} aria-label="Cerrar el consejo"><LuX /></button>
              <p><b>📷 ¿Tienes tus datos en un cuaderno?</b> Toca el botón de foto, súbela y yo los paso aquí.</p>
            </div>
          )}
          <form onSubmit={enviar} onDragOver={(e) => e.preventDefault()} onDrop={soltar}>
            <button type="button" className="mc-chat-cam mc-chat-foto" onClick={() => { cerrarConsejo(); fotoRef.current?.click() }} disabled={escribiendo} aria-label="Subir una foto" title="Subir una foto"><LuImagePlus /></button>
            <button type="button" className="mc-chat-cam" onClick={() => { cerrarConsejo(); docRef.current?.click() }} disabled={escribiendo} aria-label="Adjuntar un documento" title="Adjuntar PDF, Excel, Word…"><LuPaperclip /></button>
            <button type="button" className="mc-chat-cam" onClick={() => { cerrarConsejo(); setEligiendo(true) }} disabled={escribiendo} aria-label="Capturar una parte de la pantalla" title="Capturar una parte de la pantalla"><LuCamera /></button>
            <input ref={campo} value={txt} onChange={(e) => setTxt(e.target.value)} onPaste={pegar} placeholder={imagen ? 'Qué hago con esta foto…' : documento ? 'Qué hago con este archivo…' : ventana ? 'Escribe o adjunta…' : 'Escribe, sube una foto o adjunta un archivo…'} aria-label="Mensaje para Shifu" maxLength={2000} />
            <button type="submit" disabled={!puedeMandar()} aria-label="Enviar"><LuSend /></button>
          </form>
        </section>
      )}
      <button type="button" className={`mc-chat-btn ${abierto ? 'abierto' : ''}`} onClick={() => setAbierto(!abierto)} aria-expanded={abierto} aria-label={abierto ? 'Cerrar el chat con Shifu' : 'Abrir el chat con Shifu'} hidden={eligiendo || capturando || ventana}>
        {abierto ? <LuX /> : <><ShifuAvatar size={46} /><i className="punto" /></>}
      </button>
      {!abierto && pista && <span className="mc-chat-hint">¿Qué cambiamos hoy?</span>}
      <input ref={fotoRef} type="file" accept="image/*" hidden onChange={fotoElegida} />
      <input ref={docRef} type="file" accept=".pdf,.docx,.xlsx,.csv,.tsv,.txt,.md,.json" hidden onChange={docElegido} />
      {eligiendo && <SelectorCaptura onElegir={elegida} onCancelar={() => setEligiendo(false)} />}
      {capturando && <div className="mc-captura mc-captura-espera" role="status">Tomando la captura…</div>}
    </div>,
    document.body,
  )
}

/* ───────── Página ───────── */

let idMensaje = 0
const mensaje = (de, t, imagen, archivos) => { idMensaje += 1; return { id: idMensaje, de, t, imagen, archivos } }

/** El archivo que preparó Shifu, dentro de su mensaje: se vuelve a bajar cuantas veces quiera (el servidor lo guarda 24 h). */
function BotonArchivo({ archivo }) {
  const [estado, setEstado] = useState('')
  const bajar = async () => {
    setEstado('bajando')
    try { await bajarDescarga(archivo); setEstado('') } catch (e) { setEstado(e?.mensaje || e?.message || 'No se pudo descargar. Inténtalo de nuevo.') }
  }
  return (
    <span className="cb-archivo">
      <button type="button" className="mc-sec" disabled={estado === 'bajando'} onClick={bajar}><LuDownload aria-hidden="true" /> {estado === 'bajando' ? 'Descargando…' : archivo.nombre}</button>
      {estado && estado !== 'bajando' && <small role="status">{estado}</small>}
    </span>
  )
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
  const [importandoContactos, setImportandoContactos] = useState(false)
  const [chatPos, setChatPos] = useState(() => leerPos())
  const [chatEmpuja, setChatEmpuja] = useState(false)
  const onChatPosicion = (p, abiertoVentana) => {
    setChatPos(p)
    setChatEmpuja(DISENO && abiertoVentana && p?.modo === 'lado')
  }
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
  const menu = useMemo(() => conInicio(menuDe(brief?.rubro, crm?.secciones, crm?.ocultas, crm?.listas), crm), [brief, crm?.secciones, crm?.ocultas, crm?.listas, crm?.inicio]) // eslint-disable-line react-hooks/exhaustive-deps
  const seccionesBuscar = useMemo(() => menu.filter((m) => m.id === 'contactos' || m.id === 'desarrollo' || m.id.startsWith('l_')), [menu])
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
      DISENO ? 'Preparando tu pantalla de inicio' : 'Preparando tus secciones y automatizaciones',
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
  const quitarImportacion = (listaId, loteId) => aplicar(() => apiCrm.importacionQuitar(listaId, loteId))
  const vaciarLista = (listaId) => aplicar(() => apiCrm.registrosVaciar(listaId))
  const quitarTodasLasImportaciones = (listaId) => aplicar(() => apiCrm.importacionesQuitarTodas(listaId))
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
  const [ideasMod, setIdeasMod] = useState(null)
  const [capturaMod, setCapturaMod] = useState(null)
  useEffect(() => {
    if (!DISENO) return undefined
    cargarSugerencias?.().then(setIdeasMod)
    cargarCaptura?.().then(setCapturaMod)
    return undefined
  }, [])

  const sugerencias = useMemo(() => {
    if (DISENO && ideasMod && crm) {
      const lab = ideasMod.ideasDe(crm, vista, mensajes.length, { contactos: tit('contactos'), desarrollo: tit('desarrollo') })
      if (lab?.length) return lab
    }
    return sugerenciasDe(crm?.contactos ?? [])
  }, [crm, vista, mensajes.length, ideasMod]) // eslint-disable-line react-hooks/exhaustive-deps -- tit depende de crm

  const enviar = async (texto, imagen, documento) => {
    const t = texto.trim()
    const sel = tomarSeleccion() // piezas elegidas en el lienzo (D61); sin la bandera, null
    const ids = new Set()
    const seleccion = []
    for (const p of [...(sel?.contexto?.seleccion || []), ...(imagen?.piezas || [])]) {
      const clave = p.id || p.nombre
      if (!clave || ids.has(clave)) continue
      ids.add(clave)
      seleccion.push(p)
    }
    if (!t && !imagen?.url && !documento && !seleccion.length) return
    const etiquetaDoc = documento ? `${t ? ' ' : ''}📎 ${documento.nombre}` : ''
    setMensajes((l) => [...l, mensaje('yo', (sel?.prefijo || '') + t + etiquetaDoc, imagen?.url)])
    setEscribiendo(true)
    try {
      const historial = mensajes.slice(-16).filter((m) => m.t).map((m) => ({ de: m.de, t: m.t.slice(0, 500) }))
      const r = await apiChat.enviar(t, {
        pendiente: pendiente.current,
        imagen: imagen?.url,
        archivo: documento ? { nombre: documento.nombre, datos: documento.datos } : undefined,
        seccion: tit(vista),
        historial,
        ...(seleccion.length ? { seleccion } : {}),
      })
      pendiente.current = r.pendiente || null
      if (r.modo) setModo(r.modo)
      if (r.crm) setCrm(r.crm)
      if (r.vista) setVista(r.vista)
      setMensajes((l) => [...l, mensaje('shifu', r.respuesta, undefined, r.descargas)])
      // Lo pidió en este mensaje: se baja solo; el botón queda en el chat por si el navegador lo bloqueó o lo quiere otra vez.
      for (const a of r.descargas || []) bajarDescarga(a).catch(() => {})
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

  // Recién creado con IA: el chat se abre solo y cuenta cómo armó el CRM, para que la persona lo ajuste hablando. El resumen y los
  // ejemplos los escribe el backend con lo que de verdad se creó (lista 27 y 29); se dicen UNA vez: el aviso de bienvenida se cierra.
  const saludado = useRef(false)
  useEffect(() => {
    if (!crm?.resumenIA || saludado.current || !recienTerminado) return
    saludado.current = true
    const ejemplos = crm.saludoEjemplos?.length ? crm.saludoEjemplos : ['agrega a Pedro', 'quita la sección de proveedores', 'agrega un campo de cumpleaños a los contactos']
    setMensajes([mensaje('shifu', `Hola 👋 Soy Shifu. ${crm.resumenIA}

Si algo no te cuadra, dímelo y lo cambio. Por ejemplo:
${ejemplos.map((e) => `- «${e}»`).join('\n')}`)])
    setChatAbierto(true)
    setBienvenida(false)
  }, [crm, recienTerminado])

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
  const elegirBusqueda = (seccion, registroId) => {
    setBuscar('')
    ir(seccion)
    if (registroId && DISENO) window.dispatchEvent(new CustomEvent('shifu:abrir-registro', { detail: { seccion, id: registroId } }))
  }
  const vendedores = crm.vendedores
  const conDiseno = esVistaDiseno(vista, crm)

  return (
    <div {...marcoDiseno(crm, tema, chatEmpuja)} data-tema={tema}>
      <header className="mc-top">
        {DISENO && crm.marca?.logo_id
          ? <LogoNegocio id={crm.marca.logo_id} tema={tema} respaldo={<Link to="/" aria-label="Shifu"><Logo height={24} color="var(--tx)" /></Link>} />
          : <Link to="/" aria-label="Shifu"><Logo height={24} color="var(--tx)" /></Link>}
        <span className="mc-negocio">{d.nombre}</span>
        <BuscadorGlobal crm={crm} secciones={seccionesBuscar} valor={buscar} onCambiar={setBuscar} onElegir={elegirBusqueda} />
        <Avisos onIr={ir} />
        <span className="mc-yo" title={yo?.correo || d.nombre} aria-hidden="true">{inicial}</span>
      </header>

      <div className="mc-cuerpo">
        <nav className={`mc-menu ${menu.length > 9 ? 'mc-menu-denso' : ''}`} aria-label="Secciones">
          {GRUPOS.map((g, gi) => (menu.some((m) => m.grupo === gi) && (
            <div key={g} className="mc-grupo">
              <h2>{g}</h2>
              <ul>
                {menu.filter((m) => m.grupo === gi).map(({ id, t, I }) => (
                  <li key={id}><button type="button" title={t} data-seccion={id} className={vista === id ? 'on' : ''} aria-current={vista === id ? 'page' : undefined} onClick={() => ir(id)}><I aria-hidden="true" /><span>{t}</span></button></li>
                ))}
              </ul>
            </div>
          )))}
          <button type="button" className="mc-pedir" onClick={() => setChatAbierto(true)}><LuSparkles aria-hidden="true" /><span>¿Qué más quieres tener?<small>Pídeselo a Shifu y lo agrega</small></span></button>
          <button type="button" className={`mc-ajustes ${vista === 'ajustes' ? 'on' : ''}`} aria-current={vista === 'ajustes' ? 'page' : undefined} onClick={() => ir('ajustes')}><LuSettings aria-hidden="true" /><span>Ajustes</span></button>
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
          {conDiseno && (
            <Suspense fallback={<p className="mc-vacio">Cargando…</p>}>
              <DisenoCrm crm={crm} vista={vista} titulos={{ contactos: tit('contactos'), desarrollo: tit('desarrollo') }} api={apiCrm} aplicar={aplicar} buscar={buscar} setChat={setChatAbierto} onImportar={(id) => (id === 'contactos' ? setImportandoContactos(true) : setImportando(id))} />
            </Suspense>
          )}
          {!conDiseno && vista === 'contactos' && <Contactos lista={crm.contactos} total={crm.totalContactos} buscar={buscar} etapas={crm.etapas ?? ETAPAS} campos={crm.camposContacto ?? []} vendedores={vendedores} t={tit('contactos')} onAgregar={agregarContacto} onActualizar={actualizarContacto} onBorrar={(c) => aplicar(() => apiCrm.contactosEliminar(c.id))} onImportar={() => setImportandoContactos(true)} />}
          {!conDiseno && vista === 'desarrollo' && <Desarrollo t={tit('desarrollo')} tareas={crm.tareas} onMover={(x, destino) => aplicar(() => apiCrm.tareasMover(x.id, destino))} onAgregar={agregarTarea} onActualizar={actualizarTarea} onBorrar={(x) => aplicar(() => apiCrm.tareasEliminar(x.id))} />}
          {vista === 'importar' && (
            <Importar existentes={crm.contactos.map((c) => c.n)} onVer={() => ir('contactos')}
              onImportar={(filas) => aplicar(() => apiCrm.contactosCrear(filas, 'Importado', `Importaste ${filas.length} ${filas.length === 1 ? 'contacto' : 'contactos'} desde tus notas o Excel`))} />
          )}
          {!conDiseno && vista.startsWith('l_') && crm.listas?.find((l) => l.id === vista) && (
            <Lista lista={crm.listas.find((l) => l.id === vista)} metodos={comoLlevaHoy(brief)} onImportar={() => setImportando(vista)} onSubirFoto={() => window.dispatchEvent(new Event('shifu:subir-foto'))} onAgregar={(id, valores) => aplicar(() => apiCrm.registrosCrear(id, valores))}
              onActualizar={actualizarRegistro} onQuitarImportacion={quitarImportacion} onQuitarTodas={quitarTodasLasImportaciones} onVaciar={vaciarLista}
              onBorrar={(id, rid) => aplicar(() => apiCrm.registrosEliminar(id, rid))} />
          )}
          {vista === 'cobros' && <Cobros moneda={d.moneda} t={tit('cobros')} />}
          {vista === 'actividad' && <Actividad eventos={crm.eventos} t={tit('actividad')} />}
          {vista === 'rrhh' && <Rrhh vendedores={vendedores} lista={crm.contactos} total={crm.totalContactos} t={tit('rrhh')} />}
          {vista === 'ajustes' && <Ajustes tema={tema} setTema={setTema} yo={yo} negocio={d.nombre} hayServidor={HAY_SERVIDOR} onSalir={salir} onRehacer={rehacer} onDescargar={async () => {
            // Con servidor, el mismo archivo que arma Shifu (todas las secciones, también las que se ven distinto en pantalla); sin servidor, el del navegador.
            if (HAY_SERVIDOR) { await exportar('excel'); return true }
            return descargarExcel(crm, d.nombre, { contactos: tit('contactos'), desarrollo: tit('desarrollo') })
          }} onRespaldo={HAY_SERVIDOR ? () => exportar('respaldo') : null} />}
          {vista === 'automatizaciones' && <Automatizaciones autos={crm.automatizaciones} onAlternar={(a) => aplicar(() => apiCrm.automatizacionFijar(a.id, !a.on))} />}
        </main>
      </div>

      {importando && crm.listas?.find((l) => l.id === importando) && (
        <ImportarALista lista={crm.listas.find((l) => l.id === importando)} onImportar={(filas, lote) => importarLote(importando, filas, lote)} onQuitar={(loteId) => quitarImportacion(importando, loteId)} onCerrar={() => setImportando(null)} />
      )}
      {importandoContactos && (
        <div className="mc-modal" role="dialog" aria-modal="true" aria-label="Importar contactos" onMouseDown={(e) => { if (e.target === e.currentTarget) setImportandoContactos(false) }}>
          <div className="mc-modal-cuerpo mc-imp-modal">
            <Importar existentes={crm.contactos.map((c) => c.n)} onVer={() => { setImportandoContactos(false); ir('contactos') }}
              onCerrar={() => setImportandoContactos(false)}
              onImportar={(filas) => aplicar(() => apiCrm.contactosCrear(filas, 'Importado', `Importaste ${filas.length} ${filas.length === 1 ? 'contacto' : 'contactos'} desde tus notas o Excel`))} />
          </div>
        </div>
      )}
      {aviso && <p className="mc-toast" role="alert">{aviso}</p>}
      <ChatShifu modo={modo} sugerencias={sugerencias} tema={tema} abierto={chatAbierto} setAbierto={setChatAbierto} mensajes={mensajes} escribiendo={escribiendo} onEnviar={enviar} onOlvidar={HAY_SERVIDOR ? olvidar : undefined} crm={crm} aplicar={aplicar} capturaLab={DISENO ? capturaMod : null} pos={chatPos} setPos={setChatPos} onPosicion={onChatPosicion} />
    </div>
  )
}

import { useEffect, useMemo, useRef, useState } from 'react'
import { LuUpload, LuX } from 'react-icons/lu'
import { avisoDeshacer } from '../crm/avisoDeshacer'

/* Asistente para pasar a una sección lo que la persona ya tiene en Excel (.xlsx), en un CSV o copiado de una hoja.
 * Todo el análisis se hace aquí, en el navegador: se lee la tabla, se empareja cada columna con un campo de la sección,
 * se muestra una vista previa y, al confirmar, se mandan las filas al servidor (que valida y omite lo que no sirva). */

const LOTE = 300 // lo máximo que acepta el servidor por petición
const norm = (s) => String(s ?? '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9 ]+/g, ' ').replace(/\s+/g, ' ').trim()

/** Parte una línea en celdas respetando las comillas ("Arroz, grande",20). */
function partir(linea, sep) {
  const celdas = []
  let actual = ''
  let comillas = false
  for (let i = 0; i < linea.length; i++) {
    const c = linea[i]
    if (c === '"') { if (comillas && linea[i + 1] === '"') { actual += '"'; i++ } else comillas = !comillas } else if (c === sep && !comillas) { celdas.push(actual.trim()); actual = '' } else actual += c
  }
  celdas.push(actual.trim())
  return celdas
}

/** Texto pegado (celdas copiadas de Excel traen tabuladores) o CSV -> filas de celdas. */
export function leerTabla(texto) {
  const lineas = String(texto || '').split(/\r?\n/).filter((l) => l.trim())
  if (!lineas.length) return []
  const cuenta = (s) => lineas[0].split(s).length - 1
  const sep = ['\t', ';', ','].reduce((mejor, s) => (cuenta(s) > cuenta(mejor) ? s : mejor), '\t')
  return lineas.slice(0, 2001).map((l) => partir(l, sep))
}

const textoDe = (v) => {
  if (v === null || v === undefined) return ''
  if (v instanceof Date) return `${v.getUTCFullYear()}-${String(v.getUTCMonth() + 1).padStart(2, '0')}-${String(v.getUTCDate()).padStart(2, '0')}`
  return String(v).trim()
}

const esFecha = (v) => /^\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}$/.test(String(v).trim())
const esNumero = (v) => /^[-+]?[\d.,\sQ$€]+$/.test(String(v).trim()) && /\d/.test(String(v))

/** ¿Los valores de una columna sirven para un campo de ese tipo? (números en precios, fechas en fechas; el texto sirve para todo.) */
const sirve = (tipo, valores) => {
  const llenos = valores.filter((v) => v !== '')
  if (!llenos.length || (tipo !== 'numero' && tipo !== 'fecha')) return true
  return llenos.filter((v) => (tipo === 'numero' ? esNumero(v) : esFecha(v))).length / llenos.length >= 0.7
}

export default function ImportarALista({ lista, onImportar, onQuitar, onCerrar }) {
  const [filas, setFilas] = useState([])
  const [hojas, setHojas] = useState([]) // las hojas del libro de Excel (si trae varias, se puede elegir)
  const [hoja, setHoja] = useState(0)
  const [pegado, setPegado] = useState('')
  const [aviso, setAviso] = useState('')
  const [conTitulos, setConTitulos] = useState(true)
  const [mapa, setMapa] = useState({}) // idCampo -> número de columna ('' = no importar)
  const [enviando, setEnviando] = useState(false)
  const [resultado, setResultado] = useState(null)
  const [archivoNombre, setArchivoNombre] = useState('Texto pegado')
  const [loteId, setLoteId] = useState(null)
  const [deshaciendo, setDeshaciendo] = useState(null) // null | 'pregunta' | 'haciendo'
  const archivo = useRef(null)

  useEffect(() => {
    const esc = (e) => { if (e.key === 'Escape') onCerrar() }
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [onCerrar])

  const ancho = useMemo(() => filas.reduce((m, f) => Math.max(m, f.length), 0), [filas])
  const titulos = useMemo(() => Array.from({ length: ancho }, (_, i) => (conTitulos && filas[0]?.[i]) || `Columna ${i + 1}`), [filas, ancho, conTitulos])
  const datos = useMemo(() => (conTitulos ? filas.slice(1) : filas).filter((f) => f.some((c) => c !== '')), [filas, conTitulos])

  // Cada campo busca su columna por nombre (igual o parecido); si no hay títulos, por posición.
  const emparejar = (tabla, tieneTitulos) => {
    const cols = Array.from({ length: tabla.reduce((m, f) => Math.max(m, f.length), 0) }, (_, i) => norm(tieneTitulos ? tabla[0]?.[i] : ''))
    const cuerpo = (tieneTitulos ? tabla.slice(1) : tabla).slice(0, 60)
    const columna = (j) => cuerpo.map((f) => f[j] ?? '')
    const usadas = new Set()
    const salida = {}
    lista.campos.forEach((c, k) => {
      const n = norm(c.nombre)
      let i = cols.findIndex((x, j) => !usadas.has(j) && x && x === n)
      if (i < 0) i = cols.findIndex((x, j) => !usadas.has(j) && x && (x.includes(n) || n.includes(x)))
      if (i >= 0) usadas.add(i)
      salida[c.id] = i >= 0 ? i : ''
    })
    // Lo que no coincidió por nombre se asigna, en orden, a las columnas que quedaron libres: la persona lo ve en la vista previa y lo corrige si hace falta.
    // (solo con columnas que sirven para ese campo: una columna de nombres no se pone en un campo de fecha).
    lista.campos.forEach((c) => {
      if (salida[c.id] !== '') return
      const j = cols.findIndex((_, k) => !usadas.has(k) && sirve(c.tipo, columna(k)))
      if (j >= 0) { usadas.add(j); salida[c.id] = j }
    })
    return salida
  }

  const cargar = (tabla) => {
    const limpia = tabla.map((f) => f.map(textoDe))
    if (limpia.length < 1 || !limpia.some((f) => f.some((c) => c !== ''))) { setAviso('No encontré datos en ese archivo.'); return }
    // Se supone que la primera fila trae títulos si ninguna de sus celdas es un número.
    const titulos1 = limpia[0].every((c) => c === '' || !esNumero(c))
    setFilas(limpia); setConTitulos(titulos1); setMapa(emparejar(limpia, titulos1)); setAviso(''); setResultado(null)
  }

  const subir = async (e) => {
    const f = e.target.files?.[0]
    e.target.value = ''
    if (!f) return
    setAviso(''); setArchivoNombre(f.name)
    try {
      if (/\.xlsx$/i.test(f.name)) {
        const { default: leerXlsx } = await import('read-excel-file/browser')
        const r = await leerXlsx(f)
        const libro = Array.isArray(r) && r[0]?.data ? r : [{ sheet: 'Hoja 1', data: r }]
        // Si el libro trae varias hojas, se abre la que se llama como esta sección (Productos, Proveedores…); si no, la primera. Se puede cambiar.
        const n = norm(lista.nombre)
        const parecida = libro.findIndex((h) => { const x = norm(h.sheet); return x && (n.includes(x) || x.includes(n)) })
        const i = parecida >= 0 ? parecida : 0
        setHojas(libro); setHoja(i); cargar(libro[i].data)
      } else if (/\.xls$/i.test(f.name)) {
        setAviso('Ese es un Excel antiguo (.xls). Ábrelo y guárdalo como “Libro de Excel (.xlsx)” o como CSV, y vuelve a subirlo.')
      } else if (f.size > 2_000_000) {
        setAviso('Ese archivo pesa demasiado. Prueba con uno de menos de 2 MB.')
      } else {
        cargar(leerTabla(await f.text()))
      }
    } catch { setAviso('No pude leer ese archivo. Revisa que sea un Excel (.xlsx) o un CSV.') }
  }

  const cambiarHoja = (i) => { setHoja(i); cargar(hojas[i].data) }
  const alPegar = (texto) => { setPegado(texto); setArchivoNombre('Texto pegado'); if (texto.trim()) cargar(leerTabla(texto)); else { setFilas([]); setAviso('') } }
  const cambiarTitulos = (v) => { setConTitulos(v); setMapa(emparejar(filas, v)) }

  const aImportar = useMemo(() => datos.map((f) => Object.fromEntries(lista.campos.map((c) => [c.id, mapa[c.id] === '' || mapa[c.id] === undefined ? '' : (f[mapa[c.id]] ?? '')]).filter(([, v]) => v !== ''))).filter((o) => Object.keys(o).length), [datos, mapa, lista])
  // Avisa si la columna elegida para un campo no parece del tipo que ese campo espera.
  const alertas = useMemo(() => Object.fromEntries(lista.campos.filter((c) => mapa[c.id] !== '' && mapa[c.id] !== undefined && !sirve(c.tipo, datos.slice(0, 60).map((f) => f[mapa[c.id]] ?? '')))
    .map((c) => [c.id, c.tipo === 'numero' ? 'números' : 'fechas'])), [lista, mapa, datos])
  const hayMapa = lista.campos.some((c) => mapa[c.id] !== '' && mapa[c.id] !== undefined)

  const importar = async () => {
    setEnviando(true); setAviso('')
    // Todas las tandas de esta importación llevan el mismo lote: así se puede quitar entera si se importó lo que no era.
    const lote = { id: `imp_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`, nombre: `${archivoNombre}${hojas.length > 1 ? ` · ${hojas[hoja].sheet}` : ''}`.slice(0, 80) }
    setLoteId(lote.id)
    let agregadas = 0
    let omitidas = 0
    for (let i = 0; i < aImportar.length; i += LOTE) {
      const r = await onImportar(aImportar.slice(i, i + LOTE), lote)
      if (!r) { setAviso(agregadas ? 'Se importó una parte y luego algo falló. Revisa tu lista.' : 'No se pudo importar. Revisa que cada columna tenga lo que corresponde (por ejemplo, números en los precios).'); setEnviando(false); if (agregadas) setResultado({ agregadas, omitidas }); return }
      agregadas += r.agregadas; omitidas += r.omitidas
    }
    setResultado({ agregadas, omitidas }); setEnviando(false)
  }

  return (
    <div className="mc-modal" role="dialog" aria-modal="true" aria-label={`Importar a ${lista.nombre}`} onMouseDown={(e) => { if (e.target === e.currentTarget) onCerrar() }}>
      <div className="mc-modal-caja">
        <header>
          <div><h2>Importar a “{lista.nombre}”</h2><p>Pasa lo que ya tienes en Excel. Tú solo revisas que las columnas coincidan.</p></div>
          <button type="button" className="mc-modal-x" onClick={onCerrar} aria-label="Cerrar"><LuX /></button>
        </header>

        {resultado ? (
          <div className="mc-imp-listo">
            <b>¡Listo! Se importaron {resultado.agregadas.toLocaleString('es')} {resultado.agregadas === 1 ? 'registro' : 'registros'}.</b>
            {resultado.omitidas > 0 && <p>Se omitieron {resultado.omitidas} (filas vacías, repetidas o con un dato que no corresponde).</p>}
            <button type="button" className="btn-pildora mc-grande" onClick={onCerrar}>Ver mi lista</button>
            {deshaciendo === null && <button type="button" className="mc-link" onClick={() => setDeshaciendo('pregunta')}>Me equivoqué: quitar esta importación</button>}
            {deshaciendo && (
              <div className="mc-aj-confirma mc-imp-deshacer" role="alertdialog" aria-label="Confirmar que se quita la importación">
                <p>⚠ Se borrarán los {resultado.agregadas.toLocaleString('es')} registros que acabas de importar. {avisoDeshacer()}</p>
                <button type="button" className="mc-peligro" disabled={deshaciendo === 'haciendo'} onClick={async () => { setDeshaciendo('haciendo'); const ok = await onQuitar(loteId); if (ok) onCerrar(); else setDeshaciendo('pregunta') }}>{deshaciendo === 'haciendo' ? 'Quitando…' : 'Sí, quitar la importación'}</button>
                <button type="button" className="mc-link" disabled={deshaciendo === 'haciendo'} onClick={() => setDeshaciendo(null)}>Cancelar</button>
              </div>
            )}
          </div>
        ) : (
          <>
            {!filas.length ? (
              <div className="mc-imp-paso">
                <input ref={archivo} type="file" accept=".xlsx,.xls,.csv,.tsv,.txt" hidden onChange={subir} />
                <button type="button" className="btn-pildora mc-grande" onClick={() => archivo.current?.click()}><LuUpload aria-hidden="true" /> Elegir mi archivo de Excel</button>
                <small>Funciona con Excel (.xlsx) y con CSV.</small>
                <div className="mc-imp-o"><span>o</span></div>
                <label htmlFor="imp-pegar">Copia las celdas de tu hoja y pégalas aquí</label>
                <textarea id="imp-pegar" rows={5} value={pegado} onChange={(e) => alPegar(e.target.value)} placeholder={'Producto\tPrecio\tCantidad\nLeche\t12\t20\nArroz\t8\t5'} />
              </div>
            ) : (
              <div className="mc-imp-paso">
                {hojas.length > 1 && (
                  <label className="mc-imp-hoja">Tu Excel tiene varias hojas. Importar desde:
                    <select value={hoja} onChange={(e) => cambiarHoja(Number(e.target.value))}>{hojas.map((h, i) => <option key={i} value={i}>{h.sheet}</option>)}</select>
                  </label>
                )}
                <label className="mc-imp-check"><input type="checkbox" checked={conTitulos} onChange={(e) => cambiarTitulos(e.target.checked)} /> La primera fila son los títulos de las columnas</label>
                <p className="mc-imp-guia">Dime de qué columna sale cada dato de tu lista:</p>
                <div className="mc-imp-mapa">
                  {lista.campos.map((c) => (
                    <label key={c.id}>{c.nombre}
                      <select value={mapa[c.id] ?? ''} onChange={(e) => setMapa((m) => ({ ...m, [c.id]: e.target.value === '' ? '' : Number(e.target.value) }))}>
                        <option value="">No importar</option>
                        {titulos.map((t, i) => <option key={i} value={i}>{t}</option>)}
                      </select>
                      {alertas[c.id] && <em className="mc-imp-alerta">⚠ Esa columna no parece traer {alertas[c.id]}</em>}
                    </label>
                  ))}
                </div>
                <div className="mc-imp-vista">
                  <small>Así se verá ({Math.min(4, aImportar.length)} de {aImportar.length.toLocaleString('es')} filas):</small>
                  <div className="mc-imp-tabla" style={{ '--n': lista.campos.length }}>
                    <div className="cab">{lista.campos.map((c) => <span key={c.id}>{c.nombre}</span>)}</div>
                    {aImportar.slice(0, 4).map((o, i) => <div key={i}>{lista.campos.map((c) => <span key={c.id}>{o[c.id] ?? '—'}</span>)}</div>)}
                  </div>
                </div>
                <div className="mc-imp-acciones">
                  <button type="button" className="btn-pildora mc-grande" disabled={enviando || !hayMapa || !aImportar.length} onClick={importar}>
                    {enviando ? 'Importando…' : `Importar ${aImportar.length.toLocaleString('es')} ${aImportar.length === 1 ? 'fila' : 'filas'}`}
                  </button>
                  <button type="button" className="mc-link" onClick={() => { setFilas([]); setHojas([]); setPegado(''); setAviso('') }}>Elegir otro archivo</button>
                </div>
              </div>
            )}
            {aviso && <p className="mc-form-error" role="alert">{aviso}</p>}
          </>
        )}
      </div>
    </div>
  )
}

/* El sistema de diseño del laboratorio dentro del CRM de Carlos (D61): el inicio (lienzo de piezas), cada sección con su
 * vista o su lienzo propio, y la ficha de un registro. Los datos salen del `crm` de la API (desdeCrm) y cada cambio a mano
 * va por las MISMAS funciones de la API que usa CrmPage (aplicar → setCrm): esta pantalla no guarda nada por su cuenta.
 * El diseño y la estructura no se cambian a mano (D56): solo agregar, editar y eliminar registros. */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { LuPlus, LuUpload } from 'react-icons/lu'
import { AnimarContext, VelContext, FichaContext } from '@lab/plantillas/vistas'
import Ficha from '@lab/plantillas/ficha'
import { Lienzo, VistaSeccion, hacerDibujar } from '@lab/plantillas/lienzo'
import { FormRegistro } from '@lab/plantillas/manual'
import { campoTitulo } from '@lab/plantillas/valores'
import { datosEjemplo } from '@lab/plantillas/datosEjemplo'
import { acomodar } from '@lab/plantillas/edicion'
import { fijarRegion } from '@lab/plantillas/regional'
import { cargarFuentes } from '@lab/plantillas/marca'
import '@lab/plantillas/plantillas.css'
import '@lab/plantillas/estilos.css'
import '@lab/plantillas/marca-base.css'
import './diseno.css'
import { desdeCrm, contactoDesdeValores, tareaDesdeValores } from './desdeCrm'

const VEL = 2.2 // la animación lenta decidida en el laboratorio (estilo Vivo + Compacto)
const norm = (s) => String(s ?? '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').trim()
const llenos = (vals) => Object.fromEntries(Object.entries(vals).filter(([, v]) => String(v ?? '').trim() !== ''))

/**
 * crm: el de la API · vista: 'inicio' | 'contactos' | 'desarrollo' | id de una lista · titulos: nombres del menú
 * api: las funciones de `../../api` (crm) · aplicar(peticion): la de CrmPage (setCrm + aviso si falla; devuelve true/false)
 * onImportar(secId): abre la importación de esa sección · buscar: lo escrito en el buscador de arriba (filtra contactos)
 */
export default function DisenoCrm({ crm, vista, titulos, api, aplicar, onImportar, buscar = '' }) {
  fijarRegion(crm.brief?.ubicacion?.pais || 'gt')
  const tc = titulos?.contactos, td = titulos?.desarrollo
  const d = useMemo(() => desdeCrm(crm, { titulos: { contactos: tc, desarrollo: td }, acomodar }), [crm, tc, td])
  const { plantilla, porId } = d
  useEffect(() => { if (import.meta.env.DEV && d.avisos.length) console.warn('[diseño] Lo que no pasó el cerco y no se dibuja:', d.avisos) }, [d.avisos])
  useEffect(() => { cargarFuentes(d.marca) }, [d.marca])
  // El buscador de arriba filtra los contactos, como en la tabla de siempre.
  const datos = useMemo(() => {
    const q = norm(buscar)
    if (!q || !d.datos.registros.contactos) return d.datos
    return { ...d.datos, registros: { ...d.datos.registros, contactos: d.datos.registros.contactos.filter((r) => norm(r.valores.nombre).includes(q)) } }
  }, [d.datos, buscar])
  // Sin registros, cada vista muestra su forma con datos fantasma apagados (D25).
  const fantasma = useMemo(() => datosEjemplo(plantilla, 'pocos'), [plantilla])
  const dibujar = hacerDibujar({ porId, datos, fantasma })

  const [abierta, setAbierta] = useState(null) // { seccion, registro } de la ficha abierta
  const abrirFicha = useCallback((seccion, registro) => setAbierta({ seccion, registro }), [])
  const cerrarFicha = useCallback(() => setAbierta(null), [])
  const [agregando, setAgregando] = useState(null)
  useEffect(() => { setAgregando(null); setAbierta(null) }, [vista])

  /* Datos a mano → la ruta de la API que corresponde (§2). Devuelve null si salió bien o el texto del problema
   * (el aviso con el detalle del servidor ya lo muestra CrmPage). */
  const escribir = async (peticion) => ((await aplicar(peticion)) ? null : 'No se pudo guardar. Revisa los datos e inténtalo de nuevo.')
  const agregar = (s, valores) => {
    const v = llenos(valores)
    if (s.virtual === 'contactos') {
      const { etapa: _e, dueno: _d, ...fila } = contactoDesdeValores(v) // al crear, la etapa y el responsable los pone el servidor
      return escribir(() => api.contactosCrear([fila], 'Manual', `Agregaste a ${fila.n}`))
    }
    if (s.virtual === 'tareas') {
      const { cambios, columna } = tareaDesdeValores(v)
      return escribir(async () => {
        const antes = new Set(Object.values(crm.tareas || {}).flat().map((t) => t.id))
        let r = await api.tareasCrear(cambios.t, cambios.vence, cambios.hora)
        const nueva = Object.values(r.tareas || {}).flat().find((t) => !antes.has(t.id))
        if (nueva && columna && columna !== 'porHacer') r = await api.tareasMover(nueva.id, columna)
        return r
      })
    }
    return escribir(() => api.registrosCrear(s.id, v))
  }
  const onDato = async (nombre, args) => {
    const s = porId[args.seccion]
    if (!s) return 'Esa sección ya no existe.'
    const rid = args.registro
    if (nombre === 'borrar_registro') {
      return escribir(() => (s.virtual === 'contactos' ? api.contactosEliminar(rid) : s.virtual === 'tareas' ? api.tareasEliminar(rid) : api.registrosEliminar(s.id, rid)))
    }
    if (nombre === 'editar_registro') {
      if (s.virtual === 'contactos') return escribir(() => api.contactosActualizar(rid, contactoDesdeValores(args.valores, crm.contactos.find((c) => c.id === rid)?.extra)))
      if (s.virtual === 'tareas') {
        const { cambios, columna } = tareaDesdeValores(args.valores)
        return escribir(async () => {
          let r = Object.keys(cambios).length ? await api.tareasActualizar(rid, cambios) : null
          if (columna) r = await api.tareasMover(rid, columna)
          return r || crm
        })
      }
      return escribir(() => api.registrosActualizar(s.id, rid, args.valores))
    }
    if (nombre === 'agregar_registro') return agregar(s, args.valores)
    return 'Eso no se puede hacer a mano.'
  }

  const actual = vista === 'inicio' ? null : porId[vista]
  const total = !actual ? 0 : actual.virtual === 'contactos' ? (crm.totalContactos ?? datos.registros.contactos.length) : (datos.registros[actual.id] || []).length
  const importable = actual && (actual.virtual === 'contactos' || !actual.virtual)
  const formAgregar = () => {
    // Al crear un contacto la etapa y el responsable los pone el servidor (como en el formulario de siempre).
    const cs = actual.virtual === 'contactos' ? actual.campos.filter((c) => !['etapa', 'responsable'].includes(c.id)) : actual.campos
    return (
      <div className="pl-form-agregar">
        <FormRegistro key={actual.id} titulo={`Agregar a ${actual.titulo}`} campos={cs} obligatorio={campoTitulo(actual, cs)} guardar="Agregar" onCancelar={() => setAgregando(null)}
          onGuardar={async (vals) => { const err = await agregar(actual, vals); if (!err) setAgregando(null); return err }} />
      </div>
    )
  }

  return (
    <AnimarContext.Provider value><VelContext.Provider value={VEL}><FichaContext.Provider value={abrirFicha}>
      <div className="mc-diseno" key={vista} data-animar="">
        {vista === 'inicio' && (
          <>
            <div className="mc-cab"><div><h1>Inicio</h1><p>Lo más importante de {crm.brief?.nombre || 'tu negocio'}, de un vistazo. Toca cualquier registro para ver su ficha.</p></div></div>
            {d.bloques.length
              ? <Lienzo bloques={d.bloques} porId={porId} dibujar={dibujar} animado />
              : <div className="mc-vacio-grande pl-vacio pl-pagina-vacia"><b>Tu inicio está en blanco</b><p>Pídele a Shifu qué quieres ver aquí: un resumen, un tablero, un calendario, una gráfica…</p></div>}
          </>
        )}
        {actual && (
          <>
            <div className="mc-cab">
              <div><h1>{actual.titulo}</h1><p>{total ? `${total.toLocaleString('es')} ${total === 1 ? 'registro' : 'registros'}. Toca uno para ver su ficha.` : 'Todavía no hay registros.'} Para cambiar cómo se ve o sus campos, pídeselo a Shifu en el chat.</p></div>
              {agregando !== actual.id && (
                <div className="mc-cab-acc">
                  {importable && onImportar && <button type="button" className="mc-sec" onClick={() => onImportar(actual.id)}><LuUpload aria-hidden="true" /> Importar</button>}
                  <button type="button" className="btn-pildora" onClick={() => setAgregando(actual.id)}><LuPlus aria-hidden="true" /> Agregar</button>
                </div>
              )}
            </div>
            {agregando === actual.id && formAgregar()}
            <VistaSeccion seccion={actual} porId={porId} dibujar={dibujar} />
          </>
        )}
      </div>
      {abierta && <Ficha plantilla={plantilla} datos={datos} seccionId={abierta.seccion} registroId={abierta.registro} onCerrar={cerrarFicha} onAbrir={abrirFicha} onDato={onDato} />}
    </FichaContext.Provider></VelContext.Provider></AnimarContext.Provider>
  )
}

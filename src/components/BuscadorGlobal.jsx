/* El buscador de arriba (lista 36): busca en todas las secciones visibles del menú y muestra lo que encontró, por sección.
 * Tocar un resultado lleva a su sección (y, con el sistema de diseño, abre su ficha). Enter abre el primero; Esc cierra. */
import { useEffect, useMemo, useRef, useState } from 'react'
import { LuSearch } from 'react-icons/lu'
import { buscarEnCrm, MIN_LETRAS } from '../crm/buscar'

export default function BuscadorGlobal({ crm, secciones, valor, onCambiar, onElegir }) {
  const [abierto, setAbierto] = useState(false)
  const caja = useRef(null)
  const grupos = useMemo(() => buscarEnCrm(crm, secciones, valor), [crm, secciones, valor])
  const planos = useMemo(() => grupos.flatMap((g) => g.resultados.map((r) => ({ ...r, seccion: g.id }))), [grupos])
  const [activo, setActivo] = useState(0)
  useEffect(() => { setActivo(0) }, [valor])
  useEffect(() => {
    if (!abierto) return undefined
    const fuera = (e) => { if (caja.current && !caja.current.contains(e.target)) setAbierto(false) }
    document.addEventListener('mousedown', fuera)
    return () => document.removeEventListener('mousedown', fuera)
  }, [abierto])

  const elegir = (r) => { setAbierto(false); onElegir(r.seccion, r.id) }
  const tecla = (e) => {
    if (e.key === 'Escape') { setAbierto(false); return }
    if (!planos.length) return
    if (e.key === 'ArrowDown') { e.preventDefault(); setAbierto(true); setActivo((a) => (a + 1) % planos.length) }
    if (e.key === 'ArrowUp') { e.preventDefault(); setActivo((a) => (a - 1 + planos.length) % planos.length) }
    if (e.key === 'Enter') { e.preventDefault(); elegir(planos[activo] || planos[0]) }
  }
  const mostrar = abierto && valor.trim().length >= MIN_LETRAS
  let k = -1
  return (
    <div className="mc-buscar" ref={caja}>
      <LuSearch aria-hidden="true" />
      <input type="search" placeholder="Buscar en todas tus secciones…" value={valor} aria-label="Buscar en todas tus secciones"
        role="combobox" aria-expanded={mostrar} aria-controls="mc-buscar-res" aria-autocomplete="list"
        aria-activedescendant={mostrar && planos.length ? `mc-res-${activo}` : undefined}
        onChange={(e) => { onCambiar(e.target.value); setAbierto(true) }} onFocus={() => setAbierto(true)} onKeyDown={tecla} />
      {mostrar && (
        <div className="mc-buscar-res" id="mc-buscar-res" role="listbox" aria-label="Resultados">
          {!grupos.length && <p className="mc-buscar-nada">Nada coincide con “{valor.trim()}” en tus secciones.</p>}
          {grupos.map((g) => (
            <div key={g.id} role="group" aria-label={g.titulo}>
              <h3>{g.titulo}<small>{g.total > g.resultados.length ? `${g.resultados.length} de ${g.total}` : g.total}</small></h3>
              {g.resultados.map((r) => {
                k += 1
                const i = k
                return (
                  <button key={r.id} type="button" id={`mc-res-${i}`} role="option" aria-selected={i === activo} className={i === activo ? 'on' : ''}
                    onMouseEnter={() => setActivo(i)} onClick={() => elegir({ ...r, seccion: g.id })}>
                    <b>{r.titulo}</b>{r.detalle && <small>{r.detalle}</small>}
                  </button>
                )
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

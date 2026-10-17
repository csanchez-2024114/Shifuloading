/* Ficha de un registro (D28): se abre al tocar un cliente, una cita, un pedido… en cualquier vista. Muestra rápido TODO
 * lo que hay de él: sus datos en grupos (los define la persona por chat con cambiar_ficha), lo relacionado de otras
 * secciones y su línea de tiempo. Todo sale de los registros: nada escrito a mano. Panel a la derecha; en móvil, pantalla
 * completa. Se cierra con Esc, con la X o tocando fuera. */
import { useEffect, useRef } from 'react'
import { LuX, LuClock, LuLink } from 'react-icons/lu'
import { ver } from './vistas'
import { camposDe } from './validar'
import { registrosDe } from './datosEjemplo'
import { fichaDe } from './edicion'
import { region } from './regional'

const COLORES = ['#7c5cff', '#22d3a6', '#f5a623', '#f0587a', '#5b8cff', '#a3e635', '#ec4899', '#14b8a6']
const ES_TEXTO = (c) => !['estado', 'fecha', 'hora', 'numero', 'dinero'].includes(c.tipo)
const diasDesdeHoy = (iso) => { const h = new Date(); h.setHours(0, 0, 0, 0); return Math.round((new Date(`${iso}T00:00:00`) - h) / 86400000) }
const relativo = (d) => (d === 0 ? 'hoy' : d === 1 ? 'mañana' : d === -1 ? 'ayer' : d < 0 ? `hace ${-d} días` : `en ${d} días`)

/** Título de un registro: el 1.º campo de su tarjeta o su primer campo de texto. */
export function tituloRegistro(seccion, campos, r) {
  const id = seccion.tarjeta?.campos?.[0] ?? campos.find(ES_TEXTO)?.id ?? campos[0]?.id
  return ver('texto', r.valores[id])
}

/** Lo de otras secciones ligado a este registro: comparten un valor de texto (el mismo nombre, empresa, producto…). */
export function relacionadosDe(plantilla, datos, seccion, r) {
  const porId = Object.fromEntries(plantilla.secciones.map((s) => [s.id, s]))
  const mios = new Set(camposDe(seccion, porId).filter(ES_TEXTO).map((c) => String(r.valores[c.id] ?? '').trim().toLowerCase()).filter((v) => v.length >= 3))
  const fuente = seccion.fuente || seccion.id
  const out = []
  for (const s of plantilla.secciones) {
    if ((s.fuente || s.id) === fuente || s.fuente || !s.campos) continue
    const cs = camposDe(s, porId), textos = cs.filter(ES_TEXTO)
    const items = registrosDe(s, datos).filter((x) => textos.some((c) => mios.has(String(x.valores[c.id] ?? '').trim().toLowerCase())))
    // Su título dentro de la ficha: el primer texto que NO es el que los liga (si no, todos dirían el mismo nombre).
    // Un teléfono o un correo no sirve de título (medido: la visita de Ana López se titulaba «+502 4320 9266»).
    const contacto = (v) => /^[+\d\s()-]{6,}$/.test(String(v).trim()) || /@/.test(String(v))
    const tituloRel = (x) => { const c = textos.find((t) => x.valores[t.id] && !mios.has(String(x.valores[t.id]).trim().toLowerCase()) && !contacto(x.valores[t.id])); return c ? ver('texto', x.valores[c.id]) : tituloRegistro(s, cs, x) }
    if (items.length) out.push({ seccion: s, campos: cs, items, tituloRel })
  }
  return out
}

export default function Ficha({ plantilla, datos, seccionId, registroId, onCerrar, onAbrir, desdeOrigen = false }) {
  const panel = useRef(null)
  const porId = Object.fromEntries(plantilla.secciones.map((s) => [s.id, s]))
  const sec = porId[seccionId]
  const campos = sec ? camposDe(sec, porId) : []
  const r = sec ? registrosDe(sec, datos).find((x) => x.id === registroId) : null
  useEffect(() => {
    panel.current?.focus()
    const esc = (e) => { if (e.key === 'Escape') onCerrar() }
    window.addEventListener('keydown', esc); return () => window.removeEventListener('keydown', esc)
  }, [seccionId, registroId, onCerrar])
  if (!sec || !r) return null
  const f = fichaDe(sec, campos)
  const porCampo = Object.fromEntries(campos.map((c) => [c.id, c]))
  const estado = campos.find((c) => c.tipo === 'estado')
  const rel = f.relacionados || f.linea_tiempo ? relacionadosDe(plantilla, datos, sec, r) : []
  // Línea de tiempo: las fechas del registro y las de lo relacionado, de la más nueva a la más vieja.
  const eventos = !f.linea_tiempo ? [] : [
    ...campos.filter((c) => c.tipo === 'fecha' && r.valores[c.id]).map((c) => ({ iso: r.valores[c.id], texto: c.nombre, de: sec.titulo })),
    ...rel.flatMap(({ seccion: s, campos: cs, items, tituloRel }) => items.flatMap((x) => cs.filter((c) => c.tipo === 'fecha' && x.valores[c.id]).map((c) => ({ iso: x.valores[c.id], texto: `${tituloRel(x)} · ${c.nombre.toLowerCase()}`, de: s.titulo, ir: () => onAbrir(s.id, x.id) })))),
  ].sort((a, b) => b.iso.localeCompare(a.iso)).slice(0, 14)
  return (
    <div className={`pl-ficha-fondo${desdeOrigen ? ' desde-origen' : ''}`} onClick={onCerrar}>
      <aside ref={panel} className="pl-ficha" style={{ viewTransitionName: 'pl-ficha' }} role="dialog" aria-modal="true" aria-label={`Ficha de ${tituloRegistro(sec, campos, r)}`} tabIndex={-1} onClick={(e) => e.stopPropagation()}>
        <header className="pl-ficha-cab">
          <div>
            <small>{sec.titulo}</small>
            <h2>{tituloRegistro(sec, campos, r)}</h2>
            {estado && r.valores[estado.id] && <em className="pl-pildora" style={{ '--c': COLORES[Math.max(0, estado.opciones.indexOf(r.valores[estado.id])) % COLORES.length] }}>{r.valores[estado.id]}</em>}
          </div>
          <button type="button" className="pl-ficha-cerrar" onClick={onCerrar} aria-label="Cerrar ficha"><LuX /></button>
        </header>
        {f.grupos.map((g) => (
          <section key={g.titulo} className="pl-ficha-grupo">
            <h3>{g.titulo}</h3>
            <dl>{g.campos.map((id) => <div key={id}><dt>{porCampo[id].nombre}</dt><dd>{ver(porCampo[id].tipo, r.valores[id])}</dd></div>)}</dl>
          </section>
        ))}
        {f.relacionados && rel.length > 0 && (
          <section className="pl-ficha-grupo">
            <h3><LuLink aria-hidden="true" /> Relacionado</h3>
            {rel.map(({ seccion: s, campos: cs, items, tituloRel }) => (
              <div key={s.id} className="pl-ficha-rel">
                <h4>{s.titulo} <i>{region().numero(items.length)}</i></h4>
                <ul>
                  {items.slice(0, 5).map((x) => {
                    const est = cs.find((c) => c.tipo === 'estado'), fe = cs.find((c) => c.tipo === 'fecha')
                    return (
                      <li key={x.id}><button type="button" onClick={(e) => onAbrir(s.id, x.id, e.currentTarget)}>
                        <b>{tituloRel(x)}</b>
                        <span>{[est && x.valores[est.id], fe && x.valores[fe.id] && relativo(diasDesdeHoy(x.valores[fe.id]))].filter(Boolean).join(' · ')}</span>
                      </button></li>
                    )
                  })}
                  {items.length > 5 && <li className="pl-mas">+{items.length - 5} más</li>}
                </ul>
              </div>
            ))}
          </section>
        )}
        {f.linea_tiempo && eventos.length > 0 && (
          <section className="pl-ficha-grupo">
            <h3><LuClock aria-hidden="true" /> Línea de tiempo</h3>
            <ol className="pl-ficha-tiempo">
              {eventos.map((e, i) => (
                <li key={i} className={diasDesdeHoy(e.iso) > 0 ? 'futuro' : ''}>
                  <time>{relativo(diasDesdeHoy(e.iso))}</time>
                  {e.ir ? <button type="button" onClick={e.ir}>{e.texto}</button> : <span>{e.texto}</span>}
                  <small>{e.de}</small>
                </li>
              ))}
            </ol>
          </section>
        )}
      </aside>
    </div>
  )
}

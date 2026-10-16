/* Banco de estrés de piezas (D37): cada vista y cada gráfica de una plantilla, en 4 tamaños de bloque y con datos extremos
 * (vacío, 1 registro, muchos, nombres larguísimos, nombres de 1 letra). La revisa `servidor/estres.mjs`, que MIDE en el DOM
 * si algo se sale, se corta o queda sin alto. Ruta: /vista?estres=1&plantilla=…&variante=…&tema=… */
import { useMemo } from 'react'
import { Grafico, compatibles } from '../plantillas/graficos'
import { COMPONENTES, AnimarContext } from '../plantillas/vistas'
import { camposDe } from '../plantillas/validar'
import { datosEjemplo, registrosDe } from '../plantillas/datosEjemplo'
import { ESTILOS } from '../plantillas/estilos'
import '@base/crm.css'
import '@base/crm-extra.css'
import '../plantillas/plantillas.css'
import '../plantillas/estilos.css'
import '../plantillas/marca-base.css'

export const TAMANOS_ESTRES = [{ id: 'xs', w: 220, h: 170 }, { id: 's', w: 340, h: 260 }, { id: 'm', w: 520, h: 360 }, { id: 'l', w: 900, h: 380 }]
export const VARIANTES = ['vacio', 'uno', 'pocos', 'muchos', 'largos', 'cortos']

const LARGO = ' con un nombre larguísimo que no cabe en ninguna parte del bloque'
/** La plantilla y los datos de la variante: los textos y las opciones de estado se alargan o se acortan de verdad. */
function preparar(base, variante) {
  const cambiaTexto = variante === 'largos' ? (t) => `${t}${LARGO}` : variante === 'cortos' ? (t) => String(t).slice(0, 1) : null
  const plantilla = !cambiaTexto ? base : { ...base, secciones: base.secciones.map((s) => ({ ...s, titulo: cambiaTexto(s.titulo),
    campos: s.campos?.map((c) => ({ ...c, nombre: cambiaTexto(c.nombre), opciones: c.opciones?.map((o, i) => (variante === 'cortos' ? `${o.slice(0, 1)}${i}` : cambiaTexto(o))) })) })) }
  const nivel = variante === 'muchos' ? 'muchos' : variante === 'vacio' ? 'vacio' : 'pocos'
  const datos = datosEjemplo(base, nivel)
  if (variante === 'uno') for (const k of Object.keys(datos.registros)) datos.registros[k] = datos.registros[k].slice(0, 1)
  if (cambiaTexto) {
    for (const s of base.secciones) {
      const lista = datos.registros[s.id]; if (!lista || !s.campos) continue
      const nueva = plantilla.secciones.find((x) => x.id === s.id)
      for (const r of lista) for (const c of s.campos) {
        const v = r.valores[c.id]
        if (c.tipo === 'estado') { const i = c.opciones.indexOf(v); r.valores[c.id] = nueva.campos.find((x) => x.id === c.id).opciones[i] }
        else if (typeof v === 'string' && !['fecha', 'hora'].includes(c.tipo)) r.valores[c.id] = cambiaTexto(v)
      }
    }
  }
  return { plantilla, datos }
}

/** Opciones razonables para cada vista con los campos que hay (las mismas que usaría la IA). */
function vistasPara(campos) {
  const de = (t) => campos.find((c) => c.tipo === t)?.id
  const textos = campos.filter((c) => !['estado', 'fecha', 'hora', 'numero', 'dinero'].includes(c.tipo)).map((c) => c.id)
  const titulo = textos[0] || campos[0]?.id, detalle = textos[1]
  const out = [{ vista: 'tabla', opciones: {} }, { vista: 'kpis', opciones: { por: de('estado'), hoy: de('fecha') } }]
  if (de('estado')) out.push({ vista: 'tablero', opciones: { por: de('estado'), titulo, detalle } })
  if (de('fecha')) out.push({ vista: 'agenda', opciones: { fecha: de('fecha'), hora: de('hora'), titulo, detalle, dias: 7 } })
  if (de('fecha')) out.push({ vista: 'vencimientos', opciones: { fecha: de('fecha'), titulo, detalle, grupos: [7, 30] } })
  return out
}

export default function Estres({ plantilla: base, variante = 'pocos', tema = 'oscuro', estilo = 'vivo-compacto' }) {
  const { plantilla, datos } = useMemo(() => preparar(base, variante), [base, variante])
  const porId = Object.fromEntries(plantilla.secciones.map((s) => [s.id, s]))
  const def = ESTILOS.find((e) => e.id === estilo) || ESTILOS[0]
  const piezas = []
  for (const s of plantilla.secciones.filter((x) => x.campos?.length && !x.fuente)) {
    const campos = camposDe(s, porId), registros = registrosDe(s, datos)
    for (const v of vistasPara(campos)) piezas.push({ id: `${s.id}:${v.vista}`, titulo: `${v.vista} · ${s.titulo}`, el: (() => { const V = COMPONENTES[v.vista]; return <V seccion={s} campos={campos} registros={registros} opciones={v.opciones} datos={datos} /> })() })
    for (const g of compatibles(campos)) piezas.push({ id: `${s.id}:grafico:${g.id}`, titulo: `${g.nombre} · ${s.titulo}`, el: <Grafico tipo={g.id} seccion={s} campos={campos} registros={registros} opciones={g.opciones} /> })
  }
  return (
    <AnimarContext.Provider value={false}>
      <div className="mc pl estres" data-tema={tema} data-estilo={def.base} data-densidad={def.densidad} style={{ '--acento': '#22d3a6', minHeight: '100vh', overflow: 'auto', padding: 16 }}>
        <p className="estres-cab" style={{ color: 'var(--tx)' }}>Estrés · {base.id} · {variante} · {piezas.length} piezas × {TAMANOS_ESTRES.length} tamaños</p>
        {piezas.map((p) => (
          <div key={p.id} style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-start', marginBottom: 16 }}>
            {TAMANOS_ESTRES.map((t) => (
              <section key={t.id} className="pl-bloque" data-estres={`${p.id}@${t.id}`} style={{ width: t.w, height: t.h, overflow: 'hidden', boxSizing: 'border-box', containerType: 'size', display: 'flex', flexDirection: 'column' }}>
                <h2>{p.titulo}</h2>
                <div className="estres-cuerpo" style={{ flex: 1, minHeight: 0, position: 'relative' }}>{p.el}</div>
              </section>
            ))}
          </div>
        ))}
      </div>
    </AnimarContext.Provider>
  )
}

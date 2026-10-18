/* Datos a mano (D56): agregar, editar y borrar registros como en cualquier CRM. El diseño y la estructura siguen solo por
 * chat. Mismo HTML y mismas clases que FormFila y ConfirmaBorrar del CRM de Carlos (CrmPage.jsx, estilos en crm-extra.css),
 * para que se vea igual y pasarlo a su proyecto sea directo (D58). La validación NO se repite aquí: lo que se guarda pasa por
 * el mismo código que usa el chat (registros.js: fechas, montos, opciones, campo obligatorio). */
import { useState } from 'react'

/** El texto de error del código está escrito para el modelo («pregúntale…»); a la persona se le muestra solo el problema. */
export const paraPersona = (t) => {
  const s = String(t || '').replace(/^ERROR:\s*/, '').split(/[:;.]\s*(?=preg[uú]nta|dile|d[ií]selo|dilo|si quiere|usa |no lo)/i)[0].trim()
  return s ? `${s[0].toUpperCase()}${s.slice(1)}${/[.!?]$/.test(s) ? '' : '.'}` : 'No se pudo guardar.'
}

/** Lo que muestra el campo para editar: fechas y horas en el formato de su control; números sin formato. */
const aCampo = (c, v) => (v === undefined || v === null ? '' : String(v))

/** Formulario de un registro: un control por campo según su tipo. onGuardar(valores) devuelve el error (texto) o null. */
export function FormRegistro({ titulo, campos, inicial = {}, obligatorio, onGuardar, onCancelar, guardar = 'Guardar' }) {
  const [vals, setVals] = useState(() => Object.fromEntries(campos.map((c) => [c.id, aCampo(c, inicial[c.id])])))
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)
  const poner = (id, v) => setVals((x) => ({ ...x, [id]: v }))
  const enviar = async (e) => {
    e.preventDefault()
    if (obligatorio && !String(vals[obligatorio.id] || '').trim()) { setError(`Falta ${obligatorio.nombre}.`); return }
    setEnviando(true); const err = await onGuardar(vals); setEnviando(false)
    if (err) setError(paraPersona(err))
  }
  return (
    <form className="mc-form-registro" onSubmit={enviar} noValidate>
      {titulo && <h3 className="mc-form-titulo">{titulo}</h3>}
      {campos.map((c, k) => (
        <label key={c.id}>{c.nombre}{obligatorio?.id === c.id ? ' *' : ''}
          {c.tipo === 'estado'
            ? (
              <select value={vals[c.id]} onChange={(e) => poner(c.id, e.target.value)}>
                <option value="">Elegir…</option>
                {(c.opciones || []).map((o) => <option key={o} value={o}>{o}</option>)}
              </select>
            )
            : (
              <input type={c.tipo === 'fecha' ? 'date' : c.tipo === 'hora' ? 'time' : 'text'} inputMode={['numero', 'dinero'].includes(c.tipo) ? 'decimal' : undefined}
                maxLength={200} autoFocus={k === 0} value={vals[c.id]} onChange={(e) => poner(c.id, e.target.value)} />
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

/** «¿Eliminar?» hasta que la persona confirma o se arrepiente. A diferencia del CRM de Carlos, aquí sí se puede deshacer
 * (punto de deshacer, como todo lo demás): se dice la verdad. */
export function ConfirmaBorrar({ que, onSi, onNo }) {
  const [haciendo, setHaciendo] = useState(false)
  return (
    <div className="mc-fila mc-fila-confirma" role="alertdialog" aria-label={`Confirmar que se elimina ${que}`}>
      <span>¿Eliminar {que}? Si te arrepientes, dile «deshaz» a Shifu.</span>
      <span className="mc-confirma-acc">
        <button type="button" className="mc-peligro mc-chico" disabled={haciendo} onClick={async () => { setHaciendo(true); await onSi(); setHaciendo(false) }}>{haciendo ? 'Eliminando…' : 'Sí, eliminar'}</button>
        <button type="button" className="mc-link" disabled={haciendo} onClick={onNo}>No</button>
      </span>
    </div>
  )
}

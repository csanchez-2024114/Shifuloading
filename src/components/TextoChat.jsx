import { Fragment } from 'react'

// Formato mínimo para los mensajes de Shifu: **negrita**, listas con "- " o "1.", tablas con "|" y saltos de línea.
// Se arma con elementos de React (nunca con HTML en bruto), así que un texto raro no puede meter código en la página.

function enLinea(texto) {
  return texto.split(/(\*\*[^*]+\*\*)/g).map((p, i) => (p.startsWith('**') && p.endsWith('**') && p.length > 4 ? <strong key={i}>{p.slice(2, -2)}</strong> : <Fragment key={i}>{p}</Fragment>))
}

const celdas = (l) => l.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim())
const esFilaTabla = (l) => /^\s*\|.*\|\s*$/.test(l)
const esSeparador = (l) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(l)

export function bloques(texto) {
  const lineas = String(texto || '').replace(/\r/g, '').split('\n')
  const salida = []
  let i = 0
  while (i < lineas.length) {
    const l = lineas[i]
    if (!l.trim()) { i += 1; continue }
    if (esFilaTabla(l)) {
      const filas = []
      while (i < lineas.length && esFilaTabla(lineas[i])) { if (!esSeparador(lineas[i])) filas.push(celdas(lineas[i])); i += 1 }
      if (filas.length) salida.push({ tipo: 'tabla', cab: filas[0], filas: filas.slice(1) })
      continue
    }
    const vineta = /^\s*[-•*]\s+(.*)$/.exec(l)
    const numero = /^\s*\d+[.)]\s+(.*)$/.exec(l)
    if (vineta || numero) {
      const ordenada = Boolean(numero)
      const items = []
      while (i < lineas.length) {
        const m = (ordenada ? /^\s*\d+[.)]\s+(.*)$/ : /^\s*[-•*]\s+(.*)$/).exec(lineas[i])
        if (!m) break
        items.push(m[1]); i += 1
      }
      salida.push({ tipo: ordenada ? 'ol' : 'ul', items })
      continue
    }
    const parrafo = []
    while (i < lineas.length && lineas[i].trim() && !esFilaTabla(lineas[i]) && !/^\s*([-•*]|\d+[.)])\s+/.test(lineas[i])) { parrafo.push(lineas[i]); i += 1 }
    salida.push({ tipo: 'p', lineas: parrafo })
  }
  return salida
}

export default function TextoChat({ texto }) {
  return (
    <>
      {bloques(texto).map((b, k) => {
        if (b.tipo === 'p') return <span key={k} className="tc-p">{b.lineas.map((x, j) => <Fragment key={j}>{j > 0 && <br />}{enLinea(x)}</Fragment>)}</span>
        if (b.tipo === 'ul' || b.tipo === 'ol') {
          const Lista = b.tipo
          return <Lista key={k} className="tc-lista">{b.items.map((x, j) => <li key={j}>{enLinea(x)}</li>)}</Lista>
        }
        return (
          <div key={k} className="tc-tabla-caja">
            <table className="tc-tabla">
              <thead><tr>{b.cab.map((c, j) => <th key={j}>{enLinea(c)}</th>)}</tr></thead>
              <tbody>{b.filas.map((f, j) => <tr key={j}>{f.map((c, n) => <td key={n}>{enLinea(c)}</td>)}</tr>)}</tbody>
            </table>
          </div>
        )
      })}
    </>
  )
}

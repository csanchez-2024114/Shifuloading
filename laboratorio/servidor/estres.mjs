/* Banco de estrés de piezas (D37). Abre /vista?estres=1 para cada plantilla × variante de datos × tema en Chrome sin
 * ventana y MIDE en el DOM, pieza por pieza y tamaño por tamaño:
 *  - desborde: algo visible se sale del bloque a lo ancho (más de 2 px)
 *  - cortado:  el contenido es más alto que el bloque y no tiene su propio scroll
 *  - texto:    un texto se corta (scrollWidth > clientWidth) sin "…" ni salto de línea
 *  - sin-alto: un SVG o lienzo de la pieza mide menos de 8 px de alto
 * Uso (desde la raíz de Shifuloading): node laboratorio/servidor/estres.mjs [plantilla,…] [variante,…] [tema,…] > salida.json
 * Imprime un resumen en stderr y el detalle en JSON por stdout. */
import { spawn } from 'node:child_process'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const BASE = process.env.LAB_URL || 'http://localhost:5190'
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
import { readdirSync } from 'node:fs'
// Todo el material de partida: las 6 iniciales, las estructuras por sector y cada pestaña de la biblioteca.
const deCarpeta = (d, pre = '') => readdirSync(`laboratorio/src/plantillas/${d}`).filter((f) => f.endsWith('.js')).map((f) => pre + f.replace(/\.js$/, ''))
const TODAS = ['embudo', 'agenda', 'pedidos', 'membresias', 'proyectos', 'simple', ...deCarpeta('biblioteca'), ...deCarpeta('biblioteca-pestanas', 'pestana-')]
const [pl = '', va = '', te = ''] = process.argv.slice(2)
const plantillas = pl ? pl.split(',') : TODAS
const variantes = va ? va.split(',') : ['vacio', 'uno', 'pocos', 'muchos', 'largos', 'cortos']
const temas = te ? te.split(',') : ['oscuro']
const espera = (ms) => new Promise((r) => setTimeout(r, ms))

// Se ejecuta DENTRO de la página: devuelve un resultado por bloque [data-estres].
const MEDIR = `(() => {
  const out = []
  for (const b of document.querySelectorAll('[data-estres]')) {
    const caja = b.getBoundingClientRect(), fallas = []
    const cuerpo = b.querySelector('.estres-cuerpo')
    for (const el of b.querySelectorAll('*')) {
      const cs = getComputedStyle(el); if (cs.visibility === 'hidden' || cs.display === 'none' || cs.opacity === '0') continue
      const r = el.getBoundingClientRect(); if (!r.width || !r.height) continue
      // Lo que queda dentro de un contenedor con scroll o recorte (dentro del bloque) no se sale: se recorta o se desplaza.
      let recorta = false
      for (let a = el.parentElement; a && a !== b; a = a.parentElement) { const o = getComputedStyle(a).overflowX; if (o !== 'visible') { recorta = true; break } }
      const invisible = el.classList?.contains('gr-hit') || (el instanceof SVGElement && ['none', 'transparent', 'rgba(0, 0, 0, 0)'].includes(cs.fill) && ['none', 'rgba(0, 0, 0, 0)'].includes(cs.stroke) && !el.children.length)
      if (!recorta && !invisible && (r.right > caja.right + 2 || r.left < caja.left - 2)) { fallas.push({ tipo: 'desborde', el: el.tagName.toLowerCase() + '.' + (el.className?.baseVal ?? el.className ?? '').toString().split(' ')[0], px: Math.round(Math.max(r.right - caja.right, caja.left - r.left)) }); continue }
      const tieneTexto = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim())
      if (tieneTexto && el.scrollWidth > el.clientWidth + 1 && cs.overflowX !== 'visible' && cs.textOverflow !== 'ellipsis' && cs.whiteSpace === 'nowrap') fallas.push({ tipo: 'texto', el: el.tagName.toLowerCase(), t: el.textContent.slice(0, 30) })
    }
    // Encimado y palabra partida: se mide cada texto con Range (su caja real, línea por línea).
    const textos = []
    const tw = document.createTreeWalker(b, NodeFilter.SHOW_TEXT)
    for (let n = tw.nextNode(); n && textos.length < 400; n = tw.nextNode()) {
      if (!n.textContent.trim() || n.parentElement.closest('svg, h2, [aria-hidden="true"]')) continue
      const cs = getComputedStyle(n.parentElement); if (cs.visibility === 'hidden' || cs.opacity === '0') continue
      const rg = document.createRange(); rg.selectNodeContents(n)
      const lineas = [...rg.getClientRects()].filter((x) => x.width > 1)
      // La caja visible de cada línea: recortada por los contenedores con overflow (un texto con "…" no invade al vecino).
      const recortes = []; for (let e = n.parentElement; e && e !== b.parentElement; e = e.parentElement) if (getComputedStyle(e).overflow !== 'visible') recortes.push(e.getBoundingClientRect())
      for (const l of lineas) { let x = { left: l.left, right: l.right, top: l.top, bottom: l.bottom }; for (const r of recortes) x = { left: Math.max(x.left, r.left), right: Math.min(x.right, r.right), top: Math.max(x.top, r.top), bottom: Math.min(x.bottom, r.bottom) }; if (x.right - x.left > 1 && x.bottom - x.top > 1) textos.push({ x, n }) }
      // Palabra partida: una palabra (de 4+ letras) que quedó repartida en 2 líneas. El corte después de un guion
      // («e-commerce», «FAC-2024-089») es tipografía normal: el guion separa palabras.
      if (lineas.length > 1 && !fallas.some((f) => f.tipo === 'partida')) {
        const t = n.textContent; let i = 0
        for (const w of t.split(/(\\s+|-)/)) { if (w.trim().length >= 4) { const r2 = document.createRange(); r2.setStart(n, i); r2.setEnd(n, i + w.length); const rs = [...r2.getClientRects()].filter((x) => x.width > 1); if (rs.length > 1 && Math.abs(rs[0].top - rs[rs.length - 1].top) > 2) { fallas.push({ tipo: 'partida', t: w.slice(0, 20) }); break } } i += w.length }
      }
    }
    for (let i = 0; i < textos.length && !fallas.some((f) => f.tipo === 'encimado'); i++) for (let j = i + 1; j < textos.length; j++) {
      const a = textos[i], c = textos[j]; if (a.n === c.n) continue
      const ix = Math.min(a.x.right, c.x.right) - Math.max(a.x.left, c.x.left), iy = Math.min(a.x.bottom, c.x.bottom) - Math.max(a.x.top, c.x.top)
      if (ix > 3 && iy > 3) {
        // Solo cuenta si ambos se ven (no recortados por un contenedor).
        fallas.push({ tipo: 'encimado', t: a.n.textContent.slice(0, 20) + ' / ' + c.n.textContent.slice(0, 20) }); break
      }
    }
    // Cortado: el contenido pide más alto que el bloque y nadie dentro hace scroll.
    if (cuerpo && cuerpo.scrollHeight > cuerpo.clientHeight + 4) {
      const conScroll = [...cuerpo.querySelectorAll('*')].some((el) => ['auto', 'scroll'].includes(getComputedStyle(el).overflowY) && el.scrollHeight > el.clientHeight)
      if (!conScroll) fallas.push({ tipo: 'cortado', px: cuerpo.scrollHeight - cuerpo.clientHeight })
    }
    for (const g of b.querySelectorAll('svg, canvas')) { const r = g.getBoundingClientRect(); if (r.width > 0 && r.height < 8 && !g.closest('button, i, .pl-ico')) { fallas.push({ tipo: 'sin-alto', h: Math.round(r.height) }); break } }
    // Una falla por tipo basta para el informe.
    const vistas = new Set(); out.push({ id: b.dataset.estres, fallas: fallas.filter((f) => !vistas.has(f.tipo) && vistas.add(f.tipo)) })
  }
  return out
})()`

async function abrirChrome(puerto) {
  const perfil = join(tmpdir(), `estres-perfil-${puerto}`)
  const chrome = spawn(CHROME, [`--remote-debugging-port=${puerto}`, `--user-data-dir=${perfil}`, '--headless=new', '--no-first-run', '--hide-scrollbars', '--window-size=1500,1000', 'about:blank'], { stdio: 'ignore' })
  let ws
  for (let i = 0; i < 60 && !ws; i++) { try { const l = await (await fetch(`http://127.0.0.1:${puerto}/json/list`)).json(); const p = l.find((x) => x.type === 'page'); if (p) ws = new WebSocket(p.webSocketDebuggerUrl) } catch { await espera(200) } }
  await new Promise((r) => ws.addEventListener('open', r, { once: true }))
  let id = 0; const pend = new Map(); const errores = []
  ws.addEventListener('message', (e) => {
    const m = JSON.parse(e.data)
    if (m.id && pend.has(m.id)) { pend.get(m.id)(m.result); pend.delete(m.id) }
    if (m.method === 'Runtime.exceptionThrown') errores.push(m.params.exceptionDetails.exception?.description?.slice(0, 160))
  })
  const cmd = (method, params = {}) => new Promise((ok) => { const i = ++id; pend.set(i, ok); ws.send(JSON.stringify({ id: i, method, params })) })
  await cmd('Page.enable'); await cmd('Runtime.enable')
  await cmd('Emulation.setDeviceMetricsOverride', { width: 1500, height: 1000, deviceScaleFactor: 1, mobile: false })
  return { cmd, errores, cerrar: () => { ws.close(); chrome.kill() } }
}

const { cmd, errores, cerrar } = await abrirChrome(9311)
const resultado = []
for (const p of plantillas) for (const v of variantes) for (const t of temas) {
  errores.length = 0
  await cmd('Page.navigate', { url: `${BASE}/vista?estres=1&plantilla=${p}&variante=${v}&tema=${t}` })
  await espera(2500)
  const r = await cmd('Runtime.evaluate', { expression: MEDIR, returnByValue: true })
  const bloques = r?.result?.value || []
  const malos = bloques.filter((b) => b.fallas.length)
  resultado.push({ plantilla: p, variante: v, tema: t, total: bloques.length, malos: malos.length, excepciones: [...errores], fallas: malos })
  process.stderr.write(`${p.padEnd(11)} ${v.padEnd(7)} ${t.padEnd(6)} ${String(bloques.length - malos.length).padStart(4)}/${String(bloques.length).padEnd(4)} ok${errores.length ? `  ⚠ ${errores.length} excepciones` : ''}\n`)
}
cerrar()
const tot = resultado.reduce((s, r) => s + r.total, 0), mal = resultado.reduce((s, r) => s + r.malos, 0)
const porTipo = {}
for (const r of resultado) for (const b of r.fallas) for (const f of b.fallas) porTipo[f.tipo] = (porTipo[f.tipo] || 0) + 1
process.stderr.write(`\nTOTAL ${tot - mal}/${tot} piezas×tamaño sin fallas (${((100 * (tot - mal)) / (tot || 1)).toFixed(1)} %) · por tipo: ${JSON.stringify(porTipo)}\n`)
console.log(JSON.stringify(resultado, null, 1))

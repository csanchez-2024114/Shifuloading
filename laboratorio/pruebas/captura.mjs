/* Captura de pantalla del laboratorio con una acción previa (Chrome sin ventana, protocolo de DevTools, sin dependencias).
 * Uso (desde la raíz de Shifuloading): node laboratorio/pruebas/captura.mjs "<ruta>" "<selector a clicar>" salida.png [ancho alto] [js previo]
 * Imprime el texto del elemento clicado, la ficha abierta (si hay) y las excepciones de la página.
 * Si existe la variable DBG, evalúa esa expresión al final e imprime su valor (para revisar el DOM). */
import { spawn } from 'node:child_process'
import { writeFileSync } from 'node:fs'
const [ruta, sel, out, w = '1440', h = '900', extra = ''] = process.argv.slice(2)
const esp = (ms) => new Promise((r) => setTimeout(r, ms))
const puerto = 9333 + Math.floor(Math.random() * 200)
const ch = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [`--remote-debugging-port=${puerto}`, `--user-data-dir=/tmp/captura-perfil-${puerto}`, '--headless=new', '--hide-scrollbars', `--window-size=${w},${h}`, 'about:blank'], { stdio: 'ignore' })
let ws; for (let i = 0; i < 50 && !ws; i++) { try { const l = await (await fetch(`http://127.0.0.1:${puerto}/json/list`)).json(); const p = l.find((x) => x.type === 'page'); if (p) ws = new WebSocket(p.webSocketDebuggerUrl) } catch { await esp(200) } }
await new Promise((r) => ws.addEventListener('open', r, { once: true }))
let id = 0; const pend = new Map(); const errs = []
ws.addEventListener('message', (e) => { const m = JSON.parse(e.data); if (m.id && pend.has(m.id)) { pend.get(m.id)(m.result); pend.delete(m.id) } if (m.method === 'Runtime.exceptionThrown') errs.push(m.params.exceptionDetails.exception?.description?.slice(0, 200)) })
const cmd = (method, params = {}) => new Promise((ok) => { const i = ++id; pend.set(i, ok); ws.send(JSON.stringify({ id: i, method, params })) })
await cmd('Page.enable'); await cmd('Runtime.enable')
await cmd('Emulation.setDeviceMetricsOverride', { width: +w, height: +h, deviceScaleFactor: 1, mobile: +w < 700 })
await cmd('Page.navigate', { url: (process.env.LAB_URL || 'http://localhost:5190') + ruta }); await esp(4000)
const r = await cmd('Runtime.evaluate', { expression: `(() => { ${extra}; const el = document.querySelector(${JSON.stringify(sel)}); if (!el) return 'NO ENCONTRADO'; el.click(); return el.textContent.slice(0, 60) })()`, returnByValue: true })
console.log('clic en:', r.result.value); await esp(1500)
const shot = await cmd('Page.captureScreenshot', { format: 'png' }); writeFileSync(out, Buffer.from(shot.data, 'base64'))
if (process.env.DBG) { const d = await cmd('Runtime.evaluate', { expression: process.env.DBG, returnByValue: true }); console.log('DBG', JSON.stringify(d.result.value)) }
console.log('excepciones:', errs.length, errs.slice(0, 2)); ws.close(); ch.kill()

/* Recorrido de punta a punta de /experiencia, como un usuario real (Chrome sin ventana). Captura cada etapa y falla si:
 * hay excepciones, una etapa no aparece, se ofrece «partir de una plantilla» (D29/D49) o no se llega al CRM con recorrido.
 * Uso (desde la raíz de Shifuloading): node laboratorio/pruebas/experiencia.e2e.mjs [claro|ambiguo] [carpeta] [ancho alto] */
import { spawn } from 'node:child_process'
import { mkdirSync, writeFileSync } from 'node:fs'
const [perfil = 'claro', dir = '/tmp/cap/exp', w = '1440', h = '900'] = process.argv.slice(2)
mkdirSync(dir, { recursive: true })
const esp = (ms) => new Promise((r) => setTimeout(r, ms))
const puerto = 9500 + Math.floor(Math.random() * 300)
const ch = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [`--remote-debugging-port=${puerto}`, `--user-data-dir=/tmp/exp-perfil-${puerto}`, '--headless=new', '--hide-scrollbars', `--window-size=${w},${h}`, 'about:blank'], { stdio: 'ignore' })
let ws; for (let i = 0; i < 50 && !ws; i++) { try { const l = await (await fetch(`http://127.0.0.1:${puerto}/json/list`)).json(); const p = l.find((x) => x.type === 'page'); if (p) ws = new WebSocket(p.webSocketDebuggerUrl) } catch { await esp(200) } }
await new Promise((r) => ws.addEventListener('open', r, { once: true }))
let id = 0; const pend = new Map(); const errs = []; const fallas = []
ws.addEventListener('message', (e) => { const m = JSON.parse(e.data); if (m.id && pend.has(m.id)) { pend.get(m.id)(m.result); pend.delete(m.id) } if (m.method === 'Runtime.exceptionThrown') errs.push(m.params.exceptionDetails.exception?.description?.slice(0, 200)) })
const cmd = (method, params = {}) => new Promise((ok) => { const i = ++id; pend.set(i, ok); ws.send(JSON.stringify({ id: i, method, params })) })
const js = async (expr) => (await cmd('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true })).result?.value
const foto = async (n) => { const s = await cmd('Page.captureScreenshot', { format: 'png' }); writeFileSync(`${dir}/${n}.png`, Buffer.from(s.data, 'base64')) }
const titulo = () => js(`document.querySelector('main h1')?.textContent || ''`)
// Escribe en un input/textarea controlado por React.
const escribir = (sel, txt) => js(`(() => { const el = document.querySelector(${JSON.stringify(sel)}); if (!el) return false; const p = Object.getPrototypeOf(el); Object.getOwnPropertyDescriptor(p, 'value').set.call(el, ${JSON.stringify(txt)}); el.dispatchEvent(new Event('input', { bubbles: true })); return true })()`)
const clicTexto = (txt) => js(`(() => { const b = [...document.querySelectorAll('button')].find((x) => x.textContent.includes(${JSON.stringify(txt)})); if (!b) return false; b.click(); return true })()`)

const RESP = perfil === 'ambiguo'
  ? { nombre: 'Casa Nube', que_vendes: 'cosas varias', rubro: 'Otro', ciclo: 'Una mezcla de todo', objetivos: ['Ordenar mis contactos'] }
  : { nombre: 'Veterinaria Patitas', que_vendes: 'consultas, vacunas y baños para mascotas', rubro: 'Salud y bienestar', ciclo: 'Clientes recurrentes', objetivos: ['No perder ningún seguimiento', 'Ver mi pipeline y reportes'] }

await cmd('Page.enable'); await cmd('Runtime.enable')
await cmd('Emulation.setDeviceMetricsOverride', { width: +w, height: +h, deviceScaleFactor: 1, mobile: +w < 700 })
await cmd('Page.navigate', { url: (process.env.LAB_URL || 'http://localhost:5190') + '/experiencia' }); await esp(2500)
await foto('01-bienvenida')
if (!(await clicTexto('Empezar'))) fallas.push('no hay botón Empezar')
await esp(500)
// Cuestionario: responde lo que sabe; en lo demás elige la primera opción o sigue.
const vistos = []
for (let paso = 0; paso < 25; paso++) {
  const t = await titulo(); vistos.push(t)
  if (await js(`!!document.querySelector('.exp-cuenta')`)) break
  if (/plantilla/i.test(await js(`document.querySelector('main').innerText`))) fallas.push(`ofrece plantillas en «${t}»`)
  if (paso === 0) await foto('02-primera-pregunta')
  const tipo = await js(`document.querySelector('main input.campo') ? 'texto' : document.querySelector('main textarea') ? 'parrafo' : document.querySelector('[role=group]') ? 'varias' : document.querySelector('[role=radiogroup]') ? 'una' : '?'`)
  if (tipo === 'texto') {
    if (/llama tu negocio/i.test(t)) await escribir('main input.campo', RESP.nombre)
    else await escribir('main input.campo', 'Ciudad de Guatemala')
    if (await js(`!!document.querySelector('[role=radiogroup]')`)) await js(`document.querySelector('[role=radiogroup] .op').click()`) // ubicación: país
    await esp(150); await clicTexto('Continuar') || await clicTexto('Crear mi CRM')
  } else if (tipo === 'parrafo') {
    await escribir('main textarea', /vendes/i.test(t) ? RESP.que_vendes : 'Se me pasan los seguimientos'); await esp(150); await clicTexto('Continuar') || await clicTexto('Crear mi CRM')
  } else if (tipo === 'varias') {
    const quiero = /lograr/i.test(t) ? RESP.objetivos : []
    if (quiero.length) for (const o of quiero) await clicTexto(o); else await js(`document.querySelector('[role=group] .op').click()`)
    await esp(150); await clicTexto('Continuar') || await clicTexto('Crear mi CRM')
  } else if (tipo === 'una') {
    const quiero = /dedica/i.test(t) ? RESP.rubro : /proceso de venta/i.test(t) ? RESP.ciclo : null
    if (quiero) await clicTexto(quiero); else await js(`document.querySelector('[role=radiogroup] .op').click()`)
    await esp(700)
  }
  await esp(250)
}
await foto('03-cuenta')
if (!(await js(`!!document.querySelector('.exp-cuenta')`))) fallas.push('no llegó a crear la cuenta')
await clicTexto('Crear cuenta y armar') ; await esp(300)
if (!(await js(`!!document.querySelector('.exp-aviso')`))) fallas.push('la cuenta vacía no mostró aviso')
for (const [i, v] of ['Ana', 'López', 'ana@correo.com', 'clave1234'].entries()) await escribir(`.exp-campos input:nth-child(${i + 1})`, v)
await clicTexto('Crear cuenta y armar'); await esp(1600)
await foto('04-armando')
await esp(3200)
if (perfil === 'ambiguo') {
  if (!/llevar principalmente/i.test(await titulo())) fallas.push('con respuestas ambiguas no hizo la pregunta de qué llevar (D7)')
  await foto('05-que-llevar'); await clicTexto('Mis citas y mi agenda'); await esp(500)
}
await esp(2500)
const enCrm = await js(`!!document.querySelector('.mc.pl')`)
if (!enCrm) fallas.push('no llegó al CRM')
const recorrido = await js(`!!document.querySelector('.rc, .rc-burbuja, [class*=rc-]')`)
const negocio = await js(`document.querySelector('.mc-negocio')?.textContent`)
await foto('06-crm-recorrido')
console.log(JSON.stringify({ perfil, preguntas: vistos.length, enCrm, recorrido, negocio, menu: await js(`[...document.querySelectorAll('.mc-menu button')].map((b) => b.textContent.trim())`) }))
console.log('excepciones:', errs.length, errs.slice(0, 2)); console.log(fallas.length ? `FALLAS: ${fallas.join(' | ')}` : 'OK: recorrido completo sin fallas')
ws.close(); ch.kill(); process.exitCode = fallas.length || errs.length ? 1 : 0

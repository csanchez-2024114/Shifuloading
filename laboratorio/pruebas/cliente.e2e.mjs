/* Cliente exigente: recorre /experiencia como alguien que PAGA por el CRM y captura cada paso (más un video), para
 * revisarlo cuadro por cuadro con ojo crítico. En cada paso mide lo que se ve mal sin opinar: excepciones, errores de
 * consola, desborde horizontal de la página y botones fuera de la pantalla.
 *  - Fase 1 (sin IA): registro, «Shifu arma tu CRM», recorrido, cada pestaña, una ficha, «Agregar», elegir una pieza.
 *  - Fase 2 (--ia): pedidos complejos al chat real (datos, estructura, diseño, preguntas, cosas que no existen, deshacer);
 *    guarda lo que dijo y la línea «Cambios:» que arma el código, para comparar con la pantalla.
 * Uso (desde la raíz de Shifuloading): node laboratorio/pruebas/cliente.e2e.mjs <carpeta> [ancho alto] [--ia] [--ejemplos] */
import { spawn, execFileSync } from 'node:child_process'
import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
const args = process.argv.slice(2)
const conIA = args.includes('--ia'), mantenerEjemplos = args.includes('--ejemplos')
const [dir = '/tmp/cliente', w = '1440', h = '900'] = args.filter((a) => !a.startsWith('--'))
const movil = +w < 700
mkdirSync(join(dir, 'cuadros'), { recursive: true })
const esp = (ms) => new Promise((r) => setTimeout(r, ms))
const puerto = 9600 + Math.floor(Math.random() * 300)
const ch = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [`--remote-debugging-port=${puerto}`, `--user-data-dir=/tmp/cliente-perfil-${puerto}`, '--headless=new', '--hide-scrollbars', `--window-size=${w},${h}`, 'about:blank'], { stdio: 'ignore' })
let ws; for (let i = 0; i < 50 && !ws; i++) { try { const l = await (await fetch(`http://127.0.0.1:${puerto}/json/list`)).json(); const p = l.find((x) => x.type === 'page'); if (p) ws = new WebSocket(p.webSocketDebuggerUrl) } catch { await esp(200) } }
await new Promise((r) => ws.addEventListener('open', r, { once: true }))
let id = 0; const pend = new Map(); const t0 = Date.now(); const cuadros = []; const eventos = []; const llamadas = new Map()
const ts = () => ((Date.now() - t0) / 1000).toFixed(1)
ws.addEventListener('message', (e) => {
  const m = JSON.parse(e.data)
  if (m.id && pend.has(m.id)) { pend.get(m.id)(m.result); pend.delete(m.id) }
  if (m.method === 'Page.screencastFrame') { cuadros.push({ t: (Date.now() - t0) / 1000, data: m.params.data }); ws.send(JSON.stringify({ id: ++id, method: 'Page.screencastFrameAck', params: { sessionId: m.params.sessionId } })) }
  if (m.method === 'Runtime.exceptionThrown') eventos.push(`${ts()}s EXCEPCIÓN ${m.params.exceptionDetails.exception?.description?.slice(0, 220)}`)
  // Cada llamada al chat (lo que se mandó y lo que volvió) para repetir el caso real exacto al diagnosticar.
  if (m.method === 'Network.requestWillBeSent' && m.params.request.url.includes('/api/lab/chat')) llamadas.set(m.params.requestId, { cuerpo: JSON.parse(m.params.request.postData || 'null') })
  if (m.method === 'Network.loadingFinished' && llamadas.has(m.params.requestId)) cmd('Network.getResponseBody', { requestId: m.params.requestId }).then((r) => { try { llamadas.get(m.params.requestId).respuesta = JSON.parse(r?.body || 'null') } catch { /* sin cuerpo */ } })
  if (m.method === 'Runtime.consoleAPICalled' && ['error', 'warning'].includes(m.params.type)) eventos.push(`${ts()}s CONSOLA ${m.params.type}: ${m.params.args.map((a) => a.value ?? a.description).join(' ').slice(0, 220)}`)
})
const cmd = (method, params = {}) => new Promise((ok) => { const i = ++id; pend.set(i, ok); ws.send(JSON.stringify({ id: i, method, params })) })
const js = async (expr) => (await cmd('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true })).result?.value
const pasos = []
let n = 0
/** Captura + mediciones del paso. */
async function paso(nombre, nota = '') {
  const nom = `${String(++n).padStart(2, '0')}-${nombre}`
  const s = await cmd('Page.captureScreenshot', { format: 'png' }); writeFileSync(join(dir, `${nom}.png`), Buffer.from(s.data, 'base64'))
  const medida = await js(`(() => {
    const W = innerWidth, H = innerHeight, d = document.scrollingElement
    // Fuera de pantalla de verdad: lo que ningún contenedor con desplazamiento recorta (las ideas del chat se desplazan a propósito).
    const recortado = (e) => { for (let p = e.parentElement; p && p !== document.body; p = p.parentElement) { const o = getComputedStyle(p).overflowX; if (o !== 'visible') return true } return false }
    const fuera = [...document.querySelectorAll('button, a, input')].filter((b) => { const r = b.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(b).visibility !== 'hidden' && (r.right > W + 2 || r.left < -2) && !recortado(b) }).map((b) => (b.getAttribute('aria-label') || b.textContent || b.tagName).trim().slice(0, 40))
    return { desbordeX: d.scrollWidth > W + 2 ? d.scrollWidth - W : 0, fuera: [...new Set(fuera)].slice(0, 6) }
  })()`)
  pasos.push({ paso: nom, t: ts(), nota, ...medida })
  console.log(`${nom}${nota ? ` — ${nota}` : ''}${medida.desbordeX ? ` ⚠ desborde ${medida.desbordeX}px` : ''}${medida.fuera.length ? ` ⚠ fuera de pantalla: ${medida.fuera.join(', ')}` : ''}`)
}
const escribir = (sel, txt) => js(`(() => { const el = document.querySelector(${JSON.stringify(sel)}); if (!el) return false; const p = Object.getPrototypeOf(el); Object.getOwnPropertyDescriptor(p, 'value').set.call(el, ${JSON.stringify(txt)}); el.dispatchEvent(new Event('input', { bubbles: true })); return true })()`)
const clicTexto = (txt, en = 'button') => js(`(() => { const b = [...document.querySelectorAll(${JSON.stringify(en)})].find((x) => x.textContent.trim().includes(${JSON.stringify(txt)})); if (!b) return false; b.click(); return true })()`)
const titulo = () => js(`document.querySelector('main h1')?.textContent || ''`)
/** Clic real (mouse o dedo) en el centro de un elemento. */
async function tocar(sel, { doble = false, largo = false } = {}) {
  const r = await js(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (!e) return null; e.scrollIntoView({ block: 'center' }); const r = e.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + Math.min(r.height / 2, 60) } })()`)
  if (!r) return false
  if (largo) { await cmd('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: r.x, y: r.y }] }); await esp(900); await cmd('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] }); return true }
  for (const c of doble ? [1, 2] : [1]) { await cmd('Input.dispatchMouseEvent', { type: 'mousePressed', x: r.x, y: r.y, button: 'left', clickCount: c }); await cmd('Input.dispatchMouseEvent', { type: 'mouseReleased', x: r.x, y: r.y, button: 'left', clickCount: c }) }
  return true
}

const RESP = { nombre: 'Gimnasio Fuerza Total', que_vendes: 'Membresías mensuales, clases grupales (spinning, yoga, funcional) y entrenamiento personal', rubro: 'Salud y bienestar', ciclo: 'Clientes recurrentes', objetivos: ['No perder ningún seguimiento', 'Ver mi pipeline y reportes'] }
await cmd('Page.enable'); await cmd('Runtime.enable'); await cmd('Network.enable', { maxPostDataSize: 2000000 })
await cmd('Emulation.setDeviceMetricsOverride', { width: +w, height: +h, deviceScaleFactor: 1, mobile: movil })
if (movil) await cmd('Emulation.setTouchEmulationEnabled', { enabled: true })
await cmd('Page.startScreencast', { format: 'jpeg', quality: 70, maxWidth: +w, maxHeight: +h, everyNthFrame: 1 })
await cmd('Page.navigate', { url: (process.env.LAB_URL || 'http://localhost:5190') + '/experiencia' }); await esp(2500)
await paso('bienvenida')
await clicTexto('Empezar'); await esp(600)
// ── Cuestionario: como lo llenaría el dueño de un gimnasio ──
for (let i = 0; i < 25; i++) {
  if (await js(`!!document.querySelector('.exp-cuenta')`)) break
  const t = await titulo()
  await paso('pregunta', t)
  const tipo = await js(`document.querySelector('main input.campo') ? 'texto' : document.querySelector('main textarea') ? 'parrafo' : document.querySelector('[role=group]') ? 'varias' : document.querySelector('[role=radiogroup]') ? 'una' : '?'`)
  if (tipo === 'texto') {
    await escribir('main input.campo', /llama tu negocio/i.test(t) ? RESP.nombre : 'Zona 10, Ciudad de Guatemala')
    if (await js(`!!document.querySelector('[role=radiogroup]')`)) await clicTexto('Guatemala', '[role=radiogroup] .op')
    await esp(200); await clicTexto('Continuar') || await clicTexto('Crear mi CRM')
  } else if (tipo === 'parrafo') {
    await escribir('main textarea', /vendes|te dedicas/i.test(t) ? RESP.que_vendes : 'Se me olvida quién ya pagó y quién está por vencer'); await esp(200); await clicTexto('Continuar') || await clicTexto('Crear mi CRM')
  } else if (tipo === 'varias') {
    const quiero = /lograr/i.test(t) ? RESP.objetivos : []
    if (quiero.length) for (const o of quiero) await clicTexto(o); else await js(`document.querySelector('[role=group] .op').click()`)
    await esp(200); await clicTexto('Continuar') || await clicTexto('Crear mi CRM')
  } else if (tipo === 'una') {
    const quiero = /dedica/i.test(t) ? RESP.rubro : /proceso de venta/i.test(t) ? RESP.ciclo : null
    if (quiero) await clicTexto(quiero); else await js(`document.querySelector('[role=radiogroup] .op').click()`)
    await esp(800)
  } else break
  await esp(300)
}
await paso('cuenta')
for (const [i, v] of ['Josué', 'Pérez', 'josue@fuerzatotal.com', 'clave1234'].entries()) await escribir(`.exp-campos input:nth-child(${i + 1})`, v)
await clicTexto('Crear cuenta y armar'); await esp(1500)
await paso('armando')
await esp(4500)
if (await js(`/llevar principalmente/i.test(document.querySelector('main h1')?.textContent || '')`)) { await paso('que-llevar'); await js(`document.querySelector('[role=radiogroup] .op, .op')?.click()`); await esp(800) }
await esp(1500)
// ── Primer ingreso: el recorrido paso a paso ──
for (let i = 0; i < 14; i++) {
  const texto = await js(`document.querySelector('.rc-texto, .rc p, [class*=rc-] p')?.textContent || ''`)
  await paso('recorrido', texto.slice(0, 90))
  if (await js(`[...document.querySelectorAll('button')].some((b) => b.textContent.includes('Borrar ejemplos'))`)) break
  if (!(await clicTexto('Siguiente'))) break
  await esp(700)
}
await (mantenerEjemplos ? clicTexto('Mantener ejemplos') : clicTexto('Borrar ejemplos y empezar')); await esp(1500)
await paso('inicio', mantenerEjemplos ? 'con ejemplos' : 'ejemplos borrados')
// ── Cada pestaña del menú ──
const menu = await js(`[...document.querySelectorAll('.mc-menu button[data-seccion]')].map((b) => b.dataset.seccion)`)
for (const s of menu || []) {
  if (movil) { await js(`document.querySelector('.mc-menu-btn, [aria-label*=menú i]')?.click()`); await esp(300) }
  await js(`document.querySelector('.mc-menu button[data-seccion="${s}"]')?.click()`); await esp(1100)
  await paso(`pestana-${s}`, await titulo())
}
// ── Una ficha (si hay registros) ──
await js(`document.querySelector('.mc-menu button[data-seccion]:not([data-seccion=inicio])')?.click()`); await esp(900)
if (await tocar('.pl-tabla-fila:not(.pl-tabla-cab), .pl-tarjeta, .pl-cita')) { await esp(1200); await paso('ficha', await js(`document.querySelector('.pl-ficha h2, .fi-cab h2, [class*=ficha] h2')?.textContent || 'sin ficha'`)); await js(`document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })); window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))`); await esp(800) }
// ── «o pídeselo a Shifu»: abre el chat con el pedido empezado (el formulario se prueba en «datos a mano») ──
if (await clicTexto('o pídeselo a Shifu', '.mc-cab button')) { await esp(900); await paso('agregar-abre-chat', await js(`document.querySelector('.mc-chat-panel input[aria-label="Mensaje para Shifu"]')?.value || '(sin texto)'`)) }
// ── Datos a mano (D56): agregar con el formulario, abrir la ficha, editar, eliminar (con confirmación) ──
{
  const sec = await js(`document.querySelector('.mc-menu button[data-seccion]:not([data-seccion=inicio])')?.dataset.seccion`)
  if (movil) { await js(`document.querySelector('.mc-menu-btn, [aria-label*=menú i]')?.click()`); await esp(300) }
  await js(`document.querySelector('.mc-menu button[data-seccion="${sec}"]')?.click()`); await esp(900)
  const cuantos = () => js(`(document.querySelector('.mc-cab p')?.textContent.match(/[\\d.,]+/) || ['0'])[0]`)
  const n0 = await cuantos()
  await clicTexto('Agregar', '.mc-cab button'); await esp(600)
  // Llena como una persona: el primer campo (el nombre), fechas, horas, números y una opción en cada lista.
  await js(`(() => { const f = document.querySelector('.mc-main .mc-form-registro'); if (!f) return
    const pon = (el, v) => { const p = Object.getPrototypeOf(el); Object.getOwnPropertyDescriptor(p, 'value').set.call(el, v); el.dispatchEvent(new Event(el.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true })) }
    f.querySelectorAll('input, select').forEach((el, i) => pon(el, i === 0 ? 'Prueba Manual' : el.tagName === 'SELECT' ? el.options[1]?.value || '' : el.type === 'date' ? new Date(Date.now() + 5 * 864e5).toISOString().slice(0, 10) : el.type === 'time' ? '09:30' : el.inputMode === 'decimal' ? '250' : 'dato de prueba')) })()`)
  await paso('mano-formulario', await js(`document.querySelector('.mc-form-titulo')?.textContent || '(sin formulario)'`))
  await js(`document.querySelector('.mc-main .mc-form-registro button[type=submit]')?.click()`); await esp(1200)
  const n1 = await cuantos()
  await paso('mano-agregado', `${n0} → ${n1} registros · error: ${await js(`document.querySelector('.mc-form-error')?.textContent || 'ninguno'`)}`)
  if (n1 === n0) eventos.push(`${ts()}s A MANO: agregar no sumó un registro (${n0} → ${n1})`)
  // Abrir su ficha y editar un campo de texto o número.
  await js(`(() => { const el = [...document.querySelectorAll('.pl-seccion *')].find((x) => x.children.length === 0 && x.textContent.trim() === 'Prueba Manual'); el?.closest('[role=button], button, tr, .pl-tabla-fila, .pl-tarjeta, .pl-cita, li')?.setAttribute('data-prueba', '1') })()`)
  // Al agregar se abre la ficha del registro nuevo (así se ve qué quedó guardado); si no, se busca en la lista.
  if (await js(`document.querySelector('.pl-ficha-cab h2')?.textContent === 'Prueba Manual'`) || await tocar('[data-prueba]')) {
    await esp(1200)
    await clicTexto('Editar', '.pl-ficha-acc button'); await esp(500)
    await js(`(() => { const f = document.querySelector('.pl-ficha .mc-form-registro'); const el = f?.querySelector('input:not([type=date]):not([type=time])'); if (!el) return; Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value').set.call(el, 'Prueba Editada'); el.dispatchEvent(new Event('input', { bubbles: true })) })()`)
    await js(`document.querySelector('.pl-ficha .mc-form-registro button[type=submit]')?.click()`); await esp(900)
    const titulo = await js(`document.querySelector('.pl-ficha-cab h2')?.textContent || ''`)
    await paso('mano-editado', titulo)
    if (titulo !== 'Prueba Editada') eventos.push(`${ts()}s A MANO: editar no cambió el nombre («${titulo}»)`)
    await clicTexto('Eliminar', '.pl-ficha-acc button'); await esp(400)
    await paso('mano-confirmar', await js(`document.querySelector('.pl-ficha .mc-fila-confirma span')?.textContent || '(sin confirmación)'`))
    await clicTexto('Sí, eliminar', '.pl-ficha button'); await esp(1200)
    const n2 = await cuantos()
    await paso('mano-eliminado', `${n1} → ${n2} registros · ficha ${await js(`!!document.querySelector('.pl-ficha')`) ? 'abierta' : 'cerrada'}`)
    if (n2 !== n0) eventos.push(`${ts()}s A MANO: eliminar no dejó la cuenta como al principio (${n0} → ${n2})`)
  } else eventos.push(`${ts()}s A MANO: no encontré «Prueba Manual» en la pestaña para abrir su ficha`)
}
// ── Elegir una pieza para el chat: doble clic en PC, mantener presionado en el celular (D39) ──
await js(`document.querySelector('.mc-menu button[data-seccion=inicio]')?.click()`); await esp(1000)
if (await tocar('.pl-inicio .pl-bloque', movil ? { largo: true } : { doble: true })) { await esp(900); await paso('elegir-pieza', await js(`document.querySelector('.lab-piezas, .sel-barra, [class*=seleccion]')?.textContent?.slice(0, 80) || '(no se marcó)'`)) }
// ── Fase 2: pedidos complejos a la IA real ──
const PEDIDOS = [
  'Agrega a Juan Pérez, plan mensual, se inscribió hoy y vence en un mes',
  'También a Ana Gómez, plan anual, vence el 15 de octubre del próximo año',
  'Juan me pagó Q350 hoy en efectivo',
  '¿Cuánto llevo cobrado este mes?',
  'Ponle a Ana el teléfono 5555-1234',
  'Crea una pestaña de clases con nombre de la clase, instructor, día, hora y cupo, y en el inicio quiero ver las clases',
  'Agrega la clase de Spinning con Carla los lunes a las 7 de la mañana, cupo 20',
  '¿Quiénes vencen este mes?',
  'Pasa a Juan a Pausada porque se lesionó',
  'Pon mis colores: negro #111111 y amarillo #FACC15, letra Montserrat',
  'Haz la gráfica más grande y ponla arriba de todo',
  'Exporta mis miembros a Excel',
  'Deshaz lo de los colores',
  'Borra a Ana Gómez',
  '¿Cuántos miembros activos tengo y cuánto me pagaron en total?',
]
const conversacion = []
if (conIA) {
  if (!(await js(`!!document.querySelector('.mc-chat-panel')`))) { await js(`document.querySelector('.mc-chat-btn')?.click()`); await esp(600) }
  for (const p of PEDIDOS) {
    const antes = await js(`document.querySelectorAll('.mc-chat-msgs .cb.shifu').length`)
    await escribir('.mc-chat-panel form input[aria-label]', p); await esp(150)
    await js(`document.querySelector('.mc-chat-panel form button[type=submit]')?.click()`)
    const a = Date.now()
    while (Date.now() - a < 90000) { await esp(400); if ((await js(`document.querySelectorAll('.mc-chat-msgs .cb.shifu').length`)) > antes && !(await js(`!!document.querySelector('.mc-chat-msgs .puntos')`))) break }
    await esp(1800) // que termine la animación del cambio
    const r = await js(`(() => { const m = [...document.querySelectorAll('.mc-chat-msgs .cb.shifu')].at(-1); return { dijo: m?.querySelector('.cb-t')?.innerText || '', cambios: m?.querySelector('.cb-cambios')?.innerText || '' } })()`)
    conversacion.push({ pedido: p, seg: +((Date.now() - a) / 1000).toFixed(1), ...r })
    await paso('chat', `«${p.slice(0, 50)}» → ${r.dijo.slice(0, 120).replace(/\n/g, ' ')}`)
    // Lo que el CRM muestra después (la pestaña abierta), con el chat cerrado en el celular para verlo.
    if (movil) { await js(`document.querySelector('.mc-chat-panel header button')?.click()`); await esp(700); await paso('pantalla', await titulo()); await js(`document.querySelector('.mc-chat-btn')?.click()`); await esp(600) }
  }
} else {
  // Sin IA: un mensaje basta para ver cómo responde el chat cuando la IA no está disponible.
  if (!(await js(`!!document.querySelector('.mc-chat-panel')`))) { await js(`document.querySelector('.mc-chat-btn')?.click()`); await esp(600) }
  await escribir('.mc-chat-panel form input[aria-label]', PEDIDOS[0]); await esp(150); await js(`document.querySelector('.mc-chat-panel form button[type=submit]')?.click()`); await esp(6000)
  await paso('chat-sin-ia', await js(`[...document.querySelectorAll('.mc-chat-msgs .cb.shifu')].at(-1)?.innerText?.slice(0, 160) || ''`))
}
// ── Guardar (D57): recargar y volver al MISMO CRM — misma conversación, mismas piezas, mismos registros ──
const foto = async () => {
  if (movil) { await js(`document.querySelector('.mc-chat-panel header button')?.click()`); await esp(500) }
  await js(`document.querySelector('.mc-menu button[data-seccion=inicio]')?.click()`); await esp(900)
  const piezas = await js(`document.querySelectorAll('.pl-inicio .pl-bloque').length`)
  const sec = await js(`document.querySelector('.mc-menu button[data-seccion]:not([data-seccion=inicio])')?.dataset.seccion`)
  await js(`document.querySelector('.mc-menu button[data-seccion="${sec}"]')?.click()`); await esp(900)
  const registros = await js(`document.querySelector('.mc-cab p')?.textContent || ''`)
  if (!(await js(`!!document.querySelector('.mc-chat-panel')`))) { await js(`document.querySelector('.mc-chat-btn')?.click()`); await esp(600) }
  const mensajes = await js(`document.querySelectorAll('.mc-chat-msgs .cb').length`)
  return { enCrm: await js(`!!document.querySelector('.mc-menu')`), piezas, registros, mensajes }
}
const antes = await foto()
await esp(1500) // el guardado agrupa los cambios de 0,6 s
await cmd('Page.reload'); await esp(4000)
const despues = await foto()
const igual = JSON.stringify(antes) === JSON.stringify(despues)
await paso('tras-recargar', `${igual ? 'igual' : 'DISTINTO'}: ${JSON.stringify(antes)} → ${JSON.stringify(despues)}`)
if (!igual) eventos.push(`${ts()}s GUARDAR: al recargar cambió ${JSON.stringify(antes)} → ${JSON.stringify(despues)}`)
await cmd('Page.stopScreencast')
// Video: cada cuadro dura hasta el siguiente (el screencast solo manda cuadros cuando algo cambia).
const lista = cuadros.map((c, i) => { const f = join(dir, 'cuadros', `c${String(i).padStart(5, '0')}.jpg`); writeFileSync(f, Buffer.from(c.data, 'base64')); return `file '${f}'\nduration ${((cuadros[i + 1]?.t ?? c.t + 1) - c.t).toFixed(3)}` })
if (cuadros.length) {
  writeFileSync(join(dir, 'lista.txt'), lista.join('\n') + `\nfile '${join(dir, 'cuadros', `c${String(cuadros.length - 1).padStart(5, '0')}.jpg`)}'`)
  try { execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', join(dir, 'lista.txt'), '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2,fps=15', '-pix_fmt', 'yuv420p', join(dir, 'recorrido.mp4')]) } catch (e) { eventos.push(`video: ${e.message.slice(0, 120)}`) }
}
writeFileSync(join(dir, 'llamadas.json'), JSON.stringify([...llamadas.values()]))
writeFileSync(join(dir, 'informe.json'), JSON.stringify({ tamano: `${w}x${h}`, conIA, pasos, conversacion, eventos }, null, 1))
console.log(`\n${pasos.length} pasos · ${eventos.filter((e) => /EXCEPCIÓN|error|GUARDAR|A MANO/.test(e)).length} errores · ${pasos.filter((p) => p.desbordeX || p.fuera.length).length} pasos con algo fuera de pantalla · video: ${join(dir, 'recorrido.mp4')}`)
for (const e of eventos.slice(0, 12)) console.log('  ', e)
ws.close(); ch.kill()

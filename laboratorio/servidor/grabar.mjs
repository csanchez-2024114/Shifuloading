/* Graba en video una página del laboratorio (por ejemplo la demo de la IA) en varias resoluciones, para revisarla con ojo
 * crítico: errores visuales, de lógica y tiempos. Usa Chrome sin ventana con un perfil aparte (no toca tu navegador)
 * y el protocolo de DevTools (sin dependencias). Además de cada video .mp4, guarda una hoja de cuadros (uno cada N s)
 * con su tiempo y un registro de eventos (pedidos al chat, errores de consola).
 *
 * Uso (desde la raíz de Shifuloading):
 *   node laboratorio/servidor/grabar.mjs "<ruta>" <segundos> <salida>
 *   node laboratorio/servidor/grabar.mjs "/vista?plantilla=clinica-dental&datos=muchos&tema=claro&demo=1" 110 /tmp/demo
 * Resoluciones: 1440x900, 1280x720, 1024x768 y móvil 390x844. */
import { spawn, execFileSync } from 'node:child_process'
import { mkdirSync, writeFileSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'

const [ruta = '/vista?plantilla=clinica-dental&datos=muchos&tema=claro&demo=1', seg = '110', salida = join(tmpdir(), 'grabacion')] = process.argv.slice(2)
const BASE = process.env.LAB_URL || 'http://localhost:5190'
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const TAMANOS = [
  { id: 'escritorio-1440x900', w: 1440, h: 900 },
  { id: 'laptop-1280x720', w: 1280, h: 720 },
  { id: 'tablet-1024x768', w: 1024, h: 768 },
  { id: 'movil-390x844', w: 390, h: 844, movil: true },
]
const CADA = 3 // segundos entre cuadros de la hoja de revisión

const espera = (ms) => new Promise((r) => setTimeout(r, ms))

async function grabar(t, puerto) {
  const dir = join(salida, t.id); rmSync(dir, { recursive: true, force: true }); mkdirSync(join(dir, 'cuadros'), { recursive: true })
  const perfil = join(tmpdir(), `grabar-perfil-${puerto}`)
  const chrome = spawn(CHROME, [`--remote-debugging-port=${puerto}`, `--user-data-dir=${perfil}`, '--headless=new', '--no-first-run', '--hide-scrollbars', `--window-size=${t.w},${t.h}`, 'about:blank'], { stdio: 'ignore' })
  let ws
  for (let i = 0; i < 50 && !ws; i++) { try { const l = await (await fetch(`http://127.0.0.1:${puerto}/json/list`)).json(); const p = l.find((x) => x.type === 'page'); if (p) ws = new WebSocket(p.webSocketDebuggerUrl) } catch { await espera(200) } }
  await new Promise((r) => ws.addEventListener('open', r, { once: true }))
  let id = 0; const pendientes = new Map(); const eventos = []
  const t0 = Date.now(); const ts = () => ((Date.now() - t0) / 1000).toFixed(1)
  const cmd = (method, params = {}) => new Promise((ok) => { const i = ++id; pendientes.set(i, ok); ws.send(JSON.stringify({ id: i, method, params })) })
  const cuadros = []
  ws.addEventListener('message', async (e) => {
    const m = JSON.parse(e.data)
    if (m.id && pendientes.has(m.id)) { pendientes.get(m.id)(m.result); pendientes.delete(m.id) }
    if (m.method === 'Page.screencastFrame') { cuadros.push({ t: (Date.now() - t0) / 1000, data: m.params.data }); ws.send(JSON.stringify({ id: ++id, method: 'Page.screencastFrameAck', params: { sessionId: m.params.sessionId } })) }
    if (m.method === 'Runtime.consoleAPICalled' && ['error', 'warning'].includes(m.params.type)) eventos.push(`${ts()}s CONSOLA ${m.params.type}: ${m.params.args.map((a) => a.value ?? a.description).join(' ').slice(0, 200)}`)
    if (m.method === 'Runtime.consoleAPICalled' && m.params.args[0]?.value === '[chat-lab]') eventos.push(`${ts()}s IA: ${JSON.stringify(m.params.args[1]?.preview?.properties?.map((p) => `${p.name}=${p.value}`) || '')}`)
    if (m.method === 'Runtime.exceptionThrown') eventos.push(`${ts()}s EXCEPCIÓN: ${m.params.exceptionDetails.exception?.description?.slice(0, 200)}`)
    if (m.method === 'Network.requestWillBeSent' && m.params.request.url.includes('/api/lab/chat')) eventos.push(`${ts()}s → pedido: ${(JSON.parse(m.params.request.postData || '{}').texto || '').slice(0, 80)}`)
    if (m.method === 'Network.loadingFinished' || m.method === 'Network.responseReceived') { if (m.params.response?.url?.includes('/api/lab/chat')) eventos.push(`${ts()}s ← respuesta ${m.params.response.status}`) }
  })
  await cmd('Page.enable'); await cmd('Runtime.enable'); await cmd('Network.enable')
  await cmd('Emulation.setDeviceMetricsOverride', { width: t.w, height: t.h, deviceScaleFactor: 1, mobile: !!t.movil })
  if (t.movil) await cmd('Emulation.setTouchEmulationEnabled', { enabled: true })
  await cmd('Page.startScreencast', { format: 'jpeg', quality: 70, maxWidth: t.w, maxHeight: t.h, everyNthFrame: 1 })
  await cmd('Page.navigate', { url: BASE + ruta })
  await espera(Number(seg) * 1000)
  await cmd('Page.stopScreencast')
  ws.close(); chrome.kill()
  // Video: cada cuadro dura hasta el siguiente (screencast solo manda cuadros cuando algo cambia).
  const lista = []
  cuadros.forEach((c, i) => { const f = join(dir, 'cuadros', `c${String(i).padStart(5, '0')}.jpg`); writeFileSync(f, Buffer.from(c.data, 'base64')); lista.push(`file '${f}'\nduration ${((cuadros[i + 1]?.t ?? c.t + 1) - c.t).toFixed(3)}`) })
  if (!cuadros.length) { writeFileSync(join(dir, 'eventos.txt'), 'SIN CUADROS: la página no dibujó nada\n'); return }
  lista.push(`file '${join(dir, 'cuadros', `c${String(cuadros.length - 1).padStart(5, '0')}.jpg`)}'`)
  writeFileSync(join(dir, 'lista.txt'), lista.join('\n'))
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', join(dir, 'lista.txt'), '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2,fps=15', '-pix_fmt', 'yuv420p', join(dir, `${t.id}.mp4`)])
  // Hoja de revisión: el cuadro vigente cada CADA segundos, con su tiempo en el nombre.
  mkdirSync(join(dir, 'revision'), { recursive: true })
  for (let s = 0; s <= Number(seg); s += CADA) {
    const c = [...cuadros].reverse().find((x) => x.t <= s); if (!c) continue
    writeFileSync(join(dir, 'revision', `t${String(s).padStart(3, '0')}s.jpg`), Buffer.from(c.data, 'base64'))
  }
  writeFileSync(join(dir, 'eventos.txt'), eventos.join('\n') + '\n')
  console.log(`✓ ${t.id}: ${cuadros.length} cuadros · ${join(dir, `${t.id}.mp4`)}`)
}

const puertos = [9301, 9302, 9303, 9304]
await Promise.all(TAMANOS.map((t, i) => grabar(t, puertos[i]).catch((e) => console.log(`✗ ${t.id}: ${e.message}`))))

/* Fixtures dorados (contrato §6) de validar.js y marca.js para el CRM en Python (frente C2).
 * Uso (desde la raíz del repo): node laboratorio/servidor/grabar-validar-marca.mjs [carpeta]
 *   carpeta por defecto: backend/test/crm/fixtures/lab
 * Escribe revisarVista.json, normalizarOpciones.json, validarPlantilla.json, tokensDeMarca.json y revisarLogo.json:
 *   [{ caso, entrada: {...args}, salida }]. Determinista (azar con semilla fija). Sin IA ni red. */
import { createServer } from 'vite'
import { mkdirSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const LAB = fileURLToPath(new URL('..', import.meta.url))
const destino = resolve(process.argv[2] || join(LAB, '..', 'backend/test/crm/fixtures/lab'))
const vite = await createServer({ configFile: join(LAB, 'vite.config.js'), server: { middlewareMode: true, hmr: false }, logLevel: 'error' })
try {
  const { VISTAS, revisarVista, normalizarOpciones, validarPlantilla, camposDe } = await vite.ssrLoadModule('/src/plantillas/validar.js')
  const { tokensDeMarca, revisarLogo, FUENTES } = await vite.ssrLoadModule('/src/plantillas/marca.js')
  const { PLANTILLAS } = await vite.ssrLoadModule('/src/plantillas/semillas.js')
  let semilla = 11; const azar = () => ((semilla = (semilla * 1103515245 + 12345) % 2147483648) / 2147483648)
  const uno = (xs) => xs[Math.floor(azar() * xs.length)]

  // revisarVista: cada sección con campos × cada vista × opciones armadas con sus campos de plantilla+sección (bien, mal tipo, inexistentes, listas, extras).
  const revisar = [], normalizar = []
  for (const p of PLANTILLAS) {
    const porId = Object.fromEntries(p.secciones.map((s) => [s.id, s]))
    for (const s of p.secciones.filter((x) => x.campos || x.fuente)) {
      const campos = camposDe(s, porId), ids = campos.map((c) => c.id)
      for (const vista of [...Object.keys(VISTAS), 'radar']) {
        const def = VISTAS[vista] || { requiere: {}, opcional: {} }
        const claves = [...Object.keys(def.requiere || {}), ...Object.keys(def.opcional || {}), 'dias', 'tipo', 'otra']
        for (let k = 0; k < 3; k++) {
          const op = {}
          for (const c of claves) if (azar() < 0.5) op[c] = uno([uno(ids), uno(ids), 'nada', [uno(ids)], [uno(ids), uno(ids)], '', 0, 30, ['Cancelada']])
          revisar.push({ caso: `${p.id}/${s.id}/${vista}/${k}`, entrada: { plantilla: p.id, seccion: s.id, vista, opciones: op, donde: `«${s.titulo}»` }, salida: revisarVista(vista, op, campos, `«${s.titulo}»`) })
          normalizar.push({ caso: `${p.id}/${s.id}/${vista}/${k}`, entrada: { vista, opciones: op }, salida: normalizarOpciones(vista, op) })
        }
      }
    }
  }
  revisar.push({ caso: 'sin opciones', entrada: { plantilla: null, vista: 'tablero', opciones: null, donde: 'X' }, salida: revisarVista('tablero', null, [], 'X') })

  // validarPlantilla: cada plantilla tal cual y con daños (tipo raro, estado sin opciones, id repetido, bloque de sección que no existe).
  const validar = []
  for (const p of PLANTILLAS) {
    validar.push({ caso: `${p.id} tal cual`, entrada: { p }, salida: validarPlantilla(p) })
    const conCampos = p.secciones.filter((s) => s.campos)
    const danada = structuredClone(p)
    const s0 = danada.secciones.find((s) => s.campos)
    s0.campos.push({ id: 'raro', nombre: 'Raro', tipo: 'color' }, { id: 'est', nombre: 'Est', tipo: 'estado', opciones: ['Solo'] })
    danada.secciones.push({ ...structuredClone(conCampos[0]) })
    danada.inicio = [...(danada.inicio || []), { vista: 'tabla', seccion: 'no_hay' }, { vista: 'tablero', seccion: s0.id, opciones: { por: 'nada' } }]
    delete danada.nombre
    validar.push({ caso: `${p.id} dañada`, entrada: { p: danada }, salida: validarPlantilla(danada) })
  }

  // tokensDeMarca: colores al azar (claros, oscuros, de 3 dígitos, inválidos) en los dos temas.
  const hex = () => uno([() => `#${Math.floor(azar() * 0xffffff).toString(16).padStart(6, '0')}`, () => `${Math.floor(azar() * 0xfff).toString(16).padStart(3, '0')}`,
    () => uno(['#ffffff', '#000000', '#fff', '#111', '#eeeeee', '#22d3a6', '#7c3aed', '#16A34A', 'rojo', '', null])])()
  const marcas = [{}, { logo: 'data:image/png;base64,x' }, { nombre: 'Sol' }, { logo_id: 'a1' }]
  for (let i = 0; i < 300; i++) {
    const m = {}
    for (const k of ['primario', 'secundario', 'fondo', 'superficie', 'texto']) if (azar() < 0.45) m[k] = hex()
    if (azar() < 0.3) m.fuenteTitulos = uno([...Object.keys(FUENTES), 'Comic Sans'])
    if (azar() < 0.3) m.fuenteTexto = uno([...Object.keys(FUENTES), 'Arial'])
    if (azar() < 0.2) m.nombre = 'Mi negocio'
    marcas.push(m)
  }
  const tokens = marcas.flatMap((m, i) => ['claro', 'oscuro'].map((tema) => ({ caso: `marca ${i} ${tema}`, entrada: { marca: m, tema }, salida: tokensDeMarca(m, tema) })))

  const logos = [undefined, null, 'hola', 'data:text/plain;base64,x', 'data:image/png;base64,iVBOR', 'data:image/svg+xml;base64,PHN2Zz4=',
    'data:image/webp;base64,UklG', 'data:image/jpeg;base64,/9j/', 'data:image/gif;base64,R0lG', `data:image/png;base64,${'A'.repeat(2_000_001)}`, 'data:image/png']
  const logo = logos.map((d, i) => ({ caso: `logo ${i}`, entrada: { dataUrl: d ?? null, largo: typeof d === 'string' ? d.length : null }, salida: revisarLogo(d) }))
  // el logo enorme no se guarda entero: se reconstruye en la prueba con su largo
  for (const c of logo) if (c.entrada.largo > 1000) c.entrada.dataUrl = c.entrada.dataUrl.slice(0, 40)

  mkdirSync(destino, { recursive: true })
  const escribir = (n, d) => writeFileSync(join(destino, n), `${JSON.stringify(d)}\n`)
  escribir('revisarVista.json', revisar); escribir('normalizarOpciones.json', normalizar); escribir('validarPlantilla.json', validar)
  escribir('tokensDeMarca.json', tokens); escribir('revisarLogo.json', logo)
  console.log(`revisarVista ${revisar.length} · normalizarOpciones ${normalizar.length} · validarPlantilla ${validar.length} · tokensDeMarca ${tokens.length} · revisarLogo ${logo.length}`)
} finally {
  await vite.close()
}

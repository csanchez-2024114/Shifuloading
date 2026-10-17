/* Guardar (D57): lo que la persona hace en su CRM sobrevive a recargar la página. Un archivo JSON por espacio en
 * laboratorio/.guardado (fuera de git). El navegador recuerda el id de su espacio; el servidor no sabe nada más de la persona.
 * Partes: «experiencia» (paso, respuestas, estructura elegida), «crm» (piezas, marca, estructura, datos, puntos de deshacer)
 * y «chat» (la conversación). Cada PUT reemplaza solo su parte. Nunca se guarda la contraseña (no se manda).
 * En el CRM real esto lo hace el backend (base de datos de Carlos); aquí es para vivir el producto de punta a punta. */
import { mkdirSync, readFileSync, renameSync, rmSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const DIR = fileURLToPath(new URL('../.guardado', import.meta.url))
const ID = /^[a-z0-9-]{8,64}$/
const PARTES = new Set(['experiencia', 'crm', 'chat'])
const MAX = 6 * 1024 * 1024 // los logos viajan en base64 dentro de la marca

const leer = (id) => { try { return JSON.parse(readFileSync(`${DIR}/${id}.json`, 'utf8')) } catch { return null } }
/** Escribe en un temporal y lo renombra: un corte a medias nunca deja un archivo roto. */
const escribir = (id, datos) => { mkdirSync(DIR, { recursive: true }); const tmp = `${DIR}/${id}.json.tmp`; writeFileSync(tmp, JSON.stringify(datos)); renameSync(tmp, `${DIR}/${id}.json`) }

export function guardadoLaboratorio() {
  return {
    name: 'guardado-laboratorio',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use('/api/lab/guardado', async (req, res) => {
        res.setHeader('Content-Type', 'application/json')
        const [id, parte] = (req.url || '').split('?')[0].split('/').filter(Boolean)
        if (!ID.test(id || '')) { res.statusCode = 400; return res.end(JSON.stringify({ error: 'espacio inválido' })) }
        if (req.method === 'GET') return res.end(JSON.stringify(leer(id) || {}))
        if (req.method === 'DELETE') { rmSync(`${DIR}/${id}.json`, { force: true }); return res.end('{}') }
        if (req.method !== 'PUT' || !PARTES.has(parte)) { res.statusCode = 405; return res.end('{}') }
        let cuerpo = ''
        for await (const t of req) { cuerpo += t; if (cuerpo.length > MAX) { res.statusCode = 413; return res.end(JSON.stringify({ error: 'demasiado grande' })) } }
        try {
          const valor = JSON.parse(cuerpo)
          escribir(id, { ...(leer(id) || {}), [parte]: valor, actualizado: new Date().toISOString() })
          res.end(JSON.stringify({ ok: true }))
        } catch (e) { res.statusCode = 400; res.end(JSON.stringify({ error: String(e.message || e) })) }
      })
    },
  }
}

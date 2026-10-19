/* Capturas del CRM en modo diseño (lista 31–38). Uso: BASE=http://localhost:5205 node scripts/capturas_pantalla.mjs */
import { chromium } from '/Users/josueboror/.hermes/hermes-agent/node_modules/playwright-core/index.mjs'
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'

const BASE = process.env.BASE || 'http://localhost:5205'
const OUT = path.resolve('documentos/mediciones/2026-10-19_pantalla')
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const ANCHOS = [1440, 1024, 390]

await mkdir(OUT, { recursive: true })
const browser = await chromium.launch({ executablePath: CHROME, headless: true })
const ctx = await browser.newContext({ locale: 'es-GT' })
const page = await ctx.newPage()

for (const w of ANCHOS) {
  await page.setViewportSize({ width: w, height: w === 390 ? 844 : 900 })
  await page.goto(`${BASE}/mi-crm`, { waitUntil: 'networkidle', timeout: 60000 }).catch(() => page.goto(`${BASE}/`, { waitUntil: 'networkidle' }))
  await page.waitForTimeout(1500)
  const file = path.join(OUT, `crm_${w}px.png`)
  await page.screenshot({ path: file, fullPage: false })
  await writeFile(path.join(OUT, `crm_${w}px.url.txt`), page.url())
  console.log('ok', file)
}

await browser.close()

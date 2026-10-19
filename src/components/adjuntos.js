/** Documentos para el chat del CRM (no imágenes: esas van por CapturaPantalla). */

const EXT = new Set(['pdf', 'docx', 'xlsx', 'csv', 'tsv', 'txt', 'md', 'json'])
const MAX = 5_000_000 // igual que el servidor (MAX_BYTES)

function extension(nombre) {
  const base = String(nombre || '').split(/[/\\]/).pop() || ''
  const i = base.lastIndexOf('.')
  return i < 0 ? '' : base.slice(i + 1).toLowerCase()
}

/** Convierte un File en { nombre, datos (data URL), tamano }. */
export async function documentoDeArchivo(archivo) {
  if (!archivo) throw new Error('Sin archivo')
  if (!EXT.has(extension(archivo.name))) throw new Error('Solo puedo leer PDF, Word (.docx), Excel (.xlsx), CSV, TSV, TXT, MD o JSON.')
  if (archivo.size > MAX) throw new Error('Ese archivo pesa más de 5 MB. Prueba con uno más pequeño.')
  let bytes
  try { bytes = new Uint8Array(await archivo.arrayBuffer()) } catch { throw new Error('No se pudo leer el archivo') }
  let bin = ''
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000)) // por partes: un solo apply revienta la pila
  return { nombre: archivo.name, datos: `data:${archivo.type || 'application/octet-stream'};base64,${btoa(bin)}`, tamano: archivo.size }
}

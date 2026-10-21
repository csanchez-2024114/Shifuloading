/* Los archivos que la persona pide (por el chat a Shifu o con los botones de Ajustes). Los arma el servidor (`descarga.py`);
 * aquí solo se bajan con la sesión y se guardan en su carpeta de Descargas. */
import { crm as apiCrm } from '../api'

/** Guarda un blob como archivo (el navegador lo deja en Descargas). */
export function guardarArchivo(blob, nombre) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = nombre || 'archivo'
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/** Baja un archivo que preparó Shifu ({ id, nombre } de `descargas` en la respuesta del chat). */
export async function bajarDescarga(ficha) {
  const { blob, nombre } = await apiCrm.descarga(ficha.id)
  guardarArchivo(blob, nombre || ficha.nombre)
}

/** Botón de Ajustes: el CRM completo en Excel o el respaldo (JSON). */
export async function exportar(formato) {
  const { blob, nombre } = await apiCrm.exportar(formato)
  guardarArchivo(blob, nombre)
}

/* Prepara el logotipo de un negocio para guardarlo: lo achica (no hace falta más para una barra), conserva la transparencia y
 * lo deja en un peso razonable. Devuelve la imagen como texto (data URL) lista para mandar al servidor. */

const FORMATOS = /^image\/(png|jpeg|webp)$/
const MAX_CARACTERES = 140_000 // el servidor acepta hasta 150 mil

export async function logoDeArchivo(archivo) {
  if (!archivo || !FORMATOS.test(archivo.type)) throw new Error('Elige una imagen PNG, JPG o WebP.')
  const url = URL.createObjectURL(archivo)
  let img
  try {
    img = await new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = () => no(new Error('No pude abrir esa imagen.')); i.src = url })
  } finally { URL.revokeObjectURL(url) }
  let anchoMax = 360
  let altoMax = 140
  for (let intento = 0; intento < 6; intento++) {
    const f = Math.min(1, anchoMax / img.width, altoMax / img.height)
    const c = document.createElement('canvas')
    c.width = Math.max(1, Math.round(img.width * f)); c.height = Math.max(1, Math.round(img.height * f))
    c.getContext('2d').drawImage(img, 0, 0, c.width, c.height)
    let salida = c.toDataURL('image/webp', 0.9) // WebP conserva la transparencia y pesa poco
    if (!salida.startsWith('data:image/webp')) salida = c.toDataURL('image/png') // si el navegador no sabe WebP, PNG
    if (salida.length <= MAX_CARACTERES) return salida
    anchoMax *= 0.75; altoMax *= 0.75 // todavía pesa de más: se achica un poco y se intenta otra vez
  }
  throw new Error('Esa imagen pesa demasiado. Prueba con una más sencilla.')
}

/* Preguntas del brief de bienvenida y reglas que convierten las respuestas en recomendaciones.
 * Para agregar o cambiar una pregunta basta con editar esta lista: la pantalla se arma sola. */

const o = (v, e, t, d) => ({ v, e, t, d })

export const PREGUNTAS = [
  // ───────── 1 · Tu negocio ─────────
  { id: 'nombre', capitulo: 'Tu negocio', emoji: '👋', tipo: 'texto', requerido: true,
    titulo: '¡Te damos la bienvenida a Shifu! ¿Cómo se llama tu negocio?',
    sub: 'Con eso empezamos a personalizar todo para ti.', placeholder: 'Por ejemplo: Casa Verde' },
  { id: 'ubicacion', capitulo: 'Tu negocio', emoji: '🌎', tipo: 'ubicacion',
    titulo: (r) => `Mucho gusto${r.nombre ? `, ${r.nombre}` : ''}. ¿Desde dónde vendes?`,
    sub: 'Nos ayuda a sugerirte moneda, impuestos y envíos.',
    opciones: [o('gt', '🇬🇹', 'Guatemala'), o('mx', '🇲🇽', 'México'), o('co', '🇨🇴', 'Colombia'), o('es', '🇪🇸', 'España'), o('us', '🇺🇸', 'Estados Unidos'), o('otro', '🌍', 'Otro país')] },
  { id: 'rubro', capitulo: 'Tu negocio', emoji: '🛍️', tipo: 'una', requerido: true,
    titulo: '¿A qué se dedica tu negocio?', sub: 'Elige el que más se parezca.',
    opciones: [o('moda', '👗', 'Moda y accesorios'), o('alimentos', '🍔', 'Alimentos y bebidas'), o('hogar', '🏡', 'Hogar y decoración'), o('tecnologia', '💻', 'Tecnología'),
      o('belleza', '💄', 'Belleza y cuidado'), o('servicios', '🧰', 'Servicios'), o('arte', '🎨', 'Arte y creativos'), o('otro', '✨', 'Otro')] },
  { id: 'tiempo', capitulo: 'Tu negocio', emoji: '⏳', tipo: 'una',
    titulo: '¿Hace cuánto empezaste?', sub: 'No hay respuesta mala: todos empezamos en algún lado.',
    opciones: [o('idea', '💡', 'Solo es una idea'), o('nuevo', '🌱', 'Menos de 1 año'), o('medio', '🌿', '1 a 3 años'), o('veterano', '🌳', 'Más de 3 años')] },

  // ───────── 2 · Cómo vendes hoy ─────────
  { id: 'canales', capitulo: 'Cómo vendes hoy', emoji: '📣', tipo: 'varias', requerido: true,
    titulo: '¿Dónde vendes hoy?', sub: 'Puedes elegir varios.',
    opciones: [o('fisica', '🏪', 'Tienda física'), o('redes', '📸', 'Instagram o Facebook'), o('whatsapp', '💬', 'WhatsApp'), o('web', '🌐', 'Web propia'),
      o('marketplace', '🛒', 'Marketplace'), o('nada', '🙈', 'Todavía no vendo')] },
  { id: 'pedidos', capitulo: 'Cómo vendes hoy', emoji: '📦', tipo: 'una',
    titulo: '¿Cuántos pedidos recibes al mes?', sub: 'Un cálculo aproximado basta.',
    opciones: [o('p0', '🌙', '0 a 10'), o('p1', '🌤️', '11 a 50'), o('p2', '☀️', '51 a 200'), o('p3', '🚀', 'Más de 200')] },

  // ───────── 3 · Qué vendes ─────────
  { id: 'tipo', capitulo: 'Qué vendes', emoji: '🧺', tipo: 'una',
    titulo: '¿Qué es lo que vendes?', sub: 'Elige la opción principal.',
    opciones: [o('fisico', '📦', 'Productos físicos'), o('digital', '💾', 'Productos digitales'), o('servicio', '🛎️', 'Servicios'), o('mezcla', '🔀', 'Una mezcla de todo')] },
  { id: 'catalogo', capitulo: 'Qué vendes', emoji: '🗃️', tipo: 'una',
    titulo: '¿Cuántos productos o servicios tienes?', sub: 'Así sabemos cómo ayudarte a cargarlos.',
    opciones: [o('c1', '🎯', '1 a 10'), o('c2', '📚', '11 a 50'), o('c3', '🏬', '51 a 500'), o('c4', '🏭', 'Más de 500')] },
  { id: 'logistica', capitulo: 'Qué vendes', emoji: '🚚', tipo: 'varias',
    titulo: '¿Cómo manejas inventario y envíos?', sub: 'Marca todo lo que aplique.',
    opciones: [o('propio', '📦', 'Inventario propio'), o('pedido', '🧾', 'Produzco por pedido'), o('dropshipping', '🛰️', 'Dropshipping'), o('exterior', '✈️', 'Envío al extranjero')] },

  // ───────── 4 · Tu equipo ─────────
  { id: 'equipo', capitulo: 'Tu equipo', emoji: '🤝', tipo: 'una',
    titulo: '¿Cuántas personas trabajan contigo?', sub: 'Contándote a ti.',
    opciones: [o('solo', '🧍', 'Solo yo'), o('chico', '👥', '2 a 5'), o('medio', '🏢', '6 a 20'), o('grande', '🌆', 'Más de 20')] },
  { id: 'herramientas', capitulo: 'Tu equipo', emoji: '🧰', tipo: 'varias',
    titulo: '¿Qué usas hoy para llevar tu negocio?', sub: 'Puedes marcar varias.',
    opciones: [o('excel', '📊', 'Excel o Sheets'), o('sistema', '🧩', 'Otro sistema'), o('cuaderno', '📒', 'Cuaderno o notas'), o('nada', '🤷', 'Nada todavía')] },

  // ───────── 5 · Qué buscas ─────────
  { id: 'objetivos', capitulo: 'Qué buscas', emoji: '🎯', tipo: 'varias', max: 3, requerido: true,
    titulo: '¿Qué te gustaría lograr con Shifu?', sub: 'Elige hasta 3. Son los que pondremos primero.',
    opciones: [o('vender', '📈', 'Vender más'), o('ia', '🤖', 'Atender más rápido con IA'), o('inventario', '🗂️', 'Ordenar mi inventario'), o('cobrar', '💳', 'Cobrar online'),
      o('fuera', '🌎', 'Vender fuera del país'), o('reportes', '📊', 'Ver reportes claros'), o('canales', '🔗', 'Abrir nuevos canales')] },
  { id: 'dolor', capitulo: 'Qué buscas', emoji: '💭', tipo: 'parrafo',
    titulo: '¿Qué es lo que más te complica hoy?', sub: 'Opcional. Cuéntanos con tus palabras, aunque sea una frase.',
    placeholder: 'Por ejemplo: pierdo ventas porque tardo en responder los mensajes…' },

  // ───────── 6 · Cómo quieres empezar ─────────
  { id: 'autonomia', capitulo: 'Cómo quieres empezar', emoji: '✨', tipo: 'una',
    titulo: '¿Cuánto quieres que haga la IA por ti?', sub: 'Lo puedes cambiar cuando quieras.',
    opciones: [o('alta', '🙋', 'Que responda y actúe por mí', 'Tú solo revisas lo importante'), o('media', '💡', 'Que me sugiera y yo decido', 'Tú das la última palabra'), o('baja', '📈', 'Solo reportes y análisis', 'Sin que toque nada')] },
  { id: 'presupuesto', capitulo: 'Cómo quieres empezar', emoji: '💰', tipo: 'una',
    titulo: '¿Qué presupuesto mensual tienes pensado?', sub: 'Opcional. Solo para recomendarte un plan que te convenga.',
    opciones: [o('b1', '🌱', 'Menos de $30'), o('b2', '💼', '$30 a $100'), o('b3', '🏆', 'Más de $100'), o('b4', '🤔', 'Aún no lo sé')] },
]

const ETQ = Object.fromEntries(PREGUNTAS.filter((q) => q.opciones).map((q) => [q.id, Object.fromEntries(q.opciones.map((x) => [x.v, x.t]))]))
export const etiqueta = (id, v) => ETQ[id]?.[v] ?? v

const tiene = (r, id, v) => (Array.isArray(r[id]) ? r[id].includes(v) : r[id] === v)

/** Convierte las respuestas en recomendaciones, de la más relevante a la menos. */
export function recomendar(r) {
  const lista = []
  const add = (prioridad, clave, emoji, titulo, texto, porque, boton) => lista.push({ prioridad, clave, emoji, titulo, texto, porque, boton })
  const sinVender = tiene(r, 'canales', 'nada')
  const grande = ['c3', 'c4'].includes(r.catalogo)

  if (sinVender || r.tiempo === 'idea') add(1, 'lanza', '🚀', 'Lanza tu primera tienda en 10 minutos', 'Elige una plantilla lista, sube tus primeros productos y publica.', sinVender ? 'Porque todavía no vendes' : 'Porque tu negocio está empezando', 'Crear mi tienda')
  if (tiene(r, 'canales', 'whatsapp') || tiene(r, 'canales', 'redes')) add(tiene(r, 'objetivos', 'ia') ? 0 : 2, 'ia', '🤖', 'Activa la IA de atención en tus chats', 'Shifu responde preguntas, toma pedidos y te avisa cuando hace falta una persona.', tiene(r, 'canales', 'whatsapp') ? 'Porque vendes por WhatsApp' : 'Porque vendes por redes', 'Conectar mis chats')
  else if (tiene(r, 'objetivos', 'ia')) add(0, 'ia', '🤖', 'Prueba a Shifu IA con tus clientes', 'Un asistente que responde al instante en tu tienda.', 'Porque quieres atender más rápido', 'Probar Shifu IA')
  if (grande || ['p2', 'p3'].includes(r.pedidos)) add(2, 'catalogo', '📥', 'Importa tu catálogo desde Excel', 'Sube todos tus productos de una vez, con fotos y precios.', grande ? 'Porque tienes muchos productos' : 'Porque manejas muchos pedidos', 'Importar catálogo')
  if (tiene(r, 'objetivos', 'fuera') || tiene(r, 'logistica', 'exterior')) add(0, 'mercados', '🌎', 'Configura mercados e impuestos internacionales', 'Vende en otras monedas, con envíos y aduanas resueltos.', 'Porque quieres vender fuera del país', 'Abrir mercados')
  if (tiene(r, 'objetivos', 'cobrar')) add(0, 'pagos', '💳', 'Activa Shifu Pay', 'Cobra con tarjeta y recibe el dinero directo en tu cuenta.', 'Porque quieres cobrar online', 'Activar pagos')
  if (tiene(r, 'objetivos', 'inventario') || tiene(r, 'logistica', 'propio')) add(1, 'inventario', '🗂️', 'Ordena tu inventario', 'Controla existencias, avisos de poco stock y entradas de mercadería.', tiene(r, 'objetivos', 'inventario') ? 'Porque quieres ordenar tu inventario' : 'Porque manejas inventario propio', 'Ir a inventario')
  if (tiene(r, 'objetivos', 'reportes') || r.autonomia === 'baja') add(1, 'reportes', '📊', 'Mira tu panel de reportes', 'Ventas, productos que más salen y clientes que vuelven, en un vistazo.', 'Porque quieres ver reportes claros', 'Ver reportes')
  if (tiene(r, 'objetivos', 'canales')) add(1, 'canales', '🔗', 'Conecta un nuevo canal de venta', 'Suma Instagram, TikTok o un marketplace sin duplicar trabajo.', 'Porque quieres abrir nuevos canales', 'Conectar canales')
  if (tiene(r, 'herramientas', 'nada') || tiene(r, 'herramientas', 'cuaderno')) add(3, 'plantilla', '🧱', 'Empieza con una plantilla lista', 'Deja el cuaderno: tu tienda, pedidos y clientes en un solo lugar.', 'Porque hoy lo llevas a mano', 'Ver plantillas')
  if (tiene(r, 'objetivos', 'vender')) add(2, 'vender', '📈', 'Mira ideas para vender más', 'Descuentos, correos y campañas que Shifu te sugiere según tu rubro.', 'Porque quieres vender más', 'Ver ideas')

  // Sin duplicados y de más a menos relevante (a igual prioridad se respeta el orden en que se agregaron).
  const vistos = new Set()
  const unicas = lista.filter((x) => (vistos.has(x.titulo) ? false : vistos.add(x.titulo)))
  unicas.sort((a, b) => a.prioridad - b.prioridad)
  const final = unicas.slice(0, 5)
  if (!final.length) final.push({ prioridad: 9, clave: 'inicio', emoji: '✨', titulo: 'Recorre Shifu con calma', texto: 'Te mostramos lo esencial en un recorrido de 2 minutos.', porque: 'Para que conozcas lo básico', boton: 'Empezar recorrido' })
  return final
}

export const CLAVE = 'shifu_brief'

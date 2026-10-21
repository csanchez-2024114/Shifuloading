/* Preguntas del cuestionario de bienvenida y reglas que convierten las respuestas en recomendaciones.
 * Shifu ayuda a crear CRMs con IA: las preguntas buscan entender a qué clientes atiende la persona, cómo les da seguimiento hoy
 * y qué quiere lograr. Para agregar o cambiar una pregunta basta con editar esta lista: la pantalla se arma sola. */

const o = (v, e, t, d) => ({ v, e, t, d })

export const PREGUNTAS = [
  // ───────── 1 · Tu negocio ─────────
  { id: 'nombre', capitulo: 'Para empezar', emoji: '👋', tipo: 'texto', requerido: true,
    titulo: '¡Te damos la bienvenida a Shifu! ¿Cómo se llama tu negocio o proyecto?',
    sub: 'Puede ser un negocio, un equipo, un club o algo tuyo. Con eso empezamos.', placeholder: 'Por ejemplo: Estudio Aurora' },
  { id: 'ubicacion', capitulo: 'Para empezar', emoji: '🌎', tipo: 'ubicacion',
    titulo: (r) => `Mucho gusto${r.nombre?.trim() ? `, ${r.nombre.trim()}` : ''}. ¿Desde dónde trabajas?`,
    sub: 'Nos ayuda a sugerirte moneda, impuestos y horarios.',
    opciones: [o('gt', '🇬🇹', 'Guatemala'), o('mx', '🇲🇽', 'México'), o('co', '🇨🇴', 'Colombia'), o('es', '🇪🇸', 'España'), o('us', '🇺🇸', 'Estados Unidos'), o('otro', '🌍', 'Otro país')] },
  { id: 'rubro', capitulo: 'Tu negocio', emoji: '🏷️', tipo: 'una', requerido: true,
    titulo: '¿A qué se dedica tu negocio?', sub: 'Elige el que más se parezca: así te sugerimos etapas y campos.',
    opciones: [o('servicios', '💼', 'Servicios profesionales'), o('agencia', '🎨', 'Agencia o estudio creativo'), o('comercio', '🛍️', 'Comercio y retail'), o('salud', '🩺', 'Salud y bienestar'),
      o('educacion', '🎓', 'Educación'), o('tecnologia', '💻', 'Tecnología'), o('inmobiliaria', '🏠', 'Inmobiliaria y construcción'), o('otro', '✨', 'Otro')] },
  { id: 'que_vendes', capitulo: 'Para empezar', emoji: '💬', tipo: 'parrafo', requerido: true,
    titulo: 'Cuéntame con tus palabras: ¿a qué te dedicas y qué quieres tener en orden?', sub: 'Como si se lo contaras a un amigo. No tiene que ser perfecto: es lo que más me ayuda a armar algo hecho para ti.',
    placeholder: 'Por ejemplo: vendo pan por encargo y quiero llevar mis pedidos · doy clases de guitarra y quiero tener a mis alumnos y horarios en orden · coordino un grupo de voluntarios…' },
  { id: 'tiempo', capitulo: 'Tu negocio', emoji: '⏳', tipo: 'una',
    titulo: '¿Hace cuánto empezaste?', sub: 'No hay respuesta mala: todos empezamos en algún lado.',
    opciones: [o('idea', '💡', 'Solo es una idea'), o('nuevo', '🌱', 'Menos de 1 año'), o('medio', '🌿', '1 a 3 años'), o('veterano', '🌳', 'Más de 3 años')] },

  // ───────── 2 · Tus clientes hoy ─────────
  { id: 'canales', capitulo: 'Tus clientes hoy', emoji: '💬', tipo: 'varias', requerido: true,
    titulo: '¿Por dónde te contactan tus clientes hoy?', sub: 'Puedes elegir varios.',
    opciones: [o('whatsapp', '💬', 'WhatsApp'), o('correo', '✉️', 'Correo'), o('llamadas', '📞', 'Llamadas'), o('redes', '📸', 'Instagram o Facebook'), o('presencial', '🤝', 'En persona'), o('web', '🌐', 'Formulario web')] },
  { id: 'cartera', capitulo: 'Tus clientes hoy', emoji: '🗂️', tipo: 'una',
    titulo: '¿Cuántos clientes o prospectos manejas?', sub: 'Un cálculo aproximado basta.',
    opciones: [o('k1', '🌱', 'Menos de 50'), o('k2', '🌿', '50 a 200'), o('k3', '🌳', '200 a 1,000'), o('k4', '🏔️', 'Más de 1,000')] },

  // ───────── 3 · Cómo trabajas ─────────
  { id: 'ciclo', capitulo: 'Cómo trabajas', emoji: '🔁', tipo: 'una',
    titulo: '¿Cómo es tu proceso de venta?', sub: 'Elige la opción principal.',
    opciones: [o('cotizacion', '🧾', 'Servicios con cotización'), o('rapida', '⚡', 'Ventas rápidas'), o('recurrente', '🔄', 'Clientes recurrentes'), o('mezcla', '🔀', 'Una mezcla de todo')] },
  { id: 'problemas', capitulo: 'Cómo trabajas', emoji: '😅', tipo: 'varias',
    titulo: '¿Qué te pasa más seguido con tus clientes?', sub: 'Marca todo lo que se parezca.',
    opciones: [o('olvido', '😴', 'Se me olvida dar seguimiento'), o('info', '🔍', 'No encuentro los datos de un cliente'), o('equipo', '🔁', 'Cada quien lleva sus propios datos'), o('mensajes', '💬', 'Pierdo mensajes entre chats')] },

  // ───────── 4 · Tu equipo ─────────
  { id: 'equipo', capitulo: 'Tu equipo', emoji: '🤝', tipo: 'una',
    titulo: '¿Cuántas personas trabajan contigo?', sub: 'Contándote a ti.',
    opciones: [o('solo', '🧍', 'Solo yo'), o('chico', '👥', '2 a 5'), o('medio', '🏢', '6 a 20'), o('grande', '🌆', 'Más de 20')] },
  { id: 'herramientas', capitulo: 'Tu equipo', emoji: '🧰', tipo: 'varias',
    titulo: '¿Qué usas hoy para llevar a tus clientes?', sub: 'Puedes marcar varias.',
    opciones: [o('excel', '📊', 'Excel o Sheets'), o('crm', '🧩', 'Otro CRM'), o('cuaderno', '📒', 'Cuaderno o notas'), o('nada', '🤷', 'Nada todavía')] },

  // ───────── 5 · Qué buscas ─────────
  { id: 'objetivos', capitulo: 'Qué buscas', emoji: '🎯', tipo: 'varias', requerido: true,
    titulo: '¿Qué te gustaría lograr con Shifu?', sub: 'Elige todos los que quieras. Pondremos primero los que marques.',
    opciones: [o('seguimientos', '🔔', 'No perder ningún seguimiento'), o('contactos', '🗂️', 'Ordenar mis contactos'), o('ia', '🤖', 'Que la IA responda y agende por mí'), o('reportes', '📊', 'Ver mi pipeline y reportes'),
      o('cotizaciones', '🧾', 'Enviar cotizaciones más rápido'), o('equipo', '👥', 'Trabajar en equipo'), o('integraciones', '🔗', 'Conectar WhatsApp y correo')] },
  { id: 'dolor', capitulo: 'Qué buscas', emoji: '💭', tipo: 'parrafo',
    titulo: '¿Qué es lo que más te complica hoy con tus clientes?', sub: 'Opcional. Cuéntanos con tus palabras, aunque sea una frase.',
    placeholder: 'Por ejemplo: pierdo clientes porque tardo en responder y se me pasan los seguimientos…' },

  // ───────── 6 · Cómo quieres empezar ─────────
  { id: 'armado', capitulo: 'Cómo quieres empezar', emoji: '🛠️', tipo: 'una',
    titulo: '¿Cómo quieres armar tu CRM?', sub: 'Lo puedes cambiar cuando quieras.',
    opciones: [o('ia', '✨', 'Que Shifu lo arme desde mi descripción', 'Cuéntale tu negocio y listo'), o('plantilla', '📋', 'Partir de una plantilla', 'Etapas y campos ya pensados para tu rubro'), o('excel', '📥', 'Importar mi Excel', 'Trae tus contactos de una vez')] },
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

/** Convierte las respuestas en recomendaciones, de la más relevante a la menos. `clave` las enlaza con las tarjetas del panel. */
export function recomendar(r) {
  const lista = []
  const add = (prioridad, clave, emoji, titulo, texto, porque, boton) => lista.push({ prioridad, clave, emoji, titulo, texto, porque, boton })
  const quiere = (v) => tiene(r, 'objetivos', v)
  const dolor = (v) => tiene(r, 'problemas', v)
  const usaExcel = tiene(r, 'herramientas', 'excel') || tiene(r, 'herramientas', 'cuaderno')

  if (r.armado === 'ia' || r.tiempo === 'idea') add(0, 'arma', '✨', 'Describe tu negocio y Shifu arma tu CRM', 'Cuéntale cómo vendes y te propone etapas, campos y recordatorios en minutos.', r.armado === 'ia' ? 'Porque quieres que Shifu lo arme' : 'Porque tu negocio está empezando', 'Crear mi CRM')
  if (r.armado === 'plantilla') add(0, 'plantilla', '📋', 'Elige una plantilla para tu rubro', 'Etapas y campos ya pensados para tu tipo de negocio, listos para ajustar.', 'Porque prefieres partir de una plantilla', 'Ver plantillas')
  if (r.armado === 'excel' || usaExcel) add(r.armado === 'excel' ? 0 : 2, 'importar', '📥', 'Importa tus contactos desde Excel', 'Sube tu hoja de cálculo y Shifu ordena y completa los datos por ti.', r.armado === 'excel' ? 'Porque quieres importar tu Excel' : 'Porque hoy llevas a tus clientes en hojas o notas', 'Importar contactos')
  if (quiere('seguimientos') || dolor('olvido')) add(quiere('seguimientos') ? 0 : 1, 'seguimientos', '🔔', 'Activa los recordatorios de seguimiento', 'Cada cliente tiene su siguiente paso y Shifu te avisa cuando toca escribirle.', quiere('seguimientos') ? 'Porque no quieres perder ningún seguimiento' : 'Porque se te pasa dar seguimiento', 'Activar recordatorios')
  if (quiere('contactos') || dolor('info') || ['k3', 'k4'].includes(r.cartera)) add(quiere('contactos') ? 0 : 2, 'contactos', '🗂️', 'Centraliza todos tus contactos', 'Un solo lugar con el historial, las notas y las conversaciones de cada cliente.', quiere('contactos') ? 'Porque quieres ordenar tus contactos' : 'Porque manejas muchos clientes', 'Ver contactos')
  if (quiere('ia') || tiene(r, 'canales', 'whatsapp') || tiene(r, 'canales', 'redes')) add(quiere('ia') ? 0 : 2, 'ia', '🤖', 'Activa la IA para responder y agendar por ti', 'Shifu contesta preguntas, crea el contacto y propone el siguiente paso.', quiere('ia') ? 'Porque quieres que la IA te ayude' : 'Porque te escriben por chat', 'Activar la IA')
  if (quiere('integraciones') || dolor('mensajes') || tiene(r, 'canales', 'whatsapp') || tiene(r, 'canales', 'correo')) add(quiere('integraciones') || dolor('mensajes') ? 1 : 3, 'integraciones', '🔗', 'Conecta WhatsApp y tu correo', 'Las conversaciones entran solas al CRM, sin copiar y pegar.', dolor('mensajes') ? 'Porque pierdes mensajes entre chats' : 'Porque ahí te contactan tus clientes', 'Conectar canales')
  if (quiere('reportes')) add(1, 'reportes', '📊', 'Mira tu pipeline y tus reportes', 'Cuántas oportunidades hay en cada etapa y cuáles están en riesgo.', 'Porque quieres ver tu pipeline', 'Ver reportes')
  if (quiere('cotizaciones') || r.ciclo === 'cotizacion') add(quiere('cotizaciones') ? 1 : 3, 'cotizaciones', '🧾', 'Crea tu primera cotización', 'Arma y envía cotizaciones con tus datos en pocos clics.', quiere('cotizaciones') ? 'Porque quieres cotizar más rápido' : 'Porque vendes con cotización', 'Crear cotización')
  if (r.equipo && r.equipo !== 'solo' && (quiere('equipo') || dolor('equipo'))) add(1, 'equipo', '👥', 'Invita a tu equipo y reparte clientes', 'Cada persona ve sus clientes y todos trabajan sobre los mismos datos.', dolor('equipo') ? 'Porque cada quien lleva sus propios datos' : 'Porque quieres trabajar en equipo', 'Invitar equipo')

  // Sin duplicados y de más a menos relevante (a igual prioridad se respeta el orden en que se agregaron).
  const vistos = new Set()
  const unicas = lista.filter((x) => (vistos.has(x.titulo) ? false : vistos.add(x.titulo)))
  unicas.sort((a, b) => a.prioridad - b.prioridad)
  const final = unicas.slice(0, 5)
  if (!final.length) final.push({ prioridad: 9, clave: 'inicio', emoji: '✨', titulo: 'Recorre Shifu con calma', texto: 'Te mostramos lo esencial en un recorrido de 2 minutos.', porque: 'Para que conozcas lo básico', boton: 'Empezar recorrido' })
  return final
}

export const CLAVE = 'shifu_brief'

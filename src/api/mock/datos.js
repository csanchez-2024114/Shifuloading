import { ETAPAS } from '../../crm/secciones'
import { nuevoId } from './pura'

/* Datos de ejemplo con los que el servidor simulado arma un CRM nuevo a partir de las respuestas del cuestionario. */
const NOMBRES = ['Ana Morales', 'Luis Pérez', 'Sofía Ríos', 'Marcos Díaz', 'Valeria Soto', 'Diego Castillo', 'Camila Vega', 'Jorge Luna',
  'Paola Méndez', 'Andrés Cruz', 'Lucía Torres', 'Mateo Rojas', 'Elena Salas', 'Hugo Ibarra', 'Renata Paz', 'Iván Aguirre']
const EQUIPO = ['Mariana Solís', 'Carlos Aguilar', 'Diana Hidalgo']
const CARTERA = { k1: 40, k2: 120, k3: 600, k4: 1200 }
const PERSONAS = { solo: 1, chico: 2, medio: 3, grande: 4 }
const CANALES = { whatsapp: 'WhatsApp', correo: 'Correo', llamadas: 'Llamadas', redes: 'Instagram o Facebook', presencial: 'En persona', web: 'Formulario web' }

export function generar(brief) {
  const total = CARTERA[brief.cartera] || 60
  const vendedores = ['Tú', ...EQUIPO, 'Ana Ruiz'].slice(0, PERSONAS[brief.equipo] || 1)
  const canales = (brief.canales?.length ? brief.canales : ['whatsapp']).map((c) => CANALES[c] || c)
  const visibles = Math.min(total, 16)
  const quiere = (v) => brief.objetivos?.includes(v)
  const canal = (v) => brief.canales?.includes(v)
  return {
    brief,
    totalContactos: total,
    contactos: Array.from({ length: visibles }, (_, k) => ({
      id: nuevoId(), n: NOMBRES[k % NOMBRES.length], canal: canales[k % canales.length], etapa: ETAPAS[k % 4], dueno: vendedores[k % vendedores.length], dias: (k % 6) + 1,
    })),
    vendedores,
    tareas: {
      porHacer: ['Importar contactos', 'Definir etapas de venta', 'Plantilla de cotización'].map((t) => ({ id: nuevoId(), t })),
      enCurso: ['Conectar WhatsApp', 'Invitar al equipo'].map((t) => ({ id: nuevoId(), t })),
      hecho: ['Crear cuenta', 'Responder el cuestionario'].map((t) => ({ id: nuevoId(), t })),
    },
    eventos: [
      ['🤖', 'Shifu creó tu CRM', 'hace un momento'], ['📥', `Se cargaron ${total.toLocaleString('es')} contactos de ejemplo`, 'hace un momento'],
      ['🔔', 'Se activaron los recordatorios de seguimiento', 'hace 1 min'], ['💬', `Canales listos para conectar: ${canales.join(', ')}`, 'hace 1 min'], ['👋', 'Cuenta creada', 'hoy'],
    ].map(([e, t, h]) => ({ id: nuevoId(), e, t, h })),
    automatizaciones: [
      { id: 'recordatorios', pilar: 'Estructura', t: 'Recordatorios de seguimiento', d: 'Te avisa cuando un contacto lleva 3 días sin respuesta.', on: quiere('seguimientos') || !!brief.problemas?.includes('olvido') },
      { id: 'bienvenida', pilar: 'Estructura', t: 'Bienvenida automática por WhatsApp', d: 'Responde al instante cuando alguien te escribe por primera vez.', on: canal('whatsapp') },
      { id: 'contacto', pilar: 'Estructura', t: 'Crear el contacto desde cada mensaje', d: 'Shifu detecta quién te escribe y lo agrega con lo que pidió.', on: quiere('ia') },
      { id: 'reparto', pilar: 'Medición y equipo', t: 'Repartir contactos nuevos entre el equipo', d: 'Cada contacto nuevo se asigna por turnos a tu equipo.', on: !!brief.equipo && brief.equipo !== 'solo' },
      { id: 'vencidos', pilar: 'Medición y equipo', t: 'Aviso de cobros vencidos', d: 'Te avisa y le recuerda al cliente cuando un pago se atrasa.', on: false },
      { id: 'resumen', pilar: 'Medición y equipo', t: 'Resumen semanal por correo', d: 'Cada lunes recibes cuánto vendiste, cuánto falta y quién avanzó más.', on: quiere('reportes') },
    ],
    secciones: {},
  }
}

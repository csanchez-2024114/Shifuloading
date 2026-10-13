import { nuevoId } from './pura'

/* El servidor simulado arma el CRM igual que el real: vacío, sin contactos ni equipo inventados. */

export function generar(brief) {
  const quiere = (v) => brief.objetivos?.includes(v)
  const canal = (v) => brief.canales?.includes(v)
  return {
    brief,
    totalContactos: 0,
    contactos: [],
    vendedores: ['Tú'], // la persona; su equipo se agrega después
    tareas: { porHacer: [], enCurso: [], hecho: [] },
    eventos: [{ id: nuevoId(), e: '🤖', t: 'Shifu creó tu CRM', h: 'ahora' }],
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

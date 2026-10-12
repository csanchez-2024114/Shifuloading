/* "Base de datos" del servidor simulado: guarda el CRM en el navegador. Desaparece cuando se conecte el servidor real. */
const CLAVE = 'shifu_crm'
export const leer = () => { try { return JSON.parse(localStorage.getItem(CLAVE)) || null } catch { return null } }
export const guardar = (s) => { try { localStorage.setItem(CLAVE, JSON.stringify(s)) } catch { /* sin almacenamiento */ } }
export const borrar = () => { try { localStorage.removeItem(CLAVE) } catch { /* sin almacenamiento */ } }

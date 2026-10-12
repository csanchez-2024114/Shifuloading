/* Si existe VITE_API_URL (ver .env.example) la app habla con el servidor de Shifu; si no, usa el servidor simulado del navegador. */
export const API_URL = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
export const HAY_SERVIDOR = API_URL !== ''
export const CLAVE_TOKEN = 'shifu_token'

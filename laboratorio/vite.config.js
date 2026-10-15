import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { chatLaboratorio } from './servidor/chat.js'

// Laboratorio de plantillas: app APARTE del CRM de Shifu (otro servidor, otro puerto, otras rutas).
// Solo LEE los estilos y el logo del proyecto base (@base); nunca lo modifica ni comparte su arranque.
// Se levanta desde la raíz del repo con: npx vite --config laboratorio/vite.config.js
const aqui = (p) => fileURLToPath(new URL(p, import.meta.url))
export default defineConfig({
  root: aqui('.'),
  plugins: [react(), chatLaboratorio()], // chat con IA: solo en desarrollo (apply: 'serve')
  resolve: { alias: { '@base': aqui('../src') } },
  publicDir: aqui('../public'), // imágenes del CRM base (mascota de Shifu), solo lectura
  server: { port: 5190, strictPort: true, fs: { allow: [aqui('..')] }, watch: { ignored: ['**/backend/**', '**/dist/**'] } },
  optimizeDeps: { entries: ['index.html'] },
  build: { outDir: aqui('dist') },
})

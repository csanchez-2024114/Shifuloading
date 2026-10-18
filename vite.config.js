import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// El backend (Python, con su .venv de miles de archivos) vive dentro de esta carpeta: Vite no debe escanearlo ni vigilarlo.
// Alias del sistema de diseño (D61): '@lab' = las piezas del laboratorio (una sola fuente mientras se mudan) y '@base' = src,
// que es como el laboratorio nombra lo de este proyecto. Solo se cargan con VITE_CRM_DISENO=1.
const aqui = (p) => fileURLToPath(new URL(p, import.meta.url))
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@lab': aqui('./laboratorio/src'), '@base': aqui('./src') } },
  server: { port: 5180, watch: { ignored: ['**/backend/**', '**/dist/**'] } },
  optimizeDeps: { entries: ['index.html'] },
})

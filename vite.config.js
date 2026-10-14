import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// El backend (Python, con su .venv de miles de archivos) vive dentro de esta carpeta: Vite no debe escanearlo ni vigilarlo.
export default defineConfig({
  plugins: [react()],
  server: { port: 5180, watch: { ignored: ['**/backend/**', '**/dist/**'] } },
  optimizeDeps: { entries: ['index.html'] },
})

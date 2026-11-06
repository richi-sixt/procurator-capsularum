import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Im Dev-Modus leitet Vite /api an den lokalen Python-Server weiter (pc serve).
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:8765' } },
})

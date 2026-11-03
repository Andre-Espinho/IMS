import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The Electron window loads this dev server; API calls are forwarded to the
// FastAPI backend that Electron starts on 127.0.0.1:8000.
// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Proxy API calls to the FastAPI backend during development so the
      // SPA and API look same-origin. In prod the built assets are served
      // by FastAPI itself, so no proxy is needed.
      '/api': 'http://127.0.0.1:8080',
    },
  },
  build: {
    // Emit the built SPA where FastAPI can serve it as static files.
    outDir: '../src/reconciliation_agent/static',
    emptyOutDir: true,
  },
})

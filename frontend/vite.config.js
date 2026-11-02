import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const apiProxy = process.env.DEV_API_PROXY?.trim()

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    // Enabled only for the source-bind container. Keep the browser Host so
    // cookie writes retain their same-origin checks on any local dev port.
    proxy: apiProxy ? {
      '/api': { target: apiProxy, changeOrigin: false },
      '/health': { target: apiProxy, changeOrigin: false },
    } : undefined,
    watch: {
      // Filesystem events do not cross a Docker bind mount on Windows/macOS,
      // so without polling Vite never notices edits and keeps serving stale
      // modules — which silently desynchronises the UI from the API.
      usePolling: true,
      interval: 300,
    },
  },
})

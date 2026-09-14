import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    watch: {
      // Filesystem events do not cross a Docker bind mount on Windows/macOS,
      // so without polling Vite never notices edits and keeps serving stale
      // modules — which silently desynchronises the UI from the API.
      usePolling: true,
      interval: 300,
    },
  },
})

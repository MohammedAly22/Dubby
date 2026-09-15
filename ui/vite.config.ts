import { createLogger, defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const BACKEND_PORT = process.env.DUBBY_PORT ?? '8765'
const BACKEND = `http://127.0.0.1:${BACKEND_PORT}`

// While the Python studio is down every proxied request fails. Collapse those
// stack traces into one friendly, throttled hint instead of flooding the console.
const logger = createLogger()
const logError = logger.error.bind(logger)
let lastHint = 0
logger.error = (msg, options) => {
  const text = `${msg} ${options?.error?.stack ?? ''}`
  if (text.includes('proxy error') && /ECONNREFUSED|ECONNRESET|EPIPE|socket hang up/.test(text)) {
    if (Date.now() - lastHint > 20_000) {
      lastHint = Date.now()
      logger.warn(`\x1b[33m[dubby] backend not reachable at ${BACKEND} - start it with "dubby serve --no-open" (or run "dubby dev" to launch both). Retrying quietly...\x1b[0m`, { timestamp: true })
    }
    return
  }
  logError(msg, options)
}

// The built UI is served by the Python studio (dubby/web/dist).
// Relative base + hash routing keep it working behind proxies (e.g. Google Colab).
export default defineConfig({
  base: './',
  customLogger: logger,
  plugins: [react(), tailwindcss()],
  build: {
    outDir: '../dubby/web/dist',
    emptyOutDir: true,
    chunkSizeWarningLimit: 900,
  },
  server: {
    port: 5173,
    // Flag images live in the repository-level /assets folder.
    fs: { allow: ['..'] },
    proxy: {
      '/api': { target: BACKEND, ws: true, changeOrigin: true },
    },
  },
})

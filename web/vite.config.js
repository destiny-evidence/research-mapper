import { defineConfig } from 'vite'
import preact from '@preact/preset-vite'

// Relative base: the built app is uploaded to blob storage and may be served
// from any prefix.
export default defineConfig({
  base: './',
  plugins: [preact()],
  server: {
    // The API has no CORS. In development we borrow the demo's trick and
    // proxy; in production both must sit behind one hostname (docs/08 §5).
    proxy: { '/api': { target: 'http://127.0.0.1:8080', rewrite: p => p.replace(/^\/api/, '') } },
  },
  test: { environment: 'node', include: ['test/**/*.test.{js,jsx}'] },
})

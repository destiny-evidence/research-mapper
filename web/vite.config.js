import { defineConfig } from 'vite'
import preact from '@preact/preset-vite'

// Relative base: the built app is uploaded to blob storage and may be served
// from any prefix.
export default defineConfig({
  base: './',
  plugins: [preact()],
  server: {
    // Listen on every interface so the dev server works from inside a container.
    host: true,
    // Same-origin in development, so no CORS and no preflight. Deployed, the
    // app is on a storage static-website endpoint and the API allows it by
    // origin via MAPPER_CORS_ORIGINS (docs/08 §5).
    proxy: {
      '/api': {
        target: process.env.MAPPER_API_TARGET ?? 'http://127.0.0.1:8080',
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  test: { environment: 'node', include: ['test/**/*.test.{js,jsx}'] },
})

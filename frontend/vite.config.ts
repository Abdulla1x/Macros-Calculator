import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      // App shell only. API responses are never cached: stale cross-user data
      // in a shared browser cache would undermine per-user isolation.
      workbox: {
        navigateFallbackDenylist: [/^\/api\//],
      },
      includeAssets: ['apple-touch-icon.png'],
      manifest: {
        name: 'Macros Calculator',
        short_name: 'Macros',
        description: 'Track meals, macros, and goals',
        // theme_color paints the PWA status bar and matches the opaque sticky
        // header (bg-surface) exactly, so the two meet with no seam. It is also
        // duplicated in index.html — if the surface ramp is ever retuned, both
        // must move together.
        theme_color: '#0f172a',
        // The splash screen, which should be the page ground rather than the
        // header. body is slate-950; this said slate-900 and flashed the wrong
        // colour on every cold launch.
        background_color: '#020617',
        display: 'standalone',
        icons: [
          { src: 'pwa-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'pwa-512.png', sizes: '512x512', type: 'image/png' },
          {
            src: 'pwa-maskable-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
    }),
  ],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})

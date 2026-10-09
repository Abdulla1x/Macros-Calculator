import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig({
  // `@/` is src/, as in tsconfig.app.json: shadcn/ui's components import
  // through it (components.json).
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      // App shell only. API responses are never cached: stale cross-user data
      // in a shared browser cache would undermine per-user isolation.
      workbox: {
        navigateFallbackDenylist: [/^\/api\//],
        // The default (js, css, html) plus the two fonts' Latin and Latin
        // Extended files, so an installed app keeps its type offline. The other
        // subsets (Cyrillic, Vietnamese) are left to the network: a browser only
        // fetches them for text that needs them.
        globPatterns: ['**/*.{js,css,html}', '**/*-latin-*.woff2'],
      },
      includeAssets: ['apple-touch-icon.png', 'favicon.svg'],
      manifest: {
        name: 'Trackaholic',
        short_name: 'Trackaholic',
        description: 'Track meals, macros, and goals',
        // theme_color paints the PWA status bar; background_color is the
        // splash screen. Both are the ground (Daylight dark, #0b0e0c), which
        // the new shell's pages and tab bar sit on, so the bar meets the page
        // with no seam. index.html's theme-color meta is the same value; if
        // the ground ever changes, all three move together.
        theme_color: '#0b0e0c',
        background_color: '#0b0e0c',
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

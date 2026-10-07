import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [vue(), VitePWA({
    registerType: 'prompt',
    includeAssets: ['logo.svg', 'favicon.ico', 'apple-touch-icon-180x180.png'],
    manifest: {
      id: '/', name: '候车 · 公交查询', short_name: '候车', lang: 'zh-CN',
      description: '附近公交站、线路与实时到站查询',
      start_url: '/', scope: '/', display: 'standalone',
      theme_color: '#087d63', background_color: '#f2f6f5',
      icons: [
        { src: '/pwa-192x192.png', sizes: '192x192', type: 'image/png' },
        { src: '/pwa-512x512.png', sizes: '512x512', type: 'image/png' },
        { src: '/maskable-icon-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
      ],
    },
    workbox: {
      globPatterns: ['**/*.{js,css,html,svg,png,ico,webmanifest}'],
      navigateFallbackDenylist: [/^\/api(?:\/|$)/, /^\/(?:health|ready)(?:\?|$)/],
      cleanupOutdatedCaches: true,
    },
  })],
  server: { proxy: { '/api': 'http://127.0.0.1:8765' } },
})

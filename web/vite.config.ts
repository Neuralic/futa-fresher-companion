import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';
import { VitePWA } from 'vite-plugin-pwa';
import { isAnnouncementsRequest, isCacheablePublicApi } from './sw-matchers';

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'FUTA Fresher Companion',
        short_name: 'FUTA Companion',
        description: 'Navigate FUTA, find the right people and places, get the info you need.',
        theme_color: '#0b6e4f',
        background_color: '#ffffff',
        display: 'standalone',
        start_url: '/',
        icons: [
          { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,png,svg,woff2}'],
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//],
        runtimeCaching: [
          {
            // Announcements: freshness matters most, fall back to cache when offline/slow.
            // The matchers come from sw-matchers.ts: Workbox copies them as text (see that file).
            urlPattern: isAnnouncementsRequest,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-announcements',
              networkTimeoutSeconds: 4,
              expiration: { maxEntries: 50, maxAgeSeconds: 60 * 60 * 24 * 7 },
            },
          },
          {
            // Everything else public (departments, lecturers, buildings...): show cache, refresh quietly.
            urlPattern: isCacheablePublicApi,
            handler: 'StaleWhileRevalidate',
            options: {
              cacheName: 'api-reference',
              expiration: { maxEntries: 200, maxAgeSeconds: 60 * 60 * 24 * 30 },
            },
          },
          // TODO (Maps/GIS): add a CacheFirst rule for map tiles limited to the FUTA area.
        ],
      },
    }),
  ],
  server: {
    proxy: { '/api': 'http://localhost:8000' },
  },
});
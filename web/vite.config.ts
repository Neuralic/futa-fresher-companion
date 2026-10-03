import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';
import { VitePWA } from 'vite-plugin-pwa';

const API = '/api/v1/';
const isCacheableApi = ({ url }: { url: URL }) =>
  url.pathname.startsWith(API) &&
  !url.pathname.startsWith(API + 'auth') &&
  !url.pathname.startsWith(API + 'admin') &&
  !url.pathname.startsWith(API + 'sync');

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
        runtimeCaching: [
          {
            // Announcements: freshness matters most, fall back to cache when offline/slow.
            urlPattern: ({ url }) => url.pathname.startsWith(API + 'announcements'),
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-announcements',
              networkTimeoutSeconds: 4,
              expiration: { maxEntries: 50, maxAgeSeconds: 60 * 60 * 24 * 7 },
            },
          },
          {
            // Everything else public (departments, lecturers, buildings...): show cache, refresh quietly.
            urlPattern: isCacheableApi,
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

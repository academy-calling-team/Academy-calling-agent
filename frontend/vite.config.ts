import { defineConfig, loadEnv, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import { apiMiddleware } from './server/api';

function apiPlugin(): Plugin {
  return {
    name: 'hakwon-api',
    configureServer(server) {
      server.middlewares.use(apiMiddleware());
    },
    configurePreviewServer(server) {
      server.middlewares.use(apiMiddleware());
    },
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  process.env.ACADEMY_BACKEND_URL = env.ACADEMY_BACKEND_URL || process.env.ACADEMY_BACKEND_URL || '';
  process.env.FRONTEND_ORIGIN = env.FRONTEND_ORIGIN || process.env.FRONTEND_ORIGIN || 'http://127.0.0.1:5173';

  return {
    plugins: [react(), apiPlugin()],
    server: {
      port: 5173,
      strictPort: true,
      host: '127.0.0.1',
    },
    preview: {
      port: 4173,
      strictPort: true,
      host: '127.0.0.1',
    },
  };
});

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 80,
    allowedHosts: true,
    watch: {
      usePolling: true,
    },
    proxy: {
      '/api': {
        target: 'http://api:8000',
        changeOrigin: true,
      },
    },
    // HMR configuration
    hmr: {
      // Use 443 for ngrok, or default for local
      clientPort: process.env.NODE_ENV === 'production' ? 443 : undefined,
    },
  },
  // Pre-bundle heavy dependencies to reduce request count
  optimizeDeps: {
    include: [
      '@assistant-ui/react',
      '@assistant-ui/react-ui',
      '@assistant-ui/react-ai-sdk',
      '@mantine/core',
      '@mantine/hooks',
      'react',
      'react-dom',
      'react-markdown',
      'mermaid',
      'katex',
    ],
  },
})

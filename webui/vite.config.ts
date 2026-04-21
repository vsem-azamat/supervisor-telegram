import tailwindcss from '@tailwindcss/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	server: {
		host: '0.0.0.0',
		port: 5173,
		strictPort: true,
		// Dev on a VPS: accept any Host header so you can hit the server by
		// public IP or domain. Tighten this when auth lands.
		allowedHosts: true,
		proxy: {
			'/api': {
				target: 'http://127.0.0.1:8787',
				changeOrigin: true
			}
		}
	}
});

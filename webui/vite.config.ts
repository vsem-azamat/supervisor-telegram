import tailwindcss from '@tailwindcss/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
	const env = loadEnv(mode, '.', 'VITE_');
	const extraAllowedHosts = env.VITE_ALLOWED_HOSTS?.split(',')
		.map((host: string) => host.trim())
		.filter(Boolean);

	return {
		plugins: [tailwindcss(), sveltekit()],
		server: {
			host: '0.0.0.0',
			port: 5174,
			strictPort: true,
			// IP hosts are allowed by Vite by default. Add owned DNS names only when
			// needed, e.g. VITE_ALLOWED_HOSTS=dev.example.com.
			allowedHosts: extraAllowedHosts,
			proxy: {
				'/api': {
					target: 'http://127.0.0.1:8787',
					changeOrigin: true
				}
			}
		}
	};
});

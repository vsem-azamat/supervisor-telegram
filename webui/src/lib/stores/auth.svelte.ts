import { apiFetch } from '$lib/api/client';
import type { components } from '$lib/api/types';

type Me = components['schemas']['AuthMeResponse'];

type AuthState = {
	me: Me | null;
	loading: boolean;
	initialized: boolean;
};

const state = $state<AuthState>({ me: null, loading: false, initialized: false });

export const auth = {
	get me() {
		return state.me;
	},
	get loading() {
		return state.loading;
	},
	get initialized() {
		return state.initialized;
	},
	/**
	 * Sign in with the identity Telegram signed before this page loaded.
	 *
	 * `initData` is present only inside a Telegram client, which is the whole
	 * authentication story: there is no form to fill in and no token to carry,
	 * so a browser that has it is a browser Telegram opened.
	 */
	async signInWithTelegram(): Promise<boolean> {
		const initData = (window as unknown as { Telegram?: { WebApp?: { initData?: string } } }).Telegram
			?.WebApp?.initData;
		if (!initData) return false;

		const res = await apiFetch<Me>('/api/auth/webapp', {
			method: 'POST',
			body: JSON.stringify({ init_data: initData })
		});
		if (res.error) return false;

		state.me = res.data;
		return true;
	},
	async refresh(): Promise<void> {
		state.loading = true;
		try {
			const res = await apiFetch<Me>('/api/auth/me');
			state.me = res.data ?? null;
		} finally {
			state.loading = false;
			state.initialized = true;
		}
	},
	async logout(): Promise<void> {
		await apiFetch('/api/auth/logout', { method: 'POST' });
		state.me = null;
	}
};

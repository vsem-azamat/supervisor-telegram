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

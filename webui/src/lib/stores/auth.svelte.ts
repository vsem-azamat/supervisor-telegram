import { apiFetch } from '$lib/api/client';
import type { components } from '$lib/api/types';

type Me = components['schemas']['AuthMeResponse'];

/**
 * Why a sign-in did not happen — which the console has to be able to say.
 *
 * These four used to be one `false`. The screen that followed named the last
 * of them, so a rejected signature read as "your account is not on the list":
 * a server-side verification bug spent eight days looking like a
 * configuration mistake, and the one person who could have reported it
 * accurately was told, plausibly, that he was not an administrator.
 *
 * - `not-in-telegram` — no `initData`, so nothing to offer. An ordinary
 *   browser, and not an error.
 * - `refused` — Telegram's signature did not verify. Ours to fix, not theirs.
 * - `not-an-admin` — verified, and not on the list. The only case the old
 *   wording was ever right about.
 * - `unavailable` — the server did not answer.
 */
export type SignInFailure = 'not-in-telegram' | 'refused' | 'not-an-admin' | 'unavailable';

type AuthState = {
	me: Me | null;
	loading: boolean;
	initialized: boolean;
	failure: SignInFailure | null;
};

const state = $state<AuthState>({ me: null, loading: false, initialized: false, failure: null });

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
	get failure() {
		return state.failure;
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
		if (!initData) {
			state.failure = 'not-in-telegram';
			return false;
		}

		const res = await apiFetch<Me>('/api/auth/webapp', {
			method: 'POST',
			body: JSON.stringify({ init_data: initData })
		});
		if (res.error) {
			// The server keeps its own answer vague on purpose — which check
			// failed is useful to somebody probing the endpoint. The status is
			// enough to tell the three cases apart here, where the person
			// reading is the one who was refused.
			state.failure =
				res.error.status === 403
					? 'not-an-admin'
					: res.error.status === 401
						? 'refused'
						: 'unavailable';
			return false;
		}

		state.me = res.data;
		state.failure = null;
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
		state.failure = null;
	}
};

import type { ApiResult } from '$lib/api/client';
import { apiFetch } from '$lib/api/client';

type State<T> = {
	data: T | null;
	error: string | null;
	loading: boolean;
	lastUpdatedAt: Date | null;
	refresh: () => Promise<void>;
};

/**
 * Reactive polling hook. Returns $state-wrapped view; call `refresh()` for
 * a manual re-fetch. Starts immediately, polls every `intervalMs` (default
 * 30s), and cleans up its timer when the using component unmounts.
 *
 * The path may be a string or a thunk — when passed as a thunk, the $effect
 * tracks reactive state inside it and re-fetches when that state changes.
 */
export function useLivePoll<T>(
	path: string | (() => string),
	intervalMs = 30_000
): State<T> {
	const resolvePath = typeof path === 'function' ? path : () => path;

	const view = $state<State<T>>({
		data: null,
		error: null,
		loading: true,
		lastUpdatedAt: null,
		refresh: async () => {
			await run();
		}
	});

	async function run() {
		const res: ApiResult<T> = await apiFetch<T>(resolvePath());
		if (res.error) {
			view.error = res.error.message;
			view.data = null;
		} else {
			view.data = res.data;
			view.error = null;
			view.lastUpdatedAt = new Date();
		}
		view.loading = false;
	}

	$effect(() => {
		// Read the path so Svelte tracks any reactive deps the thunk uses.
		resolvePath();
		void run();
		const id = setInterval(run, intervalMs);
		return () => clearInterval(id);
	});

	return view;
}

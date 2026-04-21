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
 */
export function useLivePoll<T>(path: string, intervalMs = 30_000): State<T> {
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
		const res: ApiResult<T> = await apiFetch<T>(path);
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
		void run();
		const id = setInterval(run, intervalMs);
		return () => clearInterval(id);
	});

	return view;
}

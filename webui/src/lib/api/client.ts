/**
 * Thin typed fetch wrapper. Call sites get back { data } on success or
 * { error } on failure — forces them to handle the failure path.
 *
 * The frontend hits same-origin /api/* which Vite proxies to FastAPI.
 */

export type ApiResult<T> = { data: T; error: null } | { data: null; error: ApiError };

export type ApiError = {
	status: number;
	code: string;
	message: string;
};

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
	try {
		const res = await fetch(path, {
			...init,
			headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) }
		});
		if (!res.ok) {
			const body = await res.json().catch(() => ({}));
			return {
				data: null,
				error: {
					status: res.status,
					code: body?.error?.code ?? `http_${res.status}`,
					message: body?.error?.message ?? body?.detail ?? res.statusText
				}
			};
		}
		const data = (await res.json()) as T;
		return { data, error: null };
	} catch (e) {
		return {
			data: null,
			error: {
				status: 0,
				code: 'network_error',
				message: e instanceof Error ? e.message : String(e)
			}
		};
	}
}

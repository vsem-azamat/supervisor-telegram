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
			// 401 on a protected endpoint → bounce to /login. Two families are
			// exempt. `/api/auth` returns 401 as a normal answer (`/me` on boot
			// says "nobody is signed in"). `/api/public` is read by people who
			// have no session and are not meant to get one — a student on the
			// catalog, or an applicant opening the join check inside Telegram —
			// and sending them to a sign-in page would be answering a question
			// they did not ask.
			const exempt = path.startsWith('/api/auth') || path.startsWith('/api/public');
			if (res.status === 401 && !exempt) {
				const { goto } = await import('$app/navigation');
				void goto('/login');
			}
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

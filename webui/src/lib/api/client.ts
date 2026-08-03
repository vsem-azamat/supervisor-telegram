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

/**
 * What to show a person when the API refuses.
 *
 * FastAPI answers a rejected field with a list of per-field objects rather than
 * a sentence, and putting that straight into a toast reads as
 * "[object Object]" — so the one message that would have told the admin what
 * they typed wrong is the one that never arrives. Flattened here because every
 * form in the console posts through this function.
 */
function messageFrom(body: unknown, fallback: string): string {
	const detail = (body as { detail?: unknown } | null)?.detail;
	if (typeof detail === 'string') return detail;
	if (Array.isArray(detail)) {
		const written = detail
			.map((entry) => (entry as { msg?: string })?.msg)
			.filter((msg): msg is string => typeof msg === 'string')
			// Pydantic prefixes its own wording; the sentence after it is ours.
			.map((msg) => msg.replace(/^Value error, /, ''));
		if (written.length > 0) return written.join('; ');
	}
	return fallback;
}

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
					message: body?.error?.message ?? messageFrom(body, res.statusText)
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

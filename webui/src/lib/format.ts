/**
 * Wording shared by every screen, console and catalogue alike.
 *
 * Relative time was written three times — on the chat page, in settings and in
 * the spam list — and each copy spelled it slightly differently. In English
 * that was three ways to say "5m ago"; in Russian it is three chances to write
 * "5 минуты назад", because the ending depends on the number. `Intl` already
 * knows the rule, so nothing here counts cases by hand.
 */

const RELATIVE = new Intl.RelativeTimeFormat('ru', { numeric: 'auto' });

export function relativeTime(iso: string | null | undefined, never = '—'): string {
	if (!iso) return never;
	const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
	if (Math.abs(minutes) < 1) return 'только что';
	if (Math.abs(minutes) < 60) return RELATIVE.format(-minutes, 'minute');
	const hours = Math.round(minutes / 60);
	if (Math.abs(hours) < 24) return RELATIVE.format(-hours, 'hour');
	return RELATIVE.format(-Math.round(hours / 24), 'day');
}

/** "3 чата" / "5 чатов" — the ending Russian needs and English does not. */
export function plural(count: number, one: string, few: string, many: string): string {
	const mod100 = Math.abs(count) % 100;
	const mod10 = mod100 % 10;
	if (mod100 >= 11 && mod100 <= 14) return many;
	if (mod10 === 1) return one;
	if (mod10 >= 2 && mod10 <= 4) return few;
	return many;
}

/** Digits a person compares down a column, grouped the way Russian groups them. */
export function num(value: number | null | undefined, absent = '—'): string {
	if (value === null || value === undefined) return absent;
	return value.toLocaleString('ru-RU');
}

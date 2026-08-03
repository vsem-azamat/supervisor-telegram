import { redirect } from '@sveltejs/kit';

// /admin/catalog listed the same rows as /admin/chats from the same endpoint,
// differing only in which four columns it picked. The link survives because it
// is bookmarked and linked to from elsewhere in the console; the second table
// does not.
export function load() {
	redirect(307, '/admin/chats');
}

import { redirect } from '@sveltejs/kit';

// The tree used to sit under a catalogue page that no longer exists. Kept as a
// redirect because both of the people who use this console have the old address
// in a tab.
export function load() {
	redirect(307, '/admin/hierarchy');
}

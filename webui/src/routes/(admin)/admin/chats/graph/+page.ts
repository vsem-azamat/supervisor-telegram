import { redirect } from '@sveltejs/kit';

// Pointed at /catalog/hierarchy, which stopped existing when the console moved
// under /admin — so this link led to a blank page rather than to the tree.
export function load() {
	redirect(307, '/admin/hierarchy');
}

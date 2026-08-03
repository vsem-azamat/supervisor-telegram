<script lang="ts">
	import { page } from '$app/state';
	import { LogOut, User } from '@lucide/svelte';
	import { auth } from '$lib/stores/auth.svelte';

	type Props = { onLogout?: () => void | Promise<void> };
	let { onLogout }: Props = $props();

	function currentTitle(pathname: string): string {
		const map: Record<string, string> = {
			'/admin': 'Dashboard',
			'/admin/catalog': 'Catalog',
			'/admin/catalog/hierarchy': 'Hierarchy',
			'/admin/chats': 'Chats',
			'/admin/settings': 'Settings'
		};
		if (map[pathname]) return map[pathname];
		// Fall back to the segment after /admin, so /admin/chats/-100… reads
		// "Chats" rather than "Admin".
		const segments = pathname.split('/').filter(Boolean);
		const named = segments[0] === 'admin' ? segments[1] : segments[0];
		if (named) return named.charAt(0).toUpperCase() + named.slice(1);
		return '—';
	}
</script>

<header
	class="flex h-14 shrink-0 items-center justify-between border-b border-zinc-200 bg-white px-6"
>
	<h1 class="text-base font-medium text-zinc-900">{currentTitle(page.url.pathname)}</h1>
	<div class="flex items-center gap-2 text-xs text-zinc-500">
		<span class="rounded-full bg-emerald-50 px-2.5 py-1 font-medium text-emerald-700">dev</span>
		{#if auth.me}
			<div class="flex items-center gap-1.5 rounded-md px-2 py-1">
				<User class="h-3.5 w-3.5" />
				<span class="font-mono">#{auth.me.user_id}</span>
			</div>
			<button
				type="button"
				class="flex items-center gap-1.5 rounded-md px-2 py-1 font-medium hover:bg-zinc-100 hover:text-zinc-800"
				onclick={() => onLogout?.()}
			>
				<LogOut class="h-3.5 w-3.5" />
				<span>Logout</span>
			</button>
		{:else}
			<span>admin</span>
		{/if}
	</div>
</header>

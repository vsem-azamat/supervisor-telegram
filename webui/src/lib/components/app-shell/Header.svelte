<script lang="ts">
	import { page } from '$app/state';
	import { LogOut, User } from '@lucide/svelte';
	import { auth } from '$lib/stores/auth.svelte';

	type Props = { onLogout?: () => void | Promise<void> };
	let { onLogout }: Props = $props();

	function currentTitle(pathname: string): string {
		const map: Record<string, string> = {
			'/admin': 'Сводка',
			'/admin/catalog': 'Чаты',
			'/admin/hierarchy': 'Иерархия',
			'/admin/chats': 'Чаты',
			'/admin/settings': 'Настройки'
		};
		if (map[pathname]) return map[pathname];
		// A chat's own page: /admin/chats/-100… is still the Чаты section.
		if (pathname.startsWith('/admin/chats/')) return 'Чат';
		return 'Консоль';
	}

	// Which deployment this browser is actually looking at, read off the address
	// bar rather than baked in. The badge used to say "dev" on every screen
	// including production — a label that is wrong in the one place it matters
	// is worse than no label, because it is read and believed.
	const environment = $derived.by(() => {
		const host = page.url.hostname;
		if (host === 'localhost' || host === '127.0.0.1' || host.startsWith('dev.')) return 'dev';
		return 'prod';
	});
</script>

<header
	class="flex h-14 shrink-0 items-center justify-between border-b border-zinc-200 bg-white px-6"
>
	<h1 class="text-base font-medium text-zinc-900">{currentTitle(page.url.pathname)}</h1>
	<div class="flex items-center gap-2 text-xs text-zinc-500">
		<span
			class="rounded-full px-2.5 py-1 font-medium {environment === 'prod'
				? 'bg-emerald-50 text-emerald-700'
				: 'bg-zinc-100 text-zinc-600'}"
		>
			{environment}
		</span>
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
				<span>Выйти</span>
			</button>
		{/if}
	</div>
</header>

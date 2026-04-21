<script lang="ts">
	import { page } from '$app/state';

	type NavItem = { href: string; label: string; phase?: number };

	const items: NavItem[] = [
		{ href: '/', label: 'Home', phase: 1 },
		{ href: '/posts', label: 'Posts', phase: 1 },
		{ href: '/channels', label: 'Channels', phase: 1 },
		{ href: '/chats', label: 'Chats', phase: 2 },
		{ href: '/chats/graph', label: 'Chat graph', phase: 3 },
		{ href: '/costs', label: 'Costs', phase: 1 },
		{ href: '/agent', label: 'Agent', phase: 3 },
		{ href: '/settings', label: 'Settings', phase: 4 }
	];

	function isActive(href: string): boolean {
		if (href === '/') return page.url.pathname === '/';
		return page.url.pathname === href || page.url.pathname.startsWith(href + '/');
	}
</script>

<nav class="flex h-full w-56 shrink-0 flex-col border-r border-zinc-200 bg-zinc-50">
	<div class="px-4 py-5">
		<span class="text-sm font-semibold tracking-tight text-zinc-900">Konnekt admin</span>
	</div>
	<ul class="flex flex-col gap-0.5 px-2">
		{#each items as item (item.href)}
			<li>
				<a
					href={item.href}
					class="flex items-center justify-between rounded-md px-3 py-2 text-sm transition-colors
						{isActive(item.href)
						? 'bg-zinc-900 text-white'
						: 'text-zinc-700 hover:bg-zinc-200'}"
				>
					<span>{item.label}</span>
					{#if item.phase}
						<span
							class="rounded-sm px-1.5 py-0.5 text-[10px] font-medium
								{isActive(item.href) ? 'bg-white/20 text-white' : 'bg-zinc-200 text-zinc-600'}"
						>
							P{item.phase}
						</span>
					{/if}
				</a>
			</li>
		{/each}
	</ul>
</nav>

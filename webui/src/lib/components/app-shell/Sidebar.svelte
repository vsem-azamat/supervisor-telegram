<script lang="ts">
	import { page } from '$app/state';
	import { Hash, LayoutDashboard, MessageSquare, Settings } from '@lucide/svelte';
	import type { Component } from 'svelte';

	type NavItem = { href: string; label: string; icon: Component };
	type NavGroup = { label: string; items: NavItem[] };

	// Everything the console reaches lives under /admin. The public site sits at
	// the root and is not navigable from here on purpose — it is a different
	// audience, not a different tab.
	const groups: NavGroup[] = [
		{
			label: 'Overview',
			items: [{ href: '/admin', label: 'Dashboard', icon: LayoutDashboard }]
		},
		{
			label: 'Resources',
			items: [{ href: '/admin/catalog', label: 'Catalog', icon: MessageSquare }]
		},
		{
			label: 'System',
			items: [{ href: '/admin/settings', label: 'Settings', icon: Settings }]
		}
	];

	function isActive(href: string): boolean {
		if (href === '/admin') return page.url.pathname === '/admin';
		if (href === '/admin/catalog') {
			return (
				page.url.pathname.startsWith('/admin/catalog') ||
				page.url.pathname.startsWith('/admin/chats')
			);
		}
		return page.url.pathname === href || page.url.pathname.startsWith(href + '/');
	}
</script>

<nav class="flex h-full w-56 shrink-0 flex-col border-r border-zinc-200 bg-zinc-50">
	<div class="flex items-center gap-2 px-4 py-5">
		<div class="flex h-7 w-7 items-center justify-center rounded-md bg-zinc-900 text-white">
			<Hash class="h-4 w-4" />
		</div>
		<span class="text-sm font-semibold tracking-tight text-zinc-900">Konnekt admin</span>
	</div>

	<div class="flex flex-col gap-4 px-2 pb-4">
		{#each groups as group (group.label)}
			<div class="flex flex-col gap-0.5">
				<div class="px-3 pb-1 text-[10px] font-semibold tracking-wider text-zinc-400 uppercase">
					{group.label}
				</div>
				{#each group.items as item (item.href)}
					{@const Icon = item.icon}
					{@const active = isActive(item.href)}
					<a
						href={item.href}
						class="flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors
							{active ? 'bg-zinc-900 text-white' : 'text-zinc-700 hover:bg-zinc-200'}"
					>
						<Icon class="h-4 w-4 shrink-0 {active ? 'text-white' : 'text-zinc-500'}" />
						<span>{item.label}</span>
					</a>
				{/each}
			</div>
		{/each}
	</div>
</nav>

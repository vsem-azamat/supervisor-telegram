<script lang="ts">
	import { page } from '$app/state';
	import {
		Hash,
		LayoutDashboard,
		Newspaper,
		Receipt,
		Settings,
		Sparkles,
		Tv
	} from '@lucide/svelte';
	import type { Component } from 'svelte';

	type NavItem = { href: string; label: string; icon: Component };
	type NavGroup = { label: string; items: NavItem[] };

	const groups: NavGroup[] = [
		{
			label: 'Overview',
			items: [{ href: '/', label: 'Dashboard', icon: LayoutDashboard }]
		},
		{
			label: 'Resources',
			items: [{ href: '/catalog', label: 'Catalog', icon: Tv }]
		},
		{
			label: 'Workflow',
			items: [
				{ href: '/posts', label: 'Posts', icon: Newspaper },
				{ href: '/agent', label: 'Agent', icon: Sparkles }
			]
		},
		{
			label: 'System',
			items: [
				{ href: '/costs', label: 'Costs', icon: Receipt },
				{ href: '/settings', label: 'Settings', icon: Settings }
			]
		}
	];

	function isActive(href: string): boolean {
		if (href === '/') return page.url.pathname === '/';
		if (href === '/catalog') {
			return (
				page.url.pathname === '/catalog' ||
				page.url.pathname.startsWith('/channels') ||
				page.url.pathname.startsWith('/chats')
			);
		}
		return page.url.pathname === href || page.url.pathname.startsWith(href + '/');
	}
</script>

<nav
	class="flex h-full w-60 shrink-0 flex-col border-r"
	style="border-color: var(--shell-border); background: var(--shell-sidebar); color: var(--shell-sidebar-foreground);"
>
	<div class="flex items-center gap-2.5 px-4 py-5">
		<div
			class="flex h-8 w-8 items-center justify-center rounded-md"
			style="background: var(--shell-sidebar-active); color: var(--shell-sidebar-active-foreground);"
		>
			<Hash class="h-4 w-4" />
		</div>
		<div class="min-w-0">
			<div class="text-sm font-semibold">Konnekt</div>
			<div class="text-[11px]" style="color: var(--shell-sidebar-muted);">Admin console</div>
		</div>
	</div>

	<div class="flex flex-col gap-4 px-2.5 pb-4">
		{#each groups as group (group.label)}
			<div class="flex flex-col gap-0.5">
				<div
					class="px-3 pb-1 text-[10px] font-semibold tracking-wider uppercase"
					style="color: var(--shell-sidebar-muted);"
				>
					{group.label}
				</div>
				{#each group.items as item (item.href)}
					{@const Icon = item.icon}
					{@const active = isActive(item.href)}
					<a
						href={item.href}
						class="nav-link flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors"
						class:active
						style={active
							? 'background: var(--shell-sidebar-active); color: var(--shell-sidebar-active-foreground);'
							: 'color: var(--shell-sidebar-foreground);'}
					>
						<Icon
							class="h-4 w-4 shrink-0"
							style={active ? '' : 'color: var(--shell-sidebar-muted);'}
						/>
						<span>{item.label}</span>
					</a>
				{/each}
			</div>
		{/each}
	</div>
</nav>

<style>
	.nav-link:not(.active):hover {
		background: var(--shell-sidebar-hover);
	}
</style>

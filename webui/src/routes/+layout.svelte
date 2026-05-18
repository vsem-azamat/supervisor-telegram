<script lang="ts">
	import './layout.css';
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import favicon from '$lib/assets/favicon.svg';
	import Header from '$lib/components/app-shell/Header.svelte';
	import Sidebar from '$lib/components/app-shell/Sidebar.svelte';
	import { Toaster } from '$lib/components/ui/sonner/index.js';
	import { auth } from '$lib/stores/auth.svelte';

	let { children } = $props();

	onMount(() => {
		void auth.refresh();
	});

	const publicPath = $derived(page.url.pathname === '/catalog');

	$effect(() => {
		if (!auth.initialized || auth.me || page.url.pathname === '/login') return;
		if (page.url.pathname === '/') {
			void goto('/catalog');
			return;
		}
		if (!publicPath) void goto('/login');
	});

	async function doLogout(): Promise<void> {
		await auth.logout();
		await goto('/login');
	}
</script>

<svelte:head><link rel="icon" href={favicon} /></svelte:head>

<Toaster richColors />

{#if page.url.pathname === '/login'}
	{@render children()}
{:else if publicPath && !auth.me}
	<div class="min-h-screen bg-zinc-50 text-zinc-900">
		<header class="border-b border-zinc-200 bg-white">
			<div class="mx-auto flex h-14 max-w-6xl items-center justify-between px-6">
				<div class="flex items-center gap-2">
					<div class="flex h-7 w-7 items-center justify-center rounded-md bg-zinc-900 text-sm font-semibold text-white">
						K
					</div>
					<span class="text-sm font-semibold tracking-tight text-zinc-900">Konnekt</span>
				</div>
				<a
					href="/login"
					class="rounded-md border border-zinc-200 bg-white px-3 py-1.5 text-sm font-medium text-zinc-700 hover:bg-zinc-100"
				>
					Admin sign in
				</a>
			</div>
		</header>
		<main>
			{@render children()}
		</main>
	</div>
{:else if !auth.initialized}
	<div class="flex min-h-screen items-center justify-center text-sm text-zinc-400">Loading…</div>
{:else if !auth.me}
	<!-- The effect above has already started navigation away from this protected route. -->
{:else}
	<div class="flex h-screen w-screen bg-white text-zinc-900">
		<Sidebar />
		<div class="flex min-w-0 flex-1 flex-col">
			<Header onLogout={doLogout} />
			<main class="flex-1 overflow-auto">
				{@render children()}
			</main>
		</div>
	</div>
{/if}

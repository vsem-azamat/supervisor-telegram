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
		if (page.url.pathname !== '/login') void auth.refresh();
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
{:else if !auth.initialized}
	<div class="flex min-h-screen items-center justify-center text-sm text-zinc-400">Loading…</div>
{:else if !auth.me}
	<!-- apiFetch has already started navigation to /login; render nothing to avoid a flash. -->
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

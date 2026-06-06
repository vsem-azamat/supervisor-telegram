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
	<div class="min-h-screen bg-background text-foreground">
		<header class="border-b bg-card">
			<div class="mx-auto flex h-14 max-w-6xl items-center justify-between px-6">
				<div class="flex items-center gap-2">
					<div
						class="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-sm font-semibold text-primary-foreground"
					>
						K
					</div>
					<span class="text-sm font-semibold text-foreground">Konnekt</span>
				</div>
				<a
					href="/login"
					class="rounded-md border bg-card px-3 py-1.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
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
	<div class="flex min-h-screen items-center justify-center bg-background text-sm text-muted-foreground">
		Loading…
	</div>
{:else if !auth.me}
	<!-- The effect above has already started navigation away from this protected route. -->
{:else}
	<div class="flex h-screen w-screen bg-background text-foreground">
		<Sidebar />
		<div class="flex min-w-0 flex-1 flex-col">
			<Header onLogout={doLogout} />
			<main class="app-page flex-1 overflow-auto">
				{@render children()}
			</main>
		</div>
	</div>
{/if}

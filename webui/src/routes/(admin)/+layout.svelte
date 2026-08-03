<script lang="ts">
	// Everything nested here needs a super-administrator session. The check is a
	// layout rather than a per-page guard so that adding a screen cannot forget
	// it: a new file under `(admin)/` is protected by where it sits.
	//
	// This is a second lock, not the lock. The API refuses without a valid cookie
	// whatever the browser believes — see `require_super_admin` in
	// `app/webapi/deps.py`. What the guard buys is not safety but honesty: an
	// anonymous visitor gets the sign-in page instead of a console full of
	// failed requests.
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import Header from '$lib/components/app-shell/Header.svelte';
	import Sidebar from '$lib/components/app-shell/Sidebar.svelte';
	// Toasts are a console thing — only the chat detail page raises them. Kept
	// here rather than at the root so a student on the catalog does not download
	// a toast library to be told nothing.
	import { Toaster } from '$lib/components/ui/sonner/index.js';
	import { auth } from '$lib/stores/auth.svelte';

	let { children } = $props();

	onMount(() => {
		void auth.refresh();
	});

	$effect(() => {
		if (auth.initialized && !auth.me) void goto('/login');
	});

	async function doLogout(): Promise<void> {
		await auth.logout();
		await goto('/login');
	}
</script>

<Toaster richColors />

{#if !auth.initialized}
	<div class="flex min-h-screen items-center justify-center text-sm text-zinc-400">Загрузка…</div>
{:else if !auth.me}
	<!-- The effect above has already started navigating to the sign-in page. -->
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

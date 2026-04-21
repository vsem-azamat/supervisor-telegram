<script lang="ts">
	import './layout.css';
	import favicon from '$lib/assets/favicon.svg';
	import Header from '$lib/components/app-shell/Header.svelte';
	import Sidebar from '$lib/components/app-shell/Sidebar.svelte';

	let { children } = $props();
</script>

<svelte:head><link rel="icon" href={favicon} /></svelte:head>

<div class="flex h-screen w-screen bg-white text-zinc-900">
	<Sidebar />
	<div class="flex min-w-0 flex-1 flex-col">
		<Header />
		<main class="flex-1 overflow-auto">
			{@render children()}
		</main>
	</div>
</div>

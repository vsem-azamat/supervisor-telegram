<script lang="ts">
	import Tile from './Tile.svelte';

	type Props = { title: string; value: string | number; caption?: string };
	let { title, value, caption }: Props = $props();
</script>

<Tile {title}>
	<div class="text-2xl font-semibold tracking-tight text-zinc-900">{value}</div>
	{#if caption}
		<p class="mt-1 text-xs text-zinc-500">{caption}</p>
	{/if}
</Tile>

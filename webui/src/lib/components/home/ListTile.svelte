<script lang="ts">
	import Tile from './Tile.svelte';

	type Line = { primary: string; secondary?: string };
	type Props = { title: string; items: Line[]; empty: string };
	let { title, items, empty }: Props = $props();
</script>

<Tile {title}>
	{#if items.length === 0}
		<p class="text-xs text-zinc-500">{empty}</p>
	{:else}
		<ul class="flex flex-col gap-2">
			{#each items as item, i (i)}
				<li class="flex items-baseline justify-between text-sm">
					<span class="truncate text-zinc-800">{item.primary}</span>
					{#if item.secondary}
						<span class="ml-2 shrink-0 text-xs text-zinc-500">{item.secondary}</span>
					{/if}
				</li>
			{/each}
		</ul>
	{/if}
</Tile>
